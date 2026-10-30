"""The online way of making room (Android keeps its data; dikeckaan's method, kanoqwq's implementation): the helper
mu300-f2fs-online in git is the build of its source (tools/f2fs-online/build.sh, SHA256SUMS), a static arm64 program;
resume.py's target and state rules; and, with docker (MU300_E2E_DOCKER=1, or CI's arm64 job), the helper and
tools/android-online-shrink.sh for real on an F2FS in a loop disk (tests/online-shrink-e2e.sh). The installers' use
of them is tests/test_resume.py OnlineShrink."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

sys.path.insert(0, str(TOP / 'tools'))
import resume  # noqa: E402

HERE = TOP / 'tools/f2fs-online'


class Helper(unittest.TestCase):
    def test_the_binary_is_the_build_of_the_source(self):
        sums = dict(reversed(l.split('  ', 1)) for l in (HERE / 'SHA256SUMS').read_text().splitlines())
        for name in ('mu300-f2fs-online.c', 'mu300-f2fs-online'):
            self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), sums[name],
                             name + ' changed: run tools/f2fs-online/build.sh (it writes SHA256SUMS)')

    def test_a_static_arm64_program(self):
        raw = (HERE / 'mu300-f2fs-online').read_bytes()
        self.assertEqual(raw[:6], b'\x7fELF\x02\x01')               # ELF, 64-bit, little endian
        self.assertEqual(raw[16:20], bytes.fromhex('0200b700'))      # an executable for aarch64
        self.assertNotIn(b'/lib/ld-', raw[:4096])                    # no interpreter: static
        self.assertTrue(os.access(HERE / 'mu300-f2fs-online', os.X_OK))
        self.assertLess(len(raw), 256 << 10)

    def test_it_works_only_from_its_own_directory_in_dev(self):
        src = (HERE / 'mu300-f2fs-online.c').read_text()
        self.assertIn('strncmp(argv[10], "/dev/mu300-online-", 18)', src)
        self.assertIn('/dev/mu300-f2fs-online.lock', src)
        sh = (TOP / 'tools/android-online-shrink.sh').read_text()
        self.assertIn('/dev/mu300-online-$1', sh)

    def test_credited(self):
        for name in ('tools/f2fs-online/mu300-f2fs-online.c', 'tools/android-online-shrink.sh', 'tools/resume.sh',
                     'tools/resume.py', 'install.ps1'):
            text = (TOP / name).read_text()
            self.assertIn('kanoqwq', text, name)
            self.assertIn('dikeckaan', text, name)


class Rules(unittest.TestCase):
    def test_the_target(self):
        # whole sections, smaller than now, 2 GiB above what is used (kano's allocation)
        t = resume.online_target(new_size=20 << 21, section_blocks=512, used_bytes=5 << 30, blocks=30 << 18)
        self.assertEqual(t % 512, 0)
        self.assertLessEqual(t * 8, 20 << 21)
        self.assertEqual(resume.online_target(10000000, 512, 1 << 30, 2000000), 1249792)
        for args in ((10000000, 512, 3 << 30, 2000000),       # used + 2 GiB does not fit in 4.77 GiB
                     (20000000, 512, 0, 2000000),             # not smaller
                     (10000000, 0, 0, 2000000)):              # no geometry
            with self.assertRaises(ValueError, msg=args):
                resume.online_target(*args)

    def test_the_state_of_an_interrupted_shrink(self):
        d = Path(tempfile.mkdtemp(prefix='mu300-online-'))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        for name, data in (('gpt.head', b'old head'), ('gpt.tail', b'old tail'), ('gpt-new.head', b'new head'),
                           ('gpt-new.tail', b'new tail')):
            (d / name).write_bytes(data)
        r = {'backup': str(d), 'fs_uuid': 'u' * 32, 'fs_blocks': 1000, 'fs_target': 500}

        def state(head, tail, blocks, uuid='u' * 32):
            (d / 'h').write_bytes(head); (d / 't').write_bytes(tail)
            return resume.online_state(r, d / 'h', d / 't', blocks, uuid)
        self.assertEqual(state(b'old head', b'old tail', 1000), 'unchanged')
        self.assertEqual(state(b'old head', b'old tail', 500), 'shrunk')
        self.assertEqual(state(b'new head', b'new tail', 500), 'committed')
        # what the worker never leaves: a new table over the old size, one copy of each, another filesystem
        self.assertEqual(state(b'new head', b'new tail', 1000), 'unknown')
        self.assertEqual(state(b'new head', b'old tail', 500), 'unknown')
        self.assertEqual(state(b'old head', b'old tail', 700), 'unknown')
        self.assertEqual(state(b'old head', b'old tail', 1000, 'v' * 32), 'unknown')

    def test_check_takes_the_filesystem_of_the_online_way(self):
        rec = {'format': 1, 'state': 'prepared', 'serial': 'S', 'slot': 'a', 'cid': 'c' * 32, 'node': 'mmcblk0p18',
               'start': 2000000, 'size': 120155008, 'disk': 122159104, 'target': 100000000, 'need': 20152320,
               'usable_end': 122155007, 'region_start': 102002688, 'region_end': 122155008, 'token': 'b' * 32,
               'identity': 'i' * 64, 'method': 'online', 'fs_uuid': 'u' * 32, 'fs_blocks': 15000000, 'fs_target': 12499968}
        d = Path(tempfile.mkdtemp(prefix='mu300-online-'))
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        (d / 'marker').write_bytes(resume.marker('b' * 32))
        f = {'serial': 'S', 'slot': 'a', 'cid': 'c' * 32, 'node': 'mmcblk0p18', 'start': 2000000, 'size': 100000000,
             'disk': 122159104, 'gpt_first': 2000000, 'gpt_end': 101999999, 'usable_end': 122155007,
             'region_start': 102002688, 'region_end': 122155008, 'marker': str(d / 'marker'), 'identity': 'i' * 64,
             'fs_blocks': 12499968, 'fs_uuid': 'u' * 32}
        resume.check(rec, f)
        for change, word in ((dict(size=120155008), 'has not restarted'), (dict(fs_blocks=15000000), 'not at the size'),
                             (dict(fs_uuid='v' * 32), 'not the filesystem')):
            with self.assertRaises(ValueError) as e:
                resume.check(rec, dict(f, **change))
            self.assertIn(word, str(e.exception))


@unittest.skipUnless(os.environ.get('MU300_E2E_DOCKER') == '1' and shutil.which('docker'),
                     'MU300_E2E_DOCKER=1 and docker: the real helper on a real F2FS (minutes)')
class ForReal(unittest.TestCase):
    def test_on_a_loop_disk(self):
        for mapping in ('dm', 'direct'):
            r = subprocess.run(['docker', 'run', '--rm', '--privileged', '--platform', 'linux/arm64', '-v', '%s:/src:ro' % TOP,
                                'alpine:3.20', 'sh', '-c', 'apk add -q f2fs-tools sgdisk device-mapper python3 util-linux >/dev/null && '
                                'sh /src/tests/online-shrink-e2e.sh ' + mapping], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr[-2000:])
            self.assertIn('PASS (%s)' % mapping, r.stdout)


if __name__ == '__main__':
    unittest.main()
