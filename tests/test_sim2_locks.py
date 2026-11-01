"""Native SIM2 NR transactions against a stateful fake CP; no serial devices/network access."""
import unittest, tempfile, shutil, subprocess, json, os
from pathlib import Path
from helpers import TOP
from test_mu300dash_security import JSONFILTER
P = TOP / 'rootfs/overlay/opt/mu300/bin'

MODEM = r'''#!/usr/bin/python3
import os,json,sys
p=os.environ['MODEM'];d=json.load(open(p));q=sys.argv[-1]
generic=os.environ.get('T_GENERIC')=='1'
if generic:
 assert q.startswith('AT+') and ';' not in q;q=q[3:]
else:
 assert q.startswith('AT+SPACTCARD=1;+');q=q.split(';+',1)[1]
port=os.path.basename(os.environ['MU300_AT_DIR'])
if not (generic and q=='SPACTCARD?'):
 assert port==(('mu300-at2' if generic else 'mu300-at5') if q=='SFUN=4' else ('mu300-at' if generic else 'mu300-at4'))
d['log'].append(q)
o=''
if q=='SPLBAND=3':o='+SPLBAND: '+d['nr']
elif q=='SPACTCARD?':o='+SPACTCARD: '+os.environ.get('T_DATA_CARD' if port=='mu300-at2' else 'T_CARD','1')
elif q=='SP5GCMDS="get nr support_band"':o='+SP5GCMDS: get nr support_band,'+os.environ.get('T_CAPS','6,41,78,1,8,28,5')
elif q.startswith('SPLBAND=2,'):
 if d.pop('refuse',False):json.dump(d,open(p,'w'));print('ERROR');sys.exit(0)
 r=q.split(',',1)[1].split(',');d['nr']=','.join(r[:3]) if r[3]=='0' else ','.join(r)
elif q=='SPFORCEFRQ=16,3':o='malformed' if d.get('bad_cell') else '+SPFORCEFRQ: 16,3'+''.join(','+x for x in d['cell'])
elif q=='SPFORCEFRQ=12,3':o='+SPFORCEFRQ: 12,3'+''.join(','+x for x in d.get('lte_cell',[]))
elif q=='SPFORCEFRQ=16,4':d['cell']=[]
elif q.startswith('SPFORCEFRQ=16,6,'):d['cell'].append(q.split(',',2)[2])
elif q=='SPENGMD=0,14,1':o='41,0-524910,0-269,0-0'
elif q=='CFUN?':o='+CFUN: '+str(d['rf'])
elif q=='SFUN=5':d['rf']=int(os.environ.get('T_RF_OFF','0'))
elif q=='SFUN=4':
 d['rf']=1
 if d.pop('lose_cell',False):d['cell']=[]
else:raise Exception(q)
json.dump(d,open(p,'w'));print(o+'\nOK' if o else 'OK')
'''


class Fixture(unittest.TestCase):

    def setUp(self):
        self.p = Path(tempfile.mkdtemp(prefix='u30-native-'))
        self.root = self.p / 'root'
        self.bin = self.p / 'bin'
        self.bin.mkdir()
        s = (P / 'mu300-sim2-lock').read_text()
        for pre in ['/run/mu300', '/etc/mu300', '/etc/unisoc-modem', '/usr/libexec/unisoc-modem', '/opt/mu300/bin', '/opt/mu300/lib', '/opt/mu300/busybox-bin', '/etc/openwrt_release', '/usr/share/unisoc-modem']:
            s = s.replace(pre, str(self.root) + pre)
        self.helper = self.root / 'opt/mu300/bin/mu300-sim2-lock'
        self.helper.parent.mkdir(parents=True)
        self.helper.write_text(s)
        self.helper.chmod(0o755)
        for n in ['run/mu300', 'etc/mu300', 'etc/unisoc-modem/lock-state.d', 'opt/mu300/bin']:
            (self.root / n).mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/openwrt_release').touch()
        (self.root / 'run/mu300-radio-freeze').touch()
        (self.root / 'run/mu300/sim-slot').write_text('1')
        (self.root / 'run/mu300/sim2-nr-locks').write_text('u30air')
        for ch in ['mu300-at4', 'mu300-at5']:
            d = self.root / 'run' / ch
            (d / 'owner').mkdir(parents=True)
            os.mkfifo(d / 'cmd')
            (d / 'owner/pid').write_text(str(os.getpid()))
        self.db = self.p / 'modem.json'
        self.db.write_text(json.dumps({'nr': '0,0,0', 'cell': [], 'rf': 1, 'log': []}))
        at = self.root / 'opt/mu300/bin/mu300-at'
        at.write_text(MODEM)
        at.chmod(0o755)
        self.stub('mu300-device', 'echo u30air', self.root / 'opt/mu300/bin')
        self.stub('mobile-data', 'shift;exec "$@"', self.root / 'opt/mu300/bin')
        self.stub('ubus', 'printf \'{"up":%s,"l3_device":"%s"}\\n\' "${T_UP:-true}" "${T_DEVICE:-sipa_eth8}"')
        (self.bin / 'jsonfilter.py').write_text(JSONFILTER)
        self.stub('jsonfilter', f'exec python3 "{self.bin}/jsonfilter.py" "$@"')
        for n in ['ifup', 'ifdown', 'setsid', 'sleep', 'sync']:
            self.stub(n, 'exit 0')
        self.env = {**os.environ, 'PATH': str(self.bin) + ':' + os.environ['PATH'], 'MODEM': str(self.db)}

    def stub(self, n, s, d=None):
        f = (d or self.bin) / n
        f.write_text('#!/bin/sh\n' + s + '\n')
        f.chmod(0o755)

    def tearDown(self):
        shutil.rmtree(self.p)

    def call(self, *a, **extra):
        return subprocess.run([str(self.helper), *a], env={**self.env, **extra}, capture_output=True, text=True, timeout=30)

    def state(self):
        return json.loads(self.db.read_text())


class Native(Fixture):
    def test_model_default_enables_u30_family_only(self):
        self.stub('uci', 'case $3 in unisoc_modem.main.sim2_nr_locks) printf "%s" "${T_ENABLE:-auto}";; esac')
        flag = self.root / 'run/mu300/sim2-nr-locks'
        for device in ['u30air', 'f50', 'v50', 'unknown']:
            self.stub('mu300-device', 'echo ' + device, self.root / 'opt/mu300/bin')
            for choice in ['', 'auto', '1', '0', 'invalid']:
                flag.unlink(missing_ok=True)
                r = self.call('boot-config', T_ENABLE=choice)
                self.assertEqual(r.returncode, 0, r.stderr)
                on = (choice in ['', 'auto'] and device == 'u30air') or (choice == '1' and device != 'unknown')
                self.assertEqual(flag.read_text().strip(), device if on else 'off', (device, choice))
        self.assertEqual(self.state()['log'], [])

    def test_native_default_on_can_be_disabled_next_boot(self):
        self.stub('uci', 'case $3 in unisoc_modem.main.sim2_nr_locks) printf "%s" "${T_ENABLE:-auto}";; esac')
        flag = self.root / 'run/mu300/sim2-nr-locks'
        flag.unlink()
        self.assertEqual(self.call('boot-config').returncode, 0)
        self.assertEqual(self.call('supported', 'nr').returncode, 0)
        # Saving off cannot change this boot's policy.
        self.call('boot-config', T_ENABLE='0')
        self.assertEqual(self.call('supported', 'nr').returncode, 0)
        flag.unlink()
        self.call('boot-config', T_ENABLE='0')
        self.assertNotEqual(self.call('apply', 'nr', '41').returncode, 0)
        self.assertEqual(self.call('replay', MU300_NATIVE_EARLY='1').returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_nr_lock_readback_restart_and_commit(self):
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertTrue(json.loads(r.stdout)['wan_restored'])
        self.assertEqual(self.state()['nr'], '0,0,16')
        self.assertIn('SFUN=5', self.state()['log'])
        self.assertEqual((self.root / 'etc/unisoc-modem/lock-state.d/sim2-native/nr').read_text(), '41')

    def test_current_cell_and_unlock(self):
        r = self.call('apply', 'cell', 'auto')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.state()['cell'], ['524910,269'])
        r = self.call('apply', 'cell', 'off-nr')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.state()['cell'], [])

    def test_invalid_band_and_cell_send_nothing(self):
        for k, v in [('nr', '6'), ('nr', '79'), ('nr', '41;reboot'), ('cell', 'nr:3279166,1'), ('cell', 'nr:100,1008'), ('cell', 'lte:100,1')]:
            r = self.call('apply', k, v)
            self.assertNotEqual(r.returncode, 0, (k, v))
            self.assertEqual(self.state()['log'], [])

    def test_refused_setter_rolls_back_and_does_not_commit(self):
        d = self.state()
        d['refuse'] = True
        self.db.write_text(json.dumps(d))
        r = self.call('apply', 'nr', '41')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.state()['nr'], '0,0,0')
        self.assertFalse((self.root / 'etc/unisoc-modem/lock-state.d/sim2-native/nr').exists())
        self.assertFalse((self.root / 'run/mu300/sim-sequence').exists())

    def test_other_sim_refused(self):
        (self.root / 'run/mu300/sim-slot').write_text('0')
        r = self.call('apply', 'nr', '41')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_offline_or_wrong_bearer_sends_nothing(self):
        for extra in [{'T_UP': 'false'}, {'T_DEVICE': 'sipa_eth0'}]:
            r = self.call('apply', 'nr', '41', **extra)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(self.state()['log'], [])

    def test_existing_sim1_saved_state_untouched(self):
        parent = self.root / 'etc/unisoc-modem/lock-state.d/nr'
        parent.write_text('78')
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(parent.read_text(), '78')

    def test_replay_disabled_keeps_modem_values(self):
        d = self.root / 'etc/unisoc-modem/lock-state.d/sim2-native'
        d.mkdir()
        (d / 'nr').write_text('41')
        (d.parent / 'auto_apply').write_text('off')
        st = self.state()
        st['rf'] = 0
        self.db.write_text(json.dumps(st))
        r = self.call('replay', MU300_NATIVE_EARLY='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,0')
        self.assertEqual(self.state()['log'], ['CFUN?'])

    def test_other_board_and_disabled_radio_are_refused_without_at(self):
        self.stub('mu300-device', 'echo f50', self.root / 'opt/mu300/bin')
        self.assertNotEqual(self.call('apply', 'nr', '41').returncode, 0)
        self.assertEqual(self.state()['log'], [])
        self.stub('mu300-device', 'echo u30air', self.root / 'opt/mu300/bin')
        self.stub('mu300-sim-radio', 'exit 1', self.root / 'opt/mu300/bin')
        self.assertNotEqual(self.call('apply', 'nr', '41').returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_radio_lock_busy_does_not_write(self):
        self.stub('mobile-data', 'exit 75', self.root / 'opt/mu300/bin')
        self.assertNotEqual(self.call('apply', 'nr', '41').returncode, 0)
        self.assertEqual(self.state()['log'], [])
        self.assertFalse((self.root / 'etc/mu300/sim2-native-recovery').exists())

    def test_malformed_cell_snapshot_never_becomes_unlocked(self):
        d = self.state()
        d['bad_cell'] = True
        self.db.write_text(json.dumps(d))
        r = self.call('apply', 'nr', '41')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertFalse(any((q.startswith('SPLBAND=2') for q in self.state()['log'])))
        self.assertEqual(self.state()['nr'], '0,0,0')

    def test_configured_state_dir_and_custom_backend(self):
        lib = self.root / 'usr/share/unisoc-modem/lib.sh'
        lib.parent.mkdir(parents=True)
        source = (TOP / 'openwrt/luci-app-mu300/root/usr/share/unisoc-modem/lib.sh').read_text()
        for pre in ['/etc/unisoc-modem', '/etc/mu300']:
            source = source.replace(pre, str(self.root) + pre)
        lib.write_text(source)
        state = self.root / 'etc/unisoc-modem/alternate'
        self.stub('uci', f'case $3 in *state_dir) echo "{state}";; *at_backend) echo "${{T_BACKEND:-auto}}";; esac')
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual((state / 'sim2-native/nr').read_text(), '41')
        self.assertNotEqual(self.call('supported', 'nr', T_BACKEND='custom').returncode, 0)

    def test_missing_bearer_after_restart_rolls_back_without_reboot(self):
        ubus = self.bin / 'ubus'
        ubus.write_text("#!/usr/bin/python3\nimport os,json\nd=json.load(open(os.environ['MODEM']))\nprint(json.dumps({'up':'SFUN=4' not in d['log'],'l3_device':'sipa_eth8'}))\n")
        ubus.chmod(0o755)
        self.stub('reboot', 'echo called > "$MODEM.reboot"')
        r = self.call('apply', 'nr', '41')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.state()['nr'], '0,0,0')
        self.assertFalse((self.root / 'etc/unisoc-modem/lock-state.d/sim2-native/nr').exists())
        self.assertFalse(Path(str(self.db) + '.reboot').exists())

    def test_global_unlock_refuses_existing_lte_lock(self):
        d = self.state(); d['lte_cell'] = ['100,1']; self.db.write_text(json.dumps(d))
        r = self.call('apply', 'cell', 'off')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertEqual(self.state()['log'], ['SPFORCEFRQ=12,3'])
        self.assertEqual(self.state()['lte_cell'], ['100,1'])

    def test_global_unlock_when_lte_is_already_clear(self):
        r = self.call('apply', 'cell', 'off')
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        self.assertEqual(self.state()['cell'], [])

    def test_success_does_not_restart_the_restored_bearer_in_cleanup(self):
        self.stub('ifup', 'echo up >> "$MODEM.net"')
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(Path(str(self.db) + '.net').read_text().splitlines(), ['up'])

    def test_supported_checks_are_explicit(self):
        (self.root / 'run/mu300/sim-slot').write_text('0')
        self.assertNotEqual(self.call('supported', 'nr').returncode, 0)
        (self.root / 'run/mu300/sim-slot').write_text('1')
        (self.root / 'run/mu300-radio-freeze').unlink()
        self.assertNotEqual(self.call('supported', 'cell').returncode, 0)

    def test_cell_lost_after_restart_is_not_committed(self):
        d = self.state()
        d['lose_cell'] = True
        self.db.write_text(json.dumps(d))
        r = self.call('apply', 'cell', 'auto')
        self.assertNotEqual(r.returncode, 0, r.stdout)
        self.assertFalse((self.root / 'etc/unisoc-modem/lock-state.d/sim2-native/cell').exists())
        self.assertEqual(self.state()['cell'], [])

    def test_boot_replay_without_sfun(self):
        d = self.root / 'etc/unisoc-modem/lock-state.d/sim2-native'
        d.mkdir()
        (d / 'nr').write_text('41')
        (d / 'cell').write_text('524910,269\n')
        st = self.state()
        st['rf'] = 0
        self.db.write_text(json.dumps(st))
        r = self.call('replay', MU300_NATIVE_EARLY='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,16')
        self.assertEqual(self.state()['cell'], ['524910,269'])
        self.assertNotIn('SFUN=5', self.state()['log'])

    def test_replay_switch_target_before_slot_publication(self):
        (self.root / 'run/mu300/sim-slot').write_text('0')
        d = self.root / 'etc/unisoc-modem/lock-state.d/sim2-native'
        d.mkdir()
        (d / 'nr').write_text('41')
        st = self.state()
        st['rf'] = 0
        self.db.write_text(json.dumps(st))
        r = self.call('replay', MU300_NATIVE_EARLY='1', MU300_SIM_SLOT='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,16')

    def test_interrupted_write_restored_before_boot_replay(self):
        d = self.state()
        d['nr'] = '0,0,16'
        d['rf'] = 0
        d['cell'] = ['524910,269']
        self.db.write_text(json.dumps(d))
        pending = self.root / 'etc/mu300/sim2-native-recovery'
        pending.write_text('0,0,0\n')
        r = self.call('replay', MU300_NATIVE_EARLY='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,0')
        self.assertEqual(self.state()['cell'], [])
        self.assertFalse(pending.exists())
        self.assertNotIn('SFUN=4', self.state()['log'])
class Experimental(Fixture):
    def profile(self, device='f50', board=1, chip=0):
        self.stub('mu300-device', 'echo ' + device, self.root / 'opt/mu300/bin')
        (self.root / 'run/mu300-radio-freeze').unlink(missing_ok=True)
        (self.root / 'run/mu300/sim2-nr-locks').write_text(device)
        self.env['T_GENERIC'] = '1'
        for name in ['mu300-at', 'mu300-at2']:
            d = self.root / 'run' / name
            (d / 'owner').mkdir(parents=True, exist_ok=True)
            os.mkfifo(d / 'cmd')
            (d / 'owner/pid').write_text(str(os.getpid()))
        key = 'f50'
        if device == 'v50':
            lib = self.root / 'opt/mu300/lib/v50-card.sh'
            lib.parent.mkdir(parents=True)
            lib.write_bytes((TOP / 'rootfs/overlay/opt/mu300/lib/v50-card.sh').read_bytes())
            self.env['MU300_SYSROOT'] = str(self.root)
            b = self.root / 'proc/driver/board_id'
            b.parent.mkdir(parents=True)
            b.write_text(str(board))
            self.mux = self.p / 'mux'
            self.mux.mkdir()
            (self.mux / 'chip_select').write_text(str(chip))
            (self.mux / 'psim_select').write_text('0')
            self.env['MU300_V50_MUX'] = str(self.mux)
            key = f'v50-board{board}-card{chip + 1}'
        self.saved = self.root / ('etc/unisoc-modem/lock-state.d/sim2-' + key)
        self.recovery = self.root / ('etc/mu300/sim2-' + key + '-recovery')

    def boot_saved(self, rf=0):
        self.saved.mkdir(exist_ok=True)
        (self.saved / 'nr').write_text('41')
        (self.saved / 'cell').write_text('524910,269\n')
        d = self.state(); d['rf'] = rf; self.db.write_text(json.dumps(d))
        return self.call('replay', MU300_SIM2_BOOT='1')

    def test_f50_requires_explicit_matching_opt_in(self):
        self.profile()
        flag = self.root / 'run/mu300/sim2-nr-locks'
        for value in ['', 'v50', 'f50;reboot']:
            flag.write_text(value)
            self.assertNotEqual(self.call('apply', 'nr', '41').returncode, 0)
        flag.unlink()
        self.assertNotEqual(self.call('supported', 'nr').returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_gui_switch_defaults_off_and_is_latched_until_next_boot(self):
        self.profile()
        flag = self.root / 'run/mu300/sim2-nr-locks'
        flag.unlink()
        self.stub('uci', 'case $3 in unisoc_modem.main.sim2_nr_locks) printf "%s" "${T_ENABLE:-0}";; esac')
        self.assertEqual(self.call('boot-config').returncode, 0)
        self.assertEqual(flag.read_text().strip(), 'off')
        # Saving on during this boot (or restarting the service) cannot enable it.
        self.assertEqual(self.call('boot-config', T_ENABLE='1').returncode, 0)
        self.assertNotEqual(self.call('supported', 'nr', T_ENABLE='1').returncode, 0)
        # New /run after reboot latches the persisted enabled switch.
        flag.unlink()
        self.assertEqual(self.call('boot-config', T_ENABLE='1').returncode, 0)
        self.assertEqual(flag.read_text().strip(), 'f50')
        self.assertEqual(self.call('supported', 'nr').returncode, 0)
        # Disabling is latched on the next boot too.
        self.assertEqual(self.call('boot-config', T_ENABLE='0').returncode, 0)
        self.assertEqual(self.call('supported', 'nr').returncode, 0)
        flag.unlink()
        self.call('boot-config', T_ENABLE='0')
        self.assertNotEqual(self.call('supported', 'nr').returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_f50_lock_uses_boot_pinned_main_and_data_brokers(self):
        self.profile()
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((self.saved / 'nr').read_text(), '41')
        self.assertFalse(self.recovery.exists())
        self.assertIn('SPACTCARD?', self.state()['log'])
        self.assertEqual(json.loads(self.call('status').stdout)['experimental'], True)

    def test_f50_nr_cell_and_unlock(self):
        self.profile()
        for value in ['auto', 'off-nr']:
            r = self.call('apply', 'cell', value)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()['cell'], [])

    def test_wrong_logical_card_never_writes(self):
        self.profile()
        r = self.call('apply', 'nr', '41', T_CARD='0')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state()['log'], ['SPACTCARD?'])
        self.assertFalse(self.recovery.exists())

    def test_wrong_data_broker_never_restarts_the_other_card(self):
        self.profile()
        r = self.call('apply', 'nr', '41', T_DATA_CARD='0')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state()['log'], ['SPACTCARD?', 'SPACTCARD?'])
        self.assertFalse(self.recovery.exists())

    def test_missing_or_incompatible_capabilities_do_not_drop_wan(self):
        self.profile()
        self.stub('ifdown', 'echo down >> "$MODEM.net"')
        for caps in ['', '2,1,78', '3,1,41', 'bad,41', '1,79']:
            r = self.call('apply', 'nr', '41', T_CAPS=caps)
            self.assertNotEqual(r.returncode, 0, (caps, r.stdout))
        self.assertFalse(Path(str(self.db) + '.net').exists())
        self.assertFalse(self.recovery.exists())
        self.assertFalse(any(x.startswith('SPLBAND=2') for x in self.state()['log']))

    def test_f50_firmware_may_report_off_as_cfun2(self):
        self.profile()
        r = self.call('apply', 'nr', '41', T_RF_OFF='2')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_f50_refusal_rolls_back(self):
        self.profile()
        d = self.state(); d['refuse'] = True; self.db.write_text(json.dumps(d))
        r = self.call('apply', 'nr', '41')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.state()['nr'], '0,0,0')
        self.assertFalse((self.saved / 'nr').exists())
        self.assertFalse(self.recovery.exists())

    def test_live_ifup_never_replays_the_uncommitted_journal(self):
        self.profile()
        self.saved.mkdir(); (self.saved / 'nr').write_text('78')
        self.stub('ifup', f'MU300_SIM2_BOOT=1 "{self.helper}" replay')
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,16')
        self.assertEqual((self.saved / 'nr').read_text(), '41')

    def test_lock_lost_during_dial_is_not_saved(self):
        self.profile()
        script = self.bin / 'ifup'
        script.write_text('#!/usr/bin/python3\nimport json,os\np=os.environ["MODEM"]\n'
                          'd=json.load(open(p));d["cell"]=[];json.dump(d,open(p,"w"))\n')
        script.chmod(0o755)
        r = self.call('apply', 'cell', 'auto')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.saved / 'cell').exists())
        self.assertFalse(self.recovery.exists())

    def test_failed_boot_replay_keeps_journal_until_verified_recovery(self):
        self.profile()
        d = self.state();d['refuse'] = True;self.db.write_text(json.dumps(d))
        r = self.boot_saved()
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(self.recovery.exists())
        self.assertNotIn('SFUN=4', self.state()['log'])
        (self.saved.parent / 'auto_apply').write_text('off')
        r = self.call('replay', MU300_SIM2_BOOT='1')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.recovery.exists())
        self.assertEqual(self.state()['nr'], '0,0,0')

    def test_lte_modes_and_reset_stay_guarded(self):
        self.profile()
        for kind in ['lte', 'mode', 'endc', 'reset']:
            self.assertNotEqual(self.call('supported', kind).returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_f50_boot_replay_before_rf_on_and_once_only(self):
        self.profile()
        r = self.boot_saved()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,16')
        self.assertEqual(self.state()['cell'], ['524910,269'])
        self.assertNotIn('SFUN=4', self.state()['log'])
        before = self.state()['log']
        self.assertEqual(self.call('replay', MU300_SIM2_BOOT='1').returncode, 0)
        self.assertEqual(self.state()['log'], before)
        self.assertFalse(self.recovery.exists())

    def test_f50_boot_replay_when_bootloader_left_radio_on(self):
        self.profile()
        r = self.boot_saved(rf=1)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()['rf'], 1)
        self.assertLess(self.state()['log'].index('SFUN=5'), self.state()['log'].index('SPLBAND=2,0,0,16,0'))
        self.assertFalse(self.recovery.exists())

    def test_boot_recovery_even_with_replay_disabled(self):
        self.profile()
        self.recovery.write_text('0,0,0\n')
        (self.saved.parent / 'auto_apply').write_text('off')
        d = self.state(); d['nr'] = '0,0,16'; d['rf'] = 0; self.db.write_text(json.dumps(d))
        r = self.call('replay', MU300_SIM2_BOOT='1')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()['nr'], '0,0,0')
        self.assertFalse(self.recovery.exists())

    def test_invalid_saved_cells_are_checked_before_rf_or_lock_write(self):
        self.profile()
        self.saved.mkdir()
        (self.saved / 'cell').write_text('524910,1008\n')
        r = self.call('replay', MU300_SIM2_BOOT='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.recovery.exists())
        self.assertEqual(self.state()['log'], ['SPACTCARD?', 'SPACTCARD?', 'CFUN?'])

    def test_v50_state_uses_actual_physical_card(self):
        self.profile('v50', board=1, chip=0)
        r = self.call('apply', 'nr', '41')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        first = self.saved
        (self.mux / 'chip_select').write_text('1')
        r = self.call('apply', 'nr', '78')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual((first / 'nr').read_text(), '41')
        self.assertEqual((first.parent / 'sim2-v50-board1-card2/nr').read_text(), '78')

    def test_v50_absent_physical_card_and_unknown_board_refused(self):
        self.profile('v50', board=3, chip=1)
        self.assertNotEqual(self.call('supported', 'nr').returncode, 0)
        (self.root / 'proc/driver/board_id').write_text('9')
        self.assertNotEqual(self.call('supported', 'nr').returncode, 0)
        self.assertEqual(self.state()['log'], [])

    def test_all_v50_board_variants_only_offer_present_sim2_cards(self):
        self.profile('v50')
        for board in range(4):
            for chip in range(2):
                (self.root / 'proc/driver/board_id').write_text(str(board))
                (self.mux / 'chip_select').write_text(str(chip))
                r = self.call('status')
                allowed = chip == 0 or board in (0, 1)
                self.assertEqual(r.returncode == 0, allowed, (board, chip))
                if allowed:
                    self.assertEqual(json.loads(r.stdout)['profile'], f'v50-board{board}-card{chip + 1}')
        self.assertEqual(self.state()['log'], [])

    def test_v50_card_changed_while_waiting_for_radio_lock_is_refused(self):
        self.profile('v50')
        self.stub('mobile-data', f'echo 1 > "{self.mux}/chip_select";shift;exec "$@"', self.root / 'opt/mu300/bin')
        r = self.call('apply', 'nr', '41')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(self.recovery.exists())
        self.assertFalse(any(x.startswith('SPLBAND=2') for x in self.state()['log']))

    def test_v50_boot_never_replays_other_physical_cards_state(self):
        self.profile('v50', board=1, chip=0)
        self.saved.mkdir(); (self.saved / 'nr').write_text('41')
        (self.mux / 'chip_select').write_text('1')
        r = self.call('replay', MU300_SIM2_BOOT='1')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.state()['log'], [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
