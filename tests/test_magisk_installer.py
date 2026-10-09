"""android/magisk/installer/mu300-install.sh: the installer a Magisk zip runs on the device. mu300-install.conf is
read, never run; on a fake device (tests/fakedevice.py) it finds the model, the slots, where Linux goes and what is
already there, and a refusal or a dry run writes nothing; an installation writes boot_<linux slot>, verifies it
and arms misc last."""
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from fakedevice import UBB, FakeDevice
from helpers import TOP, ShellTest
from test_android_boot_image import MAGISKBOOT, cpio_all, fake_android_root, ramdisk_of
from test_boot_image import HAVE_LZ4, unlz4_legacy

# the zip's mu300/ directory, entry -> source in this repository (None: made per zip). Task 10's zip builder copies
# exactly these; its test compares the two lists.
MU300_FILES = {
    'mu300/install.sh': 'android/magisk/installer/mu300-install.sh',
    'mu300/android-boot-image.sh': 'tools/android-boot-image.sh',
    'mu300/mu300-update': 'rootfs/overlay/opt/mu300/bin/mu300-update',
    'mu300/android-install.sh': 'tools/android-install.sh',
    'mu300/android-mount-mu300root.sh': 'tools/android-mount-mu300root.sh',
    'mu300/storage.sh': 'tools/storage.sh',
    'mu300/i18n.sh': 'tools/i18n.sh',
    'mu300/i18n/tr.tsv': 'i18n/tr.tsv',
    'mu300/i18n/zh.tsv': 'i18n/zh.tsv',
    'mu300/subset-files.txt': 'android-vendor/subset-files.txt',
    'mu300/gpu-files.txt': 'android-vendor/gpu-files.txt',
    'mu300/busybox': None,      # the 5.4 bundle's static busybox; here the fake device's mkpasswd
    'mu300/manifest': None,     # what the zip carries, written by InstallerCase.zip()
}

BUSYBOX = shutil.which('busybox')
INSTALLER_DIR = INSTALLER = None
_staged = None


def stage_mu300(dest):
    """DEST laid out like the zip's mu300/ (without its manifest)"""
    for entry, src in MU300_FILES.items():
        out = dest / entry[len('mu300/'):]
        out.parent.mkdir(parents=True, exist_ok=True)
        if src:
            shutil.copy(TOP / src, out)
    (dest / 'busybox').write_text(UBB)
    (dest / 'busybox').chmod(0o755)


def setUpModule():
    global INSTALLER_DIR, INSTALLER, _staged
    _staged = tempfile.mkdtemp(prefix='mu300-magisk-stage-')
    INSTALLER_DIR = Path(_staged) / 'mu300'
    stage_mu300(INSTALLER_DIR)
    INSTALLER = INSTALLER_DIR / 'install.sh'


def tearDownModule():
    shutil.rmtree(_staged, ignore_errors=True)


def busybox_has(applet):
    if not BUSYBOX:
        return False
    r = subprocess.run([BUSYBOX, '--list'], capture_output=True, text=True)
    return applet in r.stdout.split()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_ext4_bytes(label):
    """the start of an ext4 filesystem as sd_existing reads it: the magic and the label"""
    data = bytearray(4096)
    data[1080:1082] = b'\x53\xef'
    data[1144:1144 + len(label)] = label.encode()
    return bytes(data)


def tar_gz(files):
    """{name: bytes} -> a .tar.gz as the release makes them (./ names)"""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for name, data in files.items():
            info = tarfile.TarInfo('./' + name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


_generic = {}


def generic_ramdisk():
    """the bundle's ramdisk-generic.lz4, built once from fake modules with build-boot-image.py --generic-ramdisk"""
    if 'data' not in _generic:
        tmp = tempfile.mkdtemp(prefix='mu300-generic-')
        try:
            t = Path(tmp)
            (t / 'mods').mkdir()
            for n in (TOP / 'boot' / 'module-order.txt').read_text().split():
                (t / 'mods' / n).write_bytes(b'\x7fELF base ' + n.encode())
            for f in ('busybox', 'logdw'):
                (t / f).write_bytes(b'\x7fELF ' + f.encode())
            r = subprocess.run([sys.executable, str(TOP / 'boot' / 'build-boot-image.py'), '--generic-ramdisk',
                                '--modules', str(t / 'mods'), '--busybox', str(t / 'busybox'),
                                '--logdw', str(t / 'logdw'),
                                '--ueventd-perms', str(TOP / 'android-vendor' / 'ueventd-perms.sh'),
                                '--out', str(t / 'ramdisk-generic.lz4')], capture_output=True, text=True)
            assert r.returncode == 0, r.stderr
            _generic['data'] = (t / 'ramdisk-generic.lz4').read_bytes()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return _generic['data']


ROOTFS_ASSET = {'openwrt': 'mu300-openwrt-rootfs.tar.gz', 'ubuntu-24.04': 'mu300-ubuntu-rootfs.tar.gz',
                'ubuntu-26.04': 'mu300-ubuntu-26.04-rootfs.tar.gz'}


class Conf(ShellTest):
    def lib(self, shell, code, **env):
        return self.sh(shell, f'MU300_LIB=1 MU300_DIR="{INSTALLER_DIR}" . "{INSTALLER}"; ' + code, **env)

    def load(self, shell, text, trust=''):
        f = self.tmp / 'mu300-install.conf'
        f.write_bytes(text.encode())
        # the installer sets -u: a key the file does not give stays unset
        return self.lib(shell, f'conf_load "{f}" {trust}; echo "S=${{MU300_STORAGE:-}} E=${{MU300_SD_ERASE:-}} '
                               'B=${MU300_BOOT:-} P=${MU300_PASSWORD:-} M=${MU300_MODE:-} D=${MU300_DEVICE:-}"')

    def test_values_quotes_crlf_comments(self):
        for shell in self.each_shell():
            r = self.load(shell, '# a comment\r\nMU300_STORAGE=sd\r\nMU300_SD_ERASE="yes"\n  MU300_BOOT = android\n'
                                 "MU300_PASSWORD='p a$s 1'\n", 'trusted')
            self.assertIn("S=sd E=yes B=android P=p a$s 1", r.stdout)

    def test_unknown_keys_are_reported_not_set(self):
        for shell in self.each_shell():
            r = self.load(shell, 'PATH=/nowhere\nMU300_STORAGE=internal\n')
            self.assertIn('S=internal', r.stdout)
            self.assertIn('PATH', r.stdout + r.stderr)   # reported
            self.assertNotEqual(r.returncode, 127)       # PATH was not replaced

    def test_conf_is_never_executed(self):
        for shell in self.each_shell():
            r = self.load(shell, f'MU300_BOOT=$(touch {self.tmp}/ran)\nMU300_STORAGE=`touch {self.tmp}/ran2`\n')
            self.assertFalse((self.tmp / 'ran').exists())
            self.assertFalse((self.tmp / 'ran2').exists())

    def test_check_refuses_bad_values(self):
        for shell in self.each_shell():
            for bad in ('MU300_STORAGE=usb', 'MU300_BOOT_ATTEMPTS=9', 'MU300_PASSWORD=short', 'MU300_MODE=maybe',
                        'MU300_PASSWORD_FILE=/etc/shadow'):
                f = self.tmp / 'c.conf'; f.write_text(bad + '\n')
                r = self.lib(shell, f'conf_load "{f}" trusted; conf_check')
                self.assertNotEqual(r.returncode, 0, bad)

    def test_values_are_checked_before_they_are_assigned(self):
        # MU300_LANG is part of t()'s file name: a later message must not be read from a file it points at
        evil = self.tmp / 'evil.tsv'
        evil.write_text('mu300-install.conf: {1} is not a setting of this installer; ignored\tPWNED\n')
        up = '../' * 12
        for shell in self.each_shell():
            for line in (f'MU300_LANG={up}{self.tmp}/evil', 'MU300_BOOT_OS=-rf', 'MU300_STORAGE=../sd',
                         'MU300_LANG=tr x'):
                r = self.load(shell, line + '\nBOGUS=1\n')
                self.assertNotEqual(r.returncode, 0, line)
                self.assertIn('is not valid', r.stdout, line)
                self.assertNotIn('PWNED', r.stdout + r.stderr, line)
            # from the environment too
            r = self.lib(shell, 'conf_check', MU300_BOOT_OS='../x')
            self.assertNotEqual(r.returncode, 0)

    def test_untrusted_file_chooses_nothing_destructive(self):
        # any app with storage access can write /sdcard: it may not erase, wipe, set the password or the model
        text = ('MU300_STORAGE=sd\nMU300_SD_ERASE=yes\nMU300_PASSWORD=hunter22\nMU300_MODE=wipe\nMU300_DEVICE=f50\n'
                'MU300_REGION_OVERWRITE=yes\nMU300_PASSWORD_FILE=sdcard\nMU300_PASSWORD_RESET=yes\n')
        for shell in self.each_shell():
            r = self.load(shell, text)
            self.assertIn('S=sd E= B= P= M= D=', r.stdout)
            for k in ('MU300_SD_ERASE', 'MU300_PASSWORD', 'MU300_MODE=wipe', 'MU300_DEVICE', 'MU300_REGION_OVERWRITE',
                      'MU300_PASSWORD_RESET'):
                self.assertIn(k, r.stdout)
            self.assertNotIn('hunter22', r.stdout)                       # a password's value is never shown
            self.assertIn("su -c 'cp ", r.stdout)                        # the way to make it trusted
            r = self.load(shell, 'MU300_MODE=update\n')
            self.assertIn('M=update', r.stdout)

    def test_which_file_is_trusted(self):
        f = self.tmp / 'adb.conf'
        f.write_text('x\n')
        uid = os.getuid()
        for shell in self.each_shell():
            for mode, owner, want in ((0o600, uid, 0), (0o644, uid, 0), (0o664, uid, 1), (0o646, uid, 1),
                                      (0o600, uid + 1, 1)):
                f.chmod(mode)
                r = self.lib(shell, f'conf_trusted "{f}"', MU300_TRUSTED_UID=owner)
                self.assertEqual(r.returncode, want, (oct(mode), owner))
            f.chmod(0o600)
            link = self.tmp / 'link.conf'
            link.unlink(missing_ok=True); link.symlink_to(f)
            self.assertNotEqual(self.lib(shell, f'conf_trusted "{link}"', MU300_TRUSTED_UID=uid).returncode, 0)

    def test_trusted_values_win(self):
        sd, adb = self.tmp / 'sdcard', self.tmp / 'adb'
        sd.mkdir(); adb.mkdir()
        (sd / 'mu300-install.conf').write_text('MU300_STORAGE=internal\nMU300_BOOT=android\n')
        (adb / 'mu300-install.conf').write_text('MU300_STORAGE=sd\nMU300_SD_ERASE=yes\n')
        (adb / 'mu300-install.conf').chmod(0o600)
        for shell in self.each_shell():
            for uid, want in ((os.getuid(), 'S=sd E=yes B=android'), (os.getuid() + 1, 'S=sd E= B=android')):
                r = self.lib(shell, 'conf_read; echo "S=$MU300_STORAGE E=${MU300_SD_ERASE:-} B=$MU300_BOOT"',
                             MU300_SDCARD=sd, MU300_TRUSTED_CONF=adb / 'mu300-install.conf', MU300_TRUSTED_UID=uid)
                self.assertIn(want, r.stdout)

    def test_every_example_line_loads_once_uncommented(self):
        # the documented way: copy the example, remove the # of a line, install again. An explanation on the key's
        # own line would become part of its value, and the value would be refused.
        sd = self.tmp / 'sd'
        sd.mkdir()
        for shell in self.each_shell():
            r = self.lib(shell, 'write_example', MU300_SDCARD=sd)
            self.assertEqual(r.returncode, 0, r.stderr)
            ex = (sd / 'mu300-install.conf.example').read_text()
            lines = ex.splitlines()
            keys = [l for l in lines if re.match(r'#MU300_[A-Z_]+=', l)]
            self.assertEqual(len(keys), 15, ex)
            for line in keys:
                i = lines.index(line)
                self.assertTrue(lines[i - 1].startswith('# '), line)          # its explanation, on a line of its own
                f = self.tmp / 'c.conf'
                f.write_text('\n'.join(lines[:i] + [line[1:]] + lines[i + 1:]) + '\n')
                r = self.lib(shell, f'conf_load "{f}" trusted; conf_check; echo LOADED')
                self.assertEqual(r.returncode, 0, (line, r.stdout + r.stderr))
                self.assertIn('LOADED', r.stdout, line)
                self.assertNotIn('not valid', r.stdout, line)

    def arm(self, shell, mode):
        """arm_linux on a fake misc whose block is LIVE, with a dd that, for MODE, fails or writes the wrong bytes
        when it writes to misc (stuck: every write to misc goes wrong, the restore too)"""
        w, adb = self.tmp / 'w', self.tmp / 'adb'
        shutil.rmtree(w, ignore_errors=True); shutil.rmtree(adb, ignore_errors=True)
        (w / 'ramdisk/etc').mkdir(parents=True); adb.mkdir()
        (w / 'ramdisk/etc/misc-bc-slot-b-trial.bin').write_bytes(b'TRIA' * 8)
        misc = self.tmp / 'misc'
        misc.write_bytes(b'\0' * 2048 + b'LIVE' * 8 + b'\0' * 2016)
        dd = ('dd() { case "$*" in *"of=$MISC"*) case "$MODE:$*" in fail:*trial*) return 1 ;; '
              'garble:*trial*|stuck:*) printf garbage | command dd of="$MISC" bs=1 seek=2048 conv=notrunc 2>/dev/null; '
              'return 0 ;; esac ;; esac; command dd "$@"; }; ')
        r = self.lib(shell, f'W="{w}"; MISC="{misc}"; LINUX_SLOT=b; LIVE_BC=$(hex_at "$MISC" 2048 32); misc_save; '
                            + dd + f'MODE={mode}; arm_linux; echo ARMED', MU300_WORK_PARENT=adb)
        return r, misc.read_bytes()[2048:2080]

    def test_misc_that_does_not_verify_gets_its_block_back(self):
        for shell in self.each_shell():
            r, bc = self.arm(shell, 'ok')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(bc, b'TRIA' * 8)
            for mode in ('fail', 'garble'):
                r, bc = self.arm(shell, mode)
                self.assertEqual(r.returncode, 1, (mode, r.stdout + r.stderr))
                self.assertEqual(bc, b'LIVE' * 8, mode)                       # the block it held, written back
                self.assertIn('written back', r.stdout, mode)
                self.assertIn('Android boots as before', r.stdout, mode)
            r, bc = self.arm(shell, 'stuck')
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotEqual(bc, b'LIVE' * 8)
            self.assertNotIn('Android boots as before', r.stdout)
            self.assertIn('Do not reboot', r.stdout)                           # said plainly, with what to do
            saved = self.tmp / 'adb/mu300-misc-bc-before.bin'
            self.assertEqual(saved.read_bytes(), b'LIVE' * 8)
            self.assertIn(f'if={saved} of={self.tmp}/misc', r.stdout)

    def test_cleanup_never_removes_a_mounted_filesystem(self):
        w = self.tmp / 'work'
        for shell in self.each_shell():
            for d in ('kernel', 'x/root', 'mnt'):
                (w / d).mkdir(parents=True, exist_ok=True)
            (w / 'kernel/Image').write_text('k')
            (w / 'x/root/home').write_text('precious')
            (w / 'mnt/home').write_text('precious')
            mounts = self.tmp / 'mounts'
            mounts.write_text(f'/dev/block/loop7 {w}/x/root ext4 rw 0 0\n')
            r = self.lib(shell, f'W="{w}"; SDCARD="{self.tmp}/none"; cleanup', MU300_MOUNTS=mounts)
            self.assertFalse((w / 'kernel').exists())
            self.assertEqual((w / 'x/root/home').read_text(), 'precious')
            self.assertEqual((w / 'mnt/home').read_text(), 'precious')    # a mount point is only ever rmdir'd
            self.assertIn('still mounted', r.stdout)
            # no mount table to read: nothing is removed at all
            (w / 'kernel').mkdir()
            r = self.lib(shell, f'W="{w}"; SDCARD="{self.tmp}/none"; cleanup', MU300_MOUNTS=self.tmp / 'missing')
            self.assertTrue((w / 'kernel').exists())
            # unmounted (the mount point empty again): all of it goes
            (w / 'mnt/home').unlink()
            mounts.write_text('')
            r = self.lib(shell, f'W="{w}"; SDCARD="{self.tmp}/none"; cleanup', MU300_MOUNTS=mounts)
            self.assertFalse(w.exists())
            self.assertNotIn('still mounted', r.stdout)


class AndroidSide(ShellTest):
    def test_mount_helper_read_only_on_request(self):
        card = self.tmp / 'card'
        card.write_bytes(fake_ext4_bytes('mu300sd'))
        self.stub('mount', 'echo "mount $*" >> "$STUBLOG/calls"')
        for shell in self.each_shell():
            for ro, opts in (('1', '-o ro,noload'), ('', '-o noatime')):
                (self.tmp / 'calls').unlink(missing_ok=True)
                r = self.script(shell, TOP / 'tools/android-mount-mu300root.sh', self.tmp / 'mp',
                                MU300_SD_DEV=card, MU300_RO=ro)
                self.assertIn('MOUNTED', r.stdout, r.stderr)
                self.assertIn(f'mount -t ext4 {opts} {card}', (self.tmp / 'calls').read_text())

    def test_android_install_takes_its_directory_from_the_installer(self):
        # the Magisk installer's work directory, only root can write it; /data/local/tmp for install.sh
        self.assertIn('\nT=${MU300_DEVICE_WORK:-/data/local/tmp}\n', (TOP / 'tools/android-install.sh').read_text())


@unittest.skipIf(not BUSYBOX, 'no busybox (the installer runs under Magisk\'s busybox)')
@unittest.skipIf(not HAVE_LZ4, 'neither the lz4 command nor the lz4 Python module is installed')
class InstallerCase(ShellTest):
    """a zip (mu300/ beside a real zip of payload/) and a FakeDevice; run_installer() runs install.sh as Magisk's
    busybox would"""

    def setUp(self):
        super().setUp()
        self.stub('magiskboot', MAGISKBOOT)
        self.reset()

    def reset(self):
        self.magiskboot = self.stubs / 'magiskboot'
        self.zip()
        self.device()

    def no_magiskboot(self):
        self.magiskboot = self.tmp / 'no-magiskboot'

    def fake_install_hook(self, line):
        """LINE runs inside the fake android-install.sh, before it says MU300-INSTALL-OK"""
        (self.fake.root / 'install-hook').write_text(line + '\n')

    def device(self, **kw):
        shutil.rmtree(self.tmp / 'fake', ignore_errors=True)
        self.fake = FakeDevice(self.tmp, self.stubs, **kw)
        fake_android_root(self.fake.root / 'android')
        (self.fake.root / 'magisk/busybox').symlink_to(BUSYBOX)

    IMAGE_SHADOW = 'root::19000:0:99999:7:::\nubuntu:$6$img$imagehash:19000:0:99999:7:::\n'

    def zip(self, system='openwrt', kernel='6.18', features=('sdcard',), devices='f50', corrupt=False,
            image_shadow=True):
        """mu300/ with its manifest, and the zip with the payload of SYSTEM and KERNEL"""
        self.mu300 = self.tmp / 'zip' / 'mu300'
        shutil.rmtree(self.tmp / 'zip', ignore_errors=True)
        shutil.copytree(INSTALLER_DIR, self.mu300, symlinks=True)
        self.zip_args = dict(system=system, kernel=kernel, features=features, devices=devices, image_shadow=image_shadow)
        self.kernel_release = f'{kernel}.0-mu300' if kernel != '5.4' else '5.4.254-mu300'
        kasset = 'mu300-kernel.tar.gz' if kernel == '5.4' else f'mu300-kernel-{kernel}.tar.gz'
        rasset = ROOTFS_ASSET[system]
        os_, _, ubuntu = system.partition('-')
        kb = tar_gz({'Image': b'\x7fkernel' * 1000, 'ramdisk-generic.lz4': generic_ramdisk(),
                     'modules/mu300-test.ko': b'\x7fELF test module', 'kernel.release': (self.kernel_release + '\n').encode(),
                     'devices': (devices + '\n').encode(), 'features': ''.join(f + '\n' for f in features).encode()})
        files = {'etc/os-release': f'ID={os_}\n'.encode()}
        if image_shadow:
            files['etc/shadow'] = self.IMAGE_SHADOW.encode()
        rootfs = tar_gz(files)
        (self.mu300 / 'manifest').write_text(
            f'TAG=v2026.10.06\nSYSTEM={system}\nOS={os_}\nUBUNTU={ubuntu}\nKERNEL={kernel}\nKERNEL_ASSET={kasset}\n'
            f'ROOTFS_ASSET={rasset}\nSHA256_KERNEL={hashlib.sha256(kb).hexdigest()}\n'
            f'SHA256_ROOTFS={hashlib.sha256(rootfs).hexdigest()}\n')
        self.zipfile = self.tmp / 'zip' / 'mu300-magisk.zip'
        with zipfile.ZipFile(self.zipfile, 'w') as z:
            z.writestr(f'payload/{kasset}', kb, compress_type=zipfile.ZIP_STORED)
            z.writestr(f'payload/{rasset}', rootfs + (b'x' if corrupt else b''), compress_type=zipfile.ZIP_STORED)

    def corrupt_payload(self):
        self.zip(**self.zip_args, corrupt=True)

    def existing_filesystem(self, systems=('ubuntu',), ubuntu=None):
        """an installed mu300root in the free eMMC region holding SYSTEMS (and Ubuntu's release)"""
        last_end = 2048 + (8 << 21)
        start = (last_end // 4096 + 1) * 4096
        end = (((16 << 21) - 34) // 4096 - 1) * 4096
        off = start * 512
        with open(self.fake.root / 'dev/block/mmcblk0', 'r+b') as f:
            f.truncate(16 << 30)
            f.seek(off + 1028); f.write(((end - start) * 512 // 4096).to_bytes(4, 'little'))
            f.seek(off + 1080); f.write(b'\x53\xef')
            f.seek(off + 1144); f.write(b'mu300root')
        if ubuntu and 'ubuntu' not in systems:
            systems = tuple(systems) + ('ubuntu',)
        for s in systems:
            (self.fake.root / 'fs' / s / 'etc').mkdir(parents=True, exist_ok=True)
        (self.fake.root / 'fs/home').mkdir(exist_ok=True)
        (self.fake.root / 'fs/home/precious').write_text('a user file')
        if ubuntu:
            rel = self.fake.root / 'fs/ubuntu/usr/lib/os-release'
            rel.parent.mkdir(parents=True, exist_ok=True)
            rel.write_text(f'NAME="Ubuntu"\nVERSION_ID="{ubuntu}"\n')

    def accounts(self, system, marked=False):
        """SYSTEM on the existing filesystem has accounts of its own; MARKED: still the image's
        (.mu300-accounts-from-image: an older mu300-update installed it and never carried them over)"""
        etc = self.fake.root / 'fs' / system / 'etc'
        etc.mkdir(parents=True, exist_ok=True)
        (etc / 'shadow').write_text('root:$6$theirs$root:19000::::::\nubuntu:$6$theirs$hash:19000::::::\n')
        if marked:
            (etc / '.mu300-accounts-from-image').write_text('')

    def snapshot(self):
        """what a run that writes nothing leaves as it was: the partitions, the disks, /data/local/tmp (never used)
        and /data/adb (the work directory is gone again)"""
        r = self.fake.root
        snap = {n: sha(r / 'dev/block/by-name' / n) for n in ('boot_a', 'boot_b', 'misc')}
        for d in ('mmcblk0', 'mmcblk1'):
            p = r / 'dev/block' / d
            if p.exists():
                st = p.stat()
                snap[d] = (st.st_size, st.st_mtime_ns)
        snap['local tmp'] = {str(p.relative_to(r)): sha(p) for p in sorted((r / 'tmp').rglob('*')) if p.is_file()}
        snap['data/adb'] = sorted(p.name for p in (r / 'data/adb').iterdir())
        return snap

    def nothing_written(self, except_fs=False):
        """EXCEPT_FS: the disks the Linux filesystem is on may have changed (the systems were installed)"""
        now, before = self.snapshot(), dict(self.before)
        if except_fs:
            for d in ('mmcblk0', 'mmcblk1'):
                now.pop(d, None); before.pop(d, None)
        return now == before

    def work_dirs(self):
        return sorted((self.fake.root / 'data/adb').glob('mu300-magisk.*'))

    def run_installer(self, conf=None, trusted=None, extra_env=None):
        """CONF: /sdcard/mu300-install.conf (any app can write it); TRUSTED: /data/adb/mu300-install.conf, mode 600"""
        for text, f in ((conf, self.fake.root / 'sdcard/mu300-install.conf'),
                        (trusted, self.fake.root / 'data/adb/mu300-install.conf')):
            if text is None:
                f.unlink(missing_ok=True)
            else:
                f.write_text(text)
                f.chmod(0o600)
        self.before = self.snapshot()
        env = self.fake.env(self.mu300, self.magiskboot)
        env['ZIPFILE'] = self.zipfile
        env.update(extra_env or {})
        return subprocess.run([BUSYBOX, 'sh', str(self.mu300 / 'install.sh')], capture_output=True, text=True,
                              env=self.env(**env), timeout=120)


class Plan(InstallerCase):
    def test_v50_model_uses_f50_dry_run(self):
        self.device(model='MU3351')
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertTrue(self.nothing_written())

    def test_defaults_internal_region(self):
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('internal', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_card_with_mu300sd_is_the_default(self):
        self.device(card=fake_ext4_bytes('mu300sd'))
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('/mmcblk1', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_internal_while_a_mu300sd_card_is_in_the_slot_is_refused(self):
        # boot/init starts the card first: an internal installation would never start, and nobody can type the word
        self.device(card=fake_ext4_bytes('mu300sd'))
        r = self.run_installer(conf='MU300_STORAGE=internal\nMU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('mu300sd', r.stdout)
        self.assertIn('MU300_STORAGE=sd', r.stdout)      # the way out is named
        self.assertTrue(self.nothing_written())

    def test_card_is_never_erased_without_consent(self):
        self.device(card=bytes(1 << 20), region=False)
        r = self.run_installer(conf='MU300_STORAGE=sd\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn('MU300_SD_ERASE=yes', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_hostile_sdcard_conf_erases_nothing(self):
        # any app with storage access can write /sdcard: an erase, a wipe or a password there is not taken
        self.device(card=bytes(1 << 20), region=False)
        r = self.run_installer(conf='MU300_STORAGE=sd\nMU300_SD_ERASE=yes\nMU300_PASSWORD=hunter22\nMU300_MODE=wipe\n')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('MU300_SD_ERASE', r.stdout)
        self.assertNotIn('hunter22', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_trusted_conf_allows_the_erase(self):
        self.device(card=bytes(1 << 20), region=False)
        r = self.run_installer(conf='MU300_DRY_RUN=1\n',
                               trusted='MU300_STORAGE=sd\nMU300_SD_ERASE=yes\nMU300_PASSWORD=hunter22\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('/mmcblk1', r.stdout)
        self.assertIn('CREATE new ext4', r.stdout)
        self.assertIn('data/adb/mu300-install.conf', r.stdout)      # the plan says where the values came from
        self.assertIn('data/adb/mu300-linux-password.txt', r.stdout)
        self.assertNotIn('hunter22', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_untrusted_storage_does_not_aim_a_standing_erase(self):
        # an erase allowed in /data/adb long ago, and a card someone put into the slot: /sdcard cannot pick it
        self.device(card=bytes(1 << 20), region=False)
        r = self.run_installer(conf='MU300_STORAGE=sd\nMU300_DRY_RUN=1\n', trusted='MU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('MU300_STORAGE=sd and MU300_SD_ERASE=yes', r.stdout)
        self.assertTrue(self.nothing_written())
        r = self.run_installer(conf='MU300_DRY_RUN=1\n', trusted='MU300_STORAGE=sd\nMU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('CREATE new ext4', r.stdout)

    def test_untrusted_storage_does_not_aim_a_standing_region_overwrite(self):
        def dirty():
            with open(self.fake.root / 'dev/block/mmcblk0', 'r+b') as f:
                f.truncate(16 << 30)
                start = ((2048 + (8 << 21)) // 4096 + 1) * 4096 * 512
                f.seek(start + (512 << 10)); f.write(b'data' * 1024)
        for conf, trusted, rc in (('MU300_STORAGE=internal\nMU300_DRY_RUN=1\n', 'MU300_REGION_OVERWRITE=yes\n', 1),
                                  ('MU300_DRY_RUN=1\n', 'MU300_REGION_OVERWRITE=yes\n', 3),
                                  ('MU300_DRY_RUN=1\n', 'MU300_STORAGE=internal\nMU300_REGION_OVERWRITE=yes\n', 3),
                                  ('MU300_DRY_RUN=1\n', None, 1)):
            self.device(); dirty()
            r = self.run_installer(conf=conf, trusted=trusted)
            self.assertEqual(r.returncode, rc, (conf, trusted, r.stdout + r.stderr))
            if rc == 1:
                self.assertIn('MU300_STORAGE=internal and MU300_REGION_OVERWRITE=yes', r.stdout)
            self.assertTrue(self.nothing_written())

    def test_manifest_fields_are_checked_before_any_path(self):
        bad = {'ROOTFS_ASSET': '../../../etc/passwd', 'KERNEL_ASSET': '-mu300-kernel.tar.gz', 'OS': '../openwrt',
               'TAG': 'v2026/../..', 'SYSTEM': 'openwrt x', 'KERNEL': '6.18/..', 'SHA256_ROOTFS': 'A' * 64,
               'SHA256_KERNEL': '', 'UBUNTU': '24.04'}
        good = (self.mu300 / 'manifest').read_text()
        for k, v in bad.items():
            lines = [l for l in good.splitlines() if not l.startswith(k + '=')] + [f'{k}={v}']
            (self.mu300 / 'manifest').write_text('\n'.join(lines) + '\n')
            r = self.run_installer(conf='MU300_DRY_RUN=1\n')
            self.assertEqual(r.returncode, 1, (k, v, r.stdout + r.stderr))
            self.assertIn('manifest', r.stdout, k)
            self.assertNotIn('Unpacking', r.stdout, k)                    # refused before the payload is touched
            self.assertTrue(self.nothing_written(), k)
        (self.mu300 / 'manifest').write_text(good)
        self.assertEqual(self.run_installer(conf='MU300_DRY_RUN=1\n').returncode, 3)

    def test_conf_others_can_change_is_not_trusted(self):
        trusted = 'MU300_STORAGE=sd\nMU300_SD_ERASE=yes\nMU300_DRY_RUN=1\n'
        for setup in (lambda: (self.fake.root / 'data/adb/mu300-install.conf').chmod(0o620),
                      lambda: (self.fake.root / 'data/adb/mu300-install.conf').chmod(0o606)):
            self.device(card=bytes(1 << 20), region=False)
            (self.fake.root / 'data/adb/mu300-install.conf').write_text(trusted)
            setup()
            self.before = self.snapshot()
            env = self.fake.env(self.mu300, self.stubs / 'magiskboot')
            env['ZIPFILE'] = self.zipfile
            r = subprocess.run([BUSYBOX, 'sh', str(self.mu300 / 'install.sh')], capture_output=True, text=True,
                               env=self.env(**env), timeout=120)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('not owned by root', r.stdout)
            self.assertTrue(self.nothing_written())
        # owned by someone else
        self.device(card=bytes(1 << 20), region=False)
        r = self.run_installer(trusted=trusted, extra_env={'MU300_TRUSTED_UID': os.getuid() + 1})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertTrue(self.nothing_written())

    def test_conf_inside_the_zip_is_trusted(self):
        self.device(card=bytes(1 << 20), region=False)
        (self.mu300 / 'mu300-install.conf').write_text('MU300_STORAGE=sd\nMU300_SD_ERASE=yes\nMU300_DRY_RUN=1\n')
        r = self.run_installer()
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('CREATE new ext4', r.stdout)

    def test_wiping_a_mu300sd_card_needs_the_erase_too(self):
        self.device(card=fake_ext4_bytes('mu300sd'))
        r = self.run_installer(conf='MU300_DRY_RUN=1\n', trusted='MU300_MODE=wipe\n')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('MU300_SD_ERASE=yes', r.stdout)
        self.assertTrue(self.nothing_written())
        r = self.run_installer(conf='MU300_DRY_RUN=1\n', trusted='MU300_MODE=wipe\nMU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertIn('CREATE new ext4', r.stdout)

    def test_foreign_ext4_card_is_refused_even_with_consent(self):
        self.device(card=fake_ext4_bytes('photos'))
        r = self.run_installer(trusted='MU300_STORAGE=sd\nMU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn('mu300sd', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_card_with_a_kernel_that_cannot_read_it(self):
        self.device(card=fake_ext4_bytes('mu300sd'))
        self.zip(features=())
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn('SD card', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_no_room_no_card(self):
        self.device(region=False)
        r = self.run_installer()
        self.assertEqual(r.returncode, 1)
        self.assertIn('MU300_STORAGE=sd', r.stdout)      # the way out is named
        self.assertIn('no SD card', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_no_room_messages_point_the_right_way(self):
        # a foreign card is not offered for erasing
        self.device(region=False, card=fake_ext4_bytes('photos'))
        r = self.run_installer()
        self.assertEqual(r.returncode, 1)
        self.assertIn('never formats', r.stdout)
        self.assertNotIn('MU300_SD_ERASE', r.stdout)
        # internal chosen, too little room, a card there: the card is named, not "no SD card"
        self.device(region=False, card=bytes(1 << 20))
        r = self.run_installer(conf='MU300_STORAGE=internal\n')
        self.assertEqual(r.returncode, 1)
        self.assertIn('/mmcblk1', r.stdout)
        self.assertNotIn('no SD card', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_unknown_model(self):
        self.device(model='Pixel 7')
        r = self.run_installer()
        self.assertEqual(r.returncode, 1)
        self.assertIn('MU300_DEVICE=f50', r.stdout)
        self.assertTrue(self.nothing_written())
        # from /sdcard it is not taken; from the trusted file it is
        self.assertEqual(self.run_installer(conf='MU300_DEVICE=f50\nMU300_DRY_RUN=1\n').returncode, 1)
        self.assertEqual(self.run_installer(conf='MU300_DRY_RUN=1\n', trusted='MU300_DEVICE=f50\n').returncode, 3)

    def test_android_on_slot_b_puts_linux_on_a(self):
        self.device(slot='_b')
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 3)
        self.assertIn('boot_a', r.stdout)

    def test_corrupt_payload(self):
        self.corrupt_payload()
        self.assertEqual(self.run_installer().returncode, 1)
        self.assertTrue(self.nothing_written())

    def test_ubuntu_2604_and_a_54_zip(self):
        self.existing_filesystem(ubuntu='26.04')
        self.zip(kernel='5.4', system='openwrt')
        r = self.run_installer()
        self.assertEqual(r.returncode, 1)
        self.assertIn('26.04', r.stdout)
        self.assertTrue(self.nothing_written())

    def test_example_conf_written(self):
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        ex = (self.fake.root / 'sdcard/mu300-install.conf.example').read_text()
        for k in ('MU300_STORAGE', 'MU300_SD_ERASE', 'MU300_BOOT', 'MU300_PASSWORD', 'MU300_DRY_RUN'):
            self.assertIn(k, ex)
        self.assertRegex(ex, r'# \(root\)[^\n]*\n#MU300_SD_ERASE=yes\n')  # which keys need the trusted file
        self.assertIn('data/adb/mu300-install.conf', ex)

    def test_plan_names_the_source_of_every_value(self):
        self.existing_filesystem(systems=('openwrt',))
        conf = ('MU300_DRY_RUN=1\nMU300_MODE=update\nMU300_BOOT=linux\nMU300_BOOT_ATTEMPTS=3\nMU300_HOTSPOT=no\n'
                'MU300_GPU=no\nMU300_BOOT_OS=openwrt\nMU300_STORAGE=internal\n')
        r = self.run_installer(conf=conf)
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        plan = r.stdout.split('Plan', 1)[1]
        for label in ('storage:', 'filesystem:', 'boots:', 'default boot:', 'boot attempts:', 'hotspot:', 'GPU files:'):
            [line] = [l for l in plan.splitlines() if l.strip().startswith(label)]
            self.assertIn('sdcard/mu300-install.conf', line, line)
        self.assertRegex(plan, r'boot attempts: +3 ')
        self.assertRegex(plan, r'hotspot: +not copied')
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        plan = r.stdout.split('Plan', 1)[1]
        for label in ('default boot:', 'boot attempts:', 'hotspot:', 'GPU files:'):
            [line] = [l for l in plan.splitlines() if l.strip().startswith(label)]
            self.assertIn('(default)', line, line)

    def test_plan_names_an_installed_openwrt_luci(self):
        # the third system (OpenWrt with the control panel) is one the existing filesystem can hold: it is counted
        # for the space check and named in the plan like the other two
        self.existing_filesystem(systems=('openwrt-luci', 'ubuntu'))
        r = self.run_installer(conf='MU300_DRY_RUN=1\nMU300_MODE=update\nMU300_STORAGE=internal\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        [line] = [l for l in r.stdout.splitlines() if 'already there:' in l]
        self.assertIn('openwrt-luci', line)
        self.assertIn('ubuntu', line)
        # and it may be the one that boots
        r = self.run_installer(conf='MU300_DRY_RUN=1\nMU300_MODE=update\nMU300_STORAGE=internal\nMU300_BOOT_OS=openwrt-luci\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertRegex(r.stdout, r'boots: +openwrt-luci')

    def test_example_conf_is_never_written_through_a_link(self):
        victim = self.tmp / 'victim'
        victim.write_text('not yours')
        ex = self.fake.root / 'sdcard/mu300-install.conf.example'
        ex.symlink_to(victim)
        self.assertEqual(self.run_installer(conf='MU300_DRY_RUN=1\n').returncode, 3)
        self.assertEqual(victim.read_text(), 'not yours')
        self.assertFalse(ex.is_symlink())
        self.assertIn('MU300_STORAGE', ex.read_text())
        self.assertEqual(sorted(p.name for p in ex.parent.iterdir()), ['mu300-install.conf', 'mu300-install.conf.example'])

    def test_example_conf_written_on_refusal(self):
        self.device(model='Pixel 7')
        self.assertEqual(self.run_installer().returncode, 1)
        self.assertIn('MU300_DEVICE', (self.fake.root / 'sdcard/mu300-install.conf.example').read_text())


class WorkDirectory(InstallerCase):
    """everything checked and then used lives in one directory of this run that only root can write (S1), and no
    filesystem mounted in it is ever deleted (C1)"""

    def test_local_tmp_is_never_used(self):
        # what the shell user could put into /data/local/tmp for root to run or install
        lt = self.fake.root / 'tmp'
        for n in ('android-install.sh', 'android-mount-mu300root.sh'):
            (lt / n).write_text(f'touch "{self.tmp}/ran-{n}"\n')
        (lt / 'mu300-openwrt.tar.gz').write_bytes(b'not the payload')
        (lt / 'mu300-install.env').write_text('FORMAT=1\n')
        self.existing_filesystem(systems=('openwrt',))
        r = self.run_installer(conf='MU300_DRY_RUN=1\n')
        self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
        self.assertTrue(self.nothing_written())                        # /data/local/tmp as it was, work dir gone
        self.assertEqual(list(self.tmp.glob('ran-*')), [])
        log = (self.fake.root / 'android-sh.log').read_text().splitlines()
        mount = [l for l in log if 'android-mount-mu300root.sh' in l and ' -u ' not in l]
        self.assertEqual(len(mount), 1, log)
        work = str(Path(os.path.realpath(self.fake.root / 'data/adb')) / 'mu300-magisk.')
        self.assertIn(f' {work}', mount[0])                           # the helper copied into the work directory
        self.assertTrue(mount[0].endswith(' drwx------'), mount[0])    # which only root can enter
        self.assertIn('MU300_RO=1', mount[0])                          # inspected read-only

    def test_failed_unmount_keeps_the_filesystem(self):
        self.existing_filesystem(systems=('openwrt',))
        r = self.run_installer(conf='MU300_DRY_RUN=1\n', extra_env={'FAKE_UMOUNT_FAILS': '1'})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('still mounted', r.stdout)
        [w] = self.work_dirs()
        self.assertEqual(sorted(p.name for p in w.iterdir()), ['mnt'])     # payload and helper gone, the mount kept
        self.assertEqual((w / 'mnt/home/precious').read_text(), 'a user file')

    def test_stale_mount_of_an_earlier_run_is_never_touched(self):
        # an earlier run killed while its filesystem was mounted (no EXIT trap ran)
        old = Path(os.path.realpath(self.fake.root / 'data/adb')) / 'mu300-magisk.EARLY1'
        (old / 'mnt/home').mkdir(parents=True)
        (old / 'mnt/home/precious').write_text('a user file')
        (self.fake.root / 'mounts').write_text(f'/dev/block/loop7 {old}/mnt ext4 rw 0 0\n')
        self.existing_filesystem(systems=('openwrt',))
        for extra, rc in (({'FAKE_MOUNT_FAILS': '1'}, 1), ({}, 3)):     # the helper refuses a second mount, or not
            r = self.run_installer(conf='MU300_DRY_RUN=1\n', extra_env=extra)
            self.assertEqual(r.returncode, rc, r.stdout + r.stderr)
            self.assertEqual((old / 'mnt/home/precious').read_text(), 'a user file')
            self.assertTrue(self.nothing_written())


class Install(InstallerCase):
    """the whole installation: the systems, then boot_<linux slot> written and verified, then misc armed"""

    def linux_image(self, slot):
        img = (self.fake.root / 'dev/block/by-name' / f'boot_{slot}').read_bytes()
        self.assertEqual(img[:8], b'ANDROID!')
        # the marker the Android-side switch looks for before it arms a slot
        self.assertEqual(img[44:44 + 1536], b'loglevel=5'.ljust(1536, b'\0'))
        return cpio_all(unlz4_legacy(ramdisk_of(img)))

    def password_of(self, out):
        """the password as the output shows it, whole (between quotes: it may hold blanks)"""
        m = re.search(r'password for \w+: "(.*)"   \(also in ', out)
        self.assertTrue(m, out)
        return m.group(1)

    def test_full_install_internal(self):
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        by = self.fake.root / 'dev/block/by-name'
        self.assertEqual(sha(by / 'boot_a'), self.before['boot_a'])            # Android's partition untouched
        files = self.linux_image('b')
        self.assertEqual(files['etc/mu300-linux-slot'][1], b'b\n')
        self.assertEqual(files['etc/mu300-device'][1], b'f50\n')
        self.assertIn('android/vendor/bin/modem_control', files)
        self.assertIn('init', files)                                           # from the bundle's generic segment
        bc = (by / 'misc').read_bytes()[0x800:0x820]
        self.assertEqual(bc, files['etc/misc-bc-slot-b-trial.bin'][1])         # armed: Linux trial on b
        env = (self.fake.root / 'install.env').read_text()
        for line in ('FORMAT=1', 'OSES="openwrt"', 'SD_MODE=0', 'DEFAULT_LINUX=1', 'BOOT_ATTEMPTS=5', 'KERNEL=6.18'):
            self.assertIn(line, env)
        self.assertRegex(env, r"PWHASH='\$6\$[./0-9A-Za-z]{16}\$")
        pw = self.password_of(r.stdout)
        self.assertRegex(pw, r'^[a-km-zA-HJ-NP-Z2-9]{12}$')
        # the hash is the password's (the fake mkpasswd's "hash" is its first 10 bytes in hex)
        self.assertIn(pw.encode().hex()[:20] + "'", env)
        # root's file by default, mode 600; nothing on the shared storage
        f = self.fake.root / 'data/adb/mu300-linux-password.txt'
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertRegex(f.read_text(), rf'(?m)^password: {pw}$')
        self.assertFalse((self.fake.root / 'sdcard/mu300-linux-password.txt').exists())
        self.assertEqual(self.work_dirs(), [])                                 # proprietary staging gone

    def test_report_names_the_vpn_extra(self):
        # the zip carries no VPN engines (they are the vpn extra since mu300-extra): the report says how to add them
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('The VPN (mu300-vpn) needs the vpn extra: Xray and sing-box.', r.stdout)
        self.assertIn('sudo mu300-extra install vpn', r.stdout)

    def test_slot_b_android(self):
        self.device(slot='_b')
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        by = self.fake.root / 'dev/block/by-name'
        self.assertEqual(sha(by / 'boot_b'), self.before['boot_b'])            # Android's partition untouched
        files = self.linux_image('a')
        self.assertEqual(files['etc/mu300-linux-slot'][1], b'a\n')
        self.assertEqual((by / 'misc').read_bytes()[0x800:0x820], files['etc/misc-bc-slot-a-trial.bin'][1])

    def test_sd_card_install(self):
        self.device(card=bytes(1 << 20))
        r = self.run_installer(trusted='MU300_STORAGE=sd\nMU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        by = self.fake.root / 'dev/block/by-name'
        self.assertEqual(sha(by / 'boot_a'), self.before['boot_a'])
        files = self.linux_image('b')
        self.assertEqual((by / 'misc').read_bytes()[0x800:0x820], files['etc/misc-bc-slot-b-trial.bin'][1])
        env = (self.fake.root / 'install.env').read_text()
        self.assertIn('SD_MODE=1', env)
        self.assertIn('SD_DEV=' + str(self.fake.root / 'dev/block/mmcblk1'), env)
        # OFF/SIZE stay the internal region, as install.sh writes them (the root-on-sd marker needs it)
        start = ((2048 + (8 << 21)) // 4096 + 1) * 4096
        end = (((16 << 21) - 34) // 4096 - 1) * 4096
        self.assertIn(f'OFF={start * 512}\nSIZE={(end - start) * 512}\n', env)
        self.assertIn('FORMAT=1', env)

    def test_android_side_runs_with_android_tools(self):
        self.assertEqual(self.run_installer().returncode, 0)
        for line in (self.fake.root / 'android-sh.log').read_text().splitlines():
            self.assertTrue(line.startswith('ASH_STANDALONE= '), line)

    def test_install_failure_leaves_boot_and_misc(self):
        r = self.run_installer(extra_env={'FAKE_INSTALL_FAILS': '1'})
        self.assertEqual(r.returncode, 1)
        self.assertIn('boot_b and misc were not changed', r.stdout)
        (self.fake.root / 'data/adb/mu300-linux-password.txt').unlink()      # saved first (the next test)
        self.assertTrue(self.nothing_written(except_fs=True))

    def test_password_is_saved_before_anything_is_written(self):
        # android-install.sh puts the hash into the systems: a run that fails or is killed after that must not
        # leave a Linux whose password was never shown or saved
        r = self.run_installer(extra_env={'FAKE_INSTALL_FAILS': '1'})
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        pw = self.password_of(r.stdout)
        self.assertLess(r.stdout.index('password for'), r.stdout.index('Installing'))
        f = self.fake.root / 'data/adb/mu300-linux-password.txt'
        self.assertRegex(f.read_text(), rf'(?m)^password: {re.escape(pw)}$')
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        # a password file that cannot be written stops the run before anything is installed
        self.device()
        (self.fake.root / 'sdcard/mu300-linux-password.txt').mkdir()
        r = self.run_installer(trusted='MU300_PASSWORD_FILE=sdcard\n')
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn('could not write', r.stdout)
        self.assertNotIn('Installing', r.stdout)
        self.assertFalse((self.fake.root / 'install.env').exists())
        self.assertTrue(self.nothing_written())

    def test_destructive_keys_are_used_once(self):
        # a standing wipe, erase or overwrite in /data/adb would apply to every later flash: once used, each becomes
        # a comment, the way a used password does
        conf = self.fake.root / 'data/adb/mu300-install.conf'
        self.existing_filesystem(systems=('openwrt',))
        r = self.run_installer(trusted='MU300_MODE=wipe\nMU300_BOOT_ATTEMPTS=3\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('FORMAT=1', (self.fake.root / 'install.env').read_text())
        text = conf.read_text()
        self.assertNotRegex(text, r'(?m)^\s*MU300_MODE')
        self.assertIn('# MU300_MODE was used by the installer and removed', text)
        self.assertIn('MU300_BOOT_ATTEMPTS=3\n', text)
        self.assertEqual(conf.stat().st_mode & 0o777, 0o600)
        self.assertRegex(r.stdout, r'MU300_MODE.*removed|removed.*MU300_MODE')     # the report says so
        r = self.run_installer(trusted=text)                                  # the next flash is an update
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('FORMAT=0', (self.fake.root / 'install.env').read_text())
        # the card's erase: once
        self.device(card=bytes(1 << 20))
        r = self.run_installer(trusted='MU300_STORAGE=sd\nMU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = conf.read_text()
        self.assertIn('MU300_STORAGE=sd\n', text)
        self.assertNotRegex(text, r'(?m)^\s*MU300_SD_ERASE')
        self.assertIn('# MU300_SD_ERASE was used by the installer and removed', text)
        # an erase not used (an update of a mu300sd card) stays
        self.device(card=fake_ext4_bytes('mu300sd'))
        r = self.run_installer(trusted='MU300_SD_ERASE=yes\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(conf.read_text(), 'MU300_SD_ERASE=yes\n')
        # the region overwrite: once
        self.device()
        with open(self.fake.root / 'dev/block/mmcblk0', 'r+b') as f:
            f.truncate(16 << 30)
            f.seek(((2048 + (8 << 21)) // 4096 + 1) * 4096 * 512 + (512 << 10)); f.write(b'data' * 1024)
        r = self.run_installer(trusted='MU300_REGION_OVERWRITE=yes\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('# MU300_REGION_OVERWRITE was used by the installer and removed', conf.read_text())

    def test_a_wipe_counts_for_one_install_whatever_the_target_held(self):
        # MU300_MODE=wipe in /data/adb is used by the install that formats, also when the target had no filesystem
        # yet (a blank region, a new card): left standing, the next flash (the second zip, an update) would wipe
        # the system this one installed
        conf = self.fake.root / 'data/adb/mu300-install.conf'
        cases = (  # name, card before, trusted conf, the target as the first install leaves it
            ('blank region', None, 'MU300_MODE=wipe\n', lambda: self.existing_filesystem(systems=('openwrt',))),
            ('installed region', 'region', 'MU300_MODE=wipe\n', lambda: None),
            ('new card', bytes(1 << 20), 'MU300_STORAGE=sd\nMU300_SD_ERASE=yes\nMU300_MODE=wipe\n',
             lambda: self.device(card=fake_ext4_bytes('mu300sd'))),
            ('mu300sd card', fake_ext4_bytes('mu300sd'), 'MU300_SD_ERASE=yes\nMU300_MODE=wipe\n',
             lambda: self.device(card=fake_ext4_bytes('mu300sd'))))
        for name, card, trusted, formatted in cases:
            with self.subTest(name):
                self.reset()
                if card == 'region':
                    self.existing_filesystem(systems=('openwrt',))
                elif card is not None:
                    self.device(card=card)
                r = self.run_installer(trusted=trusted)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn('FORMAT=1', (self.fake.root / 'install.env').read_text())
                text = conf.read_text()
                for k in ('MU300_MODE', 'MU300_SD_ERASE'):
                    self.assertNotRegex(text, rf'(?m)^\s*{k}\s*=')
                self.assertIn('# MU300_MODE was used by the installer and removed', text)
                formatted()
                # the next flash, with the conf as the first one left it: an update, nothing formatted
                r = self.run_installer(conf='MU300_DRY_RUN=1\n', trusted=text)
                self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
                self.assertNotIn('CREATE new ext4', r.stdout)
                self.assertIn('keep: settings and data', r.stdout)
                self.assertTrue(self.nothing_written())

    def test_misc_changed_meanwhile_is_not_armed(self):
        # a stub android-install.sh that changes misc while "installing" (an OTA, another installer)
        self.fake_install_hook('printf X | dd of="$FAKE/dev/block/by-name/misc" bs=1 seek=2060 conv=notrunc 2>/dev/null')
        r = self.run_installer()
        self.assertEqual(r.returncode, 1)
        self.assertIn('misc changed during the installation', r.stdout)
        self.assertNotEqual((self.fake.root / 'dev/block/by-name/misc').read_bytes()[0x800:0x802], b'_b')

    def test_refusals_write_nothing(self):
        for setup in (lambda: self.device(region=False), lambda: self.corrupt_payload(),
                      lambda: self.device(model='Pixel 7'), lambda: self.no_magiskboot()):
            self.reset(); setup()
            self.assertEqual(self.run_installer().returncode, 1)
            self.assertTrue(self.nothing_written())

    def test_password_from_conf_is_used_and_removed(self):
        conf = self.fake.root / 'data/adb/mu300-install.conf'
        r = self.run_installer(trusted='MU300_BOOT_ATTEMPTS=3\nMU300_PASSWORD=correct horse\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.password_of(r.stdout), 'correct horse')          # shown whole, blank and all
        self.assertIn('correct horse', (self.fake.root / 'data/adb/mu300-linux-password.txt').read_text())
        self.assertIn('correct horse'.encode().hex()[:20], (self.fake.root / 'install.env').read_text())
        text = conf.read_text()
        self.assertNotIn('correct horse', text)
        self.assertIn('MU300_BOOT_ATTEMPTS=3\n', text)                         # the other settings stay
        self.assertIn('# MU300_PASSWORD was used by the installer and removed', text)
        self.assertEqual(conf.stat().st_mode & 0o777, 0o600)
        self.assertFalse(conf.is_symlink())
        self.assertEqual(sorted(p.name for p in conf.parent.iterdir()),
                         ['mu300-install.conf', 'mu300-linux-password.txt'])
        # a conf inside the zip is never edited
        (self.mu300 / 'mu300-install.conf').write_text('MU300_PASSWORD=battery staple\n')
        self.assertEqual(self.run_installer().returncode, 0)
        self.assertIn('battery staple', (self.mu300 / 'mu300-install.conf').read_text())

    def test_password_file_on_the_shared_storage_only_when_trusted(self):
        r = self.run_installer(conf='MU300_PASSWORD_FILE=sdcard\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((self.fake.root / 'sdcard/mu300-linux-password.txt').exists())
        self.assertTrue((self.fake.root / 'data/adb/mu300-linux-password.txt').exists())
        self.device()
        r = self.run_installer(trusted='MU300_PASSWORD_FILE=sdcard\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        f = self.fake.root / 'sdcard/mu300-linux-password.txt'
        self.assertIn(self.password_of(r.stdout), f.read_text())
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.fake.root / 'data/adb/mu300-linux-password.txt').exists())

    def test_password_file_is_never_written_through_a_link(self):
        victim = self.tmp / 'victim'
        victim.write_text('not yours')
        f = self.fake.root / 'sdcard/mu300-linux-password.txt'
        f.symlink_to(victim)
        r = self.run_installer(trusted='MU300_PASSWORD_FILE=sdcard\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(victim.read_text(), 'not yours')
        self.assertFalse(f.is_symlink())
        self.assertIn(self.password_of(r.stdout), f.read_text())

    def test_second_zip_keeps_the_first_systems_password(self):
        # Both systems are two zips. The second one installs beside the first and leaves that system's password as
        # it was, so the file must keep it: the first zip's output may be gone, and the file is the only other place
        # (seen on the F50: the Ubuntu zip's file replaced the OpenWrt root password)
        f = self.fake.root / 'data/adb/mu300-linux-password.txt'
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pw_root = self.password_of(r.stdout)
        self.existing_filesystem(systems=('openwrt',))
        self.zip(system='ubuntu-24.04', kernel='5.4')
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pw_ubuntu = self.password_of(r.stdout)
        text = f.read_text()
        self.assertIn(f'user: ubuntu\npassword: {pw_ubuntu}\n', text)
        self.assertIn(f'user: root\npassword: {pw_root}\n', text)
        self.assertTrue(text.startswith('MU300 Linux '))                       # the newest first
        self.assertLess(text.index('user: ubuntu'), text.index('user: root'))
        self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        # the first system again with a new password asked for: it replaces its old one, the other one stays
        self.zip(system='openwrt')
        r = self.run_installer(trusted='MU300_PASSWORD_RESET=yes\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pw_root2 = self.password_of(r.stdout)
        text = f.read_text()
        self.assertEqual(text.count('user: root\n'), 1, text)
        self.assertEqual(text.count('user: ubuntu\n'), 1, text)
        self.assertIn(f'user: root\npassword: {pw_root2}\n', text)
        self.assertIn(f'user: ubuntu\npassword: {pw_ubuntu}\n', text)
        self.assertNotIn(f'password: {pw_root}\n', text)
        # a wipe leaves one system: no password of the erased one
        r = self.run_installer(trusted='MU300_MODE=wipe\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = f.read_text()
        self.assertNotIn('user: ubuntu', text)
        self.assertEqual(text.count('user: root\n'), 1, text)

    def kept(self, r, users):
        """R kept the password: no hash for android-install.sh, no password shown, the plan and report say so"""
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PWHASH=''", (self.fake.root / 'install.env').read_text())
        self.assertNotRegex(r.stdout, r'password for \w+: "')
        self.assertIn('password:       kept: the accounts and passwords of the installed system are not changed',
                      r.stdout)
        self.assertIn(f'password for {users}: unchanged', r.stdout)

    def test_update_keeps_the_password(self):
        # update (keep) mode: the accounts and their passwords stay as the device has them, as with mu300-update; no
        # new password is generated and the password file is left alone (seen on a device: the Ubuntu zip's
        # update replaced the user's own password with a generated one)
        f = self.fake.root / 'data/adb/mu300-linux-password.txt'
        for system, users in (('openwrt', 'root'), ('ubuntu-24.04', 'ubuntu')):
            with self.subTest(system):
                self.reset()
                self.zip(system=system, kernel='6.18')
                os_ = system.partition('-')[0]
                self.existing_filesystem(systems=(os_,))
                self.accounts(os_)
                f.write_text('MU300 Linux v2026.10.01\nuser: x\npassword: the earlier one\n')
                f.chmod(0o600)
                r = self.run_installer()
                self.kept(r, users)
                self.assertIn('keep: settings and data', r.stdout)
                self.assertEqual(f.read_text(), 'MU300 Linux v2026.10.01\nuser: x\npassword: the earlier one\n')
                # no file at all: none is made either
                self.reset()
                self.zip(system=system, kernel='6.18')
                self.existing_filesystem(systems=(os_,))
                self.accounts(os_)
                self.kept(self.run_installer(), users)
                self.assertFalse(f.exists())

    def test_password_is_generated_for_a_fresh_install_or_a_wipe(self):
        cases = (  # name, the target, trusted conf
            ('blank region', lambda: None, None),
            ('wipe', lambda: (self.existing_filesystem(systems=('openwrt',)), self.accounts('openwrt')),
             'MU300_MODE=wipe\n'),
            # a system added beside another: the new one has only the image's accounts
            ('second system', lambda: (self.existing_filesystem(systems=('ubuntu',)), self.accounts('ubuntu')), None),
            # the system there still has the image's accounts (an older mu300-update never carried them over)
            ('image accounts', lambda: (self.existing_filesystem(systems=('openwrt',)),
                                        self.accounts('openwrt', marked=True)), None),
            # a system without an /etc/shadow (damaged): nothing to keep
            ('no shadow', lambda: self.existing_filesystem(systems=('openwrt',)), None),
            # the images' well-known ubuntu/ubuntu (the fake mkpasswd's hash of "ubuntu" with that salt)
            ('default password', lambda: (self.existing_filesystem(systems=('openwrt',)),
                                          (self.fake.root / 'fs/openwrt/etc/shadow').write_text(
                                              'root:$6$abc$' + b'ubuntu'.hex() + ':19000::::::\n')), None),
            # the image's own hash carried over from a system without the mark
            ('image hash', lambda: (self.zip(system='ubuntu-24.04'), self.existing_filesystem(systems=('ubuntu',)),
                                    (self.fake.root / 'fs/ubuntu/etc/shadow').write_text(
                                        'ubuntu:$6$img$imagehash:19000::::::\n')), None),
            # the zip's image shadow cannot be read: nothing to compare with, so not kept
            ('unreadable image', lambda: (self.zip(image_shadow=False), self.existing_filesystem(systems=('openwrt',)),
                                          self.accounts('openwrt')), None),
            # root has no password of its own (OpenWrt's image leaves it empty; locked or missing alike)
            ('no hash', lambda: (self.existing_filesystem(systems=('openwrt',)),
                                 (self.fake.root / 'fs/openwrt/etc/shadow').write_text('root::19000::::::\nubuntu:$6$x$y:1::\n')),
             None))
        for name, target, trusted in cases:
            with self.subTest(name):
                self.reset()
                target()
                r = self.run_installer(trusted=trusted)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                pw = self.password_of(r.stdout)
                self.assertRegex(pw, r'^[a-km-zA-HJ-NP-Z2-9]{12}$')
                self.assertIn('password:       generated, written to', r.stdout)
                self.assertIn(pw.encode().hex()[:20] + "'", (self.fake.root / 'install.env').read_text())
                self.assertIn(f'password: {pw}\n', (self.fake.root / 'data/adb/mu300-linux-password.txt').read_text())

    def test_password_reset_only_when_a_trusted_conf_asks(self):
        conf = self.fake.root / 'data/adb/mu300-install.conf'
        f = self.fake.root / 'data/adb/mu300-linux-password.txt'
        # any app could write /sdcard: a reset asked for there is ignored, the password stays
        self.existing_filesystem(systems=('openwrt',)); self.accounts('openwrt')
        r = self.run_installer(conf='MU300_PASSWORD_RESET=yes\n')
        self.kept(r, 'root')
        self.assertIn('MU300_PASSWORD_RESET is taken only from', r.stdout)
        self.assertFalse(f.exists())
        # from /data/adb: generated, shown, saved, and the line used once
        r = self.run_installer(trusted='MU300_PASSWORD_RESET=yes\nMU300_BOOT_ATTEMPTS=3\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        pw = self.password_of(r.stdout)
        self.assertIn(pw.encode().hex()[:20] + "'", (self.fake.root / 'install.env').read_text())
        self.assertIn(f'password: {pw}\n', f.read_text())
        text = conf.read_text()
        self.assertIn('# MU300_PASSWORD_RESET was used by the installer and removed', text)
        self.assertIn('MU300_BOOT_ATTEMPTS=3\n', text)
        # the next flash keeps the new one
        self.kept(self.run_installer(trusted=text), 'root')
        self.assertIn(f'password: {pw}\n', f.read_text())
        # a password of one's own in /data/adb is a reset too
        r = self.run_installer(trusted='MU300_PASSWORD=correct horse\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.password_of(r.stdout), 'correct horse')
        self.assertIn('correct horse'.encode().hex()[:20], (self.fake.root / 'install.env').read_text())
        self.assertIn('password:       from ', r.stdout)

    def test_payload_replaced_after_verification_is_not_installed(self):
        # the zip changes under the installer once the payload is checked (magiskboot runs only after that): what
        # gets installed is the checked copy
        good = self.tmp / 'good.zip'
        shutil.copy(self.zipfile, good)
        self.corrupt_payload()
        evil = self.tmp / 'evil.zip'
        shutil.copy(self.zipfile, evil)
        shutil.copy(good, self.zipfile)
        self.stub('magiskboot-swap', f'cp "{evil}" "$ZIPFILE"; exec "{self.stubs}/magiskboot" "$@"')
        self.magiskboot = self.stubs / 'magiskboot-swap'
        r = self.run_installer()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sha(self.zipfile), sha(evil))                         # the swap happened
        want = re.search(r'SHA256_ROOTFS=(\w+)', (self.mu300 / 'manifest').read_text()).group(1)
        installed = [l.split()[0] for l in (self.fake.root / 'installed.sha256').read_text().splitlines()]
        self.assertEqual(installed, [want])

    def test_mainline_modules_into_every_system(self):
        self.existing_filesystem(systems=('ubuntu',))
        r = self.run_installer()                                       # an OpenWrt 6.18 zip added to it
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        krel = self.kernel_release
        self.assertTrue((self.fake.root / f'fs/ubuntu/lib/modules/{krel}/extra/mu300-test.ko').is_file())
        self.assertTrue((self.fake.root / f'fs/openwrt/lib/modules/{krel}/mu300-test.ko').is_file())
        self.assertEqual((self.fake.root / 'fs/home/precious').read_text(), 'a user file')
        self.assertEqual((self.fake.root / 'mounts').read_text(), '')                 # unmounted again
        self.assertEqual(self.work_dirs(), [])


class Password(ShellTest):
    def lib(self, shell, code):
        return self.sh(shell, f'MU300_LIB=1 MU300_DIR="{INSTALLER_DIR}" MU300_UBB="busybox" . "{INSTALLER}"; ' + code)

    @unittest.skipIf(not busybox_has('mkpasswd'), "this busybox has no mkpasswd")
    def test_hash_is_sha512crypt(self):
        # the bundled busybox's mkpasswd and tools/sha512crypt.py agree
        import importlib.util
        spec = importlib.util.spec_from_file_location('s', TOP / 'tools' / 'sha512crypt.py')
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        for shell in self.each_shell():
            r = self.lib(shell, 'password_hash "s3cret pw"')
            self.assertEqual(r.returncode, 0, r.stderr)
            h = r.stdout.strip()
            salt = h.split('$')[2]
            self.assertEqual(len(salt), 16)
            self.assertEqual(h, m.sha512_crypt('s3cret pw', salt))

    def test_random_chars(self):
        for shell in self.each_shell():
            seen = set()
            for _ in range(20):
                r = self.lib(shell, 'random_chars "$PW_ALPHABET" 12')
                self.assertRegex(r.stdout.strip(), r'^[a-km-np-zA-HJ-NP-Z2-9]{12}$')
                seen.add(r.stdout)
            self.assertEqual(len(seen), 20)


if __name__ == '__main__':
    unittest.main()
