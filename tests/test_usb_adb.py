"""MTP off while an installer works over adb (reported by kanoqwq: an F50's stock MTP hangs, and Windows then resets
the USB device about every ten seconds, which ends the adb session each time). tools/android-usb.sh on the device,
against getprop/setprop stubs that behave like Android's init (sys.usb.state follows sys.usb.config); tools/usb-adb.sh
in install.sh and uninstall.sh against the fake adb (tests/fakeadb.py)."""
import json
import subprocess
import time
import unittest
from pathlib import Path

from helpers import TOP, ShellTest
from test_answers import Device, events

SCRIPT = TOP / 'tools/android-usb.sh'
BOOT = '6f1d2c3b-aaaa-4bbb-8ccc-000000000001'


class DeviceSide(ShellTest):
    def setUp(self):
        super().setUp()
        self.props = self.tmp / 'props'
        self.props.mkdir()
        self.log = self.tmp / 'setprop.log'
        self.stub('getprop', f'cat "{self.props}/$1" 2>/dev/null; echo')
        # init: sys.usb.state follows sys.usb.config
        self.stub('setprop', f'echo "$1=$2" >> "{self.log}"; printf %s "$2" > "{self.props}/$1"; '
                             f'[ "$1" != sys.usb.config ] || printf %s "$2" > "{self.props}/sys.usb.state"')
        (self.tmp / 'boot_id').write_text(BOOT + '\n')

    def set(self, **props):
        for k, v in props.items():
            (self.props / k.replace('_', '.')).write_text(v)

    def run_usb(self, shell, *args, detach='0'):
        env = self.env(MU300_GETPROP='getprop', MU300_SETPROP='setprop', MU300_BOOT_ID=str(self.tmp / 'boot_id'),
                       MU300_USB_DELAY='0', MU300_USB_DETACH=detach)
        return subprocess.run(shell + [str(SCRIPT)] + list(args), capture_output=True, text=True, env=env, timeout=30)

    def setprops(self):
        return self.log.read_text().split() if self.log.exists() else []

    def fresh(self, cfg):
        if self.log.exists():
            self.log.unlink()
        for p in self.props.iterdir():
            p.unlink()
        self.set(sys_usb_config=cfg, sys_usb_state=cfg)

    def test_mtp_goes_the_way_android_switches(self):
        for shell in self.each_shell():
            for cfg in ('ecm,mtp,adb', 'mtp,adb', 'ptp,adb', 'rndis,mtp,cdrom,adb'):
                self.fresh(cfg)
                r = self.run_usb(shell, 'adb-only')
                self.assertEqual(r.stdout.strip(), f'MU300-USB switch {cfg} {BOOT}', r.stderr)
                # none first, as UsbDeviceManager does it, then adb alone; never the persistent property
                self.assertEqual(self.setprops(), ['sys.usb.config=none', 'sys.usb.config=adb'])
                self.assertEqual((self.props / 'sys.usb.state').read_text(), 'adb')

    def test_nothing_to_do_or_nothing_to_touch(self):
        for shell in self.each_shell():
            for cfg, word in (('adb', 'keep'), ('rndis,adb', 'keep'), ('mu300,adb', 'keep'),
                              ('mtp', 'skip'), ('', 'skip'), ('mtp,adb;reboot', 'skip')):
                self.fresh(cfg)
                r = self.run_usb(shell, 'adb-only')
                self.assertEqual(r.stdout.split()[:2], ['MU300-USB', word], cfg)
                self.assertEqual(self.setprops(), [], cfg)
            # a reboot under way (sys.powerctl): left alone
            self.fresh('ecm,mtp,adb'); self.set(sys_powerctl='reboot,adb')
            self.assertEqual(self.run_usb(shell, 'adb-only').stdout.split()[1], 'skip')
            self.assertEqual(self.setprops(), [])

    def test_restore_only_in_the_boot_that_was_switched(self):
        for shell in self.each_shell():
            self.fresh('adb')
            r = self.run_usb(shell, 'restore', 'ecm,mtp,adb', BOOT)
            self.assertEqual(r.stdout.strip(), 'MU300-USB restore ecm,mtp,adb')
            self.assertEqual(self.setprops(), ['sys.usb.config=none', 'sys.usb.config=ecm,mtp,adb'])
            # another boot (Android restarted: it has its own functions again), functions someone changed since,
            # a reboot under way: nothing
            for cfg, boot, powerctl in (('adb', 'another-boot', ''), ('rndis,adb', BOOT, ''), ('adb', BOOT, 'reboot')):
                self.fresh(cfg)
                if powerctl:
                    self.set(sys_powerctl=powerctl)
                r = self.run_usb(shell, 'restore', 'ecm,mtp,adb', boot)
                self.assertEqual(r.stdout.split()[:2], ['MU300-USB', 'keep'])
                self.assertEqual(self.setprops(), [])
            # only a value of the functions' own form is passed on
            self.fresh('adb')
            for bad in ('ecm;reboot', 'a b', '$(id)', ''):
                r = self.run_usb(shell, 'restore', bad, BOOT)
                self.assertEqual(r.returncode, 2, bad)
                self.assertEqual(self.setprops(), [])

    def test_the_switch_outlives_the_session_that_asked_for_it(self):
        # adb drops with the first step of the switch: the command has answered by then, and the switch goes on alone
        for shell in self.each_shell():
            self.fresh('ecm,mtp,adb')
            env = self.env(MU300_GETPROP='getprop', MU300_SETPROP='setprop', MU300_BOOT_ID=str(self.tmp / 'boot_id'),
                           MU300_USB_DELAY='1')
            t0 = time.monotonic()
            r = subprocess.run(shell + [str(SCRIPT), 'adb-only'], capture_output=True, text=True, env=env, timeout=30)
            self.assertLess(time.monotonic() - t0, 1)
            self.assertIn('MU300-USB switch', r.stdout)
            self.assertEqual(self.setprops(), [])
            for _ in range(40):
                if self.setprops() == ['sys.usb.config=none', 'sys.usb.config=adb']:
                    break
                time.sleep(0.25)
            self.assertEqual(self.setprops(), ['sys.usb.config=none', 'sys.usb.config=adb'])

    def test_the_stock_f50_has_the_adb_configuration(self):
        # what the choice rests on (tools/android-usb.sh's header), not a file this repository has: the F50's stock
        # vendor rc builds "adb" as ffs.adb alone, and Android's default property for it is "disable"
        src = SCRIPT.read_text()
        self.assertIn('setprop', src)
        self.assertNotIn('persist.sys.usb.config adb', src)
        self.assertNotRegex(src, r'SETPROP"? persist\.')


class Installers(Device):
    """install.sh and uninstall.sh against the fake adb: the switch early in the run, adb waited for, and the functions
    of before at the end while the device is still in that boot of Android."""

    def saved(self):
        return json.loads(self.state.read_text())

    def usb_calls(self):
        return [c['cmd'] for c in self.calls() if 'android-usb.sh' in c['cmd']]

    def check(self, shell, **env):
        r = self.run_script(shell, 'install.sh', '--check', MU300_NONINTERACTIVE=1, MU300_PROGRESS=1, **env)
        ev = events(r.stdout)
        return r, ev, {e['key']: e['value'] for e in ev if e['event'] == 'info'}

    def test_check_switches_and_sets_back(self):
        for shell in self.each_shell():
            self.device(usb_config='ecm,mtp,adb')
            r, ev, facts = self.check(shell)
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
            self.assertEqual((facts['usb.functions'], facts['usb.was']), ('adb', 'ecm,mtp,adb'))
            self.assertIn('USB of Android: adb only for this run (was ecm,mtp,adb', r.stdout)
            self.assertEqual(ev[-1], {'event': 'done', 'result': 'ok'})
            # before anything else is asked of the device's storage, right after root
            cmds = [c['cmd'] for c in self.calls() if c['cmd']]
            self.assertLess(cmds.index('sh /data/local/tmp/android-usb.sh adb-only'),
                            min(i for i, c in enumerate(cmds) if 'by-name' in c or '/sys/block' in c))
            self.assertIn('USB of Android set back to ecm,mtp,adb', r.stdout)
            self.assertEqual(self.saved()['usb_config'], 'ecm,mtp,adb')
            self.assert_nothing_written()

    def test_mtp_already_off_changes_nothing(self):
        for shell in self.each_shell():
            for cfg in ('adb', 'rndis,adb'):
                self.device(usb_config=cfg)
                r, ev, facts = self.check(shell)
                self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
                self.assertEqual(facts['usb.functions'], cfg)
                self.assertNotIn('usb.was', facts)
                self.assertEqual(self.usb_calls(), ['sh /data/local/tmp/android-usb.sh adb-only'])
                self.assertEqual(self.calls('usb'), [])
                self.assertNotIn('adb only for this run', r.stdout)

    def test_left_alone_when_asked(self):
        for shell in self.each_shell():
            self.device(usb_config='ecm,mtp,adb')
            r, ev, facts = self.check(shell, MU300_USB_ADB_ONLY='0')
            self.assertEqual(r.returncode, 0)
            self.assertEqual(self.usb_calls(), [])
            self.assertEqual(self.saved().get('usb_config'), 'ecm,mtp,adb')

    def test_a_device_that_does_not_come_back(self):
        for shell in self.each_shell():
            self.device(usb_config='ecm,mtp,adb', usb_back=False)
            t0 = time.monotonic()
            r, ev, facts = self.check(shell, MU300_USB_WAIT='2')
            self.assertLess(time.monotonic() - t0, 30)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(ev[-1]['event'], 'error')
            self.assertIn('did not come back on adb within 2 seconds after its USB was set to adb only', ev[-1]['message'])
            self.assertIn('MU300_USB_ADB_ONLY=0', ev[-1]['message'])

    def test_android_that_sets_its_functions_again_is_gone_on_with(self):
        for shell in self.each_shell():
            self.device(usb_config='ecm,mtp,adb', usb_revert='ecm,mtp,adb')
            r, ev, facts = self.check(shell, MU300_USB_WAIT='2')
            self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr)
            self.assertIn('Android kept its USB functions (ecm,mtp,adb); going on with them', r.stdout)
            self.assertEqual(facts['usb.functions'], 'ecm,mtp,adb')
            # nothing to set back
            self.assertEqual([c for c in self.usb_calls() if 'restore' in c], [])

    def test_a_failed_run_sets_back_too(self):
        for shell in self.each_shell():
            # a V50 on another platform: refused after root, the device stays in Android
            self.device(usb_config='ecm,mtp,adb', model='V50', device='MU3351', platform='ums9230')
            r, ev, facts = self.check(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn('This looks like a ZTE V50 but is not one', ev[-1]['message'])
            self.assertEqual(self.saved()['usb_config'], 'ecm,mtp,adb')
            self.assertTrue(any('restore ecm,mtp,adb' in c for c in self.usb_calls()))

    def test_uninstall_sets_back_at_its_end(self):
        for shell in self.each_shell():
            self.device(usb_config='ecm,mtp,adb', existing=True)
            r = self.run_script(shell, 'uninstall.sh', MU300_NONINTERACTIVE=1, MU300_PROGRESS=1,
                                MU300_ANS_WIPE='keep', MU300_ANS_CONFIRM='uninstall')
            ev = events(r.stdout)
            self.assertEqual(ev[-1], {'event': 'error', 'message': 'cancelled'})
            facts = {e['key']: e['value'] for e in ev if e['event'] == 'info'}
            self.assertEqual(facts['usb.was'], 'ecm,mtp,adb')
            self.assertEqual(self.saved()['usb_config'], 'ecm,mtp,adb')
            self.assert_nothing_written()


class LinuxSide(unittest.TestCase):
    """Our own gadget (boot/init, mu300-adbd): network, the ACM console and adb - no MTP or PTP function anywhere."""

    def test_no_mtp_in_our_gadget(self):
        for path in [TOP / 'boot/init'] + sorted((TOP / 'rootfs/overlay/opt/mu300/bin').glob('mu300-*')):
            if path.is_file():
                text = path.read_text(errors='replace')
                self.assertNotRegex(text, r'functions/(ffs\.)?(mtp|ptp)', str(path))
