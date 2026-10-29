"""The camera (MM) and DPU/VSP power domains are powered off (upstream/port/drivers/pmdomain/sprd/ums9620-unused-pd.c),
and nothing in the kernel can read a block inside them afterwards:

* the clock driver registers no controller of those domains (clk_summary would read their gates and dividers, and
  their regmaps would appear in regmap debugfs);
* the power-off driver takes regmaps of the PMU APB and the AON APB only, follows the vendor's order (bus enable off,
  auto shutdown off, force shutdown on, wait for the off state, then the pixel PLL), and registers no genpd provider,
  so no driver of a device in those domains can probe;
* it is built in and binds only through the device tree, so it runs on every boot of both boards."""
import re
import unittest

from helpers import TOP

PD = TOP / 'upstream/port/drivers/pmdomain/sprd/ums9620-unused-pd.c'
CLK = TOP / 'upstream/port/drivers/clk/sprd/ums9620-clk.c'
DEAD_CLOCK_CONTROLLERS = ('sprd,ums9620-mm-gate', 'sprd,ums9620-mm-clk', 'sprd,ums9620-dpu-vsp-gate',
                          'sprd,ums9620-dpu-vsp-clk')


def function(text, name):
    """the body of the C function NAME in TEXT"""
    m = re.search(r'^\w[^\n]*\b%s\([^)]*\)\n\{\n(.*?)^\}\n' % re.escape(name), text, re.S | re.M)
    assert m, name
    return m.group(1)


class ClockControllers(unittest.TestCase):
    def test_none_in_the_powered_off_domains(self):
        text = CLK.read_text()
        for compat in DEAD_CLOCK_CONTROLLERS:
            self.assertNotIn('"%s"' % compat, text)
        # nothing else in the port binds to them either
        for p in (TOP / 'upstream/port').rglob('*.c'):
            for compat in DEAD_CLOCK_CONTROLLERS:
                self.assertNotIn('"%s"' % compat, p.read_text(errors='replace'), p)

    def test_the_stock_tree_still_names_them(self):
        # the controllers exist in the device tree the boards boot with: leaving them out is what keeps them away
        compats = (TOP / 'upstream/dt-compatibles.txt').read_text().split()
        for compat in DEAD_CLOCK_CONTROLLERS + ('sprd,qogirn6pro-camsys-domain', 'sprd,vpu-pd'):
            self.assertIn(compat, compats)


class PowerOff(unittest.TestCase):
    def setUp(self):
        self.text = PD.read_text()

    def test_only_pmu_and_aon_regmaps(self):
        self.assertEqual(self.text.count('syscon_regmap_lookup'), 1)
        get = function(self.text, 'pd_field_get')
        check = get.index('res.start != PMU_APB_BASE && res.start != AON_APB_BASE')
        self.assertLess(check, get.index('syscon_regmap_lookup_by_phandle_args'))
        self.assertIn('#define PMU_APB_BASE\t0x64910000', self.text)
        self.assertIn('#define AON_APB_BASE\t0x64900000', self.text)
        for banned in ('ioremap', 'devm_platform_ioremap', 'of_iomap', 'clk_get', 'syscon_node_to_regmap'):
            self.assertNotIn(banned, self.text)

    def test_vendor_order(self):
        probe = function(self.text, 'unused_pd_probe')
        steps = ['pd_subs_off(dev, np, d)', 'pd_write(&eb, false)', 'pd_write(&autosd, false)',
                 'pd_write(&force, true)', 'pd_wait(&state, STATE_OFF)', 'pd_write(&pll, false)']
        at = [probe.index(s) for s in steps]
        self.assertEqual(at, sorted(at))
        # a domain that is not on is left alone, and one that does not turn off is switched back on
        self.assertLess(probe.index('if (s != STATE_ON)'), at[1])
        self.assertIn('pd_write(&force, false)', probe)
        self.assertIn('pd_write(&eb, true)', probe)

    def test_set_and_clear_registers(self):
        # writes go to the set (+0x1000) and clear (+0x2000) registers: no read-modify-write of a register the
        # clock framework changes at the same time (the AON APB's enable register)
        self.assertNotIn('regmap_update_bits', self.text)
        self.assertIn('#define REG_SET\t\t0x1000', self.text)
        self.assertIn('#define REG_CLR\t\t0x2000', self.text)

    def test_vendor_device_tree_names(self):
        for prop in ('camera_power_state', 'aon_apb_mm_eb', 'shutdown_en', 'force_shutdown', 'isp_power_state',
                     'dcam_power_state', 'pmu-pwr-status-syscon', 'vpu-domain-eb-syscon',
                     'pmu-vpu-auto-shutdown-syscon', 'pmu-vpu-force-shutdown-syscon', 'pmu-apb-pixelpll-syscon',
                     'vdsp_power_state'):
            self.assertIn('"%s"' % prop, self.text)

    def test_no_genpd_provider(self):
        for call in ('pm_genpd_init', 'of_genpd_add_provider'):
            self.assertNotIn(call, self.text)

    def test_built_in(self):
        self.assertIn('builtin_platform_driver(unused_pd_driver);', self.text)
        self.assertNotIn('MODULE_DEVICE_TABLE', self.text)
        self.assertIn('.suppress_bind_attrs = true', self.text)
        self.assertIn('CONFIG_SPRD_UMS9620_UNUSED_PD=y\n', (TOP / 'upstream/mu300-mainline.config').read_text())
        self.assertIn('config SPRD_UMS9620_UNUSED_PD\\n\\tbool', (TOP / 'upstream/port/install.py').read_text())
        self.assertIn('obj-$(CONFIG_SPRD_UMS9620_UNUSED_PD) += ums9620-unused-pd.o',
                      (PD.parent / 'Makefile').read_text())


if __name__ == '__main__':
    unittest.main()
