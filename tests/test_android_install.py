"""tools/android-install.sh: the SD card branch, cut out between its markers and run with stubs for Android's
tools (sm, mke2fs, umount) and files standing in for block devices."""
import io
import os
import re
import shutil
import tarfile

from helpers import TOP, ShellTest
from test_boot_init import fake_ext4

SRC = (TOP / 'tools' / 'android-install.sh').read_text()


class SdCard(ShellTest):
    def setUp(self):
        super().setUp()
        m = re.search(r'# --- sd begin\n(.*?)# --- sd end', SRC, re.S)
        self.assertIsNotNone(m, 'android-install.sh has no sd block')
        self.fn = m.group(1)
        self.dev = self.tmp / 'mmcblk1p1'
        self.stub('mke2fs', 'echo "mke2fs $*" >> "$STUBLOG/calls"')
        self.stub('umount', 'echo "umount $*" >> "$STUBLOG/calls"')
        (self.tmp / 'mounts').write_text('')

    def run_fn(self, shell, call, volumes='', still_mounted=False, sm_fails=False, pre=''):
        (self.tmp / 'volumes').write_text(volumes)
        after = volumes if still_mounted else volumes.replace(' mounted ', ' unmounted ')
        (self.tmp / 'volumes.after').write_text(after)
        fail = 'echo "Error: no volume manager" >&2; exit 3' if sm_fails else 'cat "$STUBLOG/volumes"'
        self.stub('sm', f'case "$1" in list-volumes) {fail} ;; '
                        'unmount) echo "sm unmount $2" >> "$STUBLOG/calls"; cp "$STUBLOG/volumes.after" "$STUBLOG/volumes" ;; esac')
        code = ('say() { echo "[device] $*"; }\n' + f'MU300_MOUNTS="{self.tmp}/mounts"\nMU300_SYSFS="{self.tmp}/sys"\n'
                + f'T="{self.tmp}"\n' + self.fn + f'\n{pre}\n{call}\necho "rc=$?"')
        r = self.sh(shell, code)
        calls = (self.tmp / 'calls').read_text() if (self.tmp / 'calls').exists() else ''
        (self.tmp / 'calls').unlink(missing_ok=True)
        return r.stdout, calls

    def test_blank_card_is_formatted(self):
        self.dev.write_bytes(bytes(4096))
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 1')
            self.assertIn('rc=0\n', out)
            # a card whose size cannot be read gets mke2fs's own ratio
            self.assertIn(f'mke2fs -t ext4 -F -b 4096 -m 0 -i 16384 -L mu300sd {self.dev}', calls)

    def test_big_card_gets_fewer_inodes(self):
        # one inode per 16 KiB on a 128 GB card is millions of inodes and a slow, failing format: the ratio grows
        # with the card, up to 1 MiB, and never below 65536 inodes (a small card keeps the default)
        self.dev.write_bytes(bytes(4096))
        size = self.tmp / 'sys' / 'class' / 'block' / 'mmcblk1p1' / 'size'
        size.parent.mkdir(parents=True)
        for sectors, ratio in ((1433600, 16384), (62333952, 262144), (249737216, 1048576), (3900000000, 1048576)):
            size.write_text(f'{sectors}\n')
            for shell in self.each_shell():
                out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 1')
                self.assertIn('rc=0\n', out)
                self.assertIn(f'-m 0 -i {ratio} -L mu300sd', calls, (sectors, shell))

    def test_foreign_ext4_is_refused(self):
        fake_ext4(self.dev, 'photos')
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 1')
            self.assertIn('rc=1\n', out)
            self.assertIn('photos', out)
            self.assertNotIn('mke2fs', calls)

    def test_unlabelled_ext4_is_refused(self):
        # an ext4 without a label is still someone's Linux data
        fake_ext4(self.dev, '')
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 1')
            self.assertIn('rc=1\n', out)
            self.assertIn('refusing to format', out)
            self.assertNotIn('mke2fs', calls)

    def test_non_ext4_card_is_formatted(self):
        # a FAT/exFAT card (magic bytes not 53ef): formatted after ERASE on the host
        fake_ext4(self.dev, 'NO NAME', magic=b'\x00\x00')
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 1')
            self.assertIn('rc=0\n', out)
            self.assertIn('mke2fs', calls)

    def test_existing_installation_is_kept_or_replaced(self):
        fake_ext4(self.dev, 'mu300sd')
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 0')
            self.assertIn('rc=0\n', out); self.assertNotIn('mke2fs', calls)
            out, calls = self.run_fn(shell, f'sd_prepare {self.dev} 1')
            self.assertIn('rc=0\n', out); self.assertIn('mke2fs', calls)

    def test_keep_without_installation_fails(self):
        self.dev.write_bytes(bytes(4096))
        for shell in self.each_shell():
            out, _ = self.run_fn(shell, f'sd_prepare {self.dev} 0')
            self.assertIn('rc=1\n', out)

    def test_android_releases_the_card(self):
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_release {self.dev}', volumes='public:179,1 mounted ABCD-1234\n')
            self.assertIn('rc=0\n', out)
            self.assertIn('sm unmount public:179,1', calls)

    def test_card_android_keeps_is_refused(self):
        for shell in self.each_shell():
            out, _ = self.run_fn(shell, f'sd_release {self.dev}', volumes='public:179,1 mounted ABCD-1234\n',
                                 still_mounted=True)
            self.assertIn('rc=1\n', out)

    def test_adopted_card_is_refused(self):
        # a card adopted as internal storage is encrypted and part of Android's data: never ours to take
        for shell in self.each_shell():
            for vols in ('private:179,3 mounted 1234-uuid\n', 'private:179,2 unmounted 1234-uuid\n'):
                out, calls = self.run_fn(shell, f'sd_release {self.dev}', volumes=vols)
                self.assertIn('rc=1\n', out)
                self.assertNotIn('sm unmount', calls)

    def test_failing_volume_manager_is_a_refusal(self):
        # no answer from sm is no proof that Android has let go of the card
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_release {self.dev}', sm_fails=True)
            self.assertIn('rc=1\n', out)
            self.assertNotIn('umount', calls)

    def test_usb_stick_is_left_alone(self):
        # public:8,1 is a USB disk (major 8): neither unmounted nor a reason to refuse; only the card (179) counts
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_release {self.dev}', still_mounted=True,
                                     volumes='public:8,1 mounted 5555-6666\n')
            self.assertIn('rc=0\n', out)
            self.assertNotIn('sm unmount', calls)

    def test_builtin_private_storage_is_not_an_adopted_card(self):
        # Android lists its own data partition as "private mounted null" (no colon): that is no reason to refuse
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_release {self.dev}',
                                     volumes='private mounted null\nemulated;0 mounted null\n'
                                             'public:179,1 mounted ABCD-1234\n')
            self.assertIn('rc=0\n', out)
            self.assertIn('sm unmount public:179,1', calls)

    def test_leftover_mounts_of_the_card_only(self):
        # vold mounts the card through /dev/block/vold/public:179,N, which sm unmount takes care of; these are
        # mounts of the card's own nodes made by hand. They go; the eMMC (mmcblk0) and another card (mmcblk10) stay
        t = self.tmp
        (t / 'mounts').write_text(f'{t}/mmcblk0p40 /data ext4 rw 0 0\n'
                                  f'{t}/mmcblk1p1 /mnt/media_rw/ABCD vfat rw 0 0\n'
                                  f'{t}/mmcblk1p2 /mnt/other ext4 rw 0 0\n'
                                  f'{t}/mmcblk10p1 /mnt/ten vfat rw 0 0\n')
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_release {self.dev}')
            self.assertIn('rc=0\n', out)
            self.assertIn('umount /mnt/media_rw/ABCD', calls)
            self.assertIn('umount /mnt/other', calls)
            self.assertNotIn('/data', calls); self.assertNotIn('/mnt/ten', calls)
            self.assertNotIn('mmcblk0', calls); self.assertNotIn('mmcblk10', calls)

    def test_whole_card_never_reaches_the_emmc(self):
        # a card without a partition table: SD_DEV is mmcblk1 itself, and mmcblk0 must stay mounted
        t = self.tmp
        (t / 'mounts').write_text(f'{t}/mmcblk0 /emmc ext4 rw 0 0\n'
                                  f'{t}/mmcblk0p40 /data ext4 rw 0 0\n'
                                  f'{t}/mmcblk1 /mnt/media_rw/ABCD vfat rw 0 0\n')
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, f'sd_release {t}/mmcblk1')
            self.assertIn('rc=0\n', out)
            self.assertIn('umount /mnt/media_rw/ABCD', calls)
            self.assertNotIn('/data', calls); self.assertNotIn('/emmc', calls)
            self.assertNotIn('mmcblk0', calls)

    def sys_type(self, disk, kind):
        d = self.tmp / 'sys' / 'block' / disk / 'device'
        d.mkdir(parents=True, exist_ok=True)
        (d / 'type').write_text(kind + '\n')

    def test_emmc_is_never_the_card(self):
        self.sys_type('mmcblk0', 'SD')   # even when sysfs would claim it
        for shell in self.each_shell():
            for dev in ('/dev/block/mmcblk0p40', '/dev/block/mmcblk0'):
                out, _ = self.run_fn(shell, f'sd_check {dev}')
                self.assertIn('rc=1\n', out, dev)

    def test_non_sd_device_is_refused(self):
        self.sys_type('mmcblk1', 'SDIO')
        for shell in self.each_shell():
            out, _ = self.run_fn(shell, 'sd_check /dev/block/mmcblk1p1')
            self.assertIn('rc=1\n', out)
            out, _ = self.run_fn(shell, 'sd_check /dev/block/mmcblk2p1')   # no sysfs entry at all
            self.assertIn('rc=1\n', out)

    def test_sd_card_is_accepted(self):
        self.sys_type('mmcblk1', 'SD')
        for shell in self.each_shell():
            for dev in ('/dev/block/mmcblk1p1', '/dev/block/mmcblk1'):
                out, _ = self.run_fn(shell, f'sd_check {dev}')
                self.assertIn('rc=0\n', out, dev)

    def test_fstab_names_the_card(self):
        r = self.tmp / 'ubuntu'
        (r / 'etc').mkdir(parents=True)
        (r / 'etc' / 'fstab').write_text('# static\nLABEL=mu300root / ext4 defaults,noatime 0 1\n'
                                         'tmpfs /tmp tmpfs defaults 0 0\n')
        for shell in self.each_shell():
            out, _ = self.run_fn(shell, f'sd_fstab {r}', pre='set -e')
            self.assertIn('rc=0\n', out)
            self.assertEqual((r / 'etc' / 'fstab').read_text(),
                             '# static\nLABEL=mu300sd / ext4 defaults,noatime 0 1\ntmpfs /tmp tmpfs defaults 0 0\n')
            out, _ = self.run_fn(shell, f'sd_fstab {self.tmp}/openwrt', pre='set -e')   # no fstab: nothing to do
            self.assertIn('rc=0\n', out)

    def fake_mount_helper(self, body):
        (self.tmp / 'android-mount-mu300root.sh').write_text(
            'echo "helper $*" >> "$STUBLOG/calls"\n' + body + '\n')

    def test_internal_installation_is_marked(self):
        self.fake_mount_helper('[ "$1" = -u ] || mkdir -p "$1"')
        mark = self.tmp / 'mu300root-internal' / '.mu300' / 'root-on-sd'
        for shell in self.each_shell():
            out, calls = self.run_fn(shell, 'sd_mark_internal', pre='set -e; SD_MODE=1 OFF=1 SIZE=2 INTERNAL_EXISTS=1')
            self.assertIn('rc=0\n', out)
            self.assertTrue(mark.exists())
            self.assertIn(f'helper -u {self.tmp}/mu300root-internal', calls)
            mark.unlink()

    def test_marker_needs_an_internal_installation(self):
        self.fake_mount_helper('[ "$1" = -u ] || mkdir -p "$1"')
        for shell in self.each_shell():
            for pre in ('SD_MODE=1 OFF=1 SIZE=2 INTERNAL_EXISTS=0', 'SD_MODE=1 INTERNAL_EXISTS=1',
                        'SD_MODE=0 OFF=1 SIZE=2 INTERNAL_EXISTS=1'):
                out, calls = self.run_fn(shell, 'sd_mark_internal', pre='set -e; ' + pre)
                self.assertIn('rc=0\n', out, pre)
                self.assertNotIn('helper', calls, pre)

    def test_marker_never_fails_the_install(self):
        for shell in self.each_shell():
            self.fake_mount_helper('exit 1')   # the internal region does not mount
            out, _ = self.run_fn(shell, 'sd_mark_internal', pre='set -e; SD_MODE=1 OFF=1 SIZE=2 INTERNAL_EXISTS=1')
            self.assertIn('rc=0\n', out)
            # it mounts, but the marker cannot be written (the mount point is a file)
            self.fake_mount_helper('[ "$1" = -u ] || : > "$1"')
            out, calls = self.run_fn(shell, 'sd_mark_internal', pre='set -e; SD_MODE=1 OFF=1 SIZE=2 INTERNAL_EXISTS=1')
            self.assertIn('rc=0\n', out)
            self.assertIn('helper -u', calls)
            (self.tmp / 'mu300root-internal').unlink()
            # the directory is there but the marker is not writable (a directory in its place)
            self.fake_mount_helper('[ "$1" = -u ] || mkdir -p "$1/.mu300/root-on-sd"')
            out, calls = self.run_fn(shell, 'sd_mark_internal', pre='set -e; SD_MODE=1 OFF=1 SIZE=2 INTERNAL_EXISTS=1')
            self.assertIn('rc=0\n', out)
            self.assertIn('helper -u', calls)
            shutil.rmtree(self.tmp / 'mu300root-internal')

    def test_internal_install_removes_a_stale_marker(self):
        # SD_MODE=0 installs into the internal filesystem; a root-on-sd left there from an earlier card
        # installation would make init wait for a card that is no longer what should boot
        m = self.tmp / 'root'
        for shell in self.each_shell():
            (m / '.mu300').mkdir(parents=True, exist_ok=True)
            (m / '.mu300' / 'root-on-sd').touch()
            out, _ = self.run_fn(shell, f'sd_unmark {m}', pre='set -e; SD_MODE=1')
            self.assertIn('rc=0\n', out)
            self.assertTrue((m / '.mu300' / 'root-on-sd').exists())
            out, _ = self.run_fn(shell, f'sd_unmark {m}', pre='set -e; SD_MODE=0')
            self.assertIn('rc=0\n', out)
            self.assertFalse((m / '.mu300' / 'root-on-sd').exists())
            out, _ = self.run_fn(shell, f'sd_unmark {m}', pre='set -e; unset SD_MODE')   # older env files
            self.assertIn('rc=0\n', out)

    def test_unmark_runs_on_the_installed_filesystem(self):
        self.assertIn('\nsd_unmark $M\n', SRC)
        self.assertLess(SRC.index('mkdir -p $M/.mu300\n'), SRC.index('\nsd_unmark $M\n'))


class Extras(ShellTest):
    """the extras block: pushed mu300-extra-<name>.tar.gz go onto the Linux partition (the VPN module of
    dikeckaan/mu300-linux-vpn as mu300-extra-vpn.tar.gz), and an update of a system that uses the VPN without the
    module says that its VPN stays off"""

    def setUp(self):
        super().setUp()
        m = re.search(r'# --- extra begin\n(.*?)# --- extra end', SRC, re.S)
        self.assertIsNotNone(m, 'android-install.sh has no extra block')
        self.fn = m.group(1)
        self.m = self.tmp / 'mu300root'
        (self.m / 'ubuntu/etc/mu300').mkdir(parents=True)

    def run_fn(self, shell, call):
        code = 'set -e\nsay() { echo "[device] $*"; }\n' + f'T="{self.tmp}"\nM="{self.m}"\n' + self.fn + f'\n{call}\necho "rc=$?"'
        return self.sh(shell, code)

    def test_pushed_module_is_installed(self):
        from test_extra import extra_tarball, module_tarball
        for shell in self.each_shell():
            shutil.rmtree(self.m / 'extra', ignore_errors=True)
            module_tarball(self.tmp / 'mu300-extra-vpn.tar.gz', version='v1.0.0')
            r = self.run_fn(shell, 'extra_from_push $M')
            self.assertIn('rc=0', r.stdout, r.stderr)
            self.assertIn('extra vpn installed (v1.0.0)', r.stdout)
            self.assertEqual((self.m / 'extra/vpn/VERSION').read_text().strip(), 'v1.0.0')
            self.assertTrue(os.access(self.m / 'extra/vpn/bin/mu300-vpn', os.X_OK))
            self.assertTrue((self.m / 'extra/vpn/hooks/link').is_file())
            self.assertFalse((self.tmp / 'mu300-extra-vpn.tar.gz').exists())
            # a broken push, or the engines alone (an older release's vpn extra), is skipped, never the install
            for bad in ('junk', 'engines'):
                if bad == 'junk':
                    (self.tmp / 'mu300-extra-vpn.tar.gz').write_bytes(b'junk')
                else:
                    extra_tarball(self.tmp / 'mu300-extra-vpn.tar.gz', name=None)
                r = self.run_fn(shell, 'extra_from_push $M')
                self.assertIn('rc=0', r.stdout, r.stderr)
                self.assertIn('skipped', r.stdout, bad)
                self.assertEqual((self.m / 'extra/vpn/VERSION').read_text().strip(), 'v1.0.0', bad)
            # the extras of mu300-linux's own releases still go in by their ./name
            extra_tarball(self.tmp / 'mu300-extra-lang.tar.gz', name='lang', bins=())
            r = self.run_fn(shell, 'extra_from_push $M')
            self.assertIn('extra lang installed (v2026.10.10)', r.stdout)
            # nothing pushed: nothing happens
            r = self.run_fn(shell, 'extra_from_push $M')
            self.assertIn('rc=0', r.stdout, r.stderr)

    def test_an_update_says_when_the_vpn_stays_off(self):
        from test_extra import module_tarball
        old = self.m / 'ubuntu'
        for shell in self.each_shell():
            for enable, module, warned in (('0', False, False), ('1', False, True), ('1', True, False)):
                shutil.rmtree(self.m / 'extra', ignore_errors=True)
                if module:
                    module_tarball(self.tmp / 'mu300-extra-vpn.tar.gz')
                    self.run_fn(shell, 'extra_from_push $M')
                (old / 'etc/mu300/vpn.conf').write_text(f'ENABLE={enable}\n')
                r = self.run_fn(shell, 'extra_keep_vpn $M $M/ubuntu')
                self.assertIn('rc=0', r.stdout, r.stderr)
                self.assertEqual('mu300-extra install vpn' in r.stdout, warned, (enable, module))

    def test_an_update_over_a_kill_switch_without_the_module_is_refused(self):
        # the VPN on with its kill switch in a system being replaced, and no module pushed or installed: nothing is
        # changed (as mu300-update apply); with the kill switch off, or with the module, it goes on
        from test_extra import module_tarball
        old = self.m / 'ubuntu'
        for shell in self.each_shell():
            for conf, module, update, refused in (('ENABLE=1\nKILL_SWITCH=1\n', False, '1', True),
                                                  ('ENABLE=1\n', False, '1', True),          # default: on
                                                  ("ENABLE='1'\nKILL_SWITCH='1'\n", False, '1', True),
                                                  ('ENABLE=1\nKILL_SWITCH=0\n', False, '1', False),
                                                  ('ENABLE=0\nKILL_SWITCH=1\n', False, '1', False),
                                                  ('ENABLE=1\nKILL_SWITCH=1\n', True, '1', False),
                                                  ('ENABLE=1\nKILL_SWITCH=1\n', False, '0', False)):   # a fresh install
                shutil.rmtree(self.m / 'extra', ignore_errors=True)
                if module:
                    module_tarball(self.tmp / 'mu300-extra-vpn.tar.gz')
                    self.run_fn(shell, 'extra_from_push $M')
                (old / 'etc/mu300/vpn.conf').write_text(conf)
                code = (f'set -e\nsay() {{ echo "[device] $*"; }}\nT="{self.tmp}"\nM="{self.m}"\nOSES="ubuntu openwrt"\n'
                        f'UPDATE={update}\n' + self.fn + '\nextra_vpn_precheck $M\necho "rc=$?"')
                r = self.sh(shell, code)
                if refused:
                    self.assertNotEqual(r.returncode, 0, (conf, module, update))
                    self.assertNotIn('rc=0', r.stdout)
                    self.assertIn('kill switch in the ubuntu being replaced', r.stdout)
                    self.assertIn('nothing was changed', r.stdout)
                    self.assertIn('MU300_VPN_MODULE', r.stdout)
                    self.assertIn('ENABLE=0', r.stdout)
                else:
                    self.assertIn('rc=0', r.stdout, (conf, module, update, r.stderr))

    def test_order_in_the_install(self):
        self.assertIn('\nextra_from_push $M\nextra_vpn_precheck $M\n', SRC)
        # refused before anything is replaced: the systems come after
        self.assertLess(SRC.index('\nextra_vpn_precheck $M\n'), SRC.index('rm -rf $M/$os && mv $M/$os.new $M/$os'))
        self.assertIn('\nextra_from_push $M\n', SRC)
        # the previous system is looked at before it is removed
        self.assertLess(SRC.index('extra_keep_vpn $M $M/$os'), SRC.index('rm -rf $M/$os && mv $M/$os.new $M/$os'))

def make_tar(path, files):
    with tarfile.open(path, 'w:gz') as t:
        for name, text in files.items():
            data = text.encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))


class Systems(ShellTest):
    """The wipe of a root-level Ubuntu and the per-system install loop, run on a fake /data/local/tmp (T) and a
    fake mounted filesystem (M)."""

    def setUp(self):
        super().setUp()
        self.T = self.tmp / 'T'
        self.M = self.T / 'mu300root'
        (self.M / '.mu300').mkdir(parents=True)
        # Android's sed has -i like GNU's; the Mac's wants an argument
        real = shutil.which('sed')   # resolved before the stubs are on PATH; /usr/bin/sed is not there on Alpine
        self.stub('sed', f'S={real}\nif [ "$1" = -i ]; then shift; if "$S" --version >/dev/null 2>&1; then exec "$S" -i "$@"; '
                         'else exec "$S" -i "" "$@"; fi; fi; exec "$S" "$@"')
        self.wipe = self.block('legacy-wipe')
        self.install = self.block('install-os')
        self.upk = self.block('user-packages')

    def block(self, name):
        m = re.search(rf'# --- {name} begin\n(.*?)# --- {name} end', SRC, re.S)
        self.assertIsNotNone(m, f'android-install.sh has no {name} block')
        return m.group(1)

    def tarball(self, os, extra=None):
        files = {'etc/shadow': 'root:*:19000:0:99999:7:::\nubuntu:*:19000:0:99999:7:::\n', 'etc/config/network': 'new\n'}
        files.update(extra or {})
        make_tar(self.T / f'mu300-{os}.tar.gz', files)

    def run_install(self, shell, fails=False, **env):
        e = dict(OSES='openwrt-luci', UPDATE='0', PWHASH='', DEFAULT_LINUX='0', BOOT_OS='openwrt-luci', WIPE_LEGACY='0')
        e.update(env)
        # sd_unmark and extra_keep_vpn are other blocks of the script (SdCard and Extras test them)
        pre = ('set -e\nsay() { echo "[device] $*"; }\nsd_unmark() { :; }\nextra_keep_vpn() { :; }\nssid=; psk=\n'
               + f'T="{self.T}"; M="{self.M}"\n' + self.upk)
        r = self.sh(shell, pre + self.install, **e)
        if fails:
            self.assertNotEqual(r.returncode, 0, r.stderr + r.stdout)
        else:
            self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        return r

    def test_installs_openwrt_luci(self):
        for shell in self.each_shell():
            shutil.rmtree(self.M / 'openwrt-luci', ignore_errors=True)
            self.tarball('openwrt-luci')
            self.run_install(shell, PWHASH='$6$salt$hash')
            self.assertTrue((self.M / 'openwrt-luci' / 'etc' / 'config' / 'network').exists())
            shadow = (self.M / 'openwrt-luci' / 'etc' / 'shadow').read_text()
            self.assertIn('root:$6$salt$hash:', shadow)
            self.assertIn('ubuntu:*:', shadow)
            self.assertEqual((self.M / '.mu300' / 'boot-os').read_text().strip(), 'openwrt-luci')
            self.assertFalse((self.T / 'mu300-openwrt-luci.tar.gz').exists())

    def test_update_keeps_openwrt_luci_config(self):
        for shell in self.each_shell():
            old = self.M / 'openwrt-luci' / 'etc' / 'config'
            old.mkdir(parents=True, exist_ok=True)
            (old / 'network').write_text('mine\n')
            self.tarball('openwrt-luci')
            self.run_install(shell, UPDATE='1', PWHASH='$6$salt$hash')
            self.assertEqual((self.M / 'openwrt-luci' / 'etc' / 'config' / 'network').read_text(), 'mine\n')

    IMAGE = {'etc/passwd': 'root:x:0:0:root:/root:/bin/bash\nubuntu:x:1000:1000::/home/ubuntu:/bin/bash\n'
                           'newsvc:x:120:120::/:/usr/sbin/nologin\n',
             'etc/group': 'root:x:0:\nsudo:x:27:ubuntu\nubuntu:x:1000:\nnewsvc:x:120:\n',
             'etc/shadow': 'root:*:19000:0:99999:7:::\nubuntu:$6$image$ubuntu:19000:0:99999:7:::\nnewsvc:!:19000::::::\n',
             'etc/gshadow': 'root:*::\nsudo:*::ubuntu\nubuntu:!::\nnewsvc:!::\n',
             'etc/.mu300-accounts-from-image': ''}
    OLD = {'passwd': 'root:x:0:0:root:/root:/bin/bash\nubuntu:x:1000:1000::/home/ubuntu:/bin/bash\n'
                     'kaan:x:1001:1001::/home/kaan:/bin/bash\n',
           'group': 'root:x:0:\nsudo:x:27:ubuntu,kaan\nubuntu:x:1000:\nkaan:x:1001:\n',
           'shadow': 'root:$6$old$root:19000:0:99999:7:::\nubuntu:$6$old$ubuntu:19000:0:99999:7:::\n'
                     'kaan:$6$old$kaan:19000:0:99999:7:::\n',
           'gshadow': 'root:*::\nsudo:*::ubuntu,kaan\nubuntu:!::\nkaan:!::\n'}

    def old_ubuntu(self):
        shutil.rmtree(self.M / 'ubuntu', ignore_errors=True)
        etc = self.M / 'ubuntu' / 'etc'
        etc.mkdir(parents=True)
        for f, text in self.OLD.items():
            (etc / f).write_text(text)
        self.tarball('ubuntu', self.IMAGE)

    def test_update_keeps_the_accounts(self):
        # update (keep) without a new password: the accounts are the device's, as mu300-update carries them over -
        # the old hashes, the users and group memberships added on the device; the image's new system user stays
        for shell in self.each_shell():
            self.old_ubuntu()
            self.run_install(shell, OSES='ubuntu', BOOT_OS='ubuntu', UPDATE='1')
            etc = self.M / 'ubuntu' / 'etc'
            shadow = (etc / 'shadow').read_text()
            for line in ('root:$6$old$root:', 'ubuntu:$6$old$ubuntu:', 'kaan:$6$old$kaan:', 'newsvc:!:'):
                self.assertIn(line, shadow)
            self.assertNotIn('$6$image$', shadow)
            self.assertIn('kaan:x:1001:1001:', (etc / 'passwd').read_text())
            self.assertIn('newsvc:x:120:', (etc / 'passwd').read_text())
            self.assertIn('sudo:x:27:ubuntu,kaan\n', (etc / 'group').read_text())
            self.assertIn('kaan:!::\n', (etc / 'gshadow').read_text())
            self.assertFalse((etc / '.mu300-accounts-from-image').exists())

    def test_update_with_a_new_password_keeps_the_other_accounts(self):
        for shell in self.each_shell():
            self.old_ubuntu()
            self.run_install(shell, OSES='ubuntu', BOOT_OS='ubuntu', UPDATE='1', PWHASH='$6$new$hash')
            shadow = (self.M / 'ubuntu' / 'etc' / 'shadow').read_text()
            self.assertIn('ubuntu:$6$new$hash:', shadow)
            self.assertIn('kaan:$6$old$kaan:', shadow)
            self.assertFalse((self.M / 'ubuntu' / 'etc' / '.mu300-accounts-from-image').exists())

    def test_fresh_install_takes_the_hash(self):
        for shell in self.each_shell():
            shutil.rmtree(self.M / 'ubuntu', ignore_errors=True)
            self.tarball('ubuntu', self.IMAGE)
            self.run_install(shell, OSES='ubuntu', BOOT_OS='ubuntu', UPDATE='0', PWHASH='$6$new$hash')
            shadow = (self.M / 'ubuntu' / 'etc' / 'shadow').read_text()
            self.assertIn('ubuntu:$6$new$hash:', shadow)
            self.assertNotIn('kaan', shadow)

    def test_never_a_default_or_empty_password(self):
        # fail closed: without a new hash a system is installed only when its account keeps a real hash of its own;
        # otherwise the old system stays as it was and the install stops (the boot image is never armed)
        cases = (  # name, os, the old system's shadow (None: no old system / no shadow file), image shadow
            ('fresh, no hash given', 'ubuntu', None, None),
            ('old system without a shadow', 'ubuntu', '', None),
            ('OpenWrt root with an empty password', 'openwrt', 'root::19000:0:99999:7:::\n', None),
            ('locked account', 'ubuntu', 'root:*:1::\nubuntu:!:19000::::::\n', None),
            ('no entry for the account', 'ubuntu', 'root:$6$a$b:1::\n', None),
            ('the image default carried over', 'ubuntu', 'root:*:1::\nubuntu:$6$image$ubuntu:19000::::::\n', None))
        for name, os_, old, _ in cases:
            with self.subTest(name):
                for shell in self.each_shell():
                    shutil.rmtree(self.M / os_, ignore_errors=True)
                    image = dict(self.IMAGE)
                    if os_ == 'openwrt':
                        image['etc/shadow'] = 'root::19000:0:99999:7:::\n'
                    self.tarball(os_, image)
                    if old is not None:
                        (self.M / os_ / 'etc').mkdir(parents=True)
                        (self.M / os_ / 'etc' / 'precious').write_text('old\n')
                        if old:
                            (self.M / os_ / 'etc' / 'shadow').write_text(old)
                    r = self.run_install(shell, fails=True, OSES=os_, BOOT_OS=os_, UPDATE='1' if old is not None else '0')
                    self.assertIn('would keep no password of its own', r.stdout)
                    self.assertFalse((self.M / f'{os_}.new').exists())
                    if old is not None:
                        self.assertEqual((self.M / os_ / 'etc' / 'precious').read_text(), 'old\n')
                    else:
                        self.assertFalse((self.M / os_).exists())
        # the same with a new hash: installed, the hash in place
        for shell in self.each_shell():
            shutil.rmtree(self.M / 'openwrt', ignore_errors=True)
            self.tarball('openwrt', {'etc/shadow': 'root::19000:0:99999:7:::\n'})
            self.run_install(shell, OSES='openwrt', BOOT_OS='openwrt', PWHASH='$6$new$hash')
            self.assertIn('root:$6$new$hash:', (self.M / 'openwrt' / 'etc' / 'shadow').read_text())

    def test_accounts_merge_is_mu300_updates(self):
        # one merge, two copies: android-install.sh runs on Android and cannot source the system's mu300-update
        upd = (TOP / 'rootfs/overlay/opt/mu300/bin/mu300-update').read_text()
        fn = re.compile(r'^merge_accounts\(\) \{.*?^\}\n', re.S | re.M)
        self.assertEqual(fn.search(self.install).group(0), fn.search(upd).group(0))

    def test_legacy_wipe_keeps_openwrt_luci(self):
        (self.M / 'lib' / 'systemd').mkdir(parents=True)
        (self.M / 'lib' / 'systemd' / 'systemd').write_text('x'); (self.M / 'lib' / 'systemd' / 'systemd').chmod(0o755)
        (self.M / 'etc').mkdir()
        (self.M / 'openwrt-luci' / 'etc').mkdir(parents=True)
        (self.M / 'ubuntu').mkdir()
        for shell in self.each_shell():
            self.sh(shell, f'say() {{ :; }}; M="{self.M}"; WIPE_LEGACY=1\n' + self.wipe)
            self.assertTrue((self.M / 'openwrt-luci' / 'etc').is_dir())
            self.assertTrue((self.M / 'ubuntu').is_dir())
            self.assertTrue((self.M / '.mu300').is_dir())
            self.assertFalse((self.M / 'lib').exists())
            self.assertFalse((self.M / 'etc').exists())
            (self.M / 'lib' / 'systemd').mkdir(parents=True)
            (self.M / 'lib' / 'systemd' / 'systemd').write_text('x'); (self.M / 'lib' / 'systemd' / 'systemd').chmod(0o755)
