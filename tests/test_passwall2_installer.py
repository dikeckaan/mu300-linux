"""Optional Passwall2 inputs: OS selection, offline integrity and packaged staging."""
import hashlib
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from helpers import TOP, ShellTest
import test_magisk_zip


class OfflineInput(ShellTest):
    def setUp(self):
        super().setUp()
        src = (TOP / 'install.sh').read_text()
        self.fn = re.search(r'\nfetch_passwall2\(\) \{\n.*?\n\}\n', src, re.S).group(0)
        self.extra = self.tmp / 'mu300/extras/mu300-extra-passwall2.tar.gz'
        self.extra.parent.mkdir(parents=True)
        self.extra.write_bytes(b'offline fixture')
        self.sums = self.extra.parent / 'SHA256SUMS'
        self.sums.write_text(hashlib.sha256(self.extra.read_bytes()).hexdigest() + '  ' + self.extra.name + '\n')
        self.computer = self.tmp / 'computer'
        self.computer.mkdir()

    def fetch(self, shell, **env):
        code = (f'set -eu; TOP="{self.computer}"; '
                'die() { echo "DIE $*"; exit 1; }; t() { echo "$*"; }; '
                'sha256_of() { sha256sum "$1" | cut -d" " -f1; };\n' + self.fn +
                '\nfetch_passwall2; printf "%s\\n" "$EXTRA_PASSWALL2"')
        return self.sh(shell, code, **env)

    def test_bundled_and_explicit_inputs_need_matching_sidecars(self):
        for shell in self.each_shell():
            for env in ({}, {'MU300_PASSWALL2_EXTRA': str(self.extra)}):
                r = self.fetch(shell, **env)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual(Path(r.stdout.strip()).resolve(), self.extra.resolve())
            self.sums.write_text('0' * 64 + '  ' + self.extra.name + '\n')
            self.assertNotEqual(self.fetch(shell).returncode, 0)
            self.sums.unlink()
            self.assertNotEqual(self.fetch(shell).returncode, 0)
            self.sums.write_text(hashlib.sha256(self.extra.read_bytes()).hexdigest() + '  ' + self.extra.name + '\n')

    def test_explicit_missing_file_does_not_fall_back_to_bundled_input(self):
        for shell in self.each_shell():
            r = self.fetch(shell, MU300_PASSWALL2_EXTRA=str(self.tmp / 'missing.tar.gz'))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('not found', r.stdout)

    def test_question_defaults_off_and_does_not_run_for_ubuntu(self):
        src = (TOP / 'install.sh').read_text()
        block = re.search(r'EXTRA_PASSWALL2=\npw=no\ncase .*?\nesac\n', src, re.S).group(0)
        for shell in self.each_shell():
            for oses, asked in [('ubuntu', False), ('openwrt', True), ('ubuntu openwrt-luci', True)]:
                code = ('t() { echo "$*"; }; ask() { printf "ASKED[%s:%s]\\n" "$3" "$4"; }; '
                        f'OSES="{oses}";\n' + block + '\necho "pw=$pw"')
                r = self.sh(shell, code)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual('ASKED[no:MU300_ANS_PASSWALL2]' in r.stdout, asked)
                self.assertIn('pw=no', r.stdout)


class PackagedExtra(unittest.TestCase):
    def test_one_payload_for_both_paths_only_in_openwrt_zips(self):
        b = test_magisk_zip.Builder('test_eleven_zips')
        b.setUp()
        self.addCleanup(b.doCleanups)
        extra = b.tmp / 'passwall2-full.tar.gz'
        extra.write_bytes(b'offline fixture')
        with patch.dict(os.environ, {'MU300_PASSWALL2_EXTRA': str(extra)}):
            result = b.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        name = 'mu300/extras/mu300-extra-passwall2.tar.gz'
        for zp in (b.tmp / 'out').glob('*.zip'):
            with zipfile.ZipFile(zp) as z:
                if '-openwrt' in zp.name:
                    self.assertEqual(z.namelist().count(name), 1)
                    self.assertEqual(z.read(name), extra.read_bytes())
                    sums = dict((n, h) for h, n in (line.split() for line in z.read('mu300/extras/SHA256SUMS').decode().splitlines()))
                    self.assertEqual(sums[Path(name).name], hashlib.sha256(z.read(name)).hexdigest())
                else:
                    self.assertNotIn(name, z.namelist())
