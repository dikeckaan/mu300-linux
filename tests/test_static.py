"""Checks over every script without running it: syntax under each shell that runs it, executable bits, and rules
that past bugs taught (see each test)."""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import BIN, TOP, shells

OPENWRT = TOP / 'openwrt' / 'overlay'
LUCI_OVERLAY = TOP / 'openwrt' / 'luci-overlay'


def shebang(p):
    try:
        with open(p, 'rb') as f:
            first = f.readline()
    except OSError:
        return ''
    return first.decode(errors='replace').strip() if first.startswith(b'#!') else ''


def shell_scripts():
    """(path, 'sh'|'bash') of every shell script the project ships or runs."""
    cands = list(BIN.iterdir()) + list((TOP / 'tools').glob('*.sh')) + [
        TOP / 'install.sh', TOP / 'uninstall.sh', TOP / 'boot' / 'init', TOP / 'rootfs' / 'assemble.sh',
        TOP / 'kernel' / 'build-all.sh', TOP / 'tools' / 'i18n.sh', TOP / 'tools' / 'self-update.sh',
        TOP / 'tools' / 'linux-mode.sh', TOP / 'tools' / 'storage.sh', TOP / 'android-vendor' / 'ueventd-perms.sh']
    cands += list((TOP / 'android' / 'magisk' / 'installer').glob('*.sh'))
    cands += [TOP / 'android' / 'magisk' / 'installer' / 'update-binary']
    cands += list((TOP / 'android' / 'magisk' / 'mu300-linux-switch').glob('*.sh'))
    cands += [p for p in OPENWRT.rglob('*') if p.is_file()]
    cands += [p for p in LUCI_OVERLAY.rglob('*') if p.is_file()]
    out = []
    for p in sorted(set(cands)):
        if not p.is_file():
            continue
        sb = shebang(p)
        if 'bash' in sb:
            out.append((p, 'bash'))
        elif sb.endswith('sh') or 'rc.common' in sb or (not sb and p.suffix == '.sh'):
            out.append((p, 'sh'))
    return out


class Syntax(unittest.TestCase):
    def test_every_script_parses(self):
        sh_shells = [s for s in shells() if s[0] != 'bash'] or shells()
        scripts = shell_scripts()
        self.assertGreater(len(scripts), 40)
        for p, kind in scripts:
            if kind == 'bash' and not shutil.which('bash'):
                continue
            for s in ([['bash']] if kind == 'bash' else sh_shells):
                with self.subTest(script=str(p.relative_to(TOP)), shell=' '.join(s)):
                    r = subprocess.run(s + ['-n', str(p)], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)

    def test_device_programs_are_executable(self):
        for p in BIN.iterdir():
            if p.is_file() and shebang(p):
                with self.subTest(p=p.name):
                    self.assertTrue(p.stat().st_mode & 0o111, 'not executable')


class Rules(unittest.TestCase):
    def test_power_page_is_wired(self):
        menu = json.loads((TOP / 'openwrt/luci-app-mu300/root/usr/share/luci/menu.d/luci-app-mu300.json').read_text())
        self.assertEqual(menu['admin/system/power']['action']['path'], 'mu300/power')
        common = (TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js').read_text()
        self.assertIn("method: 'power_get'", common)
        self.assertIn("method: 'power_set', params: [ 'op', 'key', 'value' ]", common)
        view = (TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/power.js').read_text()
        for s in ('WIFI_IDLE', 'RADIO_IDLE', 'LEDS_IDLE', 'CPU', 'SAVER_BELOW', 'CHARGE_TO', 'callPowerSet'):
            self.assertIn(s, view)
        acl = json.loads((TOP / 'openwrt/luci-app-mu300/root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())
        self.assertIn('power_get', acl['luci-app-mu300']['read']['ubus']['mu300dash'])
        self.assertIn('power_set', acl['luci-app-mu300']['write']['ubus']['mu300dash'])

    def test_power_profiles_are_wired_in(self):
        # the daemon runs on both systems, the keys wake it, the Ubuntu units skip the radios in a charging boot,
        # the command is on PATH, OpenWrt's own power-key handler (a tap = poweroff) is neutralised, and power.conf is kept
        self.assertIn('mu300-power', (TOP / 'rootfs/overlay/opt/mu300/lib/path-commands').read_text().split())
        buttons = (BIN / 'mu300-buttons').read_text()
        self.assertIn('mu300-power wake', buttons)
        unit = (TOP / 'rootfs/overlay/etc/systemd/system/mu300-power.service').read_text()
        self.assertIn('ExecStart=/opt/mu300/bin/mu300-power daemon', unit)
        self.assertIn('After=mu300-hotspot.service mu300-mobile-data.service', unit)
        # R10: stopped while idle, the TERM trap runs the whole wake (up to ~120 s for the radio lock)
        self.assertIn('TimeoutStopSec=150', unit)
        self.assertIn('mu300-power.service:multi-user.target', (TOP / 'rootfs/assemble.sh').read_text())
        init = (TOP / 'openwrt/overlay/etc/init.d/mu300-power').read_text()
        self.assertIn('procd_set_param command /opt/mu300/bin/mu300-power daemon', init)
        self.assertIn('procd_set_param term_timeout 150', init)
        self.assertRegex(init, r'START=9[6-9]')
        for u in ('mu300-hotspot.service', 'mu300-mobile-data.service'):
            self.assertIn('ConditionPathExists=!/run/mu300/charging-boot', (TOP / 'rootfs/overlay/etc/systemd/system' / u).read_text())
        build = (TOP / 'openwrt/build-rootfs.sh').read_text()
        self.assertIn('for b in power wps rfkill', build)
        self.assertIn('mkdir -p $R/etc/rc.button', build)
        self.assertIn('rc.button/$b', build)
        self.assertLess(build.index('cp -a /in/overlay/. $R/'), build.index('for b in power wps rfkill'))
        self.assertIn('mu300-power', build.split('for s in mu300-accounts')[1].split('; do')[0])
        # etc/mu300 is kept whole on both systems, and power.conf lives in it
        update = (TOP / 'rootfs/overlay/opt/mu300/bin/mu300-update').read_text()
        self.assertRegex(update, r'ubuntu\) echo "etc/mu300 ')
        self.assertRegex(update, r'openwrt\) echo "etc/config etc/mu300 ')
        self.assertIn('/etc/mu300/power.conf', (BIN / 'mu300-power').read_text())

    def test_customize_leaves_magisks_shell_alone(self):
        # Magisk sources customize.sh: errexit or nounset there would end Magisk's own installer before its cleanup
        c = (TOP / 'android' / 'magisk' / 'installer' / 'customize.sh').read_text()
        code = '\n'.join(l for l in c.splitlines() if not l.lstrip().startswith('#'))
        self.assertNotRegex(code, r'\bset\s+-[a-z]*[eu]')
        self.assertNotRegex(code, r'(^|\s)exit\b')
        self.assertIn('SKIPUNZIP=1', code)

    def test_installer_never_writes_androids_boot_partition(self):
        s = (TOP / 'android' / 'magisk' / 'installer' / 'mu300-install.sh').read_text()
        self.assertNotRegex(s, r'of="?\$BOOT_ANDROID')
        self.assertNotRegex(s, r'write_boot "?\$BOOT_ANDROID')

    def test_powershell_device_commands_have_no_double_quotes(self):
        # Windows PowerShell 5.1 drops the double quotes inside an argument to a native program: `tr -d "\000"`
        # reached the device as tr -d \000 ("delete the character 0"), and every empty region was "not empty".
        # A command for the device (SuDo, adb shell) may therefore contain no `" and no "".
        for name in ('install.ps1', 'uninstall.ps1'):
            for n, line in enumerate((TOP / name).read_text().splitlines(), 1):
                code = line.split('#', 1)[0] if not line.lstrip().startswith('#') else ''
                if re.search(r'\bSuDo(ToFile)?\s+"|adb shell\s+"', code) and ('`"' in code or '""' in code):
                    self.fail(f'{name}:{n}: double quote inside a device command: {line.strip()}')

    def test_init_restores_androids_slot(self):
        # every restore goes through restore_android, so Linux on slot a returns to Android on b
        init = (TOP / 'boot' / 'init').read_text()
        self.assertNotIn('restore_slot_a', init)
        self.assertNotIn('slot_suffix=_b/androidboot.slot_suffix=_a', init)
        self.assertIn('sleep 300', init)

    def test_powershell_scripts_are_ascii(self):
        # Windows PowerShell 5.1 reads a file without a BOM as ANSI: non-ASCII text in the script is garbled
        for name in ('install.ps1', 'uninstall.ps1'):
            data = (TOP / name).read_bytes()
            bad = [i for i, b in enumerate(data) if b > 127]
            self.assertFalse(bad, f'{name}: non-ASCII byte at offset {bad[:1]}')

    def test_windows_pushes_text_with_lf(self):
        # a CRLF clone pushed its scripts as they were and Android's sh ran none of them (issue #7): the Windows
        # installers send text files through PushUnix, never a plain adb push
        for name in ('install.ps1', 'uninstall.ps1'):
            for n, line in enumerate((TOP / name).read_text().splitlines(), 1):
                if 'adb push' in line:
                    self.assertNotRegex(line, r'\.(sh|prop)\b|mu300-linux"|\$f"', f'{name}:{n}')
        self.assertIn('eol=lf', (TOP / '.gitattributes').read_text())

    def test_single_quoted_scripts_have_no_apostrophes(self):
        # A script handed to `sh -c '...'` (docker run) ends at its first apostrophe: "the U30 Air's charger" in a
        # comment there broke OpenWrt's build at release time, while every parser still saw balanced quotes.
        for name in ('openwrt/build-rootfs.sh', 'tools/make-release.sh'):
            lines = (TOP / name).read_text().splitlines()
            for n, line in enumerate(lines):
                if not line.rstrip().endswith("-c '"):
                    continue
                for m in range(n + 1, len(lines)):
                    if "'" in lines[m]:
                        self.assertTrue(lines[m].rstrip().endswith("'") and lines[m].count("'") == 1,
                                        f'{name}:{m + 1}: an apostrophe inside the script of line {n + 1}')
                        break

    def test_every_tool_that_mounts_the_filesystem_knows_the_card(self):
        for f in ('uninstall.sh', 'uninstall.ps1', 'tools/reset-password.sh', 'tools/android-import-hotspot.sh'):
            self.assertIn('mu300sd', (TOP / f).read_text(), f)

    def test_every_system_list_has_openwrt_luci(self):
        # every place that names the systems knows the third one, by its name or by the OpenWrt kind pattern
        files = ('boot/init', 'rootfs/overlay/opt/mu300/bin/mu300-update', 'rootfs/overlay/opt/mu300/bin/mu300-os',
                 'tools/android-install.sh', 'tools/reset-password.sh', 'tools/vendor-overlay.py', 'install.sh',
                 'install.ps1', 'tools/make-release.sh', 'rootfs/overlay/opt/mu300/bin/mu300-extra',
                 'android/magisk/installer/mu300-install.sh')
        for f in files:
            with self.subTest(file=f):
                text = (TOP / f).read_text()
                self.assertTrue('openwrt-luci' in text or 'openwrt-*' in text or 'openwrt|openwrt-' in text, f)

    def test_openwrt_luci_build_wiring(self):
        # MU300_SYSTEM=openwrt-luci: the same build as plain OpenWrt plus the panel, its catalogs compiled from po/
        # and Aurora pinned by hash (D3, D5); ImmortalWrt with the panel was never tested by anyone, so refused
        text = (TOP / 'openwrt' / 'build-rootfs.sh').read_text()
        for s in ('MU300_SYSTEM', '05f9015e0a4e2859f6a153f69e472f2984481490d4ce6db19b8a41bba7264f1e', 'po2lmo.py',
                  'luci-overlay', 'packages.txt', 'luci-i18n-$c-$l', 'for l in tr zh-cn', 'base.$l.lmo'):
            self.assertIn(s, text)
        arm = re.search(r'^\s*openwrt-luci\)(.*?);;', text, re.M | re.S)
        self.assertIsNotNone(arm, 'no openwrt-luci arm in the MU300_SYSTEM case')
        self.assertRegex(arm.group(1), r'"\$FLAVOUR" = openwrt \]', 'openwrt-luci does not refuse immortalwrt')
        self.assertIn('mu300-$SYSTEM-$VER-rootfs.tar.gz', text)
        # ImmortalWrt keeps the name it had; the Aurora hash is pinned in the script, only the file may be overridden
        self.assertIn('mu300-immortalwrt-$VER-rootfs.tar.gz', text)
        self.assertNotIn('MU300_LUCI_THEME_SHA256', text)
        self.assertRegex(text, r'(?m)^\s*THEME_SHA=05f9015e0a4e2859f6a153f69e472f2984481490d4ce6db19b8a41bba7264f1e$')
        mk = (TOP / 'openwrt' / 'luci-app-mu300' / 'Makefile').read_text()
        self.assertRegex(mk, r'set -e; \$\(foreach', 'a failing catalog must fail the compile')
        f = LUCI_OVERLAY / 'etc' / 'uci-defaults' / '91-mu300-luci'
        self.assertTrue(f.is_file() and f.stat().st_mode & 0o111, f'{f} missing or not executable')
        self.assertIn('/luci-static/aurora', f.read_text())
        self.assertIn(f, [p for p, _ in shell_scripts()])   # so test_every_script_parses parses it

    def test_uninstallers_have_no_per_system_list(self):
        # they remove the whole Linux filesystem; a per-system case arm added later would forget the third name
        for f in ('uninstall.sh', 'uninstall.ps1'):
            text = (TOP / f).read_text()
            self.assertNotRegex(text, r'(^|\s)(ubuntu|openwrt)\)', f)

    def test_the_commands_on_path_are_the_same_everywhere(self):
        # the Ubuntu image, the OpenWrt image and the boot-time links (mu300-extra link, for systems installed before a
        # command had one) link the same commands. They used to be three copies of the list: the fixups' lagged behind
        # (mu300-led, mu300-device were "command not found" on an installed U30 Air), and all three left mu300-ussd out.
        # Now there is one file, and every place reads it.
        lst = (TOP / 'rootfs/overlay/opt/mu300/lib/path-commands').read_text().split()
        self.assertIn('$R/opt/mu300/lib/path-commands', (TOP / 'rootfs/assemble.sh').read_text())
        self.assertIn('/in/opt-mu300/lib/path-commands', (TOP / 'openwrt/build-rootfs.sh').read_text())
        self.assertIn('/lib/path-commands', (BIN / 'mu300-extra').read_text())
        self.assertIn('mu300-extra link', (BIN / 'rootfs-fixups').read_text())
        self.assertIn('mu300-extra link', (OPENWRT / 'etc/init.d/mu300-post').read_text())
        for c in ('mu300-device', 'mu300-led', 'mobile-data', 'mu300-update', 'mu300-ussd', 'sms', 'mu300-extra'):
            self.assertIn(c, lst)
        self.assertEqual(len(lst), len(set(lst)))
        for c in lst:
            self.assertTrue((BIN / c).is_file(), c)

    def test_reply_deadlines_are_at_least_t_whole_seconds(self):
        # date +%s counts whole seconds: "now + T" ends between T - 1 and T seconds away, so a command written late in
        # a second had almost none of its budget (mu300-atd lost replies with T=1). Every file-clock deadline is now + T + 1.
        for name, pat in (('mu300-at', r'\$\(date \+%s\) \+ T \+ 1'),
                          ('mu300-ussd', r'\$\(date \+%s\) \+ T \+ 1'),
                          ('mu300-atd', r'\$\(now\) \+ \$1 \+ 1')):
            src = (BIN / name).read_text()
            self.assertRegex(src, pat, name)
            self.assertNotRegex(src, r'date \+%s\) \+ T \)', name)

    def test_images_carry_no_vpn_engine(self):
        # the engines are the vpn extra (mu300-extra): ~120 MB that a system without a VPN does not carry
        for f in ('rootfs/assemble.sh', 'openwrt/build-rootfs.sh'):
            src = (TOP / f).read_text()
            for e in ('xray', 'sing-box', 'hev-socks5-tunnel'):
                self.assertNotRegex(src, rf'opt/mu300/bin/{e}\b', (f, e))
        rel = (TOP / 'tools/make-release.sh').read_text()
        self.assertIn('make-extra.sh', rel)
        self.assertIn('mu300-extra-', rel)
        # the audit refuses an image that still has one
        self.assertRegex(rel, r'opt/mu300/bin/\(xray\|sing-box\|hev-socks5-tunnel\)')

    def test_init_finds_partitions_after_the_modules(self):
        # the eMMC driver is one of the vendor modules: misc and boot_b cannot be found before they are loaded
        init = (TOP / 'boot' / 'init').read_text()
        calls = [l.strip() for l in init.splitlines() if l.strip() in ('load_vendor_modules', 'find_partitions')]
        self.assertEqual(calls, ['load_vendor_modules', 'find_partitions'])

    def test_every_device_has_its_files(self):
        # a device the installers know needs its module order; its modules come from kernel/build-<device>.sh
        for dev in ('u30air',):
            self.assertTrue((TOP / 'boot' / f'module-order-{dev}.txt').is_file())
            self.assertTrue((TOP / 'kernel' / f'{dev}.fragment').is_file())
            self.assertIn(dev, (TOP / 'install.sh').read_text())
            self.assertIn(dev, (TOP / 'install.ps1').read_text())

    def test_mainline_keeps_the_sd_host(self):
        # the SD card can hold the Linux filesystem: the port lets the card slot's host probe next to the eMMC, and
        # still keeps any other sdhci host (the stock DT's sdio_wifi; Wi-Fi is on PCIe) out
        port = (TOP / 'upstream' / 'port' / 'install.py').read_text()
        self.assertIn('MU300: only the eMMC and the card slot', port)
        self.assertIn('if (!of_property_read_bool(pdev->dev.of_node, "non-removable") &&', port)
        self.assertIn('of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_sd") < 0)', port)
        self.assertIn('MU300: CD GPIO deferred', port)
        # a deferral that is only masked leaves the rest of mmc_of_parse() undone (UHS modes, no-sdio, no-mmc): the
        # unresolvable cd-gpios is dropped and the parse run again
        self.assertIn('of_remove_property(pdev->dev.of_node, cd)', port)
        self.assertIn("'MU300: only the eMMC and the card slot', 'MU300: CD GPIO deferred', "
                      "'of_remove_property(pdev->dev.of_node, cd)'", port)
        self.assertRegex((TOP / 'upstream' / 'make-bundle.sh').read_text(),
                         r"printf 'sdcard\\nlinux-slot\\n' > \"\$W/b/features\"")

    def test_mainline_keeps_the_emmc_at_mmc0(self):
        # Both hosts probe asynchronously and the stock DT has no mmc aliases, so the card slot could take mmc0 and
        # leave mmcblk1 to the eMMC: init then never found the card and rebooted at 300 s (FINDINGS 31l). The card
        # slot's host waits until the eMMC's host is added.
        port = (TOP / 'upstream' / 'port' / 'install.py').read_text()
        self.assertIn('MU300: the eMMC is mmc0', port)
        self.assertIn('static bool sdhci_sprd_emmc_added;', port)
        self.assertIn('for_each_compatible_node(np, NULL, "sprd,sdhci-r11")', port)
        # the deferral sits right after the host filter, before sdhci_pltfm_init() allocates the host index
        self.assertIn('\\t    sdhci_sprd_emmc_pending(pdev->dev.of_node))\n\\t\\treturn -EPROBE_DEFER;\n', port)
        # and says what that costs: without a working eMMC host the card slot never binds
        self.assertIn("no SD root without a working eMMC host", port)
        self.assertLess(port.index("t.replace(filt, filt + '''"), port.index('add_old = '))
        # the flag is set only once the eMMC's host is added
        self.assertIn("add_old = '\\tret = __sdhci_add_host(host);\\n\\tif (ret)\\n\\t\\tgoto err_cleanup_host;\\n'",
                      port)
        self.assertIn('\\t\\tWRITE_ONCE(sdhci_sprd_emmc_added, true);', port)
        # and the build stops when the edit did not apply
        self.assertIn("'MU300: the eMMC is mmc0', 'WRITE_ONCE(sdhci_sprd_emmc_added, true);'", port)

    def test_mainline_drives_the_u30_air_charger(self):
        # Without a driver the charger kept what Android left in it: charging off (CHG_CONFIG 0), 500 mA input, and
        # the battery drained while plugged in. bq256xx drives the vendor node "ti,bq2560x_chg" now.
        cfg = (TOP / 'upstream' / 'mu300-mainline.config').read_text()
        for k in ('CONFIG_CHARGER_BQ256XX=y', 'CONFIG_REGMAP_I2C=y', 'CONFIG_I2C_SPRD=y', 'CONFIG_EXTCON_USB_GPIO=y'):
            self.assertRegex(cfg, rf'(?m)^{k}$')
        port = (TOP / 'upstream' / 'port' / 'install.py').read_text()
        # the edit itself, on the two forms of the I2C table (6.18 positional, 7.x designated), twice (idempotent)
        code = port[port.index("bp = os.path.join(tree, 'drivers/power/supply/bq256xx_charger.c')"):
                    port.index('# Every edit above is a text substitution')]
        of = ('static const struct of_device_id bq256xx_of_match[] = {\n'
              '\t{ .compatible = "ti,bq25601", .data = &bq256xx_chip_info_tbl[BQ25601] },\n\t{}\n};\n')
        acpi = ('static const struct acpi_device_id bq256xx_acpi_match[] = {\n'
                '\t{ "bq25601", (kernel_ulong_t)&bq256xx_chip_info_tbl[BQ25601] },\n\t{}\n};\n')
        for entry, want in (('{ "bq25601", (kernel_ulong_t)&bq256xx_chip_info_tbl[BQ25601] }',
                             '\t{ "bq2560x_chg", (kernel_ulong_t)&bq256xx_chip_info_tbl[BQ25601] },\n'),
                            ('{ .name = "bq25601", .driver_data = (kernel_ulong_t)&bq256xx_chip_info_tbl[BQ25601] }',
                             '\t{ .name = "bq2560x_chg", .driver_data = (kernel_ulong_t)&bq256xx_chip_info_tbl[BQ25601] },\n')):
            with tempfile.TemporaryDirectory() as tree:
                f = Path(tree, 'drivers/power/supply/bq256xx_charger.c')
                f.parent.mkdir(parents=True)
                f.write_text('static const struct i2c_device_id bq256xx_i2c_ids[] = {\n\t' + entry + ',\n\t{}\n};\n'
                             'MODULE_DEVICE_TABLE(i2c, bq256xx_i2c_ids);\n' + of + acpi)
                for _ in range(2):
                    exec(code, {'os': os, 'tree': tree})
                t = f.read_text()
                self.assertEqual(t.count(want), 1, t)
                self.assertEqual(t.count('"ti,bq2560x_chg", .data = &bq256xx_chip_info_tbl[BQ25601]'), 1, t)
                self.assertNotIn('bq2560x_chg', t[t.index('acpi_device_id'):])   # the ACPI table stays as it was
        # and the build stops when it did not apply
        self.assertIn("('drivers/power/supply/bq256xx_charger.c', ['\"ti,bq2560x_chg\"", port)
        # the driver's handling of that node: no stale cache, Android's 1.98 A and 4.208 V at most, the chip's own
        # input current from the PMIC's charger detection on every VBUS change from the extcon, the chip's own only as
        # a fallback, charging on unless userspace said "N/A"
        p9 = (TOP / 'upstream' / 'patches' / '0009-power-bq256xx-drive-the-U30-Air-charger.patch').read_text()
        for s in ('.cache_type = REGCACHE_NONE', 'BQ2560X_CHG_ICHG_MAX_uA\t\t1980000', 'BQ2560X_CHG_VBATREG_MAX_uV\t4208000',
                  'BQ256XX_IINDET_EN', 'devm_extcon_register_notifier(dev, bq->vbus_edev, EXTCON_USB',
                  '"linux,extcon-usb-gpio"', 'bq->init_data.iindpm = 500000;', 'WRITE_ONCE(bq->chg_off',
                  'off ? 0 : BQ256XX_CHG_CONFIG_MASK', 'case BQ256XX_VBUS_STAT_USB_CDP:\n+\t\treturn 1500000;',
                  'case BQ256XX_VBUS_STAT_USB_DCP:\n+\t\treturn 2000000;', 'case BQ256XX_VBUS_STAT_NONSTD:\n+\t\treturn 1000000;',
                  'static char *supplied_to[] = { "sc27xx-fgu" };',
                  # the PMIC's charger detection first: the charger's own (IINDET_EN) drives D+/D-, the gadget's lines
                  'sprd_pmic_detect_charger_type(bq->pmic)', 'of_find_compatible_node(NULL, NULL, "sprd,ump9620")',
                  'bus_find_device_by_of_node(&spi_bus_type, np)', 'no charger type from the PMIC'):
            self.assertIn(s, p9)
        # the fuel gauge asks the charger by the name the driver registers
        p10 = (TOP / 'upstream' / 'patches' / '0010-power-sc27xx-fuel-gauge-status-from-bq256xx.patch').read_text()
        self.assertIn('+\t"bq256xx-charger",', p10)
        # the PMIC's charger detection reads the UMP9620's own register (0x239c), not the SC2730's (0x1b9c), and a
        # tree prepared with the old one is corrected
        self.assertIn(r"#define SPRD_UMP9620_CHG_DET\t\t0x239c", port)
        self.assertIn(r"'\t.charger_det = SPRD_SC2730_CHG_DET,\n};\n', UMP9620_DATA)", port)
        self.assertIn("'.charger_det = SPRD_UMP9620_CHG_DET,'", port)
        # Android's last capacity in the FGU's user area is whole percent in bits 7:0 and tenths in bits 11:8 (575 =
        # 0x23f = 63.2 %), not 0.1 %; mainline writes whole percent; an ambiguous or invalid value goes to the OCV; the
        # charger's Full (from a charger driver) means 100 %; the capacity is saved as it changes and stays 0-100
        patches = TOP / 'upstream' / 'patches'
        self.assertFalse((patches / '0011-power-sc27xx-fuel-gauge-UMP9620-capacity-in-tenths.patch').exists())
        p11 = (patches / '0011-power-sc27xx-fuel-gauge-UMP9620-saved-capacity-and-full.patch').read_text()
        for s in ('+#define UMP9620_FGU_CAP_INTEGER_MASK\tGENMASK(7, 0)', '+#define UMP9620_FGU_CAP_DECIMAL_MASK\tGENMASK(11, 8)',
                  '+\t\tcap = clamp(cap, 0, 100);', '+\tvalid = whole <= 100 && tenths <= 9 && !(whole == 100 && tenths);',
                  '+\tambiguous = tenths && value <= 1000 && !(value % 10);',
                  '+\tif (valid && (!ambiguous || abs(cur) >= UMP9620_FGU_RELAXED_MA)) {',
                  '+\t*cap = power_supply_ocv2cap_simple(data->cap_table, data->table_len, ocv);',
                  '+\tif (!is_first_poweron && data->var == &ump9620_info)',
                  '+\tif (data->var == &ump9620_info && chg_sts == POWER_SUPPLY_STATUS_FULL && cap != 100 &&',
                  '+\t    sc27xx_fgu_has_charger() &&', '+\t\tsc27xx_fgu_adjust_cap(data, 100);',
                  '+\t\tif (*cap != data->saved_cap && sc27xx_fgu_save_last_cap(data, *cap))',
                  '+\t\tval->intval = clamp(value, 0, 100);'):
            self.assertIn(s, p11)
        self.assertNotIn('* 10;', p11)
        # mu300-usb reaches the chip past the driver and leaves its watchdog off then
        usb = (BIN / 'mu300-usb').read_text()
        self.assertIn('[ -e "$R/sys/bus/i2c/devices/$BUS-006b/driver" ] && FORCE=-f', usb)

    def test_mainline_can_suspend(self):
        # System suspend (PSCI SYSTEM_SUSPEND) and a tickless idle: under the periodic tick a CPU brought back online
        # was left out of the timer broadcast and locked up, which every suspend (and `cpu7 offline/online`) hit
        cfg = (TOP / 'upstream' / 'mu300-mainline.config').read_text()
        for k in ('CONFIG_SUSPEND', 'CONFIG_PM_SLEEP', 'CONFIG_NO_HZ_IDLE', 'CONFIG_HIGH_RES_TIMERS'):
            self.assertRegex(cfg, rf'(?m)^{k}=y$')
        drv = TOP / 'upstream' / 'port' / 'drivers'
        # the PMIC watchdog keeps counting while the AP sleeps: stopped for the sleep, armed again after it
        wdt = (drv / 'watchdog' / 'ump9620-pmic-wdt.c').read_text()
        self.assertIn('NOIRQ_SYSTEM_SLEEP_PM_OPS(ump9620_wdt_suspend_noirq, ump9620_wdt_resume_noirq)', wdt)
        self.assertIn('.pm = pm_sleep_ptr(&ump9620_wdt_pm_ops)', wdt)
        self.assertIn('platform_set_drvdata(pdev, w);', wdt)
        # PCIe WAKE# is a wakeup only when power/wakeup says so, and is masked (unlazily) for the sleep otherwise
        pcie = (drv / 'pci' / 'controller' / 'dwc' / 'pcie-sprd.c').read_text()
        self.assertIn('if (device_may_wakeup(pci->dev))\n\t\tpm_wakeup_hard_event(pci->dev);', pcie)
        self.assertNotIn('IRQF_TRIGGER_FALLING | IRQF_NO_SUSPEND', pcie)
        self.assertIn('irq_set_status_flags(ctrl->wakeup_irq, IRQ_DISABLE_UNLAZY);', pcie)
        self.assertNotIn('device_init_wakeup(dev, true)', pcie)
        self.assertIn('SET_SYSTEM_SLEEP_PM_OPS(sprd_pcie_pm_suspend, sprd_pcie_pm_resume)', pcie)
        # the firmware's debug log pulled WAKE# right after every L2 entry: off by default, and a resume leaves it be
        mods = TOP / 'upstream' / 'modules'
        sysfs = (mods / 'wcn_bsp' / 'platform' / 'sysfs.c').read_text()
        self.assertRegex(sysfs, r'#endif\n(\t.*\n)*\tsysfs_info\.armlog_status = 0;\n')
        ep = (mods / 'wcn_bsp' / 'pcie' / 'pcie.c').read_text()
        resume = ep[ep.index('static int sprd_ep_resume('):ep.index('const struct dev_pm_ops sprd_ep_pm_ops')]
        self.assertNotIn('wcn_set_armlog(true)', resume)
        # without a WoWLAN configuration cfg80211 closed the interfaces while the bus was going down, and the
        # firmware asserted at the next Wi-Fi open: WoWLAN "any" from the wiphy's registration on
        iface = (mods / 'sprd_wlan_combo' / 'common' / 'iface.c').read_text()
        self.assertIn('wowlan->any = true;\n\t\t\twiphy->wowlan_config = wowlan;', iface)
        self.assertLess(iface.index('ret = wiphy_register(wiphy);'), iface.index('wiphy->wowlan_config = wowlan;'))

    def test_mainline_config_has_kvm_and_the_module_set(self):
        # /dev/kvm (the CPUs start at EL2) and the router/container modules; the kernel's own modules reach the bundle
        cfg = (TOP / 'upstream' / 'mu300-mainline.config').read_text()
        opts = {}
        for line in cfg.splitlines():
            if line.startswith('CONFIG_'):
                k, v = line.split('=', 1)
                # an option given twice must say the same thing both times: merge_config takes the last one silently
                self.assertEqual(opts.setdefault(k, v), v, k)
        for k in ('CONFIG_VIRTUALIZATION', 'CONFIG_KVM', 'CONFIG_MODULES', 'CONFIG_WIREGUARD', 'CONFIG_NET_SCH_CAKE',
                  'CONFIG_TUN', 'CONFIG_NF_FLOW_TABLE', 'CONFIG_IKCONFIG_PROC'):
            self.assertEqual(opts.get(k), 'y', k)
        for k in ('CONFIG_VHOST_NET', 'CONFIG_NTFS3_FS', 'CONFIG_DM_CRYPT', 'CONFIG_NET_SCH_HTB', 'CONFIG_USB_NET_CDC_MBIM',
                  'CONFIG_XFRM_USER', 'CONFIG_BRIDGE_NETFILTER', 'CONFIG_BINFMT_MISC', 'CONFIG_SND_USB_AUDIO'):
            self.assertEqual(opts.get(k), 'm', k)
        mods = (TOP / 'upstream' / 'build-modules.sh').read_text()
        self.assertIn('INSTALL_MOD_STRIP=1 DEPMOD=true modules_install', mods)
        self.assertIn('has the name of an in-tree module', mods)

    def test_ttl_page_is_wired(self):
        # Cellular > TTL: the menu entry right after the AT terminal, its view, the rpc declarations in common.js,
        # ttl_get readable and ttl_set only with write access, the adapter executable
        import json
        app = TOP / 'openwrt' / 'luci-app-mu300'
        menu = json.loads((app / 'root/usr/share/luci/menu.d/luci-app-mu300.json').read_text())
        ttl = menu['admin/modem/ttl']
        self.assertEqual(ttl['title'], 'TTL')
        self.assertEqual(ttl['action'], {'type': 'view', 'path': 'mu300/ttl'})
        cellular = sorted((v['order'], k) for k, v in menu.items() if k.startswith('admin/modem/'))
        keys = [k for _, k in cellular]
        self.assertEqual(keys[keys.index('admin/modem/at') + 1], 'admin/modem/ttl')
        self.assertEqual(len({o for o, _ in cellular}), len(cellular), 'two Cellular pages with the same order')
        self.assertTrue((app / 'htdocs/luci-static/resources/view/mu300/ttl.js').is_file())
        common = (app / 'htdocs/luci-static/resources/mu300/common.js').read_text()
        self.assertIn("method: 'ttl_get'", common)
        self.assertIn("method: 'ttl_set', params: [ 'value' ]", common)
        self.assertIn('callTtlGet: callTtlGet, callTtlSet: callTtlSet', common)
        acl = json.loads((app / 'root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())['luci-app-mu300']
        self.assertIn('ttl_get', acl['read']['ubus']['mu300dash'])
        self.assertNotIn('ttl_set', acl['read']['ubus']['mu300dash'])
        self.assertIn('ttl_set', acl['write']['ubus']['mu300dash'])
        self.assertTrue((app / 'root/usr/libexec/unisoc-modem/ttl').stat().st_mode & 0o111)
        # the fast-path note belongs to the nft backend only
        view = (app / 'htdocs/luci-static/resources/view/mu300/ttl.js').read_text()
        self.assertRegex(view, r"if \(st\.backend === 'nft'\)\s*card\.appendChild\([^;]*firewall fast-path is off")

    def test_mainline_rewrites_the_ttl_in_tc(self):
        # mu300-ttl's tc backend (clsact egress, matchall, pedit, csum): the flowtable transmits through egress, so
        # flow offloading stays on. The 5.4 kernel has no pedit: mu300-ttl falls back to nftables there.
        cfg = (TOP / 'upstream' / 'mu300-mainline.config').read_text()
        for k in ('CONFIG_NET_SCH_INGRESS', 'CONFIG_NET_CLS_ACT'):
            self.assertRegex(cfg, rf'(?m)^{k}=y$')
        for k in ('CONFIG_NET_CLS_MATCHALL', 'CONFIG_NET_ACT_PEDIT', 'CONFIG_NET_ACT_CSUM'):
            self.assertRegex(cfg, rf'(?m)^{k}=[ym]$')
        # tc itself: tc-tiny comes with sqm-scripts on OpenWrt
        self.assertIn('sqm-scripts', (TOP / 'openwrt' / 'build-rootfs.sh').read_text())

    def test_every_release_kernel_bundle_has_the_sd_host(self):
        # 5.4 reads the card as well (FINDINGS 31j): its bundle says so, and the release audit fails when any of the
        # three bundles does not (mu300-update refuses such a bundle for a system on the card)
        mr = (TOP / 'tools' / 'make-release.sh').read_text()
        self.assertIn("printf 'sdcard\\nlinux-slot\\n' > \"$K/features\"", mr)
        self.assertLess(mr.index('$K/features'), mr.index('tar -C "$K" -czf "$D/mu300-kernel.tar.gz" .'))
        self.assertIn('for a in mu300-kernel mu300-kernel-6.18 mu300-kernel-7.2; do\n'
                      '    tar -xzOf "$D/$a.tar.gz" ./features 2>/dev/null | grep -qx sdcard', mr)
        # and that its init works with Linux on either slot (mu300-update refuses one without it on slot a)
        self.assertIn('    tar -xzOf "$D/$a.tar.gz" ./features 2>/dev/null | grep -qx linux-slot', mr)

    def test_release_can_be_a_prerelease(self):
        # a release is published as a prerelease first and promoted to "latest" only after a board ran it: the
        # option reaches `gh release create`, and an unknown option stops the script instead of being ignored
        mr = (TOP / 'tools' / 'make-release.sh').read_text()
        self.assertIn('--prerelease) PRERELEASE=--prerelease ;;', mr)
        self.assertIn('--publish) PUBLISH=--publish ;;', mr)
        self.assertRegex(mr, r'\*\) echo "unknown option \$a')
        self.assertRegex(mr, r'gh release create "\$TAG" [^\n]*\$PRERELEASE')
        self.assertNotIn('--latest', mr)

    def test_proc_reads_are_braced(self):
        # `tr < /proc/$pid/cmdline 2>/dev/null` reports a failed redirection (the process just went) before its own
        # 2>/dev/null applies, so "can't open /proc/..." reaches the log: the read is braced, `{ tr < ...; } 2>/dev/null`
        files = [p for p, _ in shell_scripts()]
        files += [p for p in (TOP / 'openwrt' / 'luci-app-mu300' / 'root').rglob('*')
                  if p.is_file() and shebang(p).endswith('sh')]
        bad = re.compile(r'<\s*"?/proc/\$[^\s;|]*\s+2>\s*/dev/null')
        found = []
        for p in sorted(set(files)):
            for n, line in enumerate(p.read_text(errors='replace').splitlines(), 1):
                if bad.search(line):
                    found.append(f'{p.relative_to(TOP)}:{n}')
        self.assertEqual(found, [])

    def test_quiet_console_sysctl_on_both_systems(self):
        # K24: both images carry the same drop-in (systemd-sysctl on Ubuntu, procd's /etc/init.d/sysctl on OpenWrt)
        a = (TOP / 'rootfs' / 'overlay' / 'etc' / 'sysctl.d' / '99-mu300-console.conf').read_text()
        b = (TOP / 'openwrt' / 'overlay' / 'etc' / 'sysctl.d' / '99-mu300-console.conf').read_text()
        self.assertEqual(a, b)
        self.assertRegex(a, r'(?m)^kernel\.printk = 1$')

    def test_modem_control_is_released_early_and_without_a_fixed_wait(self):
        # K22, K23: S09 (leading zero kept, rc.common embeds START verbatim: S9 would sort after S19) and no
        # unconditional sleep before android-vendor-start, which waits for the modem nodes itself
        f = (TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d' / 'mu300-vendor').read_text()
        self.assertRegex(f, r'(?m)^START=09$')
        self.assertIn('leading zero', f)
        self.assertIn('procd_set_param command /opt/mu300/bin/android-vendor-start\n', f)
        self.assertNotRegex(f, r'sleep 5')
        # nothing else may order itself in front of it
        for s in (TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d').iterdir():
            m = re.search(r'(?m)^START=(\d+)', s.read_text())
            if s.name != 'mu300-vendor' and m:
                self.assertGreater(int(m.group(1)), 9, s.name)

    def test_atd_before_the_network_with_a_second_daemon_on_nr2(self):
        # K16, K17, K18, K21: S19 (the dial at S20 asks the daemon), nr1 and nr2 only, nr2 without a URC channel
        f = (TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d' / 'mu300-atd').read_text()
        self.assertRegex(f, r'(?m)^START=19$')
        # K20: radio-warmup is the third instance, and it opens no channel: it waits for nr1's daemon and asks it
        # These assertions describe the unchanged default SIM1 path. SIM2 is exercised by test_sim2.
        f = f[:f.index('\nbroker() {')]
        self.assertEqual(re.findall(r'procd_open_instance (\S+)', f), ['atd', 'atd2', 'radio-warmup'])
        warm = f[f.index('procd_open_instance radio-warmup'):]
        warm = warm[:warm.index('procd_close_instance')]
        self.assertIn('until [ -p /run/mu300-at/cmd ]', warm)
        self.assertIn('exec /opt/mu300/bin/mobile-data radio-on', warm)
        # a charging boot (init's marker) keeps the radio off until the Wi-Fi key
        self.assertLess(warm.index('[ -e /run/mu300/charging-boot ] && exit 0'), warm.index('mobile-data radio-on'))
        self.assertNotIn('stty_nr', warm)
        self.assertNotIn('respawn', warm)   # one round per start; netifd's dial and watch retry
        self.assertIn('wait_and_exec /dev/stty_nr1 /opt/mu300/bin/mu300-atd', f)
        self.assertIn('wait_and_exec /dev/stty_nr2 /opt/mu300/bin/mu300-atd', f)
        self.assertIn('procd_set_param env MU300_AT_DEV=/dev/stty_nr2 MU300_AT_DIR=/run/mu300-at2 '
                      'MU300_AT_URC_CHANNELS=\n', f)
        self.assertNotRegex(f, r'stty_nr[3-7]')
        self.assertIn('[ ! -x /usr/libexec/unisoc-modem/lock ] || : > /run/unisoc-modem-early-hook-pending', f)
        u = (TOP / 'rootfs' / 'overlay' / 'etc' / 'systemd' / 'system' / 'mu300-atd2.service').read_text()
        for line in ('Environment=MU300_AT_DEV=/dev/stty_nr2', 'Environment=MU300_AT_DIR=/run/mu300-at2',
                     'Environment=MU300_AT_URC_CHANNELS=\n', 'ConditionPathExists=|/dev/stty_nr2'):
            self.assertIn(line, u)
        self.assertIn('mu300-atd2.service:multi-user.target', (TOP / 'rootfs' / 'assemble.sh').read_text())
        self.assertIn('mu300-atd2.service:multi-user.target', (TOP / 'arch' / 'build-rootfs.sh').read_text())

    def test_cellular_downlink_in_the_software_flowtable(self):
        # K28, K29: mu300cell reports sipa_eth0 as l3_device only, so fw4 leaves it out of its flowtable and the
        # downlink takes the slow forwarding path. The patch puts it in; it is applied with --fuzz=0 to every OpenWrt
        # system (outside the panel block), so a changed fw4 fails the build instead of shipping without it.
        patch = (TOP / 'openwrt' / 'patches' / 'fw4-sipa-offload.patch').read_text()
        self.assertIn('+++ b/usr/share/ucode/fw4.uc', patch)
        self.assertIn("+\t\t\tif (fs.access('/sys/class/net/sipa_eth0'))", patch)
        self.assertIn("+\t\t\t\tpush(devices, 'sipa_eth0');", patch)
        text = (TOP / 'openwrt' / 'build-rootfs.sh').read_text()
        self.assertIn('-v "$FW4PATCH":/in/fw4-sipa-offload.patch:ro', text)
        apply = 'patch --batch --fuzz=0 -d $R -p1 -i /in/fw4-sipa-offload.patch'
        self.assertIn(apply, text)
        self.assertLess(text.index('cp -a /in/overlay/. $R/'), text.index(apply))
        self.assertLess(text.index(apply), text.index('if [ -d /in/luci-plugin ]; then\n    [ -d /in/luci-overlay ]'))
        # the patch tool is installed after the copy into $R: the build container has it, the image does not
        self.assertLess(text.index('for e in /*; do'), text.index('apk add patch'))
        self.assertLess(text.index(apply), text.index('apk del patch'))
        self.assertLess(text.index('apk del patch'), text.index('apk list --installed | sort'))
        # software offloading on, hardware off: the SIPA and SC2355 drivers have no nftables hardware offload
        uci = (OPENWRT / 'etc' / 'uci-defaults' / '90-mu300').read_text()
        self.assertIn("uci -q set firewall.@defaults[0].flow_offloading='1'", uci)
        self.assertIn("uci -q set firewall.@defaults[0].flow_offloading_hw='0'", uci)
        self.assertIn('uci commit firewall', uci)

    def test_build_stops_without_the_cellular_protocol(self):
        # K74: without mu300cell.sh netifd has no wan, and the image would boot without mobile data; openwrt-luci's
        # first boot selects relay mode (K30), which runs mu300cell-v6.sh: its overlay must have it, whatever
        # mu300cell.sh says. Checked before any download.
        def run(files, system, extra_env=None):
            with tempfile.TemporaryDirectory() as d:
                top = Path(d)
                (top / 'openwrt').mkdir()
                shutil.copy(TOP / 'openwrt' / 'build-rootfs.sh', top / 'openwrt' / 'build-rootfs.sh')
                for rel, body in files.items():
                    (top / rel).parent.mkdir(parents=True, exist_ok=True)
                    (top / rel).write_text(body)
                env = dict(os.environ, MU300_SYSTEM=system, MU300_INPUTS=d, PATH='/usr/bin:/bin',
                           MU300_LUCI_THEME_APK=str(top / 'no-theme.apk'))
                env.update(extra_env or {})
                return subprocess.run(['sh', str(top / 'openwrt' / 'build-rootfs.sh'), 'x.tar.gz'], env=env,
                                      capture_output=True, text=True, timeout=30)
        cell = 'openwrt/overlay/lib/netifd/proto/mu300cell.sh'
        v6 = 'openwrt/luci-overlay/lib/netifd/proto/mu300cell-v6.sh'
        patch = {'openwrt/patches/fw4-sipa-offload.patch': 'x\n'}
        for system in ('openwrt', 'openwrt-luci'):
            with self.subTest(system=system, missing='mu300cell.sh'):
                r = run(patch, system)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn('mu300cell.sh', r.stderr)
            with self.subTest(system=system, missing='the patch'):
                r = run({cell: 'x\n', v6: 'x\n'}, system)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn('fw4-sipa-offload.patch', r.stderr)
        # openwrt-luci needs the monitor even when mu300cell.sh does not name it; plain OpenWrt (never relay) does not
        r = run(dict(patch, **{cell: 'x\n'}), 'openwrt-luci')
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn('mu300cell-v6.sh', r.stderr)
        # with every file present neither check stops the build (it stops later: openwrt-luci at the theme this tree
        # lacks, plain OpenWrt at its download, which a curl stub refuses)
        with tempfile.TemporaryDirectory() as stubs:
            curl = Path(stubs) / 'curl'
            curl.write_text('#!/bin/sh\necho "curl: stub refuses" >&2\nexit 22\n')
            curl.chmod(0o755)
            for system, files in (('openwrt', dict(patch, **{cell: 'x\n'})),
                                  ('openwrt-luci', dict(patch, **{cell: 'x\n', v6: 'x\n'}))):
                r = run(files, system, {'PATH': f'{stubs}:/usr/bin:/bin'})
                self.assertNotEqual(r.returncode, 0, r.stderr)
                self.assertIn('stub refuses' if system == 'openwrt' else 'theme package missing', r.stderr)
                self.assertNotIn('required cellular protocol helper missing', r.stderr)
                self.assertNotIn('fw4-sipa-offload.patch', r.stderr)

    def test_panel_mounts_survive_spaces_in_paths(self):
        # final review minor 5: the panel system's docker mounts were one word-split string; a checkout or a
        # MU300_LUCI_THEME_APK path with a space broke the build. They are the positional parameters now, each path
        # one argument: the build's own `set --` statement is run with spaces in every path
        text = (TOP / 'openwrt' / 'build-rootfs.sh').read_text()
        self.assertNotIn('$LUCI', text)
        m = re.search(r'\n    (set -- -v "\$THEME_APK:.*?:/in/catalogs:ro")\n', text, re.S)
        self.assertTrue(m, 'the luci mounts are not one set -- statement')
        self.assertRegex(text, r'-v "\$REGDB":/in/regdb:ro "\$@" \\\n')
        for sh in shells():
            r = subprocess.run(sh + ['-c', m.group(1) + '\nprintf "%s\\n" "$@"'], capture_output=True, text=True,
                               env=dict(os.environ, THEME_APK='/a b/theme.apk', TOP='/my repo', CAT='/t m/cat'))
            self.assertEqual(r.stdout.splitlines(), [
                '-v', '/a b/theme.apk:/in/luci-theme-aurora.apk:ro', '-v', '/my repo/openwrt/luci-app-mu300:/in/luci-plugin:ro',
                '-v', '/my repo/openwrt/luci-overlay:/in/luci-overlay:ro', '-v', '/t m/cat:/in/catalogs:ro'], sh)

    def test_openwrt_luci_starts_ndp_learn(self):
        # K37: init.d/mu300-ndp is enabled in openwrt-luci's image (it does nothing unless wan is in relay mode) and
        # is executable there, beside the SMS service
        text = (TOP / 'openwrt' / 'build-rootfs.sh').read_text()
        block = text[text.index('ln -sf ../init.d/unisoc-modem-ui $R/etc/rc.d/'):text.index('apk list --installed | sort')]
        self.assertIn('$R/etc/init.d/mu300-ndp', block)
        self.assertIn('ln -sf ../init.d/mu300-ndp $R/etc/rc.d/S${n}mu300-ndp', block)
        for f in ('etc/init.d/mu300-ndp', 'opt/mu300/bin/ndp-learn', 'lib/netifd/proto/mu300cell-v6.sh'):
            self.assertTrue((LUCI_OVERLAY / f).stat().st_mode & 0o111, f)

    def test_wifi_power_transitions_are_serialised(self):
        # FINDINGS 31n: the probe's power-off (outside RTNL) ran post_deinit while hostapd's open ran post_init;
        # post_deinit cleared the context post_init had just set, and the next RX interrupt read it as NULL in hard
        # IRQ. Both kernels' drivers hold a mutex across the power transition and drop RX with no context
        wlan = TOP / 'upstream' / 'modules' / 'sprd_wlan_combo'
        patch = (TOP / 'kernel' / 'patches' / 'wlan_combo-wcn-power-serialise.patch').read_text()
        hif = (wlan / 'common' / 'hif.h').read_text()
        iface = (wlan / 'common' / 'iface.c').read_text()
        pcie = (wlan / 'sc2355' / 'pcie.c').read_text()
        self.assertIn('\tstruct mutex power_lock;', hif)
        self.assertIn('+\tstruct mutex power_lock;', patch)
        for text, pre in ((iface, ''), (patch, '+')):
            self.assertIn(pre + '\tmutex_init(&hif->power_lock);', text)
            self.assertIn(pre + '\tmutex_lock(&hif->power_lock);', text)
            self.assertIn(pre + '\tmutex_unlock(&hif->power_lock);', text)
        body = iface[iface.index('int sprd_iface_set_power('):]
        body = body[:body.index('\n}\n')]
        # no return between the lock and the unlock
        self.assertNotIn('return ret;', body[:body.index('mutex_unlock')])
        rx = pcie[pcie.index('static int pcie_rx_handle('):]
        rx = rx[:rx.index('\n}\n')]
        guard = 'rx_mgmt = hif ? (struct rx_mgmt *)READ_ONCE(hif->rx_mgmt) : NULL;'
        self.assertLess(rx.index(guard), rx.index('if (unlikely(!rx_mgmt))'))
        self.assertLess(rx.index('if (unlikely(!rx_mgmt))'), rx.index('rx_mgmt->rx_list'))
        self.assertIn('+\t' + guard, patch)
        # remove powers off before sprd_core_free frees priv (and hif, and the lock in it)
        rm = iface[iface.index('int sprd_iface_remove('):]
        self.assertLess(rm.index('sprd_iface_set_power(hif, false);'), rm.index('sprd_core_free(priv);'))
        for text, pre in ((pcie, ''), (patch, '+')):
            self.assertIn(pre + '\tsmp_store_release(&sc2355_hif.hif, (void *)hif);', text)
            self.assertIn(pre + '\tWRITE_ONCE(sc2355_hif.hif, NULL);', text)


if __name__ == '__main__':
    unittest.main()
