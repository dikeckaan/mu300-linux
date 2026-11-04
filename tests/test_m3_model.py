"""M3 identity is derived from Android, independently of the shared U30 Air hardware profile."""
import re
from helpers import TOP, ShellTest


class Model(ShellTest):
    def test_model_marker_uses_exact_android_identity_and_clears_stale_labels(self):
        source = (TOP / 'tools/android-install.sh').read_text()
        block = re.search(r'# --- device model begin\n(.*?)# --- device model end', source, re.S)[1]
        root = self.tmp / 'root'
        marker = root / 'etc/mu300/device-model'
        cases = [('MU5352', 'MU5352', 'ums9620', 'old-label\n', 'm3\n'),
                 ('MU5352', 'MU5352', 'ums9632', 'old-label\n', 'old-label\n'),
                 ('M3Pro', 'MU5352', 'ums9620', 'old-label\n', 'old-label\n'),
                 ('MU5352', 'other', 'ums9620', 'old-label\n', 'old-label\n'),
                 ('U30Air', 'U30Air', 'ums9620', 'm3\n', None),
                 ('F50', 'MU300', 'ums9620', 'custom\n', 'custom\n'),
                 ('V50', 'MU3351', 'ums9620', 'custom\n', 'custom\n')]
        for model, device, platform, initial, expected in cases:
            self.stub('getprop', f'''case "$1" in
ro.product.model) echo '{model}' ;;
ro.product.device) echo '{device}' ;;
ro.board.platform) echo '{platform}' ;;
esac''')
            for shell in self.each_shell():
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(initial)
                result = self.sh(shell, block + f'\ninstall_device_model "{root}"\n')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(marker.read_text() if marker.exists() else None, expected, (model, device, platform))

    def test_openwrt_model_label_does_not_override_device_tree_or_driver_dispatch(self):
        source = (TOP / 'openwrt/overlay/etc/init.d/mu300-hw').read_text()
        block = re.search(r'boot\(\) \{\n(.*?)\n\t/opt/mu300/bin/mu300-led', source, re.S)[1]
        for variant in ('m3', 'u30air', 'f50', 'v50'):
            self.stub('mu300-device', f'echo {variant}')
            sysinfo = self.tmp / 'sysinfo'
            sysinfo.mkdir(exist_ok=True)
            label = sysinfo / 'model'
            for shell in self.each_shell():
                label.write_text('device-tree model\n')
                code = block.replace('/opt/mu300/bin/mu300-device', 'mu300-device').replace('/tmp/sysinfo', str(sysinfo))
                result = self.sh(shell, code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(label.read_text(), 'ZTE M3 (MU5352)\n' if variant == 'm3' else 'device-tree model\n')

    def test_carried_model_symlink_is_not_followed(self):
        source = (TOP / 'tools/android-install.sh').read_text()
        block = re.search(r'# --- device model begin\n(.*?)# --- device model end', source, re.S)[1]
        self.stub('getprop', 'case "$1" in ro.board.platform) echo ums9620 ;; *) echo MU5352 ;; esac')
        root = self.tmp / 'root'
        marker = root / 'etc/mu300/device-model'
        marker.parent.mkdir(parents=True)
        outside = self.tmp / 'outside'
        outside.write_text('must stay unchanged\n')
        for shell in self.each_shell():
            marker.unlink(missing_ok=True)
            marker.symlink_to(outside)
            result = self.sh(shell, block + f'\ninstall_device_model "{root}"\n')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.is_symlink())
            self.assertEqual(marker.read_text(), 'm3\n')
            self.assertEqual(outside.read_text(), 'must stay unchanged\n')
