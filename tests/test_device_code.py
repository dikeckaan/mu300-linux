"""The device code (lib/storage.sh's mu300_device_code, bin/mu300-device-code) and the same computation under Android
(tools/device-code.sh, sent over adb by the installers): 16 lowercase hex digits of
sha256("mu300-audio-device-v1\\n" + IDENTITY), the same on both for an eMMC and for a UFS, and never the raw identity."""
import hashlib
import os
import re

from helpers import BIN, TOP, ShellTest

LIB = TOP / 'rootfs' / 'overlay' / 'opt' / 'mu300' / 'lib' / 'storage.sh'
ANDROID = TOP / 'tools' / 'device-code.sh'
CID = '150100444a54423452010a1b2c3d4e00'           # made up, of the shape a Samsung eMMC's CID has
UFS_MAKER, UFS_SERIAL = 'SAMSUNG', '0123456789AB CDEF'   # made up; a space inside, for word splitting


def code(identity):
    return hashlib.sha256(b'mu300-audio-device-v1\n' + identity.encode()).hexdigest()[:16]


def android_cmd():
    m = re.search(r"^MU300_DEVICE_CODE_CMD='([^']*)'$", ANDROID.read_text(), re.M)
    assert m, 'no MU300_DEVICE_CODE_CMD line'
    return m.group(1)


class Fake:
    """sysfs as the kernel lays it out - /sys/block/X and /sys/class/block/X links into /sys/devices, a disk's device
    a link to its parent device - and Android's /dev/block/by-name/userdata."""

    def __init__(self, root):
        self.root = root
        self.sys = root / 'sys'
        for d in ('block', 'class/block'):
            (self.sys / d).mkdir(parents=True)
        (root / 'dev' / 'block' / 'by-name').mkdir(parents=True)

    def disk(self, dev, name, parts, typ=None):
        dev = self.sys / 'devices' / dev
        d = dev / 'block' / name
        d.mkdir(parents=True)
        os.symlink('../..', d / 'device')
        if typ:
            (dev / 'type').write_text(typ + '\n')
        for link in (self.sys / 'block' / name, self.sys / 'class' / 'block' / name):
            os.symlink(d, link)
        prefix = name + 'p' if name[-1].isdigit() else name
        for n, label in parts.items():
            p = d / f'{prefix}{n}'
            p.mkdir()
            (p / 'uevent').write_text(f'DEVTYPE=partition\nPARTN={n}\nPARTNAME={label}\n')
            os.symlink(p, self.sys / 'class' / 'block' / p.name)
            (self.root / 'dev' / 'block' / p.name).write_text('')
            if label == 'userdata':
                os.symlink(self.root / 'dev' / 'block' / p.name, self.root / 'dev' / 'block' / 'by-name' / 'userdata')
        return dev

    def emmc(self, cid=CID):
        dev = self.disk('platform/soc/sdio/mmc_host/mmc0/mmc0:0001', 'mmcblk0', {5: 'misc', 60: 'userdata'}, 'MMC')
        if cid is not None:
            (dev / 'cid').write_text(cid + '\n')

    def ufs(self, maker=UFS_MAKER, serial=UFS_SERIAL):
        host = self.sys / 'devices' / 'platform/soc/soc:ap-ahb/22000000.ufs'
        self.disk('platform/soc/soc:ap-ahb/22000000.ufs/host0/target0:0:0/0:0:0:0', 'sda', {3: 'misc', 75: 'userdata'})
        self.disk('platform/soc/soc:ap-ahb/22000000.ufs/host0/target0:0:0/0:0:0:1', 'sdb', {})
        (host / 'string_descriptors').mkdir()
        if maker is not None:
            (host / 'string_descriptors' / 'manufacturer_name').write_text(maker + '\n')
        if serial is not None:
            (host / 'string_descriptors' / 'serial_number').write_text(serial + '\n')


class DeviceCode(ShellTest):
    def linux(self, shell, fake):
        return self.script(shell, BIN / 'mu300-device-code', MU300_SYS=fake.sys)

    def android(self, shell, fake):
        cmd = android_cmd().replace('/dev/block/by-name/', f'{fake.root}/dev/block/by-name/') \
                           .replace('/sys/class/block/', f'{fake.sys}/class/block/')
        return self.sh(shell, cmd)

    def check(self, fake, identity):
        want = code(identity)
        for shell in self.each_shell():
            lin, andr = self.linux(shell, fake), self.android(shell, fake)
            self.assertEqual((lin.returncode, lin.stdout, lin.stderr), (0, want + '\n', ''))
            self.assertEqual((andr.returncode, andr.stdout), (0, want + '\n'))
            self.assertRegex(lin.stdout, r'^[0-9a-f]{16}\n$')
            for raw in (CID, UFS_SERIAL, UFS_MAKER):
                self.assertNotIn(raw, lin.stdout + lin.stderr + andr.stdout + andr.stderr)

    def test_emmc(self):
        f = Fake(self.tmp / 'r'); f.emmc()
        self.check(f, 'emmc:' + CID)

    def test_ufs(self):
        f = Fake(self.tmp / 'r'); f.ufs()
        self.check(f, f'ufs:{UFS_MAKER}:{UFS_SERIAL}')

    def test_other_device_other_code(self):
        a = Fake(self.tmp / 'a'); a.emmc()
        b = Fake(self.tmp / 'b'); b.emmc(CID[:-2] + '01')
        shell = self.shells[0]
        self.assertNotEqual(self.linux(shell, a).stdout, self.linux(shell, b).stdout)

    def test_no_identity(self):
        for name, make in (('emmc', lambda f: f.emmc(cid=None)), ('ufs', lambda f: f.ufs(serial=None))):
            f = Fake(self.tmp / name); make(f)
            for shell in self.each_shell():
                lin, andr = self.linux(shell, f), self.android(shell, f)
                self.assertEqual((lin.returncode, lin.stdout), (1, ''), name)
                self.assertIn('no identity', lin.stderr)
                self.assertEqual(andr.stdout, '', name)

    def test_function_in_lib(self):
        f = Fake(self.tmp / 'r'); f.emmc()
        for shell in self.each_shell():
            r = self.sh(shell, f'set -e; . "{LIB}"; mu300_device_code', MU300_SYS=f.sys)
            self.assertEqual(r.stdout, code('emmc:' + CID) + '\n')

    def test_android_text_survives_su_and_powershell(self):
        cmd = android_cmd()
        self.assertNotIn('"', cmd)       # Windows PowerShell 5.1 drops double quotes on the way to adb
        self.assertNotIn("'", cmd)       # su_do wraps it in single ones
        self.assertNotIn('\n', cmd)
