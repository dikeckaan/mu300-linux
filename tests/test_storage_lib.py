"""The internal disk and its partitions, found the one way (rootfs/overlay/opt/mu300/lib/storage.sh): an eMMC
(mmcblkN) as before, and a UFS (sdX below the UFS host) as on the 1 TB U30 Air of issue #396 - for init, early-recorder,
android-vendor-start, mu300-cpu and mu300-update's copy - and the Android side's lookup through by-name."""
import os
import re
import shutil

from helpers import BIN, TOP, ShellTest

LIB = TOP / 'rootfs' / 'overlay' / 'opt' / 'mu300' / 'lib' / 'storage.sh'
INIT = (TOP / 'boot' / 'init').read_text()
# the U30 Air of issue #396: misc is sda3, boot_a/boot_b sda37/38, userdata sda75; sdb and sdc are 4 MiB boot LUs
UFS_GPT = {3: 'misc', 37: 'boot_a', 38: 'boot_b', 75: 'userdata'}


def block(text, name):
    m = re.search(rf'# --- {name} begin\n(.*?)# --- {name} end', text, re.S)
    assert m, f'no {name} block'
    return m.group(1)


class Fake:
    """A sysfs (ROOT/sys) as the kernel lays it out: /sys/block/X a link into /sys/devices, partitions below the disk,
    /sys/class/block links to every disk and partition."""

    def __init__(self, root):
        self.root = root
        self.sys = root / 'sys'
        (self.sys / 'block').mkdir(parents=True)
        (self.sys / 'class' / 'block').mkdir(parents=True)

    def disk(self, name, where, parts, typ=None, lbs=512):
        d = self.sys / 'devices' / where / 'block' / name
        (d / 'queue').mkdir(parents=True)
        (d / 'queue' / 'logical_block_size').write_text(f'{lbs}\n')
        (d / 'device').mkdir()
        if typ:
            (d / 'device' / 'type').write_text(typ + '\n')
        os.symlink(d, self.sys / 'block' / name)
        os.symlink(d, self.sys / 'class' / 'block' / name)
        prefix = name + 'p' if name[-1].isdigit() else name
        for n, label in parts.items():
            p = d / f'{prefix}{n}'
            p.mkdir()
            (p / 'partition').write_text(f'{n}\n')
            (p / 'uevent').write_text(f'MAJOR=8\nDEVNAME={prefix}{n}\nDEVTYPE=partition\nPARTN={n}\nPARTNAME={label}\n')
            os.symlink(p, self.sys / 'class' / 'block' / p.name)

    def ufs(self):
        host = 'platform/soc/soc:ap-ahb/22000000.ufs/host0/target0:0:0'
        self.disk('sda', f'{host}/0:0:0:0', UFS_GPT, lbs=4096)
        self.disk('sdb', f'{host}/0:0:0:1', {}, lbs=4096)
        self.disk('sdc', f'{host}/0:0:0:2', {}, lbs=4096)

    def usb(self, name='sdd'):   # a USB stick with a raw clone of a device backup on it
        self.disk(name, 'platform/usb/usb1/1-1/1-1:1.0/host1/target1:0:0/1:0:0:0', UFS_GPT)

    def emmc(self, name='mmcblk0', typ='MMC'):
        self.disk(name, f'platform/soc/sdio/mmc0/{name[6:]}', {5: 'misc', 6: 'boot_a', 7: 'boot_b'}, typ=typ)


class Library(ShellTest):
    def run_lib(self, shell, fake, code):
        r = self.sh(shell, f'. "{LIB}"\n{code}', MU300_SYS=fake.sys)
        return r.stdout.strip()

    def test_ufs_unit(self):
        f = Fake(self.tmp / 'r'); f.ufs()
        for shell in self.each_shell():
            self.assertEqual(self.run_lib(shell, f, 'mu300_storage_disk'), 'sda', shell)
            self.assertEqual(self.run_lib(shell, f, 'mu300_storage_part misc; mu300_storage_part boot_b; '
                                                    'mu300_storage_part userdata sda'), 'sda3\nsda38\nsda75', shell)
            self.assertEqual(self.run_lib(shell, f, 'mu300_storage_prefix sda; mu300_storage_sector_size sda; '
                                                    'mu300_storage_ufs sda && echo ufs'), 'sda\n4096\nufs', shell)
            self.assertEqual(self.run_lib(shell, f, 'mu300_storage_part nothing; echo rc=$?'), 'rc=1', shell)

    def test_emmc_unit_as_before(self):
        f = Fake(self.tmp / 'r'); f.emmc('mmcblk1'); f.emmc('mmcblk0', typ='SD')   # the card took mmc0 (31l)
        for shell in self.each_shell():
            self.assertEqual(self.run_lib(shell, f, 'mu300_storage_disk; mu300_storage_part boot_a; '
                                                    'mu300_storage_prefix mmcblk1; mu300_storage_sector_size mmcblk1; '
                                                    'mu300_storage_mmc SD'),
                             'mmcblk1\nmmcblk1p6\nmmcblk1p\n512\nmmcblk0', shell)

    def test_never_a_usb_disk_or_a_card(self):
        # a USB stick or a card can carry the same GPT names; without the UFS (its driver not bound yet) nothing is found
        f = Fake(self.tmp / 'r'); f.usb('sda'); f.emmc('mmcblk0', typ='SD')
        for shell in self.each_shell():
            self.assertEqual(self.run_lib(shell, f, 'mu300_storage_disk; echo rc=$?; mu300_storage_part misc; echo rc=$?'),
                             'rc=1\nrc=1', shell)
        # the UFS there too, after the stick in the order of names
        g = Fake(self.tmp / 'g'); g.usb('sda')
        g.disk('sdb', 'platform/soc/soc:ap-ahb/22000000.ufs/host0/target0:0:0/0:0:0:0', UFS_GPT, lbs=4096)
        for shell in self.each_shell():
            self.assertEqual(self.run_lib(shell, g, 'mu300_storage_disk; mu300_storage_part boot_a'), 'sdb\nsdb37', shell)

    def test_set_e_and_no_variables_of_the_caller(self):
        f = Fake(self.tmp / 'r'); f.ufs()
        for shell in self.each_shell():
            r = self.sh(shell, f'set -e\nb=keep; d=keep; e=keep; p=keep\n. "{LIB}"\nmu300_storage_disk >/dev/null || :\nmu300_storage_mmc SD; mu300_storage_parts sda\n'
                               'x=$(mu300_storage_part none) || x=none\necho "$b $d $e $p $x"', MU300_SYS=self.tmp / 'none')
            self.assertEqual((r.returncode, r.stdout), (0, 'keep keep keep keep none\n'), (shell, r.stderr))
        self.assertNotRegex(LIB.read_text(), r'(?m)^\s*local ')   # mksh, ash and dash alike: no "local"

    def test_mu300_update_carries_the_same(self):
        # a self-update runs the new mu300-update on a system that may not have lib/storage.sh: a copy, the same
        self.assertEqual(block((BIN / 'mu300-update').read_text(), 'storage'), block(LIB.read_text(), 'storage'))

    def test_the_ramdisk_has_it(self):
        src = (TOP / 'boot' / 'build-boot-image.py').read_text()
        self.assertIn("'etc/mu300-storage.sh': (text(HERE.parent / 'rootfs/overlay/opt/mu300/lib/storage.sh')", src)
        self.assertIn('_sl=${MU300_STORAGE_LIB:-/etc/mu300-storage.sh}', INIT)
        self.assertIn('rootfs/overlay/opt/mu300/lib/storage.sh',
                      (TOP / 'android' / 'magisk' / 'computer' / 'files.txt').read_text().split())


class UfsLookups(ShellTest):
    """init, early-recorder, android-vendor-start and mu300-update on the UFS unit find the same partitions."""

    def test_every_lookup_on_the_ufs(self):
        f = Fake(self.tmp / 'r'); f.ufs(); f.usb()
        for shell in self.each_shell():
            init = self.sh(shell, 'log() { :; }\n' + block(INIT, 'emmc') + '\nemmc_dev; emmc_part misc; emmc_part boot_b',
                           MU300_SYS=f.sys, MU300_DEV='/dev').stdout
            self.assertEqual(init, '/dev/sda\n/dev/sda3\n/dev/sda38\n', shell)
            rec = self.sh(shell, 'PART=boot_a\n' + block((BIN / 'early-recorder').read_text(), 'part')
                          + '\necho "$LOGDEV $LOGSYS"', MU300_SYS=f.sys).stdout
            self.assertEqual(rec, f'/dev/sda37 {f.sys}/block/sda/sda37\n', shell)
            upd = self.sh(shell, f'. "{BIN}/mu300-update"; part_dev boot_b', MU300_LIB=1, MU300_BIN=BIN,
                          MU300_SYSROOT=f.root).stdout
            self.assertEqual(upd, '/dev/sda38\n', shell)
            avs = self.sh(shell, 'set -e\n' + block((BIN / 'android-vendor-start').read_text(), 'emmc')
                          + '\necho "$E $(mu300_storage_prefix "$E")"', MU300_SYS=f.sys)
            self.assertEqual((avs.returncode, avs.stdout), (0, 'sda sda\n'), (shell, avs.stderr))

    def test_init_by_name_links_and_region_take_the_disk_prefix(self):
        self.assertIn('for u in /sys/class/block/$(mu300_storage_prefix "$EMMC")[0-9]*/uevent; do', INIT)
        self.assertIn('for p in "$b/$(mu300_storage_prefix "$EMMC")"[0-9]*; do', INIT)
        self.assertNotIn('${EMMC##*/}p', INIT)

    def test_link_partitions_of_a_ufs(self):
        text = (BIN / 'android-vendor-start').read_text()
        body = text[text.index('\nlink_partitions() {'):text.index('\n}\n', text.index('\nlink_partitions() {')) + 3]
        f = Fake(self.tmp / 'r'); f.ufs()
        dev = self.tmp / 'dev'
        for shell in self.each_shell():
            (dev / 'block' / 'by-name').mkdir(parents=True)
            r = self.sh(shell, body + f'\nlink_partitions {f.sys}/class/block {dev} sda')
            self.assertEqual(r.returncode, 0, (shell, r.stderr))
            names = sorted(p.name for p in (dev / 'block' / 'by-name').iterdir())
            self.assertEqual(names, ['boot_a', 'boot_b', 'misc', 'userdata'], shell)
            self.assertEqual(os.readlink(dev / 'block' / 'by-name' / 'misc'), f'{dev}/sda3', shell)
            self.assertFalse((dev / 'block' / 'sdb').exists(), shell)   # the boot LUs are disks, not partitions
            shutil.rmtree(dev)


class AndroidSide(ShellTest):
    """The scripts that run on Android find the disk through Android's by-name links: the same lines in each."""
    FILES = ('tools/android-install.sh', 'tools/android-mount-mu300root.sh', 'tools/android-web.sh')

    def test_one_text(self):
        blocks = {f: block((TOP / f).read_text(), 'android-disk') for f in self.FILES}
        self.assertEqual(len(set(blocks.values())), 1, list(blocks))
        st = (TOP / 'tools' / 'storage.sh').read_text()
        probe = ("'d=$(readlink -f /dev/block/by-name/misc); d=$(readlink -f /sys/class/block/${d##*/}/..); "
                 "echo ${d##*/} $(cat $d/queue/logical_block_size)'")
        self.assertIn('su_do ' + probe, st)
        for ps in ('install.ps1', 'uninstall.ps1'):
            self.assertIn('SuDo ' + probe, (TOP / ps).read_text(encoding='utf-8'))

    def test_found(self):
        code = block((TOP / self.FILES[0]).read_text(), 'android-disk') + '\necho "$IDISK $IPART $GPT_HEAD $GPT_TAIL"'
        f = Fake(self.tmp / 'r'); f.ufs()
        by = self.tmp / 'by-name'; by.mkdir()
        os.symlink(f.sys / 'class' / 'block' / 'sda3', by / 'misc')
        for shell in self.each_shell():
            self.assertEqual(self.sh(shell, 'set -e\n' + code, MU300_BY_NAME=by, MU300_SYSFS=f.sys).stdout, 'sda sda 48 40\n')
            # Android says nothing (no by-name): mmcblk0, as every installer had it
            self.assertEqual(self.sh(shell, 'set -e\n' + code, MU300_BY_NAME=self.tmp / 'none',
                                     MU300_SYSFS=f.sys).stdout, 'mmcblk0 mmcblk0p 34 33\n')
            self.assertEqual(self.sh(shell, 'set -e\n' + code, MU300_DISK='sdb', MU300_BY_NAME=by,
                                     MU300_SYSFS=f.sys).stdout, 'sdb sdb 48 40\n')
