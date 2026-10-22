"""Shared helpers for the tests: the shells the scripts run under, stub commands, a scratch directory.

The device scripts run under dash (Ubuntu's /bin/sh), bash and busybox ash (OpenWrt); every shell test runs under
each of them that this machine has (MU300_TEST_SHELLS="dash,busybox sh" picks others). Commands a script calls that
touch the device (nft, ip, id, ...) are replaced by stubs in a directory put first on PATH.
"""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]
BIN = TOP / 'rootfs' / 'overlay' / 'opt' / 'mu300' / 'bin'
# the tests that read what git tracks (file modes, ls-files) skip where there is no git or no checkout of this tree,
# e.g. a container with the worktree mounted but not the repository it belongs to
GIT_CHECKOUT = bool(shutil.which('git')) and subprocess.run(['git', '-C', str(TOP), 'rev-parse', '--git-dir'],
                                                           capture_output=True).returncode == 0


# The panel's ucode programs (unisoc-modem/dashboard-info and cell, FINDINGS 206) run under a ucode interpreter:
# MU300_TEST_UCODE (a command line, e.g. a wrapper that sets LD_LIBRARY_PATH for a local build), else `ucode` on PATH.
# The modules they load from the device's own ucode packages (ubus, uci, nl80211, rtnl) are stood in for by
# tests/ucode-stubs, which run the same stubbed commands (ubus, uci, iw, ip) the shell versions ran; mu300.dash comes
# from the tree. A test of such a program is skipped where there is no ucode.
UCODE_STUBS = TOP / 'tests' / 'ucode-stubs'
UCODE_MODULES = TOP / 'openwrt' / 'luci-app-mu300' / 'root' / 'usr' / 'share' / 'ucode'
# the modules of the base system (mu300.cellparse: the modem daemon's and the panel's collector's parsers)
UCODE_BASE_MODULES = TOP / 'rootfs' / 'overlay' / 'usr' / 'share' / 'ucode'


def ucode_paths():
    """The -L arguments: the stand-ins first, then the tree's modules."""
    return ['-L', f'{UCODE_STUBS}/*.uc', '-L', f'{UCODE_MODULES}/*.uc', '-L', f'{UCODE_BASE_MODULES}/*.uc']


def ucode():
    """[argv] of a ucode interpreter, or None."""
    cmd = os.environ.get('MU300_TEST_UCODE', '').split() or ([shutil.which('ucode')] if shutil.which('ucode') else [])
    if not cmd:
        return None
    try:
        ok = subprocess.run(cmd + ['-e', 'print(1)'], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        ok = False
    return cmd if ok else None


def is_ucode(path):
    try:
        with open(path, 'rb') as f:
            return f.readline().startswith(b'#!/usr/bin/ucode')
    except OSError:
        return False


def ucode_argv(path):
    """The command line that runs the ucode program at PATH with the stand-in modules, or None without ucode."""
    u = ucode()
    if not u:
        return None
    return u + ucode_paths() + [str(path)]


def _works(argv):
    try:
        return subprocess.run(argv + ['-c', 'true'], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def shells():
    """[argv, ...] of the POSIX shells available here, e.g. [['dash'], ['bash'], ['busybox', 'sh']]."""
    names = os.environ.get('MU300_TEST_SHELLS', 'dash,bash,busybox sh,sh').split(',')
    found, seen = [], set()
    for n in names:
        argv = n.split()
        path = shutil.which(argv[0])
        if not path or not _works(argv):
            continue
        key = (os.path.realpath(path),) + tuple(argv[1:])
        if key not in seen:
            seen.add(key)
            # by its full path: a test that stubs a command of the same name (busybox) must not replace the shell
            found.append([path] + argv[1:])
    return found


class ShellTest(unittest.TestCase):
    """A scratch directory (self.tmp) with a stub directory first on PATH (self.stub)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mu300-test-'))
        self.stubs = self.tmp / 'stubs'
        self.stubs.mkdir()
        self.shells = shells()
        if not self.shells:
            self.skipTest('no POSIX shell')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, name, body):
        """A command NAME that runs BODY (sh); $STUBLOG is the scratch directory, for recording calls."""
        p = self.stubs / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)

    def env(self, **extra):
        e = dict(os.environ)
        e['PATH'] = f'{self.stubs}{os.pathsep}{e.get("PATH", "")}'
        e['STUBLOG'] = str(self.tmp)
        e['LC_ALL'] = 'C.UTF-8' if os.name != 'nt' else e.get('LC_ALL', '')
        e.update({k: str(v) for k, v in extra.items()})
        return e

    def sh(self, shell, code, stdin=None, **env):
        """Run CODE with SHELL; returns the CompletedProcess (text)."""
        return subprocess.run(shell + ['-c', code], input=stdin, capture_output=True, text=True,
                              env=self.env(**env), timeout=60)

    def script(self, shell, path, *args, stdin=None, **env):
        """Run the script at PATH with SHELL (not its #! line: the point is to try every shell). A ucode program
        (#!/usr/bin/ucode) runs under ucode instead, with the stand-in modules; skipped where there is none."""
        argv = shell + [str(path)]
        if is_ucode(path):
            argv = ucode_argv(path)
            if argv is None:
                self.skipTest('no ucode interpreter (MU300_TEST_UCODE)')
        return subprocess.run(argv + [str(a) for a in args], input=stdin, capture_output=True,
                              text=True, env=self.env(**env), timeout=60)

    def each_shell(self):
        for s in self.shells:
            with self.subTest(shell=' '.join(s)):
                yield s
