"""boot/build-boot-image.py: the generic ramdisk segment (what every release and mu300-update ship) holds init,
the modules of boot/module-order.txt and, for another device, its own modules, order and kernel release."""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

try:
    import lz4.block
except ImportError:
    lz4 = None
HAVE_LZ4 = lz4 is not None or shutil.which('lz4') is not None

BOOT = TOP / 'boot'
RELEASE = '5.4.254-gtest'


def unlz4_legacy(data):
    """Concatenated LZ4 legacy frames (magic 0x184C2102, then blocks of <u32 size><data>) -> bytes."""
    if lz4 is None:
        return subprocess.run(['lz4', '-dc'], input=data, capture_output=True, check=True).stdout
    out, i = b'', 0
    while i < len(data):
        assert data[i:i + 4] == b'\x02\x21\x4c\x18', 'not an LZ4 legacy frame'
        i += 4
        while i + 4 <= len(data) and data[i:i + 4] != b'\x02\x21\x4c\x18':
            n = int.from_bytes(data[i:i + 4], 'little')
            i += 4
            out += lz4.block.decompress(data[i:i + n], uncompressed_size=8 << 20)
            i += n
    return out


def cpio_files(data):
    """newc cpio -> {name: (mode, data)}"""
    files, i = {}, 0
    while True:
        h = data[i:i + 110]
        assert h[:6] == b'070701', 'not newc'
        mode = int(h[14:22], 16)
        size = int(h[54:62], 16)
        nlen = int(h[94:102], 16)
        name = data[i + 110:i + 110 + nlen - 1].decode()
        i = (i + 110 + nlen + 3) & ~3
        body = data[i:i + size]
        i = (i + size + 3) & ~3
        if name == 'TRAILER!!!':
            return files
        files[name] = (mode, body)


@unittest.skipIf(not HAVE_LZ4, 'neither the lz4 command nor the lz4 Python module is installed')
class GenericRamdisk(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mu300-bootimg-'))
        self.mods = self.tmp / 'modules'
        self.u30 = self.tmp / 'modules-u30air'
        for d in (self.mods, self.u30):
            d.mkdir()
        base = (BOOT / 'module-order.txt').read_text().split()
        u30 = (BOOT / 'module-order-u30air.txt').read_text().split()
        for n in set(base) | set(u30):
            (self.mods / n).write_bytes(b'\x7fELF base ' + n.encode() + b'\0vermagic=' + RELEASE.encode() + b' SMP\0')
        # the U30 Air set: the modules it builds differently plus the ones the F50 order does not have
        self.u30_only = sorted(set(u30) - set(base)) + ['sprd-charger-manager.ko']
        for n in self.u30_only:
            (self.u30 / n).write_bytes(b'\x7fELF u30 ' + n.encode() + b'\0vermagic=' + RELEASE.encode() + b' SMP\0')
        for f in ('busybox', 'logdw'):
            (self.tmp / f).write_bytes(b'\x7fELF ' + f.encode())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build(self, *extra):
        out = self.tmp / 'ramdisk-generic.lz4'
        r = subprocess.run([sys.executable, str(BOOT / 'build-boot-image.py'), '--generic-ramdisk',
                            '--modules', str(self.mods), '--busybox', str(self.tmp / 'busybox'),
                            '--logdw', str(self.tmp / 'logdw'),
                            '--ueventd-perms', str(TOP / 'android-vendor' / 'ueventd-perms.sh'),
                            '--out', str(out), *extra], capture_output=True, text=True)
        return r, out

    def test_base(self):
        r, out = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        files = cpio_files(unlz4_legacy(out.read_bytes()))
        self.assertEqual(files['init'][1], (BOOT / 'init').read_bytes())
        self.assertTrue(files['init'][0] & 0o111, 'init is not executable')
        self.assertEqual(files['etc/module-order'][1], (BOOT / 'module-order.txt').read_bytes())
        for n in (BOOT / 'module-order.txt').read_text().split():
            self.assertIn('linux-modules/' + n, files)
        self.assertNotIn('etc/mu300-device', files)
        # an empty trial guard: disarms one an experiment left in the device segment that mu300-update keeps
        self.assertEqual(files['etc/mu300-trial-guard'][1], b'')
        self.assertFalse([f for f in files if f.startswith('linux-modules/u30air/')])

    def test_device_modules(self):
        r, out = self.build('--device-modules', f'u30air={self.u30}')
        self.assertEqual(r.returncode, 0, r.stderr)
        files = cpio_files(unlz4_legacy(out.read_bytes()))
        self.assertEqual(files['etc/module-order-u30air'][1], (BOOT / 'module-order-u30air.txt').read_bytes())
        for n in self.u30_only:
            self.assertEqual(files['linux-modules/u30air/' + n][1], (self.u30 / n).read_bytes())
        # the U30 Air's modules are used only with the kernel they were built for
        self.assertEqual(files['linux-modules/u30air/kernel.release'][1].decode().strip(), RELEASE)
        # every module the U30 Air order names is in the image, in its own set or the base one
        for n in (BOOT / 'module-order-u30air.txt').read_text().split():
            self.assertTrue('linux-modules/u30air/' + n in files or 'linux-modules/' + n in files, n)

    def test_crlf_checkout(self):
        # a Windows clone with core.autocrlf=true (issue #7): the device's shell must still get LF
        crlf = {}
        for name, src in (('init', BOOT / 'init'), ('perms', TOP / 'android-vendor' / 'ueventd-perms.sh'),
                          ('order', BOOT / 'module-order.txt')):
            crlf[name] = self.tmp / name
            crlf[name].write_bytes(src.read_bytes().replace(b'\n', b'\r\n'))
        r, out = self.build('--init', str(crlf['init']), '--ueventd-perms', str(crlf['perms']),
                            '--module-order', str(crlf['order']))
        self.assertEqual(r.returncode, 0, r.stderr)
        files = cpio_files(unlz4_legacy(out.read_bytes()))
        self.assertEqual(files['init'][1], (BOOT / 'init').read_bytes())
        self.assertEqual(files['etc/ueventd-perms.sh'][1], (TOP / 'android-vendor' / 'ueventd-perms.sh').read_bytes())
        self.assertEqual(files['etc/module-order'][1], (BOOT / 'module-order.txt').read_bytes())

    def test_generic_refuses_device_settings(self):
        # the generic segment is the same for every device: it must not name one, nor carry a trial guard
        for extra in (['--device', 'u30air'], ['--trial-guard', '300']):
            r, _ = self.build(*extra)
            self.assertNotEqual(r.returncode, 0, extra)

    def test_missing_module(self):
        (self.mods / (BOOT / 'module-order.txt').read_text().split()[0]).unlink()
        r, _ = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('missing module', r.stderr)


class ModuleOrder(unittest.TestCase):
    def test_u30air_order(self):
        base = (BOOT / 'module-order.txt').read_text().split()
        u30 = (BOOT / 'module-order-u30air.txt').read_text().split()
        self.assertEqual(len(u30), len(set(u30)), 'a module is listed twice')
        # the F50's charger driver is replaced, not loaded next to the SQC one
        self.assertNotIn('bq2560x-charger.ko', u30)
        for n in ('sqc_bq2560x.ko', 'sqc_charger.ko', 'charger_policy_service.ko', 'zte_power_supply.ko'):
            self.assertIn(n, u30)
        # dependencies first: the fuel gauge needs the charger manager, which needs the SQC stack
        for a, b in (('zte_power_supply.ko', 'charger_policy_service.ko'), ('sqc_charger.ko', 'sqc_bq2560x.ko'),
                     ('sprd-charger-manager.ko', 'sc27xx_fuel_gauge.ko'), ('sprd_tcpm.ko', 'sc27xx_pd.ko')):
            self.assertLess(u30.index(a), u30.index(b), f'{a} must load before {b}')
        # everything else keeps the F50's order
        common = [n for n in base if n in u30]
        self.assertEqual(common, [n for n in u30 if n in common])


if __name__ == '__main__':
    unittest.main()
