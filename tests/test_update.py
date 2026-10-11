"""mu300-update, sourced for its functions (MU300_LIB=1) against a fake Linux partition (MU300_DISK): which files of a
release it takes, the kernel choice, the byte helpers it edits boot image headers with, and whether a kernel bundle
may go onto this device."""
import io
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import unittest

from helpers import BIN, TOP, ShellTest
from test_boot_image import HAVE_LZ4, fake_stock, fake_misc, BOOT


class UpdateBase(ShellTest):
    def setUp(self):
        super().setUp()
        self.disk = self.tmp / 'disk'
        (self.disk / 'ubuntu' / 'etc').mkdir(parents=True)
        self.root = self.tmp / 'root'
        (self.root / 'run/mu300').mkdir(parents=True)
        self.device('f50')

    def device(self, name):
        (self.root / 'run/mu300/device').write_text(name + '\n')

    def up(self, shell, code, **env):
        return self.sh(shell, f'. "{BIN}/mu300-update"; {code}', MU300_LIB=1, MU300_DISK=self.disk, MU300_BIN=BIN,
                       MU300_SYSROOT=self.root, **env)

    def busybox_applets(self, shell):
        """For busybox sh, {'PATH': ...} that runs the applets the update uses from busybox, as on OpenWrt: busybox sh
        on Ubuntu runs /usr/bin/cp, GNU's, which hides what busybox's own cp does. {} for the other shells."""
        if os.path.basename(shell[0]) != 'busybox':
            return {}
        d = self.tmp / 'busybox-applets'
        if not d.exists():
            d.mkdir()
            for a in ('cp', 'find', 'mkdir', 'rm', 'mv', 'ln', 'cat', 'dirname', 'tar', 'gzip', 'awk', 'sed', 'grep'):
                (d / a).write_text(f'#!/bin/sh\nexec "{shell[0]}" {a} "$@"\n')
                (d / a).chmod(0o755)
        return {'PATH': f'{d}{os.pathsep}{self.stubs}{os.pathsep}{os.environ.get("PATH", "")}'}


class Update(UpdateBase):
    def test_sourcing_does_nothing(self):
        for shell in self.each_shell():
            r = self.up(shell, 'echo loaded')
            self.assertEqual((r.returncode, r.stdout), (0, 'loaded\n'), r.stderr)

    def test_linux_slot(self):
        f = self.root / 'run/mu300/linux-slot'
        for shell in self.each_shell():
            f.unlink(missing_ok=True)
            self.assertEqual(self.up(shell, 'linux_slot').stdout.strip(), 'b')
            for v, want in (('a\n', 'a'), ('b\n', 'b'), ('x\n', 'b')):
                f.write_text(v)
                self.assertEqual(self.up(shell, 'linux_slot').stdout.strip(), want, v)

    def test_linux_slot_without_the_file_is_the_booted_one(self):
        # an initramfs that did not publish it (or a garbled file): the slot LK booted, from the command line or the
        # bootargs in the device tree; b only when neither says
        f = self.root / 'run/mu300/linux-slot'
        cmdline = self.root / 'proc/cmdline'
        bootargs = self.root / 'proc/device-tree/chosen/bootargs'
        bootargs.parent.mkdir(parents=True)
        cases = [(None, 'console=x androidboot.slot_suffix=_a quiet', None, 'a'),
                 ('x\n', 'loglevel=5', b'console=x\0androidboot.slot_suffix=_a\0', 'a'),
                 (None, 'loglevel=5', None, 'b'),
                 (None, 'androidboot.slot_suffix=_b', b'androidboot.slot_suffix=_a\0', 'b'),
                 ('b\n', 'androidboot.slot_suffix=_a', None, 'b')]       # what the initramfs published wins
        for shell in self.each_shell():
            for v, cl, ba, want in cases:
                for p, data in ((f, v), (cmdline, cl), (bootargs, ba)):
                    p.unlink(missing_ok=True)
                    if data is not None:
                        p.write_bytes(data if isinstance(data, bytes) else data.encode())
                self.assertEqual(self.up(shell, 'linux_slot').stdout.strip(), want, (v, cl, ba))

    def test_rollback_stays_on_its_slot(self):
        # the kept image was taken from the slot Linux ran from then (no prev.slot: b); after Linux moved to a,
        # rolling back would put an init that knows only slot b onto a - refused before anything is written
        boot = self.disk / 'boot'
        boot.mkdir()
        (boot / 'prev.body').write_bytes(b'old image')
        f = self.root / 'run/mu300/linux-slot'
        for shell in self.each_shell():
            for prev, now, refused in ((None, 'a', True), ('b', 'a', True), ('a', 'b', True), ('a', 'a', False),
                                       (None, 'b', False), ('b', 'b', False)):
                (boot / 'prev.slot').unlink(missing_ok=True)
                if prev:
                    (boot / 'prev.slot').write_text(prev + '\n')
                f.write_text(now + '\n')
                r = self.up(shell, 'part_dev() { echo "PART $1" >&2; return 1; }; rollback_boot')
                self.assertNotEqual(r.returncode, 0)
                if refused:
                    self.assertIn('was taken from slot', r.stderr, (prev, now))
                    self.assertNotIn('PART', r.stderr)
                else:
                    self.assertIn(f'PART boot_{now}', r.stderr, (prev, now))

    def test_boot_update_keeps_the_slot_of_the_image(self):
        src = (BIN / 'mu300-update').read_text()
        self.assertIn('linux_slot > "$BOOTDIR/prev.slot"', src)
        self.assertLess(src.index('cp "$tmp/body" "$BOOTDIR/prev.body"'),
                        src.index('linux_slot > "$BOOTDIR/prev.slot"'))

    def test_slot_a_needs_a_slot_aware_bundle(self):
        # an older bundle's init knows only slot b: on Linux-on-a it would restore the wrong block and log into
        # Android's boot partition
        old = self.bundle('old.tar.gz', 'f50\n', 'sdcard\n')
        new = self.bundle('new.tar.gz', 'f50\n', 'sdcard\nlinux-slot\n')
        f = self.root / 'run/mu300/linux-slot'
        for shell in self.each_shell():
            for slot, b, ok in (('a', old, False), ('a', new, True), ('b', old, True), ('b', new, True)):
                f.write_text(slot + '\n')
                d = self.tmp / 'x'
                d.mkdir(exist_ok=True)
                r = self.up(shell, f'tar -tzf "{b}" > "{d}/list"; '
                                   f'bundle_fits_slot "{b}" "{d}/list" && echo OK || echo REFUSE')
                self.assertEqual(r.stdout.strip(), 'OK' if ok else 'REFUSE', (slot, b.name, r.stderr))

    def test_fetch_retries_a_network_error(self):
        # right after boot the VPN is up some seconds after mobile data, and a request in between is reset
        # (curl 35/56): "mu300-update check" then said "could not reach GitHub". Network errors are retried a few
        # times; an HTTP error (22: 404 and the like) is an answer and is not, and neither is a timeout (28: curl's
        # own --retry has retried it already, and four more rounds of 120 s would hold "check" for half an hour).
        for shell in self.each_shell():
            for rc, fails, want_out, want_calls in ((56, 2, 'body', 3), (35, 1, 'body', 2), (22, 1, '', 1),
                                                     (7, 9, '', 4), (28, 1, '', 1), (6, 1, 'body', 2)):
                n = self.tmp / 'n'
                n.write_text('0')
                self.stub('curl', f'c=$(($(cat "$STUBLOG/n") + 1)); echo $c > "$STUBLOG/n"; '
                                  f'[ $c -gt {fails} ] && {{ echo body; exit 0; }}; exit {rc}')
                r = self.up(shell, 'fetch_stdout https://example.invalid/x; echo "rc=$?"', MU300_FETCH_DELAY=0)
                self.assertEqual(int(n.read_text()), want_calls, (rc, fails))
                self.assertEqual(r.stdout.replace('rc=0\n', '').replace('rc=1\n', '').strip(), want_out, (rc, r.stdout))
                self.assertIn('rc=0' if want_out else 'rc=1', r.stdout)

    def test_notice(self):
        # a note for the login message and mu300-toolkit when a newer release is out; nothing else happens
        note, motd = self.tmp / 'run/update-available', self.tmp / 'motd.d'
        env = dict(MU300_NOTICE=str(note), MU300_MOTD_DIR=str(motd))
        for shell in self.each_shell():
            for installed, latest, noted in (('v2026.10.06', 'v2026.10.08', True), ('v2026.10.08', 'v2026.10.08', False),
                                             ('v2026.10.09', 'v2026.10.08', False)):   # a test release: no note
                r = self.up(shell, f'latest_release() {{ echo {latest}; }}; installed_version() {{ echo {installed}; }}; '
                                   'notice; echo rc=$?', **env)
                self.assertIn('rc=0', r.stdout, r.stderr)
                self.assertEqual(note.exists(), noted, (installed, latest))
                self.assertEqual((motd / '60-mu300-update').exists(), noted)
                if noted:
                    self.assertEqual(note.read_text(), f'mu300-linux {latest} is out (this is {installed}): '
                                                       'sudo mu300-update apply\n')
            # offline: the note stays, and the caller hears it (to ask again sooner)
            self.up(shell, 'latest_release() { echo v2026.10.08; }; installed_version() { echo v2026.10.06; }; notice', **env)
            r = self.up(shell, 'latest_release() { :; }; notice; echo rc=$?', **env)
            self.assertIn('rc=1', r.stdout)
            self.assertTrue(note.exists())

    def test_rootfs_asset(self):
        osr = self.disk / 'ubuntu' / 'etc' / 'os-release'
        cases = [('24.04', {}, 'mu300-ubuntu-rootfs.tar.gz'),
                 ('26.04', {}, 'mu300-ubuntu-26.04-rootfs.tar.gz'),
                 ('26.04', {'MU300_UBUNTU': '24.04'}, 'mu300-ubuntu-rootfs.tar.gz'),
                 ('24.04', {'MU300_UBUNTU': '26.04'}, 'mu300-ubuntu-26.04-rootfs.tar.gz'),
                 (None, {}, 'mu300-ubuntu-rootfs.tar.gz')]
        for shell in self.each_shell():
            for ver, env, want in cases:
                if ver:
                    osr.write_text(f'NAME="Ubuntu"\nVERSION_ID="{ver}"\n')
                else:
                    osr.unlink(missing_ok=True)
                self.assertEqual(self.up(shell, 'rootfs_asset ubuntu', **env).stdout.strip(), want, (ver, env))
            self.assertEqual(self.up(shell, 'rootfs_asset openwrt').stdout.strip(), 'mu300-openwrt-rootfs.tar.gz')

    def test_os_kind(self):
        for shell in self.each_shell():
            for name, kind in [('ubuntu', 'ubuntu'), ('openwrt', 'openwrt'), ('openwrt-luci', 'openwrt')]:
                self.assertEqual(self.up(shell, f'os_kind {name}').stdout.strip(), kind)
            self.assertEqual(self.up(shell, 'os_kind arch').returncode, 1)

    def test_installed_systems_three(self):
        for name in ('openwrt', 'openwrt-luci', 'openwrt-luci.old'):
            (self.disk / name).mkdir()
        for shell in self.each_shell():
            self.assertEqual(self.up(shell, 'installed_systems').stdout.split(), ['ubuntu', 'openwrt', 'openwrt-luci'])

    def test_lists_by_kind(self):
        for shell in self.each_shell():
            self.assertEqual(self.up(shell, 'keep_list openwrt-luci').stdout, self.up(shell, 'keep_list openwrt').stdout)
            self.assertEqual(self.up(shell, 'vendor_list openwrt-luci').stdout, self.up(shell, 'vendor_list openwrt').stdout)
            self.assertEqual(self.up(shell, 'rootfs_asset openwrt-luci').stdout.strip(), 'mu300-openwrt-luci-rootfs.tar.gz')

    def test_running_os_by_directory(self):
        (self.disk / 'openwrt-luci' / 'etc').mkdir(parents=True)
        (self.disk / 'openwrt-luci' / 'etc' / 'openwrt_release').write_text('x')
        for shell in self.each_shell():
            r = self.up(shell, 'running_os', MU300_ROOT=self.disk / 'openwrt-luci')
            self.assertEqual(r.stdout.strip(), 'openwrt-luci')

    def test_running_os_after_apply_is_the_kept_copy(self):
        (self.disk / 'openwrt-luci.old' / 'etc').mkdir(parents=True)
        (self.disk / 'openwrt-luci.old' / 'etc' / 'openwrt_release').write_text('x')
        for shell in self.each_shell():
            r = self.up(shell, 'running_os', MU300_ROOT=self.disk / 'openwrt-luci.old')
            self.assertEqual(r.stdout.strip(), 'openwrt-luci')

    def test_clean_knows_the_third_system(self):
        (self.disk / 'openwrt-luci.old').mkdir()
        for shell in self.each_shell():
            self.up(shell, 'STAGE=$MU300_DISK/.stage; df() { :; }; clean')
            self.assertFalse((self.disk / 'openwrt-luci.old').exists())
            (self.disk / 'openwrt-luci.old').mkdir()

    def test_kernel_choice(self):
        boot = self.disk / 'boot'
        boot.mkdir()
        cases = [(None, '5.4', 'mu300-kernel.tar.gz'), ('6.18', '6.18', 'mu300-kernel-6.18.tar.gz'),
                 ('7.2', '7.2', 'mu300-kernel-7.2.tar.gz'), ('5.4', '5.4', 'mu300-kernel.tar.gz'),
                 ('6.1', '5.4', 'mu300-kernel.tar.gz'), ('', '5.4', 'mu300-kernel.tar.gz')]
        for shell in self.each_shell():
            for c, choice, asset in cases:
                f = boot / 'kernel'
                if c is None:
                    f.unlink(missing_ok=True)
                else:
                    f.write_text(c + '\n')
                self.assertEqual(self.up(shell, 'kernel_choice; kernel_asset').stdout.split(), [choice, asset], c)

    def test_byte_helpers(self):
        # the boot image header is edited with these: sizes little endian, the AVB footer big endian
        f = self.tmp / 'bytes.bin'
        for shell in self.each_shell():
            for v in (0, 1, 255, 256, 0x12345678, 0xFFFFFFFF):
                r = self.up(shell, f'bytes {v} 4 le > "{f}"; u32 "{f}" 0')
                self.assertEqual(f.read_bytes(), struct.pack('<I', v), v)
                self.assertEqual(r.stdout.strip(), str(v))
            for v in (0, 0x1234, 0x0000000100000000, 0x7FFFFFFF12345678):
                r = self.up(shell, f'bytes {v} 8 be > "{f}"; be64 "{f}" 0')
                self.assertEqual(f.read_bytes(), struct.pack('>Q', v), v)
                self.assertEqual(r.stdout.strip(), str(v))
            # poke: overwrite in place, the rest untouched
            f.write_bytes(bytes(16))
            self.up(shell, f'bytes 3735928559 4 le | poke "{f}" 4')
            self.assertEqual(f.read_bytes(), bytes(4) + struct.pack('<I', 0xDEADBEEF) + bytes(8))

    def test_pad_page(self):
        f = self.tmp / 'img'
        for shell in self.each_shell():
            for n, want in ((0, 0), (1, 4096), (4095, 4096), (4096, 4096), (4097, 8192)):
                f.write_bytes(b'x' * n)
                self.up(shell, f'pad_page "{f}"')
                self.assertEqual(f.stat().st_size, want, n)

    def test_installed_systems(self):
        for shell in self.each_shell():
            self.assertEqual(self.up(shell, 'installed_systems').stdout.split(), ['ubuntu'])
            (self.disk / 'openwrt').mkdir(exist_ok=True)
            self.assertEqual(self.up(shell, 'installed_systems').stdout.split(), ['ubuntu', 'openwrt'])
            (self.disk / 'openwrt').rmdir()

    def test_stale_broken_copies_are_removed(self):
        # a rollback leaves the system it left as <os>.broken (it may still be running until the reboot); nothing
        # removed it after that but a second rollback or "clean" - 655 MB stayed on the second F50 through an update
        for shell in self.each_shell():
            for os_ in ('ubuntu', 'openwrt'):
                (self.disk / f'{os_}.broken' / 'etc').mkdir(parents=True, exist_ok=True)
                (self.disk / f'{os_}.old' / 'etc').mkdir(parents=True, exist_ok=True)
            r = self.up(shell, 'clean_broken')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((self.disk / 'ubuntu.broken').exists())
            self.assertFalse((self.disk / 'openwrt.broken').exists())
            self.assertIn('ubuntu: removed the copy left by a rollback (ubuntu.broken)', r.stdout)
            self.assertTrue((self.disk / 'ubuntu.old').is_dir())          # the rollback copy stays
            self.assertTrue((self.disk / 'ubuntu').is_dir())
            # the running system (rolled back from, not rebooted yet) is never removed
            (self.disk / 'ubuntu.broken' / 'etc').mkdir(parents=True)
            r = self.up(shell, f'is_root() {{ [ "$1" = "{self.disk}/ubuntu.broken" ]; }}; clean_broken')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((self.disk / 'ubuntu.broken').is_dir())
            self.assertEqual(self.up(shell, 'clean_broken; echo rc=$?').stdout.strip().splitlines()[-1], 'rc=0')
            for d in ('ubuntu.broken', 'ubuntu.old', 'openwrt.old'):
                import shutil
                shutil.rmtree(self.disk / d, ignore_errors=True)

    def test_apply_cleans_before_it_counts_free_space(self):
        src = (BIN / 'mu300-update').read_text()
        body = src[src.index('\napply() {'):src.index('\nrollback() {')]
        self.assertIn('clean_broken', body)
        self.assertLess(body.index('clean_broken'), body.index('not enough free space'))

    def bundle(self, name, devices, features=None):
        p = self.tmp / name
        with tarfile.open(p, 'w:gz') as t:
            for fn, data in [('./Image', b'kernel'), ('./ramdisk-generic.lz4', b'rd')] + (
                    [('./devices', devices.encode())] if devices is not None else []) + (
                    [('./features', features.encode())] if features is not None else []):
                ti = tarfile.TarInfo(fn)
                ti.size = len(data)
                t.addfile(ti, io.BytesIO(data))
        return p

    def test_bundle_runs_here(self):
        new = self.bundle('new.tar.gz', 'f50 u30air\n')
        old = self.bundle('old.tar.gz', None)
        f50only = self.bundle('f50.tar.gz', 'f50\n')
        cases = [('f50', new, True), ('f50', old, True), ('u30air', new, True), ('u30air', old, False),
                 ('u30air', f50only, False)]
        for shell in self.each_shell():
            for dev, b, ok in cases:
                self.device(dev)
                d = self.tmp / 'x'
                d.mkdir(exist_ok=True)
                r = self.up(shell, f'tar -tzf "{b}" > "{d}/list"; bundle_runs_here "{b}" "{d}/list" "{d}" && echo YES || echo NO')
                self.assertEqual(r.stdout.strip(), 'YES' if ok else 'NO', (dev, b.name, r.stderr))
                (d / 'devices').unlink(missing_ok=True)

    def test_card_installation_needs_an_sd_capable_kernel(self):
        rootdev = self.tmp / 'root-dev'
        plain = self.bundle('plain.tar.gz', 'f50\n')
        empty = self.bundle('empty.tar.gz', 'f50\n', '')
        sd = self.bundle('sd.tar.gz', 'f50\n', 'other\nsdcard\n')
        for shell in self.each_shell():
            def run(dev, b):
                if dev is None:
                    rootdev.unlink(missing_ok=True)
                else:
                    rootdev.write_text(dev + '\n')
                d = self.tmp / 'x'
                d.mkdir(exist_ok=True)
                code = (f'MU300_ROOT_DEV_FILE="{rootdev}"; tar -tzf "{b}" > "{d}/list"; '
                        f'if root_on_sd && ! bundle_has_sd "{b}" "{d}/list"; then echo REFUSE; else echo OK; fi')
                r = self.up(shell, code)
                return r.stdout.strip()
            self.assertEqual(run('/dev/mmcblk1p1', plain), 'REFUSE')
            self.assertEqual(run('/dev/mmcblk1p1', empty), 'REFUSE')
            self.assertEqual(run('/dev/mmcblk1p1', sd), 'OK')
            self.assertEqual(run('mmcblk0@27762098176', plain), 'OK')
            # the internal region on an eMMC that came up as mmcblk1 (FINDINGS 31l)
            self.assertEqual(run('mmcblk1@27762098176', plain), 'OK')
            self.assertEqual(run(None, plain), 'OK')


# Update's setUp, device() and up() live in UpdateBase, which has no tests; Update and FromStock both derive from it
# (deriving from Update would run its tests twice).
@unittest.skipIf(not HAVE_LZ4, 'neither the lz4 command nor the lz4 Python module is installed')
class FromStock(UpdateBase):
    """bootimg_from_stock gives the bytes boot/build-boot-image.py gives, from the same stock image, kernel and
    ramdisk: the header page of Android's image with the new sizes, loglevel=5 and no signature, its vbmeta, its
    footer with the new sizes."""

    def python_image(self, stock):
        mods = self.tmp / 'mods'; mods.mkdir(exist_ok=True)
        for n in (BOOT / 'module-order.txt').read_text().split():
            (mods / n).write_bytes(b'\x7fELF ' + n.encode())
        for f in ('busybox', 'logdw'):
            (self.tmp / f).write_bytes(b'\x7fELF ' + f.encode())
        fake_misc(self.tmp / 'misc.bin')
        (self.tmp / 'Image').write_bytes(b'\x7fkernel' * 12345)
        out = self.tmp / 'py.img'
        r = subprocess.run([sys.executable, str(BOOT / 'build-boot-image.py'), '--stock-boot', str(stock),
                            '--misc-head', str(self.tmp / 'misc.bin'), '--kernel', str(self.tmp / 'Image'),
                            '--modules', str(mods), '--busybox', str(self.tmp / 'busybox'), '--logdw', str(self.tmp / 'logdw'),
                            '--ueventd-perms', str(TOP / 'android-vendor' / 'ueventd-perms.sh'), '--out', str(out)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        img = out.read_bytes()
        ksz, rsz = struct.unpack_from('<II', img, 8)
        roff = 4096 + (ksz + 4095) // 4096 * 4096
        (self.tmp / 'ramdisk').write_bytes(img[roff:roff + rsz])
        osz, _, vbs = struct.unpack_from('>QQQ', img, len(img) - 64 + 12)
        return img[:osz + vbs], img[-64:]

    def check(self, **stock_args):
        stock = self.tmp / 'stock.img'
        fake_stock(stock, **stock_args)
        head, footer = self.python_image(stock)
        d = self.tmp / 'out'
        for shell in self.each_shell():
            if d.exists():
                shutil.rmtree(d)
            d.mkdir()
            r = self.up(shell, f'bootimg_from_stock "{stock}" "{self.tmp}/Image" "{self.tmp}/ramdisk" "{d}"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((d / 'new').read_bytes() + (d / 'vbmeta').read_bytes(), head, shell)
            self.assertEqual((d / 'newfooter').read_bytes(), footer, shell)

    def test_same_bytes_as_the_python_builder(self):
        self.check()

    def test_unaligned_vbmeta(self):
        self.check(vbmeta_offset=(1 << 20) + 100)

    def test_cmdline_is_loglevel_5_whatever_the_stock_one_is(self):
        # the Android-side switch arms a slot only when it sees this marker; stock headers have it empty, but a
        # stock image with a command line of its own must not leak it into the Linux image
        stock = self.tmp / 'stock.img'
        fake_stock(stock)
        raw = bytearray(stock.read_bytes())
        raw[44:44 + 1536] = b'console=ttyMSM0 androidboot.x=1'.ljust(1536, b'\0')
        stock.write_bytes(bytes(raw))
        (self.tmp / 'k').write_bytes(b'k'); (self.tmp / 'r').write_bytes(b'r')
        d = self.tmp / 'out'
        for shell in self.each_shell():
            if d.exists():
                shutil.rmtree(d)
            d.mkdir()
            r = self.up(shell, f'bootimg_from_stock "{stock}" "{self.tmp}/k" "{self.tmp}/r" "{d}"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((d / 'new').read_bytes()[44:44 + 1536], b'loglevel=5'.ljust(1536, b'\0'), shell)

    def test_refuses_what_is_not_a_v4_image(self):
        bad = self.tmp / 'bad.img'
        bad.write_bytes(bytes(1 << 20))
        (self.tmp / 'k').write_bytes(b'k'); (self.tmp / 'r').write_bytes(b'r')
        for shell in self.each_shell():
            r = self.up(shell, f'bootimg_from_stock "{bad}" "{self.tmp}/k" "{self.tmp}/r" "{self.tmp}"')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('does not hold a boot image header v4', r.stderr)

    def test_refuses_a_v4_image_without_an_avb_footer(self):
        stock = self.tmp / 'stock.img'
        fake_stock(stock)
        raw = bytearray(stock.read_bytes())
        raw[-64:-60] = b'XXXX'
        stock.write_bytes(bytes(raw))
        (self.tmp / 'k').write_bytes(b'k'); (self.tmp / 'r').write_bytes(b'r')
        for shell in self.each_shell():
            r = self.up(shell, f'bootimg_from_stock "{stock}" "{self.tmp}/k" "{self.tmp}/r" "{self.tmp}"')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('has no AVB footer', r.stderr)

    def test_refuses_a_result_that_reaches_the_persistent_log(self):
        stock = self.tmp / 'stock.img'
        fake_stock(stock)
        (self.tmp / 'k').write_bytes(b'k' * 4096); (self.tmp / 'r').write_bytes(b'r')
        for shell in self.each_shell():
            r = self.up(shell, f'PERSIST_LOG=8192; bootimg_from_stock "{stock}" "{self.tmp}/k" "{self.tmp}/r" "{self.tmp}"')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('persistent log area', r.stderr)

    def test_apply_keeps_the_vendor_files_the_image_has_a_directory_for(self):
        # the images ship opt/mu300/android/system/bin/cltest and a few firmware files, so the vendor directories
        # exist in the new system; busybox's `cp -an old/. new/` then skips them as existing and copies nothing (an
        # update run from OpenWrt left every system without the Android userspace: no modem, no Wi-Fi)
        img = self.tmp / 'img'
        for f, data in [('sbin/init', b'#!/bin/sh\n'), ('opt/mu300/android/system/bin/cltest', b'image'),
                        ('lib/firmware/regulatory.db', b'image'), ('etc/mu300/image-version', b'v2\n')]:
            (img / f).parent.mkdir(parents=True, exist_ok=True)
            (img / f).write_bytes(data)
        (img / 'sbin/init').chmod(0o755)
        old = self.disk / 'openwrt'
        for f, data in [('sbin/init', b'#!/bin/sh\n'), ('opt/mu300/android/system/bin/cltest', b'old'),
                        ('opt/mu300/android/system/bin/cp_diskserver', b'vendor'),
                        ('opt/mu300/android/vendor/lib/libril.so', b'vendor'),
                        ('opt/mu300/android/dev-properties/property_info', b'props'),
                        ('lib/firmware/wcnmodem.bin', b'fw'), ('lib/firmware/regulatory.db', b'old'),
                        ('lib/modules/5.4.254/x.ko', b'ko'), ('etc/mu300/vpn.conf', b'mine')]:
            (old / f).parent.mkdir(parents=True, exist_ok=True)
            (old / f).write_bytes(data)
        (old / 'opt/mu300/android/system/lib').symlink_to('../vendor/lib')
        stage = self.disk / '.mu300-update'
        for shell in self.each_shell():
            for d in ('openwrt.old', 'openwrt.new'):
                shutil.rmtree(self.disk / d, ignore_errors=True)
            stage.mkdir(exist_ok=True)
            subprocess.run(['tar', '-czf', str(stage / 'mu300-openwrt-rootfs.tar.gz'), '-C', str(img), '.'], check=True)
            r = self.up(shell, 'is_root() { false; }; apply_one openwrt v2', **self.busybox_applets(shell))
            self.assertEqual(r.returncode, 0, r.stderr)
            new = self.disk / 'openwrt'
            self.assertEqual((new / 'opt/mu300/android/system/bin/cp_diskserver').read_bytes(), b'vendor')
            self.assertEqual((new / 'opt/mu300/android/vendor/lib/libril.so').read_bytes(), b'vendor')
            self.assertEqual((new / 'opt/mu300/android/dev-properties/property_info').read_bytes(), b'props')
            self.assertEqual(os.readlink(new / 'opt/mu300/android/system/lib'), '../vendor/lib')
            self.assertEqual((new / 'lib/firmware/wcnmodem.bin').read_bytes(), b'fw')
            self.assertEqual((new / 'lib/modules/5.4.254/x.ko').read_bytes(), b'ko')
            # what the image has stays the image's
            self.assertEqual((new / 'opt/mu300/android/system/bin/cltest').read_bytes(), b'image')
            self.assertEqual((new / 'lib/firmware/regulatory.db').read_bytes(), b'image')
            self.assertEqual((new / 'etc/mu300/vpn.conf').read_bytes(), b'mine')
            # the next shell updates from this one (disk/openwrt again)

    def test_apply_keeps_the_settings_and_adds_the_images_new_config_files(self):
        # the old etc/config is kept, but a package the new image brings has its own file there: copied whole, the
        # old directory dropped /etc/config/sqm and LuCI's SQM page failed ("uci/get: Resource not found")
        img = self.tmp / 'img-cfg'
        for f, data in [('sbin/init', b'#!/bin/sh\n'), ('etc/config/network', b'image'), ('etc/config/sqm', b'image sqm'),
                        ('etc/mu300/image-version', b'v2\n')]:
            (img / f).parent.mkdir(parents=True, exist_ok=True)
            (img / f).write_bytes(data)
        (img / 'sbin/init').chmod(0o755)
        old = self.disk / 'openwrt'
        for f, data in [('sbin/init', b'#!/bin/sh\n'), ('etc/config/network', b'mine'), ('etc/config/tailscale', b'mine too')]:
            (old / f).parent.mkdir(parents=True, exist_ok=True)
            (old / f).write_bytes(data)
        stage = self.disk / '.mu300-update'
        for shell in self.each_shell():
            for d in ('openwrt.old', 'openwrt.new'):
                shutil.rmtree(self.disk / d, ignore_errors=True)
            stage.mkdir(exist_ok=True)
            subprocess.run(['tar', '-czf', str(stage / 'mu300-openwrt-rootfs.tar.gz'), '-C', str(img), '.'], check=True)
            r = self.up(shell, 'is_root() { false; }; apply_one openwrt v2', **self.busybox_applets(shell))
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = self.disk / 'openwrt/etc/config'
            self.assertEqual((cfg / 'network').read_bytes(), b'mine')          # the device's settings win
            self.assertEqual((cfg / 'tailscale').read_bytes(), b'mine too')    # and stay
            self.assertEqual((cfg / 'sqm').read_bytes(), b'image sqm')         # the new package's file is added
            self.assertFalse((self.disk / 'openwrt/etc/config.image').exists())

    def test_copy_missing_never_writes_through_a_link_of_the_target(self):
        a, b, outside = self.tmp / 'a', self.tmp / 'b', self.tmp / 'outside'
        (a / 'd/x').mkdir(parents=True)
        (a / 'd/x/f').write_text('a')
        (a / 'name with space').write_text('s')
        b.mkdir(); outside.mkdir()
        (b / 'd').symlink_to(outside)
        for shell in self.each_shell():
            r = self.up(shell, f'copy_missing "{a}" "{b}"', **self.busybox_applets(shell))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual((b / 'name with space').read_text(), 's')
            (b / 'name with space').unlink()
            r = self.up(shell, f'copy_missing "{self.tmp}/missing" "{b}"', **self.busybox_applets(shell))
            self.assertNotEqual(r.returncode, 0)

    def test_apply_takes_the_vendor_files_only_the_previous_old_copy_still_has(self):
        # a device updated by an updater with the busybox cp bug: the system in place has the image's vendor
        # directories but none of the device's files, and the only copy is in openwrt.old, which the update replaces
        img = self.tmp / 'img'
        for f, data in [('sbin/init', b'#!/bin/sh\n'), ('opt/mu300/android/system/bin/cltest', b'image'),
                        ('lib/firmware/regulatory.db', b'image')]:
            (img / f).parent.mkdir(parents=True, exist_ok=True)
            (img / f).write_bytes(data)
        (img / 'sbin/init').chmod(0o755)
        stage = self.disk / '.mu300-update'
        for shell in self.each_shell():
            for d in ('openwrt', 'openwrt.old', 'openwrt.new'):
                shutil.rmtree(self.disk / d, ignore_errors=True)
            hit, good = self.disk / 'openwrt', self.disk / 'openwrt.old'
            for f, data in [('sbin/init', b'#!/bin/sh\n'), ('opt/mu300/android/system/bin/cltest', b'image'),
                            ('lib/firmware/regulatory.db', b'image'), ('lib/firmware/mine.bin', b'newer')]:
                (hit / f).parent.mkdir(parents=True, exist_ok=True)
                (hit / f).write_bytes(data)
            for f, data in [('sbin/init', b'#!/bin/sh\n'), ('opt/mu300/android/system/bin/cp_diskserver', b'vendor'),
                            ('opt/mu300/android/vendor/lib/libril.so', b'vendor'),
                            ('lib/firmware/wcnmodem.bin', b'fw'), ('lib/firmware/mine.bin', b'older'),
                            ('lib/firmware/regulatory.db', b'old')]:
                (good / f).parent.mkdir(parents=True, exist_ok=True)
                (good / f).write_bytes(data)
            stage.mkdir(exist_ok=True)
            subprocess.run(['tar', '-czf', str(stage / 'mu300-openwrt-rootfs.tar.gz'), '-C', str(img), '.'], check=True)
            r = self.up(shell, 'is_root() { false; }; apply_one openwrt v2', **self.busybox_applets(shell))
            self.assertEqual(r.returncode, 0, r.stderr)
            new = self.disk / 'openwrt'
            self.assertEqual((new / 'opt/mu300/android/system/bin/cp_diskserver').read_bytes(), b'vendor')
            self.assertEqual((new / 'opt/mu300/android/vendor/lib/libril.so').read_bytes(), b'vendor')
            self.assertEqual((new / 'lib/firmware/wcnmodem.bin').read_bytes(), b'fw')
            # gaps only: the system in place and the image come first
            self.assertEqual((new / 'lib/firmware/mine.bin').read_bytes(), b'newer')
            self.assertEqual((new / 'lib/firmware/regulatory.db').read_bytes(), b'image')

    def test_modules_into_every_system(self):
        b = self.tmp / 'bundle'
        (b / 'modules').mkdir(parents=True)
        (b / 'modules' / 'a.ko').write_bytes(b'a')
        (b / 'kernel.release').write_text('6.18.55-mu300\n')
        (b / 'modules.builtin').write_text('kernel/x.ko\n')
        (self.disk / 'openwrt').mkdir()
        for shell in self.each_shell():
            # a module of an earlier bundle of this release that this one no longer has goes
            for d in ('ubuntu/lib/modules/6.18.55-mu300/extra', 'openwrt/lib/modules/6.18.55-mu300'):
                (self.disk / d).mkdir(parents=True, exist_ok=True)
                (self.disk / d / 'gone.ko').write_bytes(b'old')
            r = self.up(shell, f'kernel_modules_into_systems "{b}"', MU300_NO_DEPMOD=1)
            self.assertFalse((self.disk / 'ubuntu/lib/modules/6.18.55-mu300/extra/gone.ko').exists())
            self.assertFalse((self.disk / 'openwrt/lib/modules/6.18.55-mu300/gone.ko').exists())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.disk / 'ubuntu/lib/modules/6.18.55-mu300/extra/a.ko').read_bytes(), b'a')
            self.assertTrue((self.disk / 'ubuntu/lib/modules/6.18.55-mu300/modules.builtin').exists())
            self.assertEqual((self.disk / 'ubuntu/lib/modules/6.18.55-mu300/modules.order').read_bytes(), b'')
            self.assertEqual((self.disk / 'openwrt/lib/modules/6.18.55-mu300/a.ko').read_bytes(), b'a')
        (b / 'kernel.release').write_text('../evil\n')
        for shell in self.each_shell():
            self.assertNotEqual(self.up(shell, f'kernel_modules_into_systems "{b}"', MU300_NO_DEPMOD=1).returncode, 0)

    def test_a_new_boot_image_unlocks_for_its_trial(self):
        src = (BIN / 'mu300-update').read_text()
        bu = src[src.index('boot_update() {'):src.index('\n}\n', src.index('boot_update() {'))]
        self.assertLess(bu.index('unlock_for_trial'), bu.index('write_boot "$dev" "$psize" "$tmp/new"'))
        rb = src[src.index('rollback_boot() {'):src.index('\n}\n', src.index('rollback_boot() {'))]
        self.assertLess(rb.index('unlock_for_trial'), rb.index('write_boot'))
        nb = self.tmp / 'nb'
        (nb / 'mu300-next-boot').parent.mkdir(parents=True, exist_ok=True)
        (nb / 'mu300-next-boot').write_text(f'#!/bin/sh\necho "$@" >> "{self.tmp}/nb.log"\n')
        (nb / 'mu300-next-boot').chmod(0o755)
        for shell in self.each_shell():
            r = self.sh(shell, f'. "{BIN}/mu300-update"; unlock_for_trial', MU300_LIB=1, MU300_BIN=nb,
                        MU300_DISK=self.disk, MU300_SYSROOT=self.root)
            self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(set((self.tmp / 'nb.log').read_text().split()), {'--trial'})

    def test_rollback_boot_brings_the_modules_of_its_image_back(self):
        # two builds of one kernel release share lib/modules/<release>: the set in place is kept with the image it
        # runs with, and goes back with it (seen on F50-B: rollback-boot to a 6.18.55 image with the other
        # release's 6.18.55 modules did not come up)
        b = self.tmp / 'bundle'
        (b / 'modules').mkdir(parents=True)
        (b / 'modules' / 'a.ko').write_bytes(b'new')
        (b / 'modules' / 'b.ko').write_bytes(b'new')
        (b / 'kernel.release').write_text('6.18.55\n')
        (self.disk / 'openwrt').mkdir()
        dirs = ('ubuntu/lib/modules/6.18.55/extra', 'openwrt/lib/modules/6.18.55')
        for shell in self.each_shell():
            shutil.rmtree(self.disk / 'boot', ignore_errors=True)
            for d in dirs:
                shutil.rmtree(self.disk / d, ignore_errors=True)
                (self.disk / d).mkdir(parents=True)
                (self.disk / d / 'a.ko').write_bytes(b'old')
            r = self.up(shell, f'BOOTDIR="{self.disk}/boot"; mkdir -p "$BOOTDIR"; prev_modules_save "{b}" && '
                               f'kernel_modules_into_systems "{b}" >/dev/null', MU300_NO_DEPMOD=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            for d in dirs:
                self.assertEqual(sorted(f.name for f in (self.disk / d).glob('*.ko')), ['a.ko', 'b.ko'])
            r = self.up(shell, f'BOOTDIR="{self.disk}/boot"; prev_modules_restore', MU300_NO_DEPMOD=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('modules of the previous image (6.18.55) are back', r.stdout)
            for d in dirs:
                self.assertEqual({f.name: f.read_bytes() for f in (self.disk / d).glob('*.ko')}, {'a.ko': b'old'})
            # a system that had no set of this release then has none after the rollback
            shutil.rmtree(self.disk / dirs[1])
            r = self.up(shell, f'BOOTDIR="{self.disk}/boot"; prev_modules_save "{b}" && '
                               f'kernel_modules_into_systems "{b}" >/dev/null && prev_modules_restore >/dev/null',
                        MU300_NO_DEPMOD=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list((self.disk / dirs[1]).glob('*.ko')), [])
            # a 5.4 bundle (no kernel.release) leaves the mainline sets alone, and keeps nothing to restore
            (b / 'kernel.release').rename(b / 'kr')
            r = self.up(shell, f'BOOTDIR="{self.disk}/boot"; prev_modules_save "{b}"; prev_modules_restore; echo done')
            (b / 'kr').rename(b / 'kernel.release')
            self.assertEqual(r.stdout, 'done\n', r.stderr)
            self.assertFalse((self.disk / 'boot/prev.modules').exists())

    def test_boot_update_keeps_the_modules_before_it_replaces_them(self):
        src = (BIN / 'mu300-update').read_text()
        bu = src[src.index('boot_update() {'):src.index('\n}\n', src.index('boot_update() {'))]
        # the replacing set goes in after the old one is kept, and before the image is written
        self.assertLess(bu.index('prev_modules_save "$tmp"'), bu.index('! kernel_modules_into_systems "$tmp"'))
        self.assertLess(bu.index('! kernel_modules_into_systems "$tmp"'), bu.index('write_boot "$dev" "$psize" "$tmp/new"'))
        # a failed write puts the old modules back with the old image
        fail = bu[bu.index('failed verification; restoring'):]
        self.assertIn('prev_modules_restore', fail[:fail.index('return 1')])
        rb = src[src.index('rollback_boot() {'):src.index('\n}\n', src.index('rollback_boot() {'))]
        self.assertLess(rb.index('write_boot'), rb.index('prev_modules_restore'))


if __name__ == '__main__':
    unittest.main()
