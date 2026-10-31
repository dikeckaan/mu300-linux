"""Preserving-space preparation: strict profile, independent GPT plans, bounded writes and pinned TCP adb."""
import argparse
import binascii
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import fakegpt

TOP = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('preserve_space', TOP / 'tools/preserve-space.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def table():
    # Invented partitions/identities, not a device dump. Only the measured bounds and count are reproduced.
    step = (tool.FIRST - 2048) // 74
    parts = [('part' + str(i), 2048 + i * step, 2048 + (i + 1) * step - 1) for i in range(74)]
    parts.append(('userdata', tool.FIRST, tool.OLD_LAST))
    h, t = fakegpt.make(tool.DISK, tool.OLD_LAST, parts)
    h = bytearray(h)
    h[450], h[510:512] = 0xee, b'\x55\xaa'
    return bytes(h), t


def recalc(h, t):
    for buf, header, array in ((h, 512, 1024), (t, 32 * 512, 0)):
        struct.pack_into('<I', buf, header + 88, binascii.crc32(buf[array:array + 128 * 128]) & 0xffffffff)
        struct.pack_into('<I', buf, header + 16, 0)
        struct.pack_into('<I', buf, header + 16, binascii.crc32(buf[header:header + 92]) & 0xffffffff)


class FakeAdb:
    def __init__(self):
        self.commands = []
        self.remote_files = {}
        self.started = False
        self.info = {'CID': '1' * 32, 'FS_BLOCKS': tool.OLD_BLOCKS, 'DATA_SECTORS': tool.OLD_LAST - tool.FIRST + 1,
                     'GPT_LAST': tool.OLD_LAST, 'AVAILABLE_BLOCKS': 5700000, 'BATTERY': 96}

    def text(self, command, timeout=40):
        self.commands.append(command)
        if command.endswith(' inspect'):
            return '\n'.join(f'{k}={v}' for k, v in self.info.items()) + '\n'
        if command == 'cat /sys/class/block/mmcblk0/device/cid':
            return self.info['CID'] + '\n'
        if command.startswith('sha256sum '):
            path = shlex.split(command)[1]
            return tool.digest(self.remote_files[path]) + '  ' + path + '\n'
        if 'mkdir started' in command:
            if self.started:
                raise RuntimeError('already started')
            self.started = True
        return ''


class Host(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.adb = FakeAdb()
        h, t = table()
        nh, nt = tool.candidate(h, t)
        data = {'before.head': h, 'before.tail': t, 'candidate.head': nh, 'candidate.tail': nt, 'cid': b'1' * 32}
        data.update({n + '.raw': b'fake recovery' for n in tool.RECOVERY})
        for name, value in data.items():
            (self.state / name).write_bytes(value)
        self.remote = '/data/adb/mu300-preserve-' + 'a' * 32
        self.adb.remote_files = {self.remote + '/' + k: v for k, v in data.items()}
        self.adb.remote_files[self.remote + '/helper'] = b'fake helper'
        self.plan = {'version': 1, 'profile': 'u30air-m3-f2fs-4gib', 'remote': self.remote, 'facts': self.adb.info.copy(),
                     'sha256': {k: tool.digest(v) for k, v in data.items()}}
        self.plan['sha256']['helper-source'] = tool.digest(b'fake helper')
        self.save_plan()

    def save_plan(self):
        (self.state / 'plan.json').write_text(json.dumps(self.plan))

    def test_address_is_an_explicit_ipv4_endpoint(self):
        self.assertEqual(tool.address('192.168.0.1:5555'), '192.168.0.1:5555')
        for bad in ('192.168.0.1', 'router:5555', '1.2.3.4:0', '1.2.3.4:65536', '-s other', '1.2.3.4:５５５５'):
            with self.subTest(bad=bad), self.assertRaises(argparse.ArgumentTypeError):
                tool.address(bad)

    def test_connect_pins_every_root_command_even_with_other_adb_devices(self):
        adb = tool.Adb('test-adb', endpoint='192.168.0.1:5555')
        replies = [b'connected', b'device\n', b'0\n', b'MU5352\nMU5352\n']
        with patch.object(adb, 'call', side_effect=replies) as call:
            adb.connect()
        self.assertEqual(call.call_args_list[0].args, ('connect', '192.168.0.1:5555'))
        for c in call.call_args_list[1:]:
            self.assertEqual(c.args[:2], ('-s', '192.168.0.1:5555'))

    def test_u30air_uses_the_same_connection_path(self):
        for model in ('U30Air', 'U30_Air', 'U30 Air'):
            adb = tool.Adb('test-adb', endpoint='192.168.0.1:5555')
            with patch.object(adb, 'call', side_effect=[b'connected', b'device\n', b'0\n', (model + '\nU30Air\n').encode()]):
                adb.connect()

    def test_binary_pull_uses_a_device_file_and_never_su_stdout(self):
        adb = tool.Adb('test-adb', endpoint='192.168.0.1:5555')
        with patch.object(adb, 'call', return_value=b'') as call:
            adb.pull('cat /dev/block/by-name/boot_a', self.state / 'copy')
        calls = [c.args for c in call.call_args_list]
        self.assertTrue(any(c[2] == 'pull' for c in calls))
        root = next(c[-1] for c in calls if c[2] == 'exec-out')
        self.assertIn(' > /data/local/tmp/', root)
        self.assertTrue(all(c[:2] == ('-s', '192.168.0.1:5555') for c in calls))

    def test_adb_connect_zero_exit_does_not_establish_authorization(self):
        adb = tool.Adb('test-adb', endpoint='192.168.0.1:5555')
        with patch.object(adb, 'call', side_effect=[b'failed to connect', b'unauthorized\n']), self.assertRaises(RuntimeError):
            adb.connect()

    def test_no_apply_without_full_backup_acknowledgment(self):
        with self.assertRaises(RuntimeError):
            tool.apply(self.adb, self.state, False)
        self.assertEqual(self.adb.commands, [])

    def test_changed_or_missing_recovery_copy_prevents_launch(self):
        (self.state / 'metadata.raw').write_bytes(b'changed')
        with self.assertRaises(RuntimeError):
            tool.apply(self.adb, self.state, True)
        self.assertFalse(self.adb.started)

    def test_manifest_cannot_supply_paths_or_omit_required_backups(self):
        self.plan['sha256']['../outside'] = '0' * 64
        self.save_plan()
        with self.assertRaises(RuntimeError):
            tool.load(self.state)

    def test_wrong_device_or_changed_device_binary_prevents_launch(self):
        self.adb.info['CID'] = '2' * 32
        with self.assertRaises(RuntimeError):
            tool.apply(self.adb, self.state, True)
        self.adb.info['CID'] = '1' * 32
        self.adb.remote_files[self.remote + '/helper'] = b'changed'
        with self.assertRaises(RuntimeError):
            tool.apply(self.adb, self.state, True)
        self.assertFalse(self.adb.started)

    def test_launch_survives_disconnect_and_a_repeat_is_refused(self):
        with contextlib.redirect_stdout(io.StringIO()):
            tool.apply(self.adb, self.state, True)
        launch = self.adb.commands[-1]
        self.assertIn('mkdir started || exit', launch)
        self.assertIn("trap '' HUP", launch)
        self.assertIn('result.tmp', launch)
        self.assertNotIn('reboot', launch)
        with self.assertRaises(RuntimeError):
            tool.apply(self.adb, self.state, True)

    def test_status_reconnect_never_launches_or_formats(self):
        with contextlib.redirect_stdout(io.StringIO()):
            tool.status(self.adb, self.state)
        self.assertFalse(self.adb.started)
        command = self.adb.commands[-1]
        for bad in ('./helper apply', 'mkdir started', 'mkfs', 'reboot'):
            self.assertNotIn(bad, command)

    def test_verify_rejects_old_kernel_partition_size(self):
        self.adb.text = lambda cmd: ('\n'.join(f'{k}={v}' for k, v in self.adb.info.items()) + '\n'
                                     if cmd.endswith(' inspect') else '0\n' + tool.SUCCESS)
        with self.assertRaises(RuntimeError):
            tool.verify(self.adb, self.state)

    def test_status_after_address_change_still_requires_the_original_emmc(self):
        self.adb.info['CID'] = '3' * 32
        with self.assertRaises(RuntimeError):
            tool.status(self.adb, self.state)
        self.assertFalse(any('cat run.log' in command for command in self.adb.commands))

    def test_post_reboot_verification_and_a_changed_boot_image(self):
        self.adb.info.update(FS_BLOCKS=tool.NEW_BLOCKS, DATA_SECTORS=tool.NEW_LAST - tool.FIRST + 1, GPT_LAST=tool.NEW_LAST)
        original = self.adb.text
        changed_boot = False

        def replies(command, timeout=40):
            if 'cat result && cat run.log' in command:
                return '0\n' + tool.SUCCESS + '\n'
            if command.startswith('sha256sum /dev/block/by-name/'):
                name = command.rsplit('/', 1)[1]
                return ('0' * 64 if changed_boot else self.plan['sha256'][name + '.raw']) + '  partition\n'
            return original(command, timeout)

        self.adb.text = replies
        nh, nt = tool.candidate(*table())
        self.adb.read = lambda cmd: nh if 'count=34' in cmd else nt
        with contextlib.redirect_stdout(io.StringIO()):
            tool.verify(self.adb, self.state)
        changed_boot = True
        with self.assertRaises(RuntimeError):
            tool.verify(self.adb, self.state)

    @unittest.skipUnless(os.name == 'posix', 'real POSIX shell')
    def test_detached_worker_finishes_after_launch_shell_has_exited(self):
        helper = self.state / 'helper'
        helper.write_text('#!/bin/sh\nsleep 0.2\necho worker-finished\n')
        helper.chmod(0o700)
        self.adb.remote_files[self.remote + '/helper'] = helper.read_bytes()
        self.plan['sha256']['helper-source'] = tool.digest(helper.read_bytes())
        self.save_plan()
        original = self.adb.text

        def remote_shell(command, timeout=40):
            if command.startswith('cd '):
                r = subprocess.run(['sh', '-c', command.replace(self.remote, str(self.state))],
                                   capture_output=True, text=True, timeout=2)
                if r.returncode:
                    raise RuntimeError(r.stderr)
                return r.stdout
            return original(command, timeout)

        self.adb.text = remote_shell
        with contextlib.redirect_stdout(io.StringIO()):
            tool.apply(self.adb, self.state, True)
        deadline = time.monotonic() + 3
        while not (self.state / 'result').exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual((self.state / 'result').read_text(), '0\n')
        self.assertIn('worker-finished', (self.state / 'run.log').read_text())
        with self.assertRaises(RuntimeError):
            tool.apply(self.adb, self.state, True)

    def test_plan_and_manifest_roundtrip_and_bad_backup_stops_before_apply(self):
        helper = self.state / 'helper-file'
        helper.write_bytes(b'\x7fELFtest-helper')
        self.adb.push_private = lambda source, target: self.adb.remote_files.update({target: Path(source).read_bytes()})
        self.adb.read = lambda cmd: table()[0 if 'count=34' in cmd else 1]
        payload = bytes(range(256)) * 16
        self.adb.pull = lambda cmd, path: path.write_bytes(payload)
        original = self.adb.text
        bad_hash = False

        def responses(command, timeout=40):
            if command.startswith('blockdev '):
                return '4096\n'
            if command.startswith('sha256sum /dev/block/by-name/'):
                return ('0' * 64 if bad_hash else tool.digest(payload)) + '  partition\n'
            return original(command, timeout)

        self.adb.text = responses
        good = self.state / 'good-plan'
        with contextlib.redirect_stdout(io.StringIO()):
            tool.plan(self.adb, good, helper)
        self.assertEqual(tool.load(good)['profile'], 'u30air-m3-f2fs-4gib')
        self.assertFalse(any('./helper apply' in cmd for cmd in self.adb.commands))
        bad_hash = True
        bad = self.state / 'bad-plan'
        with self.assertRaises(RuntimeError):
            tool.plan(self.adb, bad, helper)
        self.assertFalse((bad / 'plan.json').exists())


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.build.cleanup)
        cls.binary = os.environ.get('MU300_PRESERVE_TEST_BINARY')
        if not cls.binary:
            compiler = shutil.which('cc') or shutil.which('gcc')
            if not sys.platform.startswith('linux') or not compiler:
                raise unittest.SkipTest('Linux native C compiler (or MU300_PRESERVE_TEST_BINARY) required')
            cls.binary = str(Path(cls.build.name) / 'native')
            subprocess.run([compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(TOP / 'tests/preserve_space_native.c'), '-o', cls.binary], check=True, capture_output=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.h, self.t = table()
        (self.tmp / 'head').write_bytes(self.h)
        (self.tmp / 'tail').write_bytes(self.t)

    def run_native(self, action='plan', output='candidate'):
        return subprocess.run([self.binary, action, str(self.tmp / 'head'), str(self.tmp / 'tail'), str(self.tmp / output)],
                              capture_output=True, text=True)

    def test_independent_host_and_native_plans_and_only_allowed_bytes_change(self):
        r = self.run_native()
        self.assertEqual(r.returncode, 0, r.stderr)
        nh, nt = tool.candidate(self.h, self.t)
        self.assertEqual((self.tmp / 'candidate').read_bytes(), nh + nt)
        for before, after, hdr, array in ((self.h, nh, 512, 1024), (self.t, nt, 32 * 512, 0)):
            allowed = set(range(hdr + 16, hdr + 20)) | set(range(hdr + 88, hdr + 92)) | set(range(array + 74 * 128 + 40, array + 74 * 128 + 48))
            changed = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
            self.assertTrue(changed)
            self.assertLessEqual(changed, allowed)
        start = ((tool.NEW_LAST + 1) // 4096 + 1) * 4096
        end = ((tool.DISK - 34) // 4096 - 1) * 4096
        self.assertEqual((end - start) * 512, 4 * 1024**3)

    def test_bad_crc_mismatched_copies_overlap_and_other_layout_refused(self):
        mutations = ('crc', 'guid', 'overlap', 'other-end', 'extra-partition', 'name', 'mbr')
        for what in mutations:
            with self.subTest(what=what):
                h, t = bytearray(self.h), bytearray(self.t)
                if what == 'crc':
                    h[1100] ^= 1
                elif what == 'guid':
                    t[32 * 512 + 56] ^= 1
                    recalc(h, t)
                elif what in ('overlap', 'other-end', 'extra-partition', 'name'):
                    offset = {'overlap': 128 + 32, 'other-end': 74 * 128 + 40,
                              'extra-partition': 75 * 128, 'name': 74 * 128 + 56}[what]
                    h[1024 + offset] ^= 1
                    t[offset] ^= 1
                    if what == 'overlap':
                        struct.pack_into('<Q', h, 1024 + offset, 2048)
                        struct.pack_into('<Q', t, offset, 2048)
                    recalc(h, t)
                else:
                    h[450] = 0
                (self.tmp / 'head').write_bytes(h)
                (self.tmp / 'tail').write_bytes(t)
                r = self.run_native()
                self.assertNotEqual(r.returncode, 0)
                self.assertFalse((self.tmp / 'candidate').exists())

    def test_commit_preserves_mbr_and_everything_between_gpt_copies(self):
        disk = self.tmp / 'disk'
        with disk.open('wb') as f:
            f.truncate(tool.DISK * 512)
            f.seek(0); f.write(self.h)
            f.seek((tool.DISK - 33) * 512); f.write(self.t)
            f.seek(100 * 512); f.write(b'protected partition data')
        r = self.run_native('commit', 'disk')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(tool.SUCCESS, r.stdout)
        nh, nt = tool.candidate(self.h, self.t)
        with disk.open('rb') as f:
            self.assertEqual(f.read(len(nh)), nh)
            f.seek((tool.DISK - 33) * 512); self.assertEqual(f.read(len(nt)), nt)
            f.seek(100 * 512); self.assertEqual(f.read(24), b'protected partition data')
        # A second invocation sees a changed GPT and refuses to overwrite either copy.
        self.assertNotEqual(self.run_native('commit', 'disk').returncode, 0)

    def test_old_and_new_f2fs_geometry_and_mismatched_superblocks(self):
        for blocks, sections in ((tool.OLD_BLOCKS, 11831), (tool.NEW_BLOCKS, 9781)):
            sb = bytearray(108)
            for off, value in ((0, 0xf2f52010), (16, 12), (20, 9), (24, 1), (28, 1),
                               (44, sections), (48, sections + 82), (68, sections), (92, 42496)):
                struct.pack_into('<I', sb, off, value)
            struct.pack_into('<Q', sb, 36, blocks)
            path = self.tmp / 'fs'
            with path.open('wb') as f:
                f.seek(1024); f.write(sb); f.seek(5120); f.write(sb)
            r = subprocess.run([self.binary, 'geometry', str(path)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(int(r.stdout), blocks)
            with path.open('r+b') as f:
                f.seek(5120 + 36); f.write(b'\0' * 8)
            self.assertNotEqual(subprocess.run([self.binary, 'geometry', str(path)], capture_output=True).returncode, 0)

    def test_partial_gpt_commit_is_refused_before_further_writes(self):
        nh, nt = tool.candidate(self.h, self.t)
        disk = self.tmp / 'disk'
        with disk.open('wb') as f:
            f.truncate(tool.DISK * 512)
            f.write(self.h)
            f.seek((tool.DISK - 33) * 512); f.write(nt)
        self.assertNotEqual(self.run_native('commit', 'disk').returncode, 0)
        with disk.open('rb') as f:
            self.assertEqual(f.read(len(self.h)), self.h)
            f.seek((tool.DISK - 33) * 512); self.assertEqual(f.read(len(nt)), nt)

    def test_shared_u30air_m3_profile_excludes_other_models_and_platforms(self):
        cases = [('MU5352', 'MU5352', 'ums9620', True), ('U30_Air', 'U30Air', 'ums9620', True),
                 ('U30Air', 'U30Air', 'ums9620', True), ('U30 Air', 'U30Air', 'ums9620', True),
                 ('F50', 'MU300', 'ums9620', False), ('V50', 'MU3351', 'ums9620', False),
                 ('M3Pro', 'MU5352', 'ums9620', False), ('MU5352', 'MU5352', 'ums9632', False)]
        for model, device, platform, accepted in cases:
            r = subprocess.run([self.binary, 'profile', model, device, platform, '5.4.254-android12-9-gtest'], capture_output=True)
            self.assertEqual(r.returncode == 0, accepted, (model, device, platform, r.stderr))


if __name__ == '__main__':
    unittest.main()
