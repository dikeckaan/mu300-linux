"""The zip: customize.sh in a fake Magisk installer environment, tools/make-magisk-zips.sh and, on a release's real
zips (MU300_MAGISK_ZIPS), the allow-list, the manifest against the payload and a dry run of each zip's installer."""
import hashlib
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from fakedevice import FakeDevice
from helpers import TOP, ShellTest, shells
from test_android_boot_image import MAGISKBOOT, fake_android_root
from test_magisk_installer import MU300_FILES

MAGISK_ENV = r'''
ui_print() { echo "$1"; }
abort() { echo "ABORT $1"; rm -rf "$MODPATH"; exit 1; }
set_perm() { chmod "$4" "$1"; }
set_perm_recursive() { chmod -R u+rwX "$1"; }
BOOTMODE=true; MAGISK_VER_CODE=30700
'''

BUSYBOX = shutil.which('busybox')


@unittest.skipUnless(BUSYBOX, 'no busybox')
class Customize(ShellTest):
    def setUp(self):
        super().setUp()
        (self.tmp / 'magisk').mkdir()
        os.symlink(BUSYBOX, self.tmp / 'magisk' / 'busybox')

    def zip_with(self, install_sh, name='m.zip', body='#!/system/bin/sh\n'):
        z = self.tmp / name
        with zipfile.ZipFile(z, 'w') as f:
            f.writestr('mu300/install.sh', install_sh + '\n')
            f.writestr('module.prop', 'id=x\n')
            f.writestr('action.sh', body)
            f.writestr('switch.sh', body)
            f.writestr('system/bin/mu300-linux', body)
        return z

    def run_customize(self, shell, install_sh, bootmode='true'):
        z = self.zip_with(install_sh)
        mod = self.tmp / 'modpath'
        mod.mkdir(exist_ok=True)
        code = (MAGISK_ENV + f'BOOTMODE={bootmode}; ZIPFILE="{z}"; MODPATH="{mod}"; TMPDIR="{self.tmp}/t"; '
                f'MAGISKBIN="{self.tmp}/magisk"; mkdir -p "$TMPDIR"; set +e +u; '
                f'. "{TOP}/android/magisk/installer/customize.sh"; echo "after opts=$-"')
        return self.sh(shell, code), mod

    def test_success_installs_the_switch(self):
        for shell in self.each_shell():
            r, mod = self.run_customize(shell, 'echo installing; exit 0')
            self.assertIn('installing', r.stdout)
            self.assertTrue((mod / 'switch.sh').exists() and (mod / 'module.prop').exists())
            opts = r.stdout.split('after opts=')[1].split('\n')[0]   # dash prints it empty
            self.assertFalse(set('eu') & set(opts), opts)             # Magisk's options untouched

    def test_failure_and_dry_run_abort(self):
        for shell in self.each_shell():
            for rc, word in ((1, 'not installed'), (3, 'Dry run')):
                r, mod = self.run_customize(shell, f'exit {rc}')
                self.assertIn('ABORT', r.stdout)
                self.assertIn(word, r.stdout)
                self.assertFalse(mod.exists())

    def test_module_files_come_from_the_zip_as_it_was_checked(self):
        # magisk --install-module /sdcard/...: any app can replace the zip while the installation runs, and
        # system/* runs as root. The module's files are taken in the first unzip, with the installer.
        evil = self.zip_with('exit 0', name='evil.zip', body='#!/system/bin/sh\ntouch /pwned\n')
        for shell in self.each_shell():
            r, mod = self.run_customize(shell, f'cp "{evil}" "$ZIPFILE"; exit 0')
            self.assertNotIn('ABORT', r.stdout, r.stdout + r.stderr)
            for f in ('switch.sh', 'action.sh', 'system/bin/mu300-linux'):
                self.assertEqual((mod / f).read_text(), '#!/system/bin/sh\n', f)
            self.assertEqual(sorted(p.name for p in (self.tmp / 't').iterdir()), [])   # nothing left behind

    def test_recovery_is_refused(self):
        for shell in self.each_shell():
            r, _ = self.run_customize(shell, 'echo ran; exit 0', bootmode='false')
            self.assertIn('ABORT', r.stdout)
            self.assertNotIn('ran', r.stdout)


ALLOWED = {'META-INF/com/google/android/update-binary', 'META-INF/com/google/android/updater-script',
           'module.prop', 'customize.sh', 'action.sh', 'switch.sh', 'system/bin/mu300-linux'} | set(MU300_FILES)
ASSETS = ('mu300-kernel.tar.gz', 'mu300-kernel-6.18.tar.gz', 'mu300-kernel-7.2.tar.gz', 'mu300-openwrt-rootfs.tar.gz',
          'mu300-openwrt-luci-rootfs.tar.gz', 'mu300-ubuntu-rootfs.tar.gz', 'mu300-ubuntu-26.04-rootfs.tar.gz')


def tar_with(members):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for name, data in members.items():
            i = tarfile.TarInfo(name)
            i.size = len(data)
            t.addfile(i, io.BytesIO(data))
    return buf.getvalue()


def fake_release(rel):
    """REL laid out like a release's assets: tiny tarballs with the right names (the 5.4 one holds ./busybox)"""
    rel.mkdir(parents=True)
    sums = []
    for a in ASSETS:
        data = tar_with({'./busybox': b'#!busybox\n', './x': a.encode()} if a == 'mu300-kernel.tar.gz' else {'./x': a.encode()})
        (rel / a).write_bytes(data)
        sums.append(f'{hashlib.sha256(data).hexdigest()}  {a}\n')
    upd = b'#!/bin/sh\n'
    (rel / 'mu300-update').write_bytes(upd)
    sums.append(f'{hashlib.sha256(upd).hexdigest()}  mu300-update\n')
    (rel / 'SHA256SUMS').write_text(''.join(sums))


class Builder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mu300-zips-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.rel = self.tmp / 'v2026.10.06'
        fake_release(self.rel)

    def build(self, *extra, rel=None):
        return subprocess.run(['sh', str(TOP / 'tools/make-magisk-zips.sh'), str(rel or self.rel), str(self.tmp / 'out'),
                               *extra], capture_output=True, text=True)

    def test_eleven_zips(self):
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        names = sorted(p.name for p in (self.tmp / 'out').glob('*.zip'))
        self.assertEqual(len(names), 11)
        self.assertNotIn('mu300-magisk-v2026.10.06-ubuntu-26.04-k5.4.zip', names)
        self.assertIn('mu300-magisk-v2026.10.06-openwrt-k6.18.zip', names)
        # OpenWrt with the control panel, on every kernel
        for k in ('5.4', '6.18', '7.2'):
            self.assertIn(f'mu300-magisk-v2026.10.06-openwrt-luci-k{k}.zip', names)
        sums = (self.tmp / 'out/SHA256SUMS-magisk').read_text().split('\n')
        self.assertEqual(len([s for s in sums if s]), 11)
        for line in sums:
            if line:
                h, n = line.split('  ')
                self.assertEqual(h, hashlib.sha256((self.tmp / 'out' / n).read_bytes()).hexdigest())

    def test_layout_manifest_and_stored_payload(self):
        self.build()
        z = zipfile.ZipFile(self.tmp / 'out/mu300-magisk-v2026.10.06-ubuntu-24.04-k7.2.zip')
        names = set(z.namelist())
        self.assertEqual(names - ALLOWED, {'payload/mu300-kernel-7.2.tar.gz', 'payload/mu300-ubuntu-rootfs.tar.gz'})
        self.assertEqual(ALLOWED - names, set())
        for i in z.infolist():
            if i.filename.startswith('payload/'):
                self.assertEqual(i.compress_type, zipfile.ZIP_STORED)
        m = dict(l.split('=', 1) for l in z.read('mu300/manifest').decode().split('\n') if '=' in l)
        self.assertEqual((m['OS'], m['UBUNTU'], m['KERNEL']), ('ubuntu', '24.04', '7.2'))
        self.assertEqual(m['SHA256_ROOTFS'], hashlib.sha256(z.read('payload/mu300-ubuntu-rootfs.tar.gz')).hexdigest())
        self.assertEqual(m['SHA256_KERNEL'], hashlib.sha256(z.read('payload/mu300-kernel-7.2.tar.gz')).hexdigest())
        self.assertIn('versionCode=20261006', z.read('module.prop').decode())
        self.assertNotIn('@', z.read('module.prop').decode())
        self.assertEqual(z.read('mu300/busybox'), b'#!busybox\n')
        for entry, src in MU300_FILES.items():     # the helper that stages the installer for its tests agrees
            if src:
                self.assertEqual(z.read(entry), (TOP / src).read_bytes(), entry)

    def test_every_manifest_is_accepted_by_the_installer(self):
        self.build()
        for zp in sorted((self.tmp / 'out').glob('*.zip')):
            d = self.tmp / 'unz' / zp.stem
            with zipfile.ZipFile(zp) as z:
                z.extractall(d, [n for n in z.namelist() if n.startswith('mu300/')])
            for shell in shells():
                r = subprocess.run(shell + ['-c', f'MU300_LIB=1 MU300_DIR="{d}/mu300" . "{d}/mu300/install.sh"; '
                                          f'manifest_load "{d}/mu300/manifest" && echo "ok $TAG $SYSTEM $KERNEL"'],
                                   capture_output=True, text=True)
                self.assertIn('ok v2026.10.06', r.stdout, f'{zp.name} {shell}: {r.stdout}{r.stderr}')

    def test_checksum_mismatch_stops(self):
        with open(self.rel / 'mu300-openwrt-rootfs.tar.gz', 'ab') as f:
            f.write(b'x')
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('mu300-openwrt-rootfs.tar.gz', r.stderr)
        self.assertEqual(list((self.tmp / 'out').glob('*.zip')), [])

    def test_a_tag_the_installer_would_refuse_stops_before_anything_is_built(self):
        for tag in ('2026.10.06', 'v', 'vx1', 'v1..2', 'v1/2', 'v1;x', 'v1 2', 'v1&2'):
            r = self.build(tag)
            self.assertEqual(r.returncode, 1, tag)
            self.assertIn('v[0-9]', r.stderr, tag)
            self.assertEqual(list((self.tmp / 'out').glob('*')), [], tag)
        bad = self.tmp / 'release-2026'                  # the default tag is the directory's name
        shutil.copytree(self.rel, bad)
        self.assertEqual(self.build(rel=bad).returncode, 1)
        self.assertEqual(list((self.tmp / 'out').glob('*')), [])
        self.assertEqual(self.build('v2026.10.06-rc1').returncode, 0)

    def test_no_conf_in_a_zip(self):
        self.assertEqual(self.build().returncode, 0)
        for zp in (self.tmp / 'out').glob('*.zip'):
            self.assertFalse([n for n in zipfile.ZipFile(zp).namelist() if n.endswith('mu300-install.conf')])


class Workflow(unittest.TestCase):
    def test_package_lists_are_fresh_before_the_tools_are_installed(self):
        # a runner image's lists go stale; apt-get install then asks for package versions the mirror dropped
        steps = (TOP / '.github/workflows/magisk.yml').read_text()
        self.assertIn('sudo apt-get update -qq', steps)
        self.assertLess(steps.index('apt-get update'), steps.index('apt-get install'))


BUSYBOX_PATH = shutil.which('busybox')


@unittest.skipUnless(os.environ.get('MU300_MAGISK_ZIPS'), 'MU300_MAGISK_ZIPS not set (the Magisk workflow sets it)')
class ReleaseZips(ShellTest):
    """the real zips of a release: the allow-list, the manifest against the payload, and a dry run of each zip's own
    installer on the fake device that must print the plan and write nothing"""

    def zips(self):
        zs = sorted(Path(os.environ['MU300_MAGISK_ZIPS']).glob('*.zip'))
        self.assertEqual(len(zs), 11, zs)          # 3 OpenWrt, 3 OpenWrt with the panel, 3 + 2 Ubuntu
        return zs

    def test_allow_list_and_manifest(self):
        for zp in self.zips():
            with zipfile.ZipFile(zp) as z:
                names = set(z.namelist())
                m = dict(l.split('=', 1) for l in z.read('mu300/manifest').decode().split('\n') if '=' in l)
                payload = {f'payload/{m["KERNEL_ASSET"]}', f'payload/{m["ROOTFS_ASSET"]}'}
                self.assertEqual(names, ALLOWED | payload, zp.name)
                for n, key in ((m['KERNEL_ASSET'], 'SHA256_KERNEL'), (m['ROOTFS_ASSET'], 'SHA256_ROOTFS')):
                    h = hashlib.sha256()
                    with z.open(f'payload/{n}') as f:
                        for chunk in iter(lambda: f.read(1 << 20), b''):
                            h.update(chunk)
                    self.assertEqual(h.hexdigest(), m[key], f'{zp.name} {n}')
                self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist()
                                    if i.filename.startswith('payload/')), zp.name)

    @unittest.skipUnless(BUSYBOX_PATH, 'no busybox')
    def test_dry_run_prints_the_plan_and_writes_nothing(self):
        self.stub('magiskboot', MAGISKBOOT)
        for zp in self.zips():
            shutil.rmtree(self.tmp / 'fake', ignore_errors=True)
            unz = self.tmp / 'unz'
            shutil.rmtree(unz, ignore_errors=True)
            with zipfile.ZipFile(zp) as z:
                z.extractall(unz, [n for n in z.namelist() if n.startswith('mu300/')])
            fake = FakeDevice(self.tmp, self.stubs)
            fake_android_root(fake.root / 'android')
            (fake.root / 'magisk/busybox').symlink_to(BUSYBOX_PATH)
            (fake.root / 'sdcard/mu300-install.conf').write_text('MU300_DRY_RUN=1\n')
            env = fake.env(unz / 'mu300', self.stubs / 'magiskboot')
            env['ZIPFILE'] = str(zp)
            before = {n: hashlib.sha256((fake.root / 'dev/block/by-name' / n).read_bytes()).hexdigest()
                      for n in ('boot_a', 'boot_b', 'misc')}
            r = subprocess.run([BUSYBOX_PATH, 'sh', str(unz / 'mu300/install.sh')], capture_output=True, text=True,
                               env=self.env(**env), timeout=600)
            self.assertEqual(r.returncode, 3, f'{zp.name}\n{r.stdout}{r.stderr}')
            self.assertIn('Plan', r.stdout, zp.name)
            after = {n: hashlib.sha256((fake.root / 'dev/block/by-name' / n).read_bytes()).hexdigest() for n in before}
            self.assertEqual(before, after, zp.name)
            self.assertEqual(list((fake.root / 'data/adb').iterdir()), [], zp.name)


if __name__ == '__main__':
    unittest.main()
