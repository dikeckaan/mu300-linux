"""Broker-only SIM transactions: successful switches persist; failed switches preserve boot policy."""
import json
import os
import subprocess
import time
import signal
from helpers import BIN, ShellTest

class HotSim(ShellTest):
    def setUp(self):
        super().setUp()
        self.run = self.tmp / 'run'
        self.etc = self.tmp / 'etc'
        self.etc.mkdir()
        (self.run / 'mu300').mkdir(parents=True)
        (self.run / 'mu300/sim-slot').write_text('1\n')
        (self.etc / 'mu300-sim-slot').write_text('1\n')
        (self.etc / 'mu300-sim-hot').write_text('1\n')
        (self.run / 'mu300-radio-freeze').touch()
        for n in ('mu300-at','mu300-at2','mu300-at4','mu300-at5'):
            d=self.run/n; (d/'owner').mkdir(parents=True)
            (d/'owner/pid').write_text(str(os.getpid())); os.mkfifo(d/'cmd')
        (self.tmp/'radio0').write_text('0'); (self.tmp/'radio1').write_text('1')
        self.stub('ifdown', 'echo down >> "$STUBLOG/net"')
        self.stub('ifup', 'echo up >> "$STUBLOG/net"')
        self.stub('mu300-at', r'''
shift 2
case "$MU300_AT_DIR" in *at4|*at5) slot=1;; *) slot=0;; esac
echo "$slot $1" >> "$STUBLOG/at"
if [ "${T_SILENT:-}" = 1 ] && [ -e "$STUBLOG/mutated" ]; then exit 1; fi
case "$1" in
 'AT+CPIN?') if [ "$slot" = 0 ]; then echo "+CPIN: ${T_PIN:-READY}"; else echo '+CPIN: READY'; fi;;
 'AT+SFUN=4') [ -z "${T_DELAY:-}" ] || sleep "$T_DELAY"; touch "$STUBLOG/mutated"; echo 1 > "$STUBLOG/radio$slot";;
 'AT+SFUN=3') echo 0 > "$STUBLOG/radio$slot";;
 'AT+CFUN?') echo "+CFUN: $(cat "$STUBLOG/radio$slot")";;
 'AT+SPSWDATA')
   if [ "${T_FAIL_ONCE:-}" = 1 ] && [ ! -e "$STUBLOG/failed" ]; then touch "$STUBLOG/failed"; echo ERROR; exit 0; fi;;
esac
echo OK
''')
        self.stub('mobile-data', 'shift; ln -s "$$" "$T_RUN/mu300-radio-on.owner"; "$@"; r=$?; rm -f "$T_RUN/mu300-radio-on.owner"; exit "$r"')
        self.controller=self.tmp/'mu300-sim'
        self.controller.write_text((BIN/'mu300-sim').read_text().replace('/run/',str(self.run)+'/').replace('/etc/',str(self.etc)+'/')
            .replace('/opt/mu300/bin/mu300-at','mu300-at').replace('/opt/mu300/bin/mobile-data','mobile-data'))
        self.controller.chmod(0o755)

    def ctl(self, *args, **env):
        return self.script(['bash'],self.controller,*args,T_RUN=self.run,**env)

    def test_bidirectional_switch_persists_default(self):
        for public,slot in [('1','0'),('2','1')]:
            r=self.ctl('switch',public)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertEqual((self.etc/'mu300-sim-slot').read_text(),slot+'\n')
            self.assertEqual((self.run/'mu300/sim-slot').read_text(),slot+'\n')
            self.assertEqual(json.loads(self.ctl('status').stdout)['active'],int(public))
        calls=(self.tmp/'at').read_text()
        self.assertIn('0 AT+SPACTCARD=0;+SFUN=2',calls)
        self.assertIn('1 AT+SPACTCARD=1;+SFUN=5',calls)
        self.assertNotIn('SPTESTMODEM',calls)
        self.assertEqual((self.tmp/'net').read_text(),'down\nup\ndown\nup\n')

    def test_same_card_sends_no_commands(self):
        self.assertEqual(self.ctl('switch','2').returncode,0)
        self.assertFalse((self.tmp/'at').exists())

    def test_target_pin_lock_rolls_back_and_preserves_default(self):
        self.assertNotEqual(self.ctl('switch','1',T_PIN='SIM PIN').returncode,0)
        self.assertEqual((self.etc/'mu300-sim-slot').read_text(),'1\n')
        self.assertEqual((self.tmp/'net').read_text(),'down\nup\n')
        self.assertEqual(json.loads(self.ctl('status').stdout)['result'],'rolled_back')

    def test_rolls_back_once_without_changing_boot_default(self):
        r=self.ctl('switch','1',T_FAIL_ONCE='1')
        self.assertNotEqual(r.returncode,0)
        s=json.loads(self.ctl('status').stdout)
        self.assertEqual(s['active'],2); self.assertEqual(s['default'],2)
        self.assertEqual(s['result'],'rolled_back')
        self.assertEqual((self.tmp/'net').read_text(),'down\nup\n')

    def test_silent_cp_stops_and_requires_reboot(self):
        self.assertNotEqual(self.ctl('switch','1',T_SILENT='1').returncode,0)
        s=json.loads(self.ctl('status').stdout)
        self.assertIsNone(s['active']); self.assertEqual(s['default'],2)
        self.assertEqual(s['result'],'reboot_required')
        self.assertEqual((self.tmp/'net').read_text(),'down\n')
        self.assertNotEqual(self.ctl('switch','1').returncode,0)

    def test_next_boot_selection_does_not_change_active(self):
        self.assertEqual(self.ctl('default','1').returncode,0)
        s=json.loads(self.ctl('status').stdout)
        self.assertEqual(s['active'],2); self.assertEqual(s['default'],1)
        self.assertFalse((self.tmp/'at').exists())

    def test_disabled_or_missing_owner_sends_nothing(self):
        (self.etc/'mu300-sim-hot').write_text('0')
        self.assertNotEqual(self.ctl('switch','1').returncode,0)
        (self.etc/'mu300-sim-hot').write_text('1')
        (self.run/'mu300-at4/owner/pid').unlink()
        self.assertNotEqual(self.ctl('switch','1').returncode,0)
        self.assertFalse((self.tmp/'at').exists())

    def test_injection_and_internal_sequence_rejected(self):
        for verb,value in [('switch','1;reboot'),('hot','yes'),('default','0'),('--sequence','0')]:
            self.assertNotEqual(self.ctl(verb,value).returncode,0)
        self.assertFalse((self.tmp/'at').exists())

    def test_concurrent_request_cannot_change_default(self):
        lock=self.run/'mu300/sim-control.lock'
        with lock.open('w') as f:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX)
            self.assertNotEqual(self.ctl('default','1').returncode,0)
            self.assertEqual(json.loads(self.ctl('status').stdout)['busy'],1)
        self.assertEqual((self.etc/'mu300-sim-slot').read_text(),'1\n')

    def test_interrupted_switch_keeps_default_and_requires_reboot(self):
        env=self.env(T_RUN=self.run,T_DELAY='10')
        p=subprocess.Popen(['bash',str(self.controller),'switch','1'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+5
            while not (self.run/'mu300/sim-switching').exists():
                self.assertLess(time.monotonic(),deadline); time.sleep(.02)
            p.send_signal(signal.SIGTERM)
            p.communicate(timeout=3)
            s=json.loads(self.ctl('status').stdout)
            self.assertIsNone(s['active']); self.assertEqual(s['default'],2)
            self.assertEqual(s['result'],'reboot_required')
        finally:
            if p.poll() is None: p.kill(); p.communicate()

    def test_interrupted_marker_never_allows_another_switch(self):
        (self.run/'mu300/sim-switching').touch()
        s=json.loads(self.ctl('status').stdout)
        self.assertIsNone(s['active']); self.assertEqual(s['result'],'reboot_required')
        self.assertNotEqual(self.ctl('switch','1').returncode,0)
        self.assertFalse((self.tmp/'at').exists())
