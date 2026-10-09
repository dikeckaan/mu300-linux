"""SIM2 boot gates with fake AT brokers; no modem devices or host /run writes."""
import os
import subprocess
import unittest

from helpers import BIN, TOP, ShellTest


class Sim2ColdStart(ShellTest):
    def setUp(self):
        super().setUp()
        self.run = self.tmp / 'run'
        (self.run / 'mu300').mkdir(parents=True)
        (self.run / 'mu300-radio-freeze').touch()
        for name in ('mu300-at', 'mu300-at2', 'mu300-at4', 'mu300-at5'):
            d = self.run / name
            (d / 'owner').mkdir(parents=True)
            (d / 'owner/pid').write_text(str(os.getpid()))
            os.mkfifo(d / 'cmd')
        urc = self.run / 'mu300-at/urc'
        urc.mkdir()
        (urc / 'stty_nr0.log').write_text('CP ready\n')
        self.stub('sleep', ':')
        self.stub('mu300-at', r'''
shift 2
echo "${MU300_AT_DIR##*/} $1" >> "$STUBLOG/at"
case $1 in
  'AT+CFUN?')
    if [ "${T_ALREADY_ON:-0}" = 1 ] || [ -e "$STUBLOG/radio-on" ]; then
      echo '+CFUN: 1'
    else echo '+CFUN: 0'; fi ;;
  'AT+CPIN?') echo "+CPIN: ${T_PIN:-READY}" ;;
  'AT+CCID') echo '+CCID: 00000000000000000001' ;;
  'AT+SFUN=4') [ "${T_FAIL_SFUN:-0}" = 1 ] && { echo ERROR; exit 0; }; touch "$STUBLOG/radio-on" ;;
  'AT+CEREG?') echo "+CEREG: 2,${T_REG:-1}" ;;
esac
echo OK
''')
        self.start = self.copy_script('mu300-sim2-start')

    def copy_script(self, name):
        p = self.tmp / name
        p.write_text((BIN / name).read_text().replace('/run/', str(self.run) + '/')
                     .replace('/opt/mu300/bin/mu300-at', 'mu300-at'))
        return p

    def boot(self, **env):
        return self.script(['bash'], self.start, '--cold-start', **env)

    def calls(self):
        p = self.tmp / 'at'
        return p.read_text().splitlines() if p.exists() else []

    def test_success_and_zero_byte_marker(self):
        r = self.boot()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.calls(), [
            'mu300-at AT+SMMSWAP=0', 'mu300-at AT+CFUN?', 'mu300-at4 AT+CFUN?',
            'mu300-at4 AT+CPIN?', 'mu300-at4 AT+CCID',
            'mu300-at5 AT+SPTESTMODEM=134,134', 'mu300-at5 AT+SPSWDATA',
            'mu300-at5 AT+SFUN=4', 'mu300-at4 AT+CFUN?', 'mu300-at4 AT+CEREG?'])
        self.assertEqual((self.run / 'mu300/sim2-radio-ready').stat().st_size, 0)
        self.assertNotIn('00000000000000000001', (self.run / 'mu300/sim2-cold-start.log').read_text())
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertEqual(len(self.calls()), 10, 'second attempt must send no commands')

    def test_active_radio_is_not_restarted(self):
        self.assertNotEqual(self.boot(T_ALREADY_ON='1').returncode, 0)
        self.assertEqual(self.calls(), ['mu300-at AT+SMMSWAP=0', 'mu300-at AT+CFUN?'])

    def test_wrong_card_stops_before_radio_on(self):
        self.assertNotEqual(self.boot(MU300_EXPECT_CCID='synthetic-mismatch').returncode, 0)
        self.assertFalse(any('SFUN' in c or 'SPTESTMODEM' in c for c in self.calls()))

    def test_unready_card_stops_before_radio_on(self):
        self.assertNotEqual(self.boot(T_PIN='SIM PIN').returncode, 0)
        self.assertFalse(any('SFUN' in c or 'SPTESTMODEM' in c for c in self.calls()))

    def test_ok_is_not_registration(self):
        self.assertNotEqual(self.boot(T_REG='2').returncode, 0)
        self.assertFalse((self.run / 'mu300/sim2-radio-ready').exists())

    def test_rejected_sfun_is_not_success(self):
        self.assertNotEqual(self.boot(T_FAIL_SFUN='1').returncode, 0)
        self.assertFalse((self.run / 'mu300/sim2-radio-ready').exists())

    def test_missing_owner_does_not_open_tty(self):
        (self.run / 'mu300-at4/owner/pid').unlink()
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertFalse(any(c.startswith('mu300-at4 ') for c in self.calls()))

    def test_missing_cp_output_sends_nothing(self):
        (self.run / 'mu300-at/urc/stty_nr0.log').write_text('')
        self.assertNotEqual(self.boot().returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_charging_boot_sends_nothing(self):
        (self.run / 'mu300/charging-boot').touch()
        self.assertEqual(self.boot().returncode, 0)
        warmup = self.copy_script('mu300-sim2-warmup')
        self.assertEqual(self.script(['bash'], warmup).returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_mobile_data_uses_ready_marker_without_second_bringup(self):
        lib = self.copy_script('mobile-data')
        (self.run / 'mu300/sim2-radio-ready').touch()
        r = self.sh(['bash'], f'MU300_LIB=1; . "{lib}"\n'
                    'at() { echo "$*" >> "$STUBLOG/radio-check"; printf "+CFUN: 1\\r\\nOK\\n"; }\n'
                    'radio_on_locked', MU300_SIM_SLOT='1')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.tmp / 'radio-check').read_text(), 'AT+CFUN? 4\n')

    def test_sim2_suspend_refused_before_any_external_action(self):
        lib = self.copy_script('mobile-data')
        r = self.sh(['bash'], f'MU300_LIB=1; . "{lib}"\n'
                    'at() { echo AT >> "$STUBLOG/actions"; }\n'
                    'ifdown() { echo ifdown >> "$STUBLOG/actions"; }\n'
                    'do_suspend off', MU300_SIM_SLOT='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse((self.tmp / 'actions').exists())
        self.assertFalse((self.run / 'mu300-mobile-data.suspend').exists())

    def init_service(self, tail='start_service', **env):
        source = TOP / 'openwrt/overlay/etc/init.d/mu300-atd'
        text = source.read_text().replace('/run/', str(self.run) + '/')
        text = text.replace('/etc/mu300-sim-slot', str(self.tmp / 'choice'))
        text = text.replace('/etc/mu300-sim-hot', str(self.tmp / 'hot-choice'))
        text = text.replace('/dev/sipc_sbuf', '/dev/null')
        harness = '''
procd_open_instance() { echo "instance $*"; }
procd_set_param() { echo "param $*"; }
procd_close_instance() { :; }
sleep() { :; }
grep() { [ "${T_READY:-1}" = 1 ]; }
'''
        return self.sh(['bash'], harness + text + '\n' + tail, **env)

    def test_sim1_cold_path_uses_its_own_data_broker(self):
        r = self.boot(MU300_SIM_SLOT='0')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('mu300-at2 AT+SPSWDATA', self.calls())
        self.assertNotIn('mu300-at5 AT+SFUN=4', self.calls())
        self.assertTrue((self.run / 'mu300/sim-radio-ready').exists())

    def test_hot_sim1_boot_opens_both_groups_once(self):
        (self.tmp / 'choice').write_text('0\n')
        (self.tmp / 'hot-choice').write_text('1\n')
        r = self.init_service()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.count('MU300_AT_DISABLE_REOPEN=1'), 4)
        self.assertTrue((self.run / 'mu300/sim-managed').exists())
        self.assertNotIn('param respawn', r.stdout)

    def test_setting_is_pinned_until_reboot(self):
        (self.tmp / 'choice').write_text('0\n')
        r = self.init_service(f'start_service; echo 1 > "{self.tmp}/choice"; start_service')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((self.run / 'mu300/sim-slot').read_text(), '0\n')
        self.assertNotIn('instance atd4', r.stdout)

    def test_sim2_owners_are_persistent_and_not_respawned(self):
        (self.tmp / 'choice').write_text('1\n')
        r = self.init_service()
        self.assertEqual(r.returncode, 0, r.stderr)
        for channel in (1, 2, 4, 5):
            self.assertIn(f'MU300_AT_DEV=/dev/stty_nr{channel}', r.stdout)
        self.assertEqual(r.stdout.count('MU300_AT_DISABLE_REOPEN=1'), 4)
        self.assertNotIn('param respawn', r.stdout)
        self.assertIn('instance sim2-cold-start', r.stdout)

    def test_sipc_not_ready_never_starts_owners(self):
        (self.tmp / 'choice').write_text('1\n')
        r = self.init_service(T_READY='0')
        self.assertNotEqual(r.returncode, 0)
        self.assertNotIn('instance ', r.stdout)


if __name__ == '__main__':
    unittest.main()
