// SPDX-License-Identifier: GPL-2.0-only
/*
 * Unisoc UMS9620 (qogirn6pro): powers off the camera (MM) and DPU/VSP power domains.
 *
 * The F50 and the U30 Air have no display, no camera and no driver for the video codecs, the DPU, the ISP or the
 * VDSP, yet the bootloader leaves both top domains on with their bus clocks enabled. The sequence is the Unisoc 5.4
 * one (camera/power sprd_camsys_pw_domain_qogirn6pro.c, video/sprd-vpu-power sprd_vpu_pw_domain.c): the domain's
 * bus enable in the AON APB off, auto shutdown off, force shutdown on, then the PMU state must read 7 (off) within
 * 15 ms; DPU/VSP also drops its pixel PLL. A domain is touched only when it is on and every sub-domain under it
 * is off; a domain that does not reach the off state is switched back on.
 *
 * No genpd provider is registered: a driver for a device of these domains can then never probe (its power domain
 * stays missing) and so never reaches a block that has no power. Every register written or read here lies in the
 * PMU APB or the AON APB, which stay powered; the blocks of the two domains (0x30000000-0x3fffffff except the IPA
 * side at 0x318xxxxx) get no clock controller and no syscon regmap in this kernel.
 */
#include <linux/bits.h>
#include <linux/mfd/syscon.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/platform_device.h>
#include <linux/property.h>
#include <linux/regmap.h>

#define PMU_APB_BASE	0x64910000
#define AON_APB_BASE	0x64900000
/* Unisoc global registers: writing a mask at reg + 0x1000 sets those bits, at reg + 0x2000 clears them */
#define REG_SET		0x1000
#define REG_CLR		0x2000
#define STATE_ON	0
#define STATE_OFF	7
#define POLL_US		300
#define TIMEOUT_US	15000

struct pd_field {
	struct regmap *map;
	u32 reg;
	u32 mask;
};

struct pd_desc {
	const char *state, *eb, *auto_shutdown, *force_shutdown, *pll;
	const char * const *sub_states;	/* sub-domain states in the domain's own node */
};

static const char * const camsys_subs[] = { "isp_power_state", "dcam_power_state", NULL };

static const struct pd_desc camsys_desc = {
	.state = "camera_power_state",
	.eb = "aon_apb_mm_eb",
	.auto_shutdown = "shutdown_en",
	.force_shutdown = "force_shutdown",
	.sub_states = camsys_subs,
};

static const struct pd_desc vpu_desc = {
	.state = "pmu-pwr-status-syscon",
	.eb = "vpu-domain-eb-syscon",
	.auto_shutdown = "pmu-vpu-auto-shutdown-syscon",
	.force_shutdown = "pmu-vpu-force-shutdown-syscon",
	.pll = "pmu-apb-pixelpll-syscon",
};

/* the state property of a device node that is a sub-domain of another one */
static const char * const child_states[] = { "pmu-pwr-status-syscon", "vdsp_power_state" };

/*
 * The field <syscon reg mask> of NP's property PROP; the syscon must be the PMU APB or the AON APB, so that no
 * regmap of a block inside the powered-off domains ever exists.
 */
static int pd_field_get(struct device_node *np, const char *prop, struct pd_field *f)
{
	struct device_node *sc = of_parse_phandle(np, prop, 0);
	struct resource res;
	struct regmap *map;
	u32 args[2];
	int ret;

	if (!sc)
		return -ENOENT;
	ret = of_address_to_resource(sc, 0, &res);
	of_node_put(sc);
	if (ret)
		return ret;
	if (res.start != PMU_APB_BASE && res.start != AON_APB_BASE)
		return -EPERM;
	map = syscon_regmap_lookup_by_phandle_args(np, prop, 2, args);
	if (IS_ERR(map))
		return PTR_ERR(map);
	if (!args[1] || args[0] + REG_CLR >= resource_size(&res))
		return -EINVAL;
	*f = (struct pd_field){ map, args[0], args[1] };
	return 0;
}

static int pd_state(const struct pd_field *f, u32 *state)
{
	u32 val;
	int ret = regmap_read(f->map, f->reg, &val);

	if (!ret)
		*state = (val & f->mask) >> __ffs(f->mask);
	return ret;
}

static void pd_write(const struct pd_field *f, bool set)
{
	regmap_write(f->map, f->reg + (set ? REG_SET : REG_CLR), f->mask);
}

static int pd_wait(const struct pd_field *f, u32 want)
{
	u32 val;

	return regmap_read_poll_timeout(f->map, f->reg, val, ((val & f->mask) >> __ffs(f->mask)) == want,
					POLL_US, TIMEOUT_US);
}

/* 0 when the state named PROP of NP reads off, -EBUSY when it does not, < 0 when it cannot be read */
static int pd_sub_off(struct device *dev, struct device_node *np, const char *prop)
{
	struct pd_field f;
	u32 state;
	int ret = pd_field_get(np, prop, &f);

	if (!ret)
		ret = pd_state(&f, &state);
	if (ret)
		return dev_err_probe(dev, ret, "%pOF %s\n", np, prop);
	if (state != STATE_OFF) {
		dev_warn(dev, "%pOF is on (%u), the domain stays on\n", np, state);
		return -EBUSY;
	}
	return 0;
}

/* every sub-domain of NP is off: those in its own node and the nodes that name NP as their power domain */
static int pd_subs_off(struct device *dev, struct device_node *np, const struct pd_desc *d)
{
	struct device_node *child;
	int i, ret;

	for (i = 0; d->sub_states && d->sub_states[i]; i++) {
		ret = pd_sub_off(dev, np, d->sub_states[i]);
		if (ret)
			return ret;
	}
	for_each_node_with_property(child, "power-domains") {
		struct device_node *parent = of_parse_phandle(child, "power-domains", 0);

		of_node_put(parent);
		if (parent != np)
			continue;
		for (i = 0; i < ARRAY_SIZE(child_states); i++) {
			if (!of_property_present(child, child_states[i]))
				continue;
			ret = pd_sub_off(dev, child, child_states[i]);
			if (ret) {
				of_node_put(child);
				return ret;
			}
		}
	}
	return 0;
}

static int unused_pd_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	const struct pd_desc *d = device_get_match_data(dev);
	struct pd_field state, eb, autosd, force, pll = { };
	u32 s;
	int ret;

	/* a sub-domain: its state is checked by the top domain's probe */
	if (of_property_present(np, "power-domains"))
		return -ENODEV;

	ret = pd_field_get(np, d->state, &state);
	if (!ret)
		ret = pd_field_get(np, d->eb, &eb);
	if (!ret)
		ret = pd_field_get(np, d->auto_shutdown, &autosd);
	if (!ret)
		ret = pd_field_get(np, d->force_shutdown, &force);
	if (!ret && d->pll && of_property_present(np, d->pll))
		ret = pd_field_get(np, d->pll, &pll);
	if (!ret)
		ret = pd_state(&state, &s);
	if (ret)
		return dev_err_probe(dev, ret, "cannot read the domain's PMU fields\n");
	if (s != STATE_ON) {
		dev_info(dev, "not on (state %u), left alone\n", s);
		return 0;
	}
	ret = pd_subs_off(dev, np, d);
	if (ret)
		return ret == -EBUSY ? 0 : ret;

	pd_write(&eb, false);
	pd_write(&autosd, false);
	pd_write(&force, true);
	ret = pd_wait(&state, STATE_OFF);
	if (ret) {
		/* back to the state found: the vendor's power-on (force shutdown off, state on, bus enable on) */
		pd_write(&force, false);
		if (pd_wait(&state, STATE_ON))
			dev_err(dev, "neither off nor on\n");
		else
			pd_write(&eb, true);
		dev_err(dev, "no power-off, the domain stays on\n");
		return 0;
	}
	if (pll.map)
		pd_write(&pll, false);
	dev_info(dev, "powered off\n");
	return 0;
}

static const struct of_device_id unused_pd_match[] = {
	{ .compatible = "sprd,qogirn6pro-camsys-domain", .data = &camsys_desc },
	{ .compatible = "sprd,vpu-pd", .data = &vpu_desc },
	{ }
};

static struct platform_driver unused_pd_driver = {
	.probe = unused_pd_probe,
	.driver = {
		.name = "ums9620-unused-pd",
		.of_match_table = unused_pd_match,
		.suppress_bind_attrs = true,
	},
};
builtin_platform_driver(unused_pd_driver);
