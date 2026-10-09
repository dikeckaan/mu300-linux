#!/usr/bin/env python3
"""Copy the MU300 driver ports (drivers ported from the Unisoc 5.4 tree) into a mainline tree and hook up
Makefile/Kconfig entries. Idempotent. usage: install.py <kernel tree>"""
import os, shutil, sys
tree = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
for root, _, files in os.walk(here):
    for f in files:
        if f in ('install.py',) or root == here:
            continue
        rel = os.path.relpath(os.path.join(root, f), here)
        dst = os.path.join(tree, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if not os.path.exists(dst) or open(os.path.join(root, f), 'rb').read() != open(dst, 'rb').read():
            shutil.copyfile(os.path.join(root, f), dst)

def append_once(path, marker, text):
    p = os.path.join(tree, path)
    s = open(p).read()
    if marker not in s:
        open(p, 'w').write(s.rstrip('\n') + '\n' + text)

append_once('drivers/clk/sprd/Makefile', 'reset.o', 'clk-sprd-y\t+= reset.o\n')
append_once('drivers/clk/sprd/Makefile', 'ums9620-clk.o', 'obj-$(CONFIG_SPRD_UMS9620_CLK)\t\t+= ums9620-clk.o\n')
kc = os.path.join(tree, 'drivers/clk/sprd/Kconfig')
s = open(kc).read()
if 'SPRD_UMS9620_CLK' not in s:
    i = s.rindex('endif')
    s = s[:i] + ('config SPRD_UMS9620_CLK\n\ttristate "Support for the Unisoc UMS9620 clocks"\n'
                 '\tdepends on (ARM64 && SPRD_COMMON_CLK) || COMPILE_TEST\n\tdefault ARM64\n'
                 '\thelp\n\t  Support for the global clock controller on UMS9620 devices (ported from the Unisoc 5.4 kernel).\n\n') + s[i:]
    open(kc, 'w').write(s)
append_once('drivers/pmdomain/Makefile', 'sprd/', 'obj-y\t\t\t\t\t+= sprd/\n')
kp = os.path.join(tree, 'drivers/pmdomain/Kconfig')
k = open(kp).read()
if 'SPRD_UMS9620_IPA_PD' not in k:
    i = k.rindex('endmenu')
    k = k[:i] + ('config SPRD_UMS9620_IPA_PD\n\tbool "Unisoc UMS9620 IPA subsystem power domain"\n'
                 '\tdepends on ARCH_SPRD && PM\n\tselect PM_GENERIC_DOMAINS\n\tselect MFD_SYSCON\n\tdefault y\n\n') + k[i:]
    open(kp, 'w').write(k)

# UMP9620 PMIC: MFD match data (IRQ base 0x80, 11 IRQs) and the ported regulator driver
mfd = os.path.join(tree, 'drivers/mfd/sprd-sc27xx-spi.c')
m = open(mfd).read()
def once(marker, old, new):
    """replace old by new unless marker is there already: every edit on its own, so a tree a failed run left
    half-edited is finished rather than skipped"""
    global m
    if marker not in m:
        m = m.replace(old, new, 1)
once('ump9620_data = {', 'static const struct sprd_pmic_data sc2731_data = {',
     'static const struct sprd_pmic_data ump9620_data = {\n\t.irq_base = 0x80,\n\t.num_irqs = 11,\n\t.charger_det = SPRD_SC2730_CHG_DET,\n};\n\nstatic const struct sprd_pmic_data sc2731_data = {')
if 'enum sprd_pmic_type' not in m:
    # up to 6.x: the match data is the pmic data, and the DT's sub-nodes are populated as they are
    once('"sprd,ump9620"', '\t{ .compatible = "sprd,sc2731", .data = &sc2731_data },\n',
         '\t{ .compatible = "sprd,sc2731", .data = &sc2731_data },\n\t{ .compatible = "sprd,ump9620", .data = &ump9620_data },\n')
    once('.name = "ump9620"', '\t{ .name = "sc2731", .driver_data = (unsigned long)&sc2731_data },\n',
         '\t{ .name = "sc2731", .driver_data = (unsigned long)&sc2731_data },\n\t{ .name = "ump9620", .driver_data = (unsigned long)&ump9620_data },\n')
else:
    # 7.x: the match data is a PMIC type, and each type brings a list of MFD cells. The vendor DT's sub-nodes are
    # in no list, so UMP9620 gets no cells and its sub-nodes populated as before.
    once('PMIC_TYPE_UMP9620,', '\tPMIC_TYPE_SC2731,\n', '\tPMIC_TYPE_SC2731,\n\tPMIC_TYPE_UMP9620,\n')
    once('case PMIC_TYPE_UMP9620:', '\tdefault:\n\t\tdev_err(&spi->dev, "Invalid device ID\\n");',
         '\tcase PMIC_TYPE_UMP9620:\n\t\t/* MU300: no cells; the DT\'s own sub-nodes are populated below */\n'
         '\t\tpdata = &ump9620_data;\n\t\tcells = NULL;\n\t\tnum_cells = 0;\n\t\tbreak;\n'
         '\tdefault:\n\t\tdev_err(&spi->dev, "Invalid device ID\\n");')
    once('if (pmic_type == PMIC_TYPE_UMP9620) {',
         '\t\tdev_err(&spi->dev, "Failed to populate sub-devices %d\\n", ret);\n\t\treturn ret;\n\t}\n',
         '\t\tdev_err(&spi->dev, "Failed to populate sub-devices %d\\n", ret);\n\t\treturn ret;\n\t}\n\n'
         '\tif (pmic_type == PMIC_TYPE_UMP9620) {\n\t\tret = devm_of_platform_populate(&spi->dev);\n'
         '\t\tif (ret)\n\t\t\treturn ret;\n\t}\n')
    once('"sprd,ump9620"', '\t{ .compatible = "sprd,sc2731", .data = (void *)PMIC_TYPE_SC2731 },\n',
         '\t{ .compatible = "sprd,sc2731", .data = (void *)PMIC_TYPE_SC2731 },\n'
         '\t{ .compatible = "sprd,ump9620", .data = (void *)PMIC_TYPE_UMP9620 },\n')
    once('.name = "ump9620"', '\t{ .name = "sc2731", .driver_data = PMIC_TYPE_SC2731 },\n',
         '\t{ .name = "sc2731", .driver_data = PMIC_TYPE_SC2731 },\n\t{ .name = "ump9620", .driver_data = PMIC_TYPE_UMP9620 },\n')
    once('linux/of_platform.h', '#include <linux/module.h>', '#include <linux/module.h>\n#include <linux/of_platform.h>')
open(mfd, 'w').write(m)
append_once('drivers/regulator/Makefile', 'ump9620-regulator.o', 'obj-$(CONFIG_REGULATOR_UMP9620) += ump9620-regulator.o\n')
rk = os.path.join(tree, 'drivers/regulator/Kconfig')
r = open(rk).read()
if 'REGULATOR_UMP9620' not in r:
    i = r.rindex('endif')
    r = r[:i] + ('config REGULATOR_UMP9620\n\ttristate "Unisoc UMP9620 PMIC regulators"\n\tdepends on MFD_SC27XX_PMIC || COMPILE_TEST\n'
                 '\thelp\n\t  Regulators of the UMP9620 PMIC (ported from the Unisoc 5.4 kernel).\n\n') + r[i:]
    open(rk, 'w').write(r)

append_once('drivers/usb/phy/Makefile', 'phy-sprd-ums9620-ssphy.o', 'obj-$(CONFIG_USB_SPRD_UMS9620_SSPHY) += phy-sprd-ums9620-ssphy.o\n')
pk = os.path.join(tree, 'drivers/usb/phy/Kconfig')
k = open(pk).read()
if 'USB_SPRD_UMS9620_SSPHY' not in k:
    i = k.rindex('endmenu')
    k = k[:i] + ('config USB_SPRD_UMS9620_SSPHY\n\ttristate "Unisoc UMS9620 USB 3.1 PHY"\n\tdepends on ARCH_SPRD\n\tselect USB_PHY\n\tselect MFD_SYSCON\n\n') + k[i:]
    open(pk, 'w').write(k)

# DWC3: vendor DT compatibles -> mainline of-simple glue (clocks, resets, power domain) and DWC3 core
for path, anchor, line in [
    ('drivers/usb/dwc3/dwc3-of-simple.c', '\t{ .compatible = "sprd,sc9860-dwc3" },\n', '\t{ .compatible = "sprd,qogirn6pro-dwc3" },\n'),
    ('drivers/usb/dwc3/core.c', '\t{\n\t\t.compatible = "synopsys,dwc3"\n\t},\n', '\t{\n\t\t.compatible = "snps,sprd-dwc3"\n\t},\n'),
]:
    fp = os.path.join(tree, path); t = open(fp).read()
    if line not in t:
        assert anchor in t, (path, anchor)
        t = t.replace(anchor, anchor + line, 1)
        open(fp, 'w').write(t)

append_once('drivers/watchdog/Makefile', 'ump9620-pmic-wdt.o', 'obj-$(CONFIG_MFD_SC27XX_PMIC) += ump9620-pmic-wdt.o\n')

# sdhci-sprd: the SD card can hold the Linux filesystem, so the card slot's host (sprd,name "sdio_sd") is probed
# next to the non-removable eMMC. Any other host the stock device tree describes (sdio_wifi: Wi-Fi is on PCIe on
# this board) stays unprobed, as before. An earlier version of this port let only the eMMC through; take that edit
# out of a kernel tree that was prepared with it.
sp = os.path.join(tree, 'drivers/mmc/host/sdhci-sprd.c')
t = open(sp).read()
t = t.replace('\t/* MU300: only the non-removable eMMC is used */\n'
              '\tif (!of_property_read_bool(pdev->dev.of_node, "non-removable"))\n\t\treturn -ENODEV;\n', '')
marker = 'MU300: only the eMMC and the card slot'
if marker not in t:
    anchor = 'static int sdhci_sprd_probe(struct platform_device *pdev)\n{\n'
    i = t.index(anchor) + len(anchor)
    j = t.index('\n\n', i) + 1          # after the local variable declarations
    t = t[:j] + '\t/* ' + marker + ' */\n' + '''\
\tif (!of_property_read_bool(pdev->dev.of_node, "non-removable") &&
\t    of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_sd") < 0)
\t\treturn -ENODEV;
''' + t[j:]
# The stock device tree gives the slot a card-detect GPIO on line 35 of the EIC's sync bank; mainline's sprd-eic
# gives that bank 24 lines, the lookup never succeeds and the host would stay deferred for ever (FINDINGS 31j). For
# the card slot alone the property is dropped and the parse run again: mmc_of_parse() requests the CD GPIO before
# it reads the write protect, the bus modes (sd-uhs-sdr104, no-sdio, no-mmc) and the power sequence, so a parse that
# stopped at the CD GPIO would leave all of those out. The host then polls for the card.
parse_old = '\tret = mmc_of_parse(host->mmc);\n\tif (ret)\n\t\treturn ret;\n'
parse_new = '''\tret = mmc_of_parse(host->mmc);
\tif (ret == -EPROBE_DEFER &&
\t    of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_sd") >= 0) {
\t\tstruct property *cd = of_find_property(pdev->dev.of_node, "cd-gpios", NULL);

\t\tif (cd && !of_remove_property(pdev->dev.of_node, cd)) {
\t\t\tdev_warn(&pdev->dev, "MU300: CD GPIO deferred, polling the card slot\\n");
\t\t\tret = mmc_of_parse(host->mmc);
\t\t\thost->mmc->caps |= MMC_CAP_NEEDS_POLL;
\t\t}
\t}
\tif (ret)
\t\treturn ret;
'''
# a tree prepared by the first version of this edit, which only masked the deferral (and so the rest of the parse)
masked = '''\tret = mmc_of_parse(host->mmc);
\tif (ret == -EPROBE_DEFER &&
\t    of_property_present(pdev->dev.of_node, "cd-gpios") &&
\t    of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_sd") >= 0) {
\t\tdev_warn(&pdev->dev, "MU300: CD GPIO deferred, polling the card slot\\n");
\t\thost->mmc->caps |= MMC_CAP_NEEDS_POLL;
\t\tret = 0;
\t}
\tif (ret)
\t\treturn ret;
'''
t = t.replace(masked, parse_old)
if 'of_remove_property(pdev->dev.of_node, cd)' not in t:
    if parse_old not in t:
        sys.exit('port: sdhci-sprd mmc_of_parse anchor changed')
    t = t.replace(parse_old, parse_new, 1)
# The eMMC is mmc0 and the card slot mmc1. The stock device tree has no mmc aliases, so the host index is the order
# in which the two hosts reach sdhci_pltfm_init(), and both probe asynchronously: about one boot in twenty the card
# slot came first, the card became mmcblk0 and the eMMC mmcblk1, and init (and everything after it) took the card
# for the eMMC - it never found the card and rebooted at 300 s (FINDINGS 31l). The card slot's host now defers until
# the eMMC's host is added; the deferral is checked before sdhci_pltfm_init(), which allocates the index. If the eMMC's
# host never binds, the card slot's host stays deferred: there is no root on the card without a working eMMC host.
emmc_marker = 'MU300: the eMMC is mmc0'
if emmc_marker not in t:
    probe = 'static int sdhci_sprd_probe(struct platform_device *pdev)\n{\n'
    t = t.replace(probe, '/* ' + emmc_marker + ''', the card slot mmc1: see sdhci_sprd_probe() */
static bool sdhci_sprd_emmc_added;

static bool sdhci_sprd_emmc_pending(struct device_node *self)
{
	struct device_node *np;

	if (READ_ONCE(sdhci_sprd_emmc_added))
		return false;
	for_each_compatible_node(np, NULL, "sprd,sdhci-r11") {
		if (np != self && of_device_is_available(np) &&
		    of_property_read_bool(np, "non-removable")) {
			of_node_put(np);
			return true;
		}
	}
	return false;
}

''' + probe, 1)
    filt = '''\tif (!of_property_read_bool(pdev->dev.of_node, "non-removable") &&
\t    of_property_match_string(pdev->dev.of_node, "sprd,name", "sdio_sd") < 0)
\t\treturn -ENODEV;
'''
    if filt not in t:
        sys.exit('port: sdhci-sprd host filter anchor changed')
    t = t.replace(filt, filt + '''\t/* MU300: the card slot waits for the eMMC's host. If that never binds, the card slot stays deferred:
\t * no SD root without a working eMMC host. */
\tif (!of_property_read_bool(pdev->dev.of_node, "non-removable") &&
\t    sdhci_sprd_emmc_pending(pdev->dev.of_node))
\t\treturn -EPROBE_DEFER;
''', 1)
    add_old = '\tret = __sdhci_add_host(host);\n\tif (ret)\n\t\tgoto err_cleanup_host;\n'
    if add_old not in t:
        sys.exit('port: sdhci-sprd __sdhci_add_host anchor changed')
    t = t.replace(add_old, add_old + '''\tif (of_property_read_bool(pdev->dev.of_node, "non-removable"))
\t\tWRITE_ONCE(sdhci_sprd_emmc_added, true);
''', 1)
# UMS9620 has the r11p3 controller: the vendor driver programs DLL phase 0x2 (mainline 0x3,
# which gives data CRC errors on HS400ES writes while reads work)
t = t.replace('#define  SDHCI_SPRD_DLL_PHASE_INTERNAL\t0x3', '#define  SDHCI_SPRD_DLL_PHASE_INTERNAL\t0x2 /* MU300 r11p3 */')
open(sp, 'w').write(t)
# thermal: UMS9620 on-die sensors (vendor sprd_thermal_r5p0), calibration from eFuse
append_once('drivers/thermal/Makefile', 'sprd_thermal_r5p0.o', 'obj-$(CONFIG_SPRD_THERMAL_R5P0) += sprd_thermal_r5p0.o\n')
append_once('drivers/thermal/Kconfig', 'SPRD_THERMAL_R5P0', '''
config SPRD_THERMAL_R5P0
	tristate "Unisoc UMS9620 thermal sensors (r5p0)"
	depends on ARCH_SPRD || COMPILE_TEST
	depends on HAS_IOMEM && NVMEM && THERMAL_OF
''')

# sprd-efuse: add the UMS9620 (qogirn6pro) variant and make the provider strictly read-only.
# Writing blows eFuses permanently; nothing on this port needs it.
ep = os.path.join(tree, 'drivers/nvmem/sprd-efuse.c')
t = open(ep).read()
if 'qogirn6pro' not in t:
    t = t.replace('static const struct of_device_id sprd_efuse_of_match[] = {\n',
                  'static const struct sprd_efuse_variant_data qogirn6pro_data = {\n\t.blk_nums = 51,\n\t.blk_offset = 53,\n\t.blk_double = true,\n};\n\nstatic const struct of_device_id sprd_efuse_of_match[] = {\n\t{ .compatible = "sprd,qogirn6pro-efuse", .data = &qogirn6pro_data },\n', 1)
    t = t.replace('econfig.read_only = false;', 'econfig.read_only = true;\t/* MU300: never blow eFuses */')
    t = t.replace('\teconfig.reg_write = sprd_efuse_write;\n', '')
    t = t.replace('static int sprd_efuse_write(', 'static int __maybe_unused sprd_efuse_write(')
    open(ep, 'w').write(t)
assert 'reg_write' not in open(ep).read()
# cpufreq: UMS9620 apcpu DVFS is done by ATF through Unisoc SIP calls (vendor sprd_sip_svc + sprd-cpufreq-v2)
append_once('drivers/firmware/Makefile', 'sprd_sip_svc.o', 'obj-$(CONFIG_SPRD_SIP_SVC) += sprd_sip_svc.o\n')
append_once('drivers/firmware/Kconfig', 'SPRD_SIP_SVC', '''
config SPRD_SIP_SVC
	bool "Unisoc SIP services (DVFS through ATF)"
	depends on ARM64 && HAVE_ARM_SMCCC
''')
append_once('drivers/cpufreq/Makefile', 'sprd-cpufreq-v2-driver.o', 'obj-$(CONFIG_ARM_SPRD_CPUFREQ_V2) += sprd-cpufreq-v2-driver.o\n')
append_once('drivers/cpufreq/Kconfig.arm', 'ARM_SPRD_CPUFREQ_V2', '''
config ARM_SPRD_CPUFREQ_V2
	bool "Unisoc UMS9620 cpufreq (v2, ATF DVFS)"
	depends on SPRD_SIP_SVC && NVMEM
	select PM_OPP
''')
# PCIe RC for the Marlin3 (SC2355) Wi-Fi/BT chip: vendor pcie-sprd glue ported to the 6.18 DWC host API
append_once('drivers/pci/controller/dwc/Makefile', 'pcie-sprd.o', 'obj-$(CONFIG_PCIE_SPRD) += pcie-sprd-misc.o pcie-sprd.o\n')
append_once('drivers/pci/controller/dwc/Kconfig', 'config PCIE_SPRD', '''
config PCIE_SPRD
	bool "Unisoc UMS9620 PCIe host (Marlin3)"
	depends on OF && PCI_MSI
	select PCIE_DW_HOST
	select MFD_SYSCON
''')
# PMIC RTC (refnotify on the modem side needs /dev/rtc0): same registers as SC2731
rp = os.path.join(tree, 'drivers/rtc/rtc-sc27xx.c')
t = open(rp).read()
if 'ump96xx-rtc' not in t:
    t = t.replace('\t{ .compatible = "sprd,sc2731-rtc", },\n', '\t{ .compatible = "sprd,sc2731-rtc", },\n\t{ .compatible = "sprd,ump96xx-rtc", },\n', 1)
    open(rp, 'w').write(t)
# Every edit above is a text substitution, and one whose anchor drifted in a new kernel release changes nothing
# without saying so. Check the result rather than trusting the substitutions.
expect = [
    ('drivers/mfd/sprd-sc27xx-spi.c', ['ump9620_data = {', '"sprd,ump9620"', '.name = "ump9620"']
     + (['case PMIC_TYPE_UMP9620:', 'if (pmic_type == PMIC_TYPE_UMP9620) {', 'linux/of_platform.h']
        if 'enum sprd_pmic_type' in open(os.path.join(tree, 'drivers/mfd/sprd-sc27xx-spi.c')).read() else [])),
    ('drivers/mmc/host/sdhci-sprd.c', ['MU300: only the eMMC and the card slot', 'MU300: CD GPIO deferred', 'of_remove_property(pdev->dev.of_node, cd)', 'DLL_PHASE_INTERNAL\t0x2 /* MU300 r11p3 */',
                                     'MU300: the eMMC is mmc0', 'WRITE_ONCE(sdhci_sprd_emmc_added, true);']),
    ('drivers/nvmem/sprd-efuse.c', ['"sprd,qogirn6pro-efuse"', 'econfig.read_only = true;']),
    ('drivers/rtc/rtc-sc27xx.c', ['"sprd,ump96xx-rtc"']),
    ('drivers/usb/dwc3/dwc3-of-simple.c', ['"sprd,qogirn6pro-dwc3"']),
    ('drivers/usb/dwc3/core.c', ['"snps,sprd-dwc3"']),
]
missing = [(p, w) for p, ws in expect for w in ws if w not in open(os.path.join(tree, p)).read()]
if missing:
    sys.exit('port: edits did not apply (anchor changed in this kernel?): ' + '; '.join(f'{p}: {w}' for p, w in missing))
print('port installed')

# The PMIC's keypad backlight sink (leds-sc27xx-kpled.c): the Wi-Fi LED of the F50/V50 and the U30 Air's red
# network LED. (leds-zte-ldo.c, the U30 Air's white LEDs on PMIC LDOs, went with that device.)
LED_DRIVERS = (
    ('LEDS_SC27XX_KPLED', 'leds-sc27xx-kpled', 'Spreadtrum/Unisoc PMIC keypad backlight',
     'LEDS_CLASS && MFD_SC27XX_PMIC && OF', "The PMIC's keypad backlight sink: this board's status LED sink."),
)
kl = os.path.join(tree, 'drivers/leds/Kconfig')
kls = open(kl).read()
for sym, obj, title, deps, text in LED_DRIVERS:
    append_once('drivers/leds/Makefile', obj + '.o', f'obj-$(CONFIG_{sym})\t\t+= {obj}.o\n')
    if f'config {sym}\n' not in kls:
        i = kls.rindex('endif # NEW_LEDS')
        kls = kls[:i] + f'config {sym}\n\ttristate "{title}"\n\tdepends on {deps}\n\thelp\n\t  {text}\n\n' + kls[i:]
open(kl, 'w').write(kls)
