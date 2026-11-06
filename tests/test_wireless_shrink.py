"""Online F2FS shrink through pinned TCP transport; fake disks only."""
import contextlib
import hashlib
import os
import subprocess
import io
import json
import shlex
import sys
from pathlib import Path
import unittest
from test_adb_network import Network, net, TOP
from test_resume import OnlineShrink, INSTALL
import fakeemmc


class Recovery(unittest.TestCase):
    def setUp(self):
        Network.setUp(self)
        self.restore_scripts = []
        original = self.s.shell
        def shell(command, **kwargs):
            if command.startswith('umask 077; mkdir -p /data/adb/service.d && printf %s '):
                words = shlex.split(command); script = words[words.index('printf') + 2]
                self.restore_scripts.append(script)
                return (hashlib.sha256(script.encode()).hexdigest() + '  ' + words[-1] + '\n').encode(), 0
            return original(command, **kwargs)
        self.s.shell = shell

    def transaction(self, **changes):
        p = self.root / 'transaction.json'
        rec = dict(format=1, method='online', state='prepared-request', serial=self.facts['SERIAL'],
                   cid=self.facts['CID'], slot='b', token='a'*32, fs_uuid='b'*32, fs_blocks=10000, fs_target=5000)
        rec.update(changes); p.write_text(json.dumps(rec))
        return p

    def test_foreign_transaction_is_refused_before_a_write(self):
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            self.s.shrink_begin(self.transaction(cid='c'*32))
        self.assertNotIn('shrink', self.s.state)

    def test_without_magisk_no_shrink_transaction_or_restore_script_is_armed(self):
        self.facts['MAGISK'] = '0'
        with self.assertRaisesRegex(RuntimeError, 'requires working Magisk'):
            self.s.shrink_begin(self.transaction())
        self.assertNotIn('shrink', self.s.state)
        self.assertEqual(self.restore_scripts, [])

    def test_bound_filesystem_uuid_and_sizes_cannot_change_before_reboot(self):
        for changes in ({'fs_uuid': 'c'*32}, {'fs_blocks': 12000}, {'fs_target': 6000}):
            self.s.state.pop('shrink', None)
            self.s.shrink_begin(self.transaction())
            with self.assertRaisesRegex(RuntimeError, 'different online shrink transaction'):
                self.s.shrink_prepared(self.transaction(state='prepared', **changes))
        self.assertEqual(self.restore_scripts, [])

    def test_lost_shrink_reply_requires_checked_resume_and_never_replays(self):
        self.s.shrink_begin(self.transaction()); commands = []
        def lost(command, **kwargs):
            commands.append(command); raise net.TransportError('reply lost')
        self.s.shell = lost
        with self.assertRaises(net.TransportError): self.s.proxy(['shell', 'su -c shrink-once'])
        self.assertEqual(self.s.state['phase'], 'shrink-recovery')
        with self.assertRaises(RuntimeError): self.s.proxy(['shell', 'su -c shrink-once'])
        with self.assertRaises(RuntimeError): self.s.connect()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.s.connect(restart=True)
        self.assertEqual(commands, ['su -c shrink-once'])
        self.assertEqual(self.s.state['phase'], 'ready')

    def test_only_a_prepared_transaction_allows_the_expected_reboot(self):
        p = self.transaction(); self.s.shrink_begin(p)
        with self.assertRaisesRegex(RuntimeError, 'read back'): self.s.shrink_prepared(p)
        p = self.transaction(state='prepared'); self.s.shrink_prepared(p)
        with self.assertRaises(RuntimeError): self.s.proxy(['shell', 'su -c touch /must-not-run'])
        with contextlib.redirect_stderr(io.StringIO()): self.s.proxy(['reboot'])
        self.assertEqual(sum(c[-1:] == ['reboot'] for c in self.calls), 1)
        with self.assertRaises(RuntimeError): self.s.proxy(['reboot'])
        with self.assertRaisesRegex(RuntimeError, 'waiting for Android'): self.s.connect(restart=True)
        self.facts['BOOT'] = 'new-android-boot'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.s.connect(restart=True)
        self.assertEqual(self.s.state['boot'], 'new-android-boot')

    def test_lost_reboot_reply_does_not_send_another_reboot(self):
        p = self.transaction(state='prepared'); self.s.shrink_begin(p); self.s.shrink_prepared(p)
        call = self.s.call
        def lost(args, timeout=20):
            if args[-1:] == ['reboot']:
                self.calls.append(args); raise net.TransportError('reply lost')
            return call(args, timeout)
        self.s.call = lost
        with contextlib.redirect_stderr(io.StringIO()): self.assertEqual(self.s.proxy(['reboot']), 0)
        with self.assertRaises(RuntimeError): self.s.proxy(['reboot'])
        self.assertEqual(sum(c[-1:] == ['reboot'] for c in self.calls), 1)

    def test_foreign_device_after_reboot_is_never_accepted(self):
        p = self.transaction(state='prepared'); self.s.shrink_begin(p); self.s.shrink_prepared(p)
        self.facts.update(BOOT='new', CID='d'*32)
        with self.assertRaises(net.PeerError): self.s.connect(restart=True)

    @unittest.skipUnless(os.name == 'posix', 'POSIX one-time Android script fixture')
    def test_one_time_script_restores_only_the_original_port_and_keeps_auth(self):
        p = self.transaction(state='prepared'); self.s.shrink_begin(p); self.s.shrink_prepared(p)
        script = self.restore_scripts[-1]
        self.assertNotIn('persist.', script)
        self.assertNotIn('ro.adb.secure', script)
        bindir = self.root / 'bin'; bindir.mkdir()
        props = self.root / 'properties'
        def exe(name, text):
            p = bindir / name; p.write_text('#!/bin/sh\n' + text); p.chmod(0o755)
        exe('getprop', 'case "$1" in ro.serialno) echo fake-serial;; ro.boot.slot_suffix) echo _b;; sys.boot_completed) echo 1;; esac\n')
        exe('cat', 'case "$1" in /sys/class/block/mmcblk0/device/cid) echo "$TEST_CID";; /proc/sys/kernel/random/boot_id) echo "$TEST_BOOT";; *) exec /usr/bin/cat "$@";; esac\n')
        exe('setprop', 'echo "$*" >> "$TEST_PROPERTIES"\n')
        for cid, boot, expected in [('1'*32, 'new-boot', True), ('2'*32, 'new-boot', False), ('1'*32, 'test-boot', False)]:
            f = self.root / 'resume.sh'; f.write_text(script)
            props.unlink(missing_ok=True)
            env = dict(os.environ, PATH=str(bindir)+':'+os.environ['PATH'], TEST_CID=cid, TEST_BOOT=boot, TEST_PROPERTIES=str(props))
            r = subprocess.run(['sh', str(f)], env=env, capture_output=True, text=True)
            self.assertFalse(f.exists(), 'the one-shot must remove itself')
            self.assertEqual(r.returncode, 0 if expected else 1, r.stderr)
            self.assertEqual(props.read_text().splitlines() if props.exists() else [],
                             ['service.adb.tcp.port 5555', 'ctl.restart adbd'] if expected else [])

    def test_lost_restore_script_ack_stops_before_reboot(self):
        p = self.transaction(state='prepared'); self.s.shrink_begin(p)
        def lost(*a, **kw): raise net.TransportError('lost script acknowledgement')
        self.s.shell = lost
        with self.assertRaises(net.TransportError): self.s.shrink_prepared(p)
        self.assertEqual(self.s.state['phase'], 'shrink-recovery')
        self.assertFalse(any(c[-1:] == ['reboot'] for c in self.calls))


@unittest.skipUnless(os.name == 'posix', 'POSIX installer entry point')
class Installer(OnlineShrink):
    def device(self, **keys):
        super().device(**keys)
        self.stub('adb', 'exec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(TOP / 'tests/fake_network_adb.py')) + ' "$@"')

    def inst(self, shell, answers, *args, **env):
        return super().inst(shell, answers, '--adb-address', '192.168.0.1:5555', *args, MU300_ADB_TIMEOUT='1', **env)

    def test_keep_over_tcp_then_reconnect_and_validate_before_install(self):
        self.fresh(); r, ev, facts, before, misc, blocks = self.keep(['bash'])
        self.assertEqual(r.returncode, 0, r.stdout[-4000:] + r.stderr)
        self.assertEqual((facts['makeroom.online'], facts['makeroom.method']), ('yes', 'keep'))
        rec = json.loads(Path(ev[-1]['transaction']).read_text())
        self.assertEqual(rec['state'], 'prepared')
        self.assertEqual(fakeemmc.f2fs_blocks(self.emmc), rec['fs_target'])
        self.assertEqual(fakeemmc.bcb(self.emmc), misc)
        state = json.loads((self.tmp / 'work/wireless-install.json').read_text())
        self.assertEqual(state['phase'], 'shrink-reboot'); self.assertTrue(state['shrink_reboot_sent'])
        self.assertEqual(len(self.calls('reboot')), 1)
        self.assertFalse([c for c in self.calls() if 'android-usb.sh' in c.get('cmd', '')])
        fakeemmc.reset(self.emmc, wipe=False)
        self.device(pull='noboot', network_boot='new-android-boot')
        r, ev, facts = self.inst(['bash'], INSTALL, '--adb-restart')
        self.assertEqual(facts.get('resume.check'), 'RESUME-OK', r.stdout[-4000:] + r.stderr)
        self.assertIn('could not read /dev/block/by-name/boot_a', ev[-1]['message'])
        self.assertFalse([c for c in self.writes() if 'of=/dev/block/' in c])
        self.assertFalse(any('android-online-shrink.sh start' in c.get('cmd','') for c in self.calls()))


def load_tests(loader, tests, pattern):
    # The storage fixture supplies helpers; its inherited wired/reset cases are tested in test_resume itself.
    return unittest.TestSuite([loader.loadTestsFromTestCase(Recovery),
        Installer('test_keep_over_tcp_then_reconnect_and_validate_before_install')])
