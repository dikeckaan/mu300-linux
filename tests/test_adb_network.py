"""Wireless main-installer transport: pinned identity, Wi-Fi/power notices, safe retry and detached jobs."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from test_answers import Device

TOP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('adb_network', TOP / 'tools/adb-network.py')
net = importlib.util.module_from_spec(spec)
spec.loader.exec_module(net)


class Network(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.wifi = patch.object(net, 'wifi_name', return_value='Device hotspot')
        self.wifi.start(); self.addCleanup(self.wifi.stop)
        self.s = net.Session('fake-adb', '192.168.0.1:5555', self.root / 'session.json', timeout=1)
        self.facts = dict(SERIAL='fake-serial', CID='1'*32, SLOT='_b', MODEL='MU5352', PRODUCT='MU5352',
                          BOOT='test-boot', BATTERY='96', POWERED='0', STATUS='Discharging')
        self.s.facts = lambda: self.facts.copy()
        self.calls = []

        def call(args, timeout=20):
            self.calls.append(args)
            return subprocess.CompletedProcess(args, 0, b'device\n' if 'get-state' in args else b'', b'')
        self.s.call = call
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.s.connect()

    def test_connect_pins_endpoint_and_reports_battery_without_charger(self):
        err, out = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.s.connect()
        self.assertIn('96%', err.getvalue())
        self.assertIn('Connect a stable charger', err.getvalue())
        self.assertNotIn('WARNING', out.getvalue())
        self.assertTrue(all(c[:2] == ['-s', self.s.address] for c in self.calls if c[0] != 'connect'))

    def test_low_or_unknown_battery_warns_and_full_does_not_imply_a_charger(self):
        for battery in ('20', '', '100'):
            err = io.StringIO()
            self.facts.update(BATTERY=battery, STATUS='Full', POWERED='0')
            with contextlib.redirect_stderr(err):
                self.s.power_warning(self.facts)
            self.assertIn('battery power', err.getvalue())
            if battery == '20':
                self.assertIn('low battery', err.getvalue())

    def test_different_wifi_warns_even_when_the_same_device_remains_reachable(self):
        with patch.object(net, 'wifi_name', return_value='Other Wi-Fi'), contextlib.redirect_stderr(io.StringIO()) as err:
            self.s.wait()
            self.assertIn('Wi-Fi changed from Device hotspot to Other Wi-Fi', err.getvalue())
            self.assertIn('Check the device hotspot', err.getvalue())
        self.assertEqual(self.s.state['wifi'], 'Other Wi-Fi')
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.s.notices()
        self.assertIn('connected Wi-Fi changed', out.getvalue())
        self.assertNotIn('wifi_notice', self.s.state)

    def test_wrong_device_or_slot_is_never_rebound(self):
        for key, wrong in (('CID', '2'*32), ('SERIAL', 'another'), ('SLOT', '_a')):
            old = self.facts[key]
            self.facts[key] = wrong
            with self.assertRaises(net.PeerError):
                self.s.wait()
            self.facts[key] = old

    def test_new_address_is_allowed_only_after_same_identity_is_verified(self):
        self.s.address = '192.168.8.1:5555'
        self.s.wait()
        self.assertEqual(net.read_state(self.s.path)['endpoint'], self.s.address)
        self.s.address = '192.168.9.1:5555'
        self.facts['CID'] = '2'*32
        with self.assertRaises(net.PeerError):
            self.s.wait()
        self.assertEqual(net.read_state(self.s.path)['endpoint'], '192.168.8.1:5555')

    def test_offline_error_mentions_wifi_and_does_not_select_another_device(self):
        self.s.call = lambda args, timeout=20: subprocess.CompletedProcess(args, 1, b'', b'offline')
        with patch.object(net.time, 'monotonic', side_effect=[0, 2]), self.assertRaises(net.TransportError) as error:
            self.s.wait()
        self.assertIn('different Wi-Fi', str(error.exception))
        self.assertIn('--adb-status', str(error.exception))

    def test_confirmed_remote_nonzero_is_distinct_from_lost_acknowledgment(self):
        def reply(args, timeout=20):
            token = re.search(r'MU300-NET-RC-[a-f0-9]+:', args[-1])[0]
            return subprocess.CompletedProcess(args, 0, b'value\n\n' + token.encode() + b'1\n', b'')
        self.s.call = reply
        output, rc = net.Session.shell(self.s, 'false')
        self.assertEqual((output, rc), (b'value\n', 1))
        self.s.call = lambda args, timeout=20: subprocess.CompletedProcess(args, 1, b'partial', b'lost')
        with self.assertRaises(net.TransportError):
            net.Session.shell(self.s, 'anything')

    def test_foreground_command_is_never_replayed_after_lost_reply(self):
        self.s.wait = lambda: self.facts
        self.s.shell = lambda *a, **k: (_ for _ in ()).throw(net.TransportError('lost'))
        with self.assertRaises(net.TransportError):
            self.s.proxy(['shell', 'su -c write-once'])
        self.assertEqual(net.read_state(self.s.path)['phase'], 'uncertain')
        with self.assertRaises(RuntimeError):
            self.s.proxy(['push', 'anything', self.s.state['remote'] + '/file'])

    def test_only_staging_transfers_retry_and_foreign_serial_is_refused(self):
        self.s.wait = lambda: self.facts
        calls = []
        def transfer(args, timeout=20):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1 if len(calls) == 1 else 0, b'', b'')
        self.s.call = transfer
        with patch.object(net.time, 'sleep'):
            self.assertEqual(self.s.proxy(['push', 'file', self.s.state['remote'] + '/file']), 0)
        self.assertEqual(len(calls), 2)
        with self.assertRaises(net.PeerError):
            self.s.proxy(['-s', 'another-device', 'shell', 'anything'])
        with self.assertRaises(RuntimeError):
            self.s.proxy(['push', 'file', '/dev/block/mmcblk0'])
        with self.assertRaises(RuntimeError):
            self.s.proxy(['push', 'file', '/data/local/tmp/../../../dev/block/mmcblk0'])
        with self.assertRaises(RuntimeError):
            self.s.proxy(['-s', self.s.address, '-s', 'another-device', 'shell', 'command'])

    def test_transfer_timeouts_block_following_writes(self):
        self.s.wait = lambda: self.facts
        self.s.call = lambda *a, **k: (_ for _ in ()).throw(net.TransportError('lost'))
        with patch.object(net.time, 'sleep'), self.assertRaises(RuntimeError):
            self.s.proxy(['push', 'file', self.s.state['remote'] + '/file'])
        self.assertEqual(self.s.state['phase'], 'blocked')

    def test_unreachable_pre_command_guard_blocks_later_writes_even_if_caller_ignores_exit(self):
        self.s.wait = lambda: (_ for _ in ()).throw(net.TransportError('unreachable'))
        with self.assertRaises(net.TransportError):
            self.s.proxy(['shell', 'su -c write-once'])
        self.assertEqual(net.read_state(self.s.path)['phase'], 'blocked')

    def test_acknowledged_device_write_failure_blocks_finish_but_optional_probe_does_not(self):
        self.s.wait = lambda: self.facts
        self.s.shell = lambda *a, **k: (b'', 1)
        self.assertEqual(self.s.proxy(['shell', "su -c '[ -e missing ] && echo y'"]), 1)
        self.assertEqual(self.s.state['phase'], 'ready')
        with self.assertRaises(RuntimeError):
            self.s.proxy(['shell', "su -c 'dd if=image of=/dev/block/by-name/boot_a'"])
        with self.assertRaises(RuntimeError):
            self.s.guard()

    def test_lost_job_launch_reply_polls_same_job_without_dispatching_again(self):
        self.s.wait = lambda: self.facts
        calls = []
        def shell(command, **kw):
            calls.append(command)
            if 'mkdir started' in command:
                raise net.TransportError('lost launch reply')
            return b'', 0
        self.s.shell = shell
        with patch.object(self.s, 'poll') as poll:
            self.s.install()
        self.assertEqual(sum('mkdir started' in c for c in calls), 1)
        poll.assert_called_once()
        self.assertEqual(self.s.state['phase'], 'installing')

    def test_original_installer_device_command_is_dispatched_as_a_detached_job(self):
        command = 'sh ' + self.s.state['remote'] + '/android-install.sh'
        with patch.object(self.s, 'install') as install, patch.object(self.s, 'shell') as shell:
            self.assertEqual(self.s.proxy(['shell', 'su -c ' + shlex.quote(command)]), 0)
        install.assert_called_once()
        shell.assert_not_called()

    def test_status_never_launches_a_worker_or_arms_the_slot(self):
        self.s.state.update(phase='installing', job='/data/adb/mu300-wireless-' + self.s.state['id'])
        self.s.wait = lambda: self.facts
        calls = []
        self.s.shell = lambda command, **kw: (calls.append(command) or (b'RUNNING_OR_INTERRUPTED\nlog', 0))
        with contextlib.redirect_stdout(io.StringIO()):
            self.s.status()
        self.assertFalse(any('mkdir' in c or 'dd ' in c or 'reboot' in c for c in calls))

    def test_lost_final_reboot_reply_does_not_repeat_reboot_or_install(self):
        self.s.wait = lambda: self.facts
        self.s.state['phase'] = 'complete'
        calls = []
        def lost(args, timeout=20):
            calls.append(args)
            raise net.TransportError('lost')
        self.s.call = lost
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(self.s.proxy(['reboot']), 0)
        self.assertIn('reboot reply was lost', out.getvalue())
        self.assertEqual(len(calls), 1)
        self.assertEqual(self.s.state['phase'], 'complete')

    def test_unknown_foreground_command_requires_manual_reboot_before_restart(self):
        self.s.state['phase'] = 'uncertain'; self.s.save()
        with self.assertRaises(RuntimeError):
            self.s.connect(restart=True)
        # An earlier successful device job says nothing about a later unacknowledged boot write.
        self.s.state['job'] = '/data/adb/mu300-wireless-' + self.s.state['id']
        self.s.job_result = lambda: (0, b'MU300-INSTALL-OK')
        with self.assertRaises(RuntimeError):
            self.s.connect(restart=True)
        self.facts['BOOT'] = 'new-boot'
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.s.connect(restart=True)
        self.assertEqual(self.s.state['phase'], 'ready')

    @unittest.skipUnless(os.name == 'posix', 'POSIX detached worker')
    def test_actual_detached_install_worker_and_existing_boot_lock(self):
        stage = self.root / 'stage'; stage.mkdir()
        (stage / 'android-install.sh').write_text('test "$MU300_ADB_WORK_T" = ' + shlex.quote(str(stage)) +
            ' || exit 8\ntest "$MU300_LOCK_DIR" = /data/adb || exit 9\nsleep 0.1\nprintf "MU300-INSTALL-OK\\n"\n')
        job = self.root / 'job'
        self.facts['BOOT'] = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        lock = self.root / ('lock-' + self.facts['BOOT'] + '.lock')
        self.s.state['boot'] = self.facts['BOOT']
        self.s.wait = lambda: self.facts

        def local_shell(command, **kw):
            command = command.replace('/data/adb/mu300-wireless-install-', str(self.root / 'lock-'))
            command = command.replace('/data/adb/mu300-wireless-' + self.s.state['id'], str(job))
            command = command.replace(self.s.state['remote'], str(stage))
            r = subprocess.run(['sh', '-c', command], capture_output=True, timeout=5)
            return r.stdout, r.returncode

        self.s.shell = local_shell
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.s.install()
        self.assertIn('MU300-INSTALL-OK', out.getvalue())
        self.assertEqual((job / 'result').read_text(), '0\n')
        self.assertEqual(self.s.state['phase'], 'installed')
        self.assertFalse(lock.exists())
        with self.assertRaises(RuntimeError):
            self.s.install()


class PowerShell(unittest.TestCase):
    def test_transport_wrapper_keeps_warnings_out_of_parsed_values(self):
        shells = [shutil.which(n) for n in ('powershell', 'pwsh')]
        shells = sorted(set(n for n in shells if n))
        if not shells:
            self.skipTest('PowerShell unavailable')
        script = r'''
$ErrorActionPreference='Stop'
$ast=[System.Management.Automation.Language.Parser]::ParseFile($args[0],[ref]$null,[ref]$null)
$d=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'Network'},$true)[0]
. ([scriptblock]::Create($d.Extent.Text))
$script:NetworkAdb='fake'; $Work='work with spaces'; $Top='top'; $AdbAddress='192.168.0.1:5555'
$script:TestPython=$args[1]
function Die($message) { throw $message }
function Python { & $script:TestPython -c "import sys; print('expected-value'); print('WARNING: Wi-Fi changed',file=sys.stderr)" }
$value=@(Network 'proxy' '--' 'shell' 'command')
if($value.Count -ne 1 -or $value[0] -ne 'expected-value') { throw 'warning contaminated parsed output' }
$a=$ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq 'adb'},$true)[0]
. ([scriptblock]::Create($a.Extent.Text))
$value=@(adb shell "su -c 'id -u'")
if($value.Count -ne 1 -or $value[0] -ne 'expected-value') { throw 'adb function changed the parsed output' }
function Python { & $script:TestPython -c 'import sys; sys.exit(125)' }
$stopped=$false
try { Network 'proxy' '--' 'shell' 'command' } catch { $stopped=$true }
if(-not $stopped) { throw 'transport failure did not stop the installer' }
Write-Output 'NETWORK-WRAPPER-OK'
'''
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'network.ps1'; path.write_text(script, encoding='utf-8')
            for shell in shells:
                environment = dict(os.environ)
                if os.name == 'nt' and Path(shell).name.lower() == 'powershell.exe':
                    environment['PSModulePath'] = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/Modules')
                r = subprocess.run([shell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(path), str(TOP / 'install.ps1'), sys.executable],
                                   capture_output=True, timeout=40, env=environment)
                self.assertEqual(r.returncode, 0, r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace'))
                self.assertIn(b'NETWORK-WRAPPER-OK', r.stdout)


@unittest.skipUnless(os.name == 'posix', 'POSIX installer entry point')
class EntryPoint(Device):
    def test_original_shell_installer_checks_the_fake_u30air_through_tcp_entry_point(self):
        adapter = TOP / 'tests/fake_network_adb.py'
        for shell in self.each_shell():
            self.device(model='U30_Air', device='U30Air', product='U30Air')
            self.stub('adb', 'exec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(adapter)) + ' "$@"')
            r = self.run_script(shell, 'install.sh', '--adb-address', '192.168.0.1:5555', '--check',
                                MU300_NONINTERACTIVE=1, MU300_PROGRESS=1, MU300_ADB_TIMEOUT=2)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn('Connected to the specified rooted Android', r.stdout)
            self.assertIn('stable charger', r.stderr)
            saved = json.loads((self.tmp / 'work/wireless-install.json').read_text())
            self.assertEqual(saved['identity']['MODEL'], 'U30_Air')
            status = self.run_script(shell, 'install.sh', '--adb-status', MU300_NONINTERACTIVE=1,
                                     MU300_ADB_ADDRESS='192.168.99.1:5555', MU300_ADB_TIMEOUT=2)
            self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
            self.assertIn('Session phase: ready', status.stdout)
            self.assertIn('No detached device installation', status.stdout)
            calls = self.calls('network-call')
            self.assertTrue(calls)
            self.assertTrue(all(c['argv'][:2] in (['connect', '192.168.0.1:5555'], ['-s', '192.168.0.1:5555']) for c in calls))
            self.assertEqual(self.calls('reboot'), [])
            self.assertFalse(any('of=/dev/block' in c['cmd'] for c in self.calls('write')))


if __name__ == '__main__':
    unittest.main()
