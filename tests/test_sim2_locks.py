"""Native SIM2 NR transactions against a stateful fake CP; no serial devices/network access."""
import unittest, tempfile, shutil, subprocess, json, os
from pathlib import Path
from helpers import TOP
from test_mu300dash_security import JSONFILTER
P = TOP / 'rootfs/overlay/opt/mu300/bin'

MODEM = r'''#!/usr/bin/python3
import os,json,sys
p=os.environ['MODEM'];d=json.load(open(p));q=sys.argv[-1];assert q.startswith('AT+SPACTCARD=1;+');q=q.split(';+',1)[1];d['log'].append(q)
o=''
if q=='SPLBAND=3':o='+SPLBAND: '+d['nr']
elif q.startswith('SPLBAND=2,'):
 if d.pop('refuse',False):json.dump(d,open(p,'w'));print('ERROR');sys.exit(0)
 r=q.split(',',1)[1].split(',');d['nr']=','.join(r[:3]) if r[3]=='0' else ','.join(r)
elif q=='SPFORCEFRQ=16,3':o='malformed' if d.get('bad_cell') else '+SPFORCEFRQ: 16,3'+''.join(','+x for x in d['cell'])
elif q=='SPFORCEFRQ=12,3':o='+SPFORCEFRQ: 12,3'+''.join(','+x for x in d.get('lte_cell',[]))
elif q=='SPFORCEFRQ=16,4':d['cell']=[]
elif q.startswith('SPFORCEFRQ=16,6,'):d['cell'].append(q.split(',',2)[2])
elif q=='SPENGMD=0,14,1':o='41,0-524910,0-269,0-0'
elif q=='CFUN?':o='+CFUN: '+str(d['rf'])
elif q=='SFUN=5':d['rf']=0
elif q=='SFUN=4':
 d['rf']=1
 if d.pop('lose_cell',False):d['cell']=[]
else:raise Exception(q)
json.dump(d,open(p,'w'));print(o+'\nOK' if o else 'OK')
'''


class Native(unittest.TestCase):

    def setUp(self):
        self.p = Path(tempfile.mkdtemp(prefix='u30-native-'))
        self.root = self.p / 'root'
        self.bin = self.p / 'bin'
        self.bin.mkdir()
        s = (P / 'mu300-sim2-lock').read_text()
        for pre in ['/run/mu300', '/etc/mu300', '/etc/unisoc-modem', '/usr/libexec/unisoc-modem', '/opt/mu300/bin', '/opt/mu300/busybox-bin', '/etc/openwrt_release', '/usr/share/unisoc-modem']:
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
if __name__ == '__main__':
    unittest.main(verbosity=2)
