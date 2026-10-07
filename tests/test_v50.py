"""V50 publication, restore boundaries and guarded hardware operations."""
import importlib.util
import io
import json
import os
import tarfile
import tempfile
import unittest
from pathlib import Path

from helpers import BIN, TOP, ShellTest


def load(name):
    spec = importlib.util.spec_from_file_location('v50_' + name, TOP / 'tools/v50' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = load('release')
maintenance = load('maintain')
patcher = load('patch-openclash')
audit = load('audit')


class Archives(unittest.TestCase):
    def test_linux_uninstaller_recognizes_v50(self):
        source = (TOP / 'uninstall.sh').read_text(encoding='utf-8')
        self.assertIn('*MU3351*|*V50*', source)

    def test_restore_excludes_old_executables_libraries_database_and_links(self):
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / 'backup.tar.gz'
            names = ('etc/config/openclash', 'etc/openclash/config/user.yaml', 'etc/mu300/led.conf',
                     'etc/openclash/core/clash_meta', 'etc/init.d/openclash', 'lib/apk/db/installed',
                     'etc/config/network')
            with tarfile.open(backup, 'w:gz') as tar:
                for name in names:
                    m = tarfile.TarInfo(name)
                    m.size = 1
                    tar.addfile(m, io.BytesIO(b'x'))
                m = tarfile.TarInfo('etc/openclash/evil')
                m.type, m.linkname = tarfile.SYMTYPE, '/etc/shadow'
                tar.addfile(m)
            with tarfile.open(fileobj=io.BytesIO(maintenance.recovery_archive(backup)), mode='r:gz') as tar:
                self.assertEqual(tar.getnames(), list(names[:3]))
                self.assertTrue(all(m.mode == 0o600 for m in tar))

    def test_traversal_and_windows_paths_rejected(self):
        for name in ('../etc/shadow', '/etc/shadow', 'etc/../../shadow', 'etc\\shadow'):
            for function in (release.safe_name, maintenance.safe_name):
                with self.assertRaises(ValueError):
                    function(name)

    def test_public_archive_rejects_device_data(self):
        for name in ('opt/mu300/android/vendor/lib/libmodem.so', 'etc/openclash/config/user.yaml',
                     'etc/mu300/hotspot.conf', 'lib/firmware/wcnmodem.bin', 'private/key'):
            with self.assertRaises(ValueError):
                release.audit_member(tarfile.TarInfo(name))

    def test_verified_inputs_refuse_a_corrupt_asset(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            sums = []
            for name in release.ASSETS:
                p = directory / name
                p.write_bytes(b'asset')
                sums.append(f'{release.sha256(p)}  {name}\n')
            (directory / 'SHA256SUMS').write_text(''.join(sums))
            self.assertEqual(set(release.verified_inputs(directory)), set(release.ASSETS))
            (directory / release.ASSETS[0]).write_bytes(b'corrupt')
            with self.assertRaises(ValueError):
                release.verified_inputs(directory)

    def test_openclash_patch_is_idempotent_and_rejects_unknown_layout(self):
        original = 'check_mod()\n{\n   modprobe "$1"\n}\n'
        patched = patcher.patch(original)
        self.assertIn('[ "$1" = tun ] && [ -c /dev/net/tun ]', patched)
        self.assertEqual(patcher.patch(patched), patched)
        with self.assertRaises(ValueError):
            patcher.patch('check_mod () { return 0; }')

    def test_host_cannot_supply_ssh_options(self):
        for host in ('-oProxyCommand=evil', 'root@host;reboot', 'root@$(evil)'):
            with self.assertRaises(ValueError):
                maintenance.ssh_args(host)

    def test_audit_checks_private_files_without_printing_credentials(self):
        self.assertTrue(audit.inspect('private/backup.json', b'{}'))
        self.assertTrue(audit.inspect('source.txt', b'-----BEGIN ' + b'OPENSSH PRIVATE KEY-----'))
        self.assertFalse(audit.inspect('profiles/v50/profile.json', b'{"kernel_device":"f50"}'))


class LedHardware(ShellTest):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / 'root'
        self.node = self.root / 'sys/bus/i2c/devices/3-005b'
        (self.node / 'of_node').mkdir(parents=True)
        (self.root / 'etc/mu300').mkdir(parents=True)
        (self.root / 'etc/mu300/led.conf').write_bytes(b'LED_DISABLED=1\n')
        (self.node / 'of_node/compatible').write_bytes(b'awinic,aw9523b\0')
        self.stub('i2cget', 'echo "$@" >> "$STUBLOG/reads"; case "$4" in 0x10) echo "${CHIP_ID:-0x23}" ;; *) echo 0x00 ;; esac')
        self.stub('i2cset', 'echo "$@" >> "$STUBLOG/writes"')
        self.stub('sleep', ':')

    def run_led(self, shell, **env):
        return self.script(shell, BIN / 'mu300-v50-led-off', MU300_SYSROOT=self.root.as_posix(), **env)

    def test_reset_requires_chip_id_and_compatible(self):
        for shell in self.each_shell():
            writes = self.tmp / 'writes'
            writes.unlink(missing_ok=True)
            self.assertNotEqual(self.run_led(shell, CHIP_ID='0xff').returncode, 0)
            self.assertFalse(writes.exists())
            self.assertEqual(self.run_led(shell).returncode, 0)
            self.assertEqual(writes.read_text().strip(), '-y 3 0x5b 0x7f 0x00')
            writes.unlink()
            (self.node / 'of_node/compatible').write_bytes(b'other,chip\0')
            self.assertEqual(self.run_led(shell).returncode, 0)
            self.assertFalse(writes.exists())
            (self.node / 'of_node/compatible').write_bytes(b'awinic,aw9523b\0')

    def test_bound_driver_and_enabled_leds_never_write(self):
        for shell in self.each_shell():
            writes = self.tmp / 'writes'
            writes.unlink(missing_ok=True)
            (self.node / 'driver').mkdir()
            self.assertEqual(self.run_led(shell).returncode, 0)
            self.assertFalse(writes.exists())
            (self.node / 'driver').rmdir()
            (self.root / 'etc/mu300/led.conf').write_bytes(b'LED_DISABLED=0\n')
            self.assertEqual(self.run_led(shell).returncode, 0)
            self.assertFalse(writes.exists())
            (self.root / 'etc/mu300/led.conf').write_bytes(b'LED_DISABLED=1\n')


class Preflight(ShellTest):
    @unittest.skipIf(os.name == 'nt', 'rootfs unpacking needs POSIX symlink permissions')
    def test_update_adopts_profile_and_rejects_a_generic_rootfs_afterward(self):
        disk = self.tmp / 'disk'
        old = disk / 'openwrt-luci'
        (old / 'etc/mu300').mkdir(parents=True)
        (old / 'etc/mu300/custom.conf').write_bytes(b'keep\n')
        stage = disk / '.mu300-update'
        stage.mkdir()

        def image(v50):
            with tarfile.open(stage / 'mu300-openwrt-luci-rootfs.tar.gz', 'w:gz') as tar:
                m = tarfile.TarInfo('sbin/init')
                m.type, m.linkname = tarfile.SYMTYPE, '/bin/busybox'
                tar.addfile(m)
                files = {'etc/mu300/image-version': b'new\n'}
                if v50:
                    files.update({'etc/mu300/profile': b'v50\n', 'etc/mu300/update.conf': b'REPO=tester/v50\n',
                                  'etc/mu300/led.conf': b'LED_DISABLED=1\n'})
                for name, body in files.items():
                    m = tarfile.TarInfo(name)
                    m.size = len(body)
                    tar.addfile(m, io.BytesIO(body))

        code = (f'. "{BIN.as_posix()}/mu300-update"; '
                'is_root() { return 1; }; merge_accounts() { :; }; vendor_list() { :; }; '
                'apply_one openwrt-luci new')
        for shell in self.each_shell():
            image(True)
            r = self.sh(shell, code, MU300_LIB=1, MU300_DISK=disk.as_posix())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((old / 'etc/mu300/profile').read_bytes(), b'v50\n')
            self.assertEqual((old / 'etc/mu300/custom.conf').read_bytes(), b'keep\n')
            self.assertEqual((old / 'etc/mu300/led.conf').read_bytes(), b'LED_DISABLED=1\n')
            self.assertEqual((old / 'etc/mu300/update.conf').read_bytes(), b'REPO=tester/v50\n')
            image(False)
            r = self.sh(shell, code, MU300_LIB=1, MU300_DISK=disk.as_posix())
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual((old / 'etc/mu300/profile').read_bytes(), b'v50\n')

    def test_repo_configuration_is_data_not_shell_code(self):
        conf = self.tmp / 'update.conf'
        marker = self.tmp / 'executed'
        code = f'. "{BIN.as_posix()}/mu300-update"; printf "%s" "$REPO"'
        for shell in self.each_shell():
            conf.write_bytes(f'REPO=tester/v50\nEVIL=$(touch {marker.as_posix()})\n'.encode())
            r = self.sh(shell, code, MU300_LIB=1, MU300_UPDATE_CONF=conf.as_posix())
            self.assertEqual(r.stdout, 'tester/v50', r.stderr)
            self.assertFalse(marker.exists())

    def test_v50_update_requires_fork_and_prepared_openclash(self):
        root = self.tmp / 'root'
        (root / 'etc/mu300').mkdir(parents=True)
        (root / 'etc/init.d').mkdir()
        (root / 'etc/mu300/profile').write_bytes(b'v50\n')
        code = f'. "{BIN.as_posix()}/mu300-update"; v50_update_preflight'
        for shell in self.each_shell():
            r = self.sh(shell, code, MU300_LIB=1, MU300_SYSROOT=root.as_posix())
            self.assertNotEqual(r.returncode, 0)
            r = self.sh(shell, code, MU300_LIB=1, MU300_SYSROOT=root.as_posix(), MU300_REPO='tester/v50')
            self.assertEqual(r.returncode, 0, r.stderr)
            (root / 'etc/init.d/openclash').write_text('proxy')
            r = self.sh(shell, code, MU300_LIB=1, MU300_SYSROOT=root.as_posix(), MU300_REPO='tester/v50')
            self.assertNotEqual(r.returncode, 0)
            r = self.sh(shell, code, MU300_LIB=1, MU300_SYSROOT=root.as_posix(),
                        MU300_REPO='tester/v50', MU300_V50_MIGRATION_READY=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            (root / 'etc/init.d/openclash').unlink()
