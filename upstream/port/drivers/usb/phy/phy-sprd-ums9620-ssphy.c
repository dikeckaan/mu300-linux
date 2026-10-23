// SPDX-License-Identifier: GPL-2.0-only
/*
 * Unisoc UMS9620 (qogirn6pro) USB 3.1 / USB 2.0 combo PHY for DWC3, device mode.
 * Ported from the Unisoc 5.4 kernel (drivers/usb/phy/phy-sprd-usb31-qogirn6pro.c). Charger detection (BC1.2)
 * and the usbm cross-PHY bookkeeping are left out: the PHY is brought up for peripheral mode and D+/D- are
 * switched from the PMIC charger detector to the PHY at probe. The USB 3 lanes follow the plug's orientation
 * (FINDINGS 195, #54): the TCA's lane flip and the PTN38003A redriver, set as ZTE's kernel sets them at every
 * attach, where ZTE's kernel brings the whole PHY up again.
 *
 * Copyright (C) 2020 Spreadtrum Communications Inc.
 */
#include <linux/delay.h>
#include <linux/err.h>
#include <linux/i2c.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/mfd/syscon.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_platform.h>
#include <linux/platform_device.h>
#include <linux/regmap.h>
#include <linux/regulator/consumer.h>
#include <linux/slab.h>
#include <linux/usb/otg.h>
#include <linux/usb/phy.h>
#include <linux/workqueue.h>
#include <dt-bindings/soc/sprd,qogirn6pro-mask.h>
#include <dt-bindings/soc/sprd,qogirn6pro-regs.h>

struct sprd_ssphy {
	struct device		*dev;
	struct usb_phy		phy;
	void __iomem		*base;
	struct regmap		*aon_apb;
	struct regmap		*ipa_apb;
	struct regmap		*ipa_dispc1_glb_apb;
	struct regmap		*ipa_usb31_dp;
	struct regmap		*ipa_usb31_dptx;
	struct regmap		*ana_g0l;
	struct regmap		*pmic;
	struct regulator	*vdd;
	u32			vdd_vol;
	u32			host_eye_pattern;
	u32			device_eye_pattern;
	u32			ssphy_ctl5_eye_pattern;
	u32			ssphy_ctl6_eye_pattern;
	atomic_t		reset;
	atomic_t		inited;
	bool			is_host;

	/* the plug's orientation (FINDINGS 195): all below under orient_lock, except force (set from any context) */
	struct mutex		orient_lock;
	struct delayed_work	orient_work;
	atomic_t		force;		/* the next run sets lanes and redriver even when nothing changed */
	struct i2c_client	*redriver;	/* the PTN38003A on i2c6, NULL until its bus is there */
	bool			no_redriver;	/* the device tree has none */
	bool			no_redriver_warned;	/* said once why a flip is skipped */
	int			lookups;
	u32			typec_base;	/* the PMIC's Type-C block (typec@380), 0 when there is none */
	u32			applied;	/* SSPHY_KEY() of what was last set, 0 = nothing attached since */
	bool			check;		/* read the redriver's own detection back on the next run */
};

#define PHY_INIT_TIMEOUT 500

#define DISPC1_GLB_APB_EB		 (0x0)
#define DISPC1_GLB_APB_RST		 (0x4)

#define PHY0_SRAM_BYPASS		(0X48)
#define PHY_SRAM_INIT_CHECK_DONE	(0x74)
#define TYPEC_DISABLE_ACK		(0xc08)

#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_VBUSVALID       0x02000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TESTCLK         0x01000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TESTDATAIN      0xff0000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TESTADDR        0xf000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TESTDATAOUTSEL  0x800
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TESTDATAOUT     0x380
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BIST_MODE       0x7c
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_T2RCOMP         0x2
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_LPBK_END        0x1
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DATABUS16_8     0x10000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_SUSPENDM        0x08000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_PORN            0x04000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_RESET           0x02000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_RXERROR         0x01000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_DRV_DP   0x00800000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_DRV_DM   0x00400000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_FS       0x00200000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_IN_DP    0x00100000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_IN_DM    0x80000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_OUT_DP   0x40000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BYPASS_OUT_DM   0x20000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_VBUSVLDEXT      0x10000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_RESERVED        0x0000FFFF
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_REXTENABLE      0x4
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DMPULLUP        0x2
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_SAMPLER_SEL     0x1
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DPPULLDOWN      0x10
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DMPULLDOWN      0x8
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TXBITSTUFFENABLE 0x4
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TXBITSTUFFENABLEH 0x2
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_SLEEPM          0x1
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNEHSAMP       0x06000000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TFREGRES        0x01f80000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TFHSRES         0x7c000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNERISE        0x3000
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNEOTG         0xe00
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNEDSC         0x180
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNESQ          0x78
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNEEQ          0x7
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_TUNEPLLS        0x7800
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_PLL_PFD_DEADZONE 0x300
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_PLL_PFD_DELAY   0xc0
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_PLL_CP_IOFFSET_EN 0x20
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_PLL_CP_IOFFSET  0x1e
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_PLL_REF_DOUBLER_EN 0x1
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BISTRAM_EN      0x2
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_BIST_MODE_EN    0x1
#define BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_ISO_SW_EN       0x1
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_SUSPENDM 0x100
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_PORN    0x80
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_RESET   0x40
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_BYPASS_FS 0x20
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_BYPASS_IN_DM 0x10
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_DPPULLDOWN 0x8
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_DMPULLDOWN 0x4
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_SLEEPM 0x2
#define BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_ISO_SW_EN 0x1

#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_TEST_PIN        0x0000
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL1       0x0004
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_BATTER_PLL      0x0008
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL2       0x000C
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_TRIMMING        0x0010
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_PLL_CTRL        0x0014
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_PHY_BIST_TEST   0x0018
#define REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_PHY             0x001C
#define REG_ANLG_PHY_G0L_ANALOG_USB20_REG_SEL_CFG_0         0x0020

#define DEFAULT_DEVICE_EYE_PATTERN			0x067bd1c0
#define DEFAULT_HOST_EYE_PATTERN			0x067bd1c0

#define CHGR_DET_FGU_CTRL		0x23a0
#define DP_DM_FS_ENB			BIT(14)
#define DP_DM_BC_ENB			BIT(0)

#define DEFAULT_SSPHY_CTL5_EYE_PATTERN			0x1e40a000
#define DEFAULT_SSPHY_CTL6_EYE_PATTERN			0x5d000083

/*
 * The Synopsys Type-C Assist (TCA) block at the start of phy_glb_regs, the names as in mainline's
 * phy-fsl-imx8mq-usb.c. ZTE's kernel runs it in controller synced mode with TCPC = 0x13 or 0x17: USB and DP
 * mux, VALID, and bit 2 - the lane flip - clear when the AON's USB_SW input is set. It writes SYSMODE_CFG bit 2
 * equal to TCPC bit 2; both are kept as ZTE has them.
 */
#define TCA_INTR_EN			0x04
#define TCA_INTR_STS			0x08
#define TCA_INTR_XA_ACK			BIT(0)
#define TCA_INTR_XA_TIMEOUT		BIT(1)
#define TCA_GCFG			0x10
#define TCA_TCPC			0x14
#define TCA_TCPC_MUX			GENMASK(1, 0)
#define TCA_TCPC_ORIENTATION_NORMAL	BIT(2)
#define TCA_TCPC_LOW_POWER_EN		BIT(3)
#define TCA_TCPC_VALID			BIT(4)
#define TCA_SYSMODE_CFG			0x18
#define TCA_SYSMODE_FLIP_BIT		BIT(2)
#define TCA_GEN_STATUS			0x34
#define TCA_GEN_PHY_TYPEC_FLIP		BIT(2)

/* the PMIC's Type-C block, from its node's reg: STATUS as ZTE's sc27xx_pd.c reads it */
#define TYPEC_STATUS			0x1c
#define TYPEC_STATE			GENMASK(4, 0)
#define TYPEC_STATE_ATTACHED_SNK	2
#define TYPEC_STATE_ATTACHED_SRC	5
#define TYPEC_CC1			BIT(5)		/* Unisoc's FINAL_SWITCH: attached on CC1 */

/* NXP PTN38003A, register 0x04 (datasheet Rev. 2.1, table 12; ZTE's ptn38003a-i2c.h) */
#define PTN38003A_MODE			0x04
#define PTN38003A_AUTO_ORIENT		BIT(7)
#define PTN38003A_ORIENT_DONE		BIT(6)
#define PTN38003A_UFP			BIT(5)
#define PTN38003A_REVERSE		BIT(4)
#define PTN38003A_OP_MODE		GENMASK(2, 0)
#define PTN38003A_OP_USB		1

#define SSPHY_KEY(normal)		((normal) ? 3 : 1)

enum { ORIENT_OFF, ORIENT_AUTO, ORIENT_CC };
static const char * const orientation_names[] = { "off", "auto", "cc" };
static int orientation = ORIENT_AUTO;
static DEFINE_MUTEX(sprd_ssphy_instance_lock);
static struct sprd_ssphy *sprd_ssphy_instance;

static void sprd_ssphy_kick(struct sprd_ssphy *phy, unsigned int ms, bool force)
{
	if (force)
		atomic_set(&phy->force, 1);
	mod_delayed_work(system_wq, &phy->orient_work, msecs_to_jiffies(ms));
}

static int orientation_set(const char *val, const struct kernel_param *kp)
{
	int i = sysfs_match_string(orientation_names, val);

	if (i < 0)
		return i;
	WRITE_ONCE(orientation, i);
	mutex_lock(&sprd_ssphy_instance_lock);
	if (sprd_ssphy_instance && i != ORIENT_OFF)
		sprd_ssphy_kick(sprd_ssphy_instance, 0, true);
	mutex_unlock(&sprd_ssphy_instance_lock);
	return 0;
}

static int orientation_get(char *buf, const struct kernel_param *kp)
{
	return sysfs_emit(buf, "%s\n", orientation_names[READ_ONCE(orientation)]);
}

static const struct kernel_param_ops orientation_ops = {
	.set = orientation_set,
	.get = orientation_get,
};
module_param_cb(orientation, &orientation_ops, NULL, 0644);
MODULE_PARM_DESC(orientation,
		 "USB 3 lanes: auto (ZTE's: the TCA from USB_SW, the redriver detects), cc (both from the PMIC's CC pin), off (set once at PHY init, no redriver)");

static bool sprd_ssphy_typec_attached(u32 status)
{
	u32 state = status & TYPEC_STATE;

	return state == TYPEC_STATE_ATTACHED_SNK || state == TYPEC_STATE_ATTACHED_SRC;
}

/* the lanes as the plug has them: ZTE's kernel reads the AON's USB_SW (BOOT_MODE bit 10), set = flipped */
static bool sprd_ssphy_lanes_normal(int mode, u32 boot_mode, bool typec, u32 typec_status, const char **from)
{
	if (mode == ORIENT_CC && typec && sprd_ssphy_typec_attached(typec_status)) {
		*from = "CC";
		return typec_status & TYPEC_CC1;
	}
	*from = "USB_SW";
	return !(boot_mode & MASK_AON_APB_USB_SW);
}

/* ZTE: bits 0, 1 and 4 set, 3 clear, 2 for the orientation */
static u32 sprd_ssphy_tcpc(u32 tcpc, bool normal)
{
	tcpc &= ~(TCA_TCPC_ORIENTATION_NORMAL | TCA_TCPC_LOW_POWER_EN);
	tcpc |= TCA_TCPC_MUX | TCA_TCPC_VALID;
	if (normal)
		tcpc |= TCA_TCPC_ORIENTATION_NORMAL;
	return tcpc;
}

static u32 sprd_ssphy_sysmode(u32 sysmode, bool normal)
{
	return normal ? sysmode | TCA_SYSMODE_FLIP_BIT : sysmode & ~TCA_SYSMODE_FLIP_BIT;
}

/* deep power saving: the high-speed pins in USB safe state, and a new detection at the next USB mode */
static u8 sprd_ssphy_redriver_off(u8 v)
{
	return v & ~(PTN38003A_AUTO_ORIENT | PTN38003A_OP_MODE);
}

/* USB 3.2 mode; the orientation detected by the redriver itself (ZTE's 0x81), or the one given */
static u8 sprd_ssphy_redriver_on(u8 v, int mode, bool normal)
{
	v &= ~(PTN38003A_AUTO_ORIENT | PTN38003A_ORIENT_DONE | PTN38003A_REVERSE | PTN38003A_OP_MODE);
	v |= PTN38003A_OP_USB;
	if (mode == ORIENT_CC) {
		if (!normal)
			v |= PTN38003A_REVERSE;
	} else {
		v |= PTN38003A_AUTO_ORIENT;
	}
	return v;
}

static void sc27xx_dpdm_switch_to_phy(struct regmap *regmap, bool enable)
{
	int ret;
	u32 val;

	pr_info("switch dp/dm to %s\n", enable ? "usb" : "other");
	ret = regmap_read(regmap, CHGR_DET_FGU_CTRL, &val);
	if (ret) {
		pr_err("%s, dp/dm switch reg read failed:%d\n",
				__func__, ret);
		return;
	}

	/*
	 * bit14: 1 switch to USB phy, 0 switch to fast charger
	 * bit0 : 1 switch to USB phy, 0 switch to BC1P2
	 */
	if (enable)
		val = val | DP_DM_FS_ENB | DP_DM_BC_ENB;
	else
		val = val & ~(DP_DM_FS_ENB | DP_DM_BC_ENB);

	ret = regmap_write(regmap, CHGR_DET_FGU_CTRL, val);
	if (ret)
		pr_err("%s, dp/dm switch reg write failed:%d\n",
				__func__, ret);
}


static inline void sprd_ssphy_reset_core(struct sprd_ssphy *phy)
{
	u32 reg, msk;
	int ret = 0;

	dev_dbg(phy->phy.dev, "%s ipa usb&phy rst!\n", __func__);

	/* Purpose: To soft-reset USB control */
	msk = MASK_IPA_APB_USB_SOFT_RST | MASK_IPA_APB_PAM_U3_SOFT_RST;
	reg = msk;
	regmap_update_bits(phy->ipa_apb, REG_IPA_APB_IPA_RST, msk, reg);

	/* Reset USB2 PHY */
	if (true) {
		msk = MASK_AON_APB_OTG_PHY_SOFT_RST | MASK_AON_APB_OTG_UTMI_SOFT_RST;
		reg = msk;
		regmap_update_bits(phy->aon_apb, REG_AON_APB_APB_RST1, msk, reg);
	}

	/* Reset USB31 PHY */
	ret |= regmap_read(phy->ipa_dispc1_glb_apb, DISPC1_GLB_APB_RST, &reg);
	reg |= BIT(4);
	ret |= regmap_write(phy->ipa_dispc1_glb_apb, DISPC1_GLB_APB_RST, reg);
	usleep_range(1, 10);
	/* ssphy power on @0x64900d14*/
	msk = MASK_AON_APB_PHY_TEST_POWERDOWN;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, 0);

	/*
	 *Reset signal should hold on for a while
	 *to issue resret process reliable.
	 */
	usleep_range(20000, 30000);
	msk = MASK_IPA_APB_USB_SOFT_RST | MASK_IPA_APB_PAM_U3_SOFT_RST;
	regmap_update_bits(phy->ipa_apb, REG_IPA_APB_IPA_RST, msk, 0);
	msk = MASK_AON_APB_OTG_PHY_SOFT_RST | MASK_AON_APB_OTG_UTMI_SOFT_RST;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_APB_RST1, msk, 0);
	ret |= regmap_read(phy->ipa_dispc1_glb_apb, DISPC1_GLB_APB_RST, &reg);
	reg &= ~BIT(4);
	ret |= regmap_write(phy->ipa_dispc1_glb_apb, DISPC1_GLB_APB_RST, reg);
}


static int sprd_ssphy_set_vbus(struct usb_phy *x, int on)
{
	struct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
	u32 reg, msk;
	int ret = 0;

	if (on) {
		regmap_write(phy->ana_g0l, REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_TRIMMING,
					phy->host_eye_pattern);
		/* set USB connector type is A-type*/
		msk = MASK_AON_APB_USB2_PHY_IDDIG;
		ret |= regmap_update_bits(phy->aon_apb,
			REG_AON_APB_OTG_PHY_CTRL, msk, 0);

		msk = BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_DMPULLDOWN |
			BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_DPPULLDOWN;
		ret |= regmap_update_bits(phy->ana_g0l,
			REG_ANLG_PHY_G0L_ANALOG_USB20_REG_SEL_CFG_0,
			msk, msk);

		/* the pull down resistance on D-/D+ enable */
		msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DMPULLDOWN |
			BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DPPULLDOWN;
		ret |= regmap_update_bits(phy->ana_g0l,
			REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL2,
			msk, msk);

		reg = 0x200;
		msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_RESERVED;
		ret |= regmap_update_bits(phy->ana_g0l,
			REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL1,
			msk, reg);
		phy->is_host = true;
	} else {
		regmap_write(phy->ana_g0l, REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_TRIMMING,
					phy->device_eye_pattern);

		if (true) {
			reg = msk = MASK_AON_APB_USB2_PHY_IDDIG;
			ret |= regmap_update_bits(phy->aon_apb,
				REG_AON_APB_OTG_PHY_CTRL, msk, reg);

			msk = BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_DMPULLDOWN |
				BIT_ANLG_PHY_G0L_DBG_SEL_ANALOG_USB20_USB20_DPPULLDOWN;
			ret |= regmap_update_bits(phy->ana_g0l,
				REG_ANLG_PHY_G0L_ANALOG_USB20_REG_SEL_CFG_0,
				msk, msk);

			/* the pull down resistance on D-/D+ enable */
			msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DMPULLDOWN |
				BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_DPPULLDOWN;
			ret |= regmap_update_bits(phy->ana_g0l,
				REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL2,
				msk, 0);

			msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_RESERVED;
			ret |= regmap_update_bits(phy->ana_g0l,
				REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL1,
				msk, 0);
		}
		phy->is_host = false;
	}

	return ret;
}


/* Requirement from usb analog compliance tests */
static void usb_config_4_cts(struct sprd_ssphy *phy)
{
	u32	reg;

	dev_dbg(phy->phy.dev, "%s enter\n", __func__);

	regmap_read(phy->ipa_usb31_dp, 0x20, &reg);
	/*enable cr apb*/
	reg |= BIT(4);
	regmap_write(phy->ipa_usb31_dp, 0x20, reg);
	/*enable cr clk*/
	reg |= BIT(3);
	regmap_write(phy->ipa_usb31_dp, 0x20, reg);

	/*phy reg addr 0x0021 SUP_DIG_LVL_OVER_IN*/
	reg = 0x10021;
	regmap_write(phy->ipa_usb31_dp, 0x8, reg);
	regmap_read(phy->ipa_usb31_dp, 0xc, &reg);
	/*bit7: TX_VBOOST_LVL_EN; bit6L4=5 TX_TXVBOOST_LVL*/
	reg &= ~(BIT(6) | BIT(5) | BIT(4));
	reg |= BIT(7) | BIT(6) | BIT(4);
	regmap_write(phy->ipa_usb31_dp, 0xc, reg);

	/*cfg for enter gen2*/
	reg = 0x10063;
	regmap_write(phy->ipa_usb31_dp, 0x8, reg);
	regmap_read(phy->ipa_usb31_dp, 0xc, &reg);
	reg |= BIT(8) | BIT(7) | BIT(1) | BIT(0);
	regmap_write(phy->ipa_usb31_dp, 0xc, reg);

	/* Configure usb31 phy eye-pattern */
	regmap_write(phy->ipa_usb31_dp, 0x44, phy->ssphy_ctl5_eye_pattern);
	regmap_write(phy->ipa_usb31_dp, 0x48, phy->ssphy_ctl6_eye_pattern);
}


/* the TCA's lane flip, as ZTE's init writes it; waits for the controller's ack (or the TCA's timeout) */
static void sprd_ssphy_tca_set(struct sprd_ssphy *phy, bool normal)
{
	int timeout = PHY_INIT_TIMEOUT;
	u32 reg;

	writel_relaxed(0xffff, phy->base + TCA_INTR_STS);
	writel_relaxed(sprd_ssphy_tcpc(readl_relaxed(phy->base + TCA_TCPC), normal), phy->base + TCA_TCPC);
	writel_relaxed(sprd_ssphy_sysmode(readl_relaxed(phy->base + TCA_SYSMODE_CFG), normal),
		       phy->base + TCA_SYSMODE_CFG);

	msleep(10);
	while (1) {
		reg = readl_relaxed(phy->base + TCA_INTR_STS);
		if (reg & (TCA_INTR_XA_ACK | TCA_INTR_XA_TIMEOUT)) {
			writel_relaxed(0xffff, phy->base + TCA_INTR_STS);
			break;
		}
		msleep(1);
		if (!--timeout) {
			dev_err(phy->dev, "tca interrupt not ready\n");
			break;
		}
	}
}

/* the PMIC's Type-C block: STATUS, or false when the device tree has no such block or the read fails */
static bool sprd_ssphy_typec_status(struct sprd_ssphy *phy, u32 *status)
{
	*status = 0;
	return phy->typec_base && !regmap_read(phy->pmic, phy->typec_base + TYPEC_STATUS, status);
}

/*
 * Set the TCA's lanes for the plug and return the key of what was set. At PHY init always (as before); later
 * only when the orientation is not the one the TCA has, so that a running link is not disturbed for nothing.
 */
static u32 sprd_ssphy_lanes(struct sprd_ssphy *phy, int mode, bool always, bool flip)
{
	u32 boot = 0, st, tcpc;
	const char *from;
	bool typec, normal;

	regmap_read(phy->aon_apb, REG_AON_APB_BOOT_MODE, &boot);
	typec = sprd_ssphy_typec_status(phy, &st);
	normal = sprd_ssphy_lanes_normal(mode, boot, typec, st, &from);
	tcpc = readl_relaxed(phy->base + TCA_TCPC);
	if (flip && (always || !!(tcpc & TCA_TCPC_ORIENTATION_NORMAL) != normal))
		sprd_ssphy_tca_set(phy, normal);
	if (mode != ORIENT_OFF)
		dev_info(phy->dev, "USB 3 lanes %s (from %s; USB_SW %d, Type-C %s, TCA flip status %d)\n",
			 normal ? "normal" : "flipped", from, !!(boot & MASK_AON_APB_USB_SW),
			 !typec ? "unknown" : !sprd_ssphy_typec_attached(st) ? "open" :
			 st & TYPEC_CC1 ? "CC1" : "CC2",
			 !!(readl_relaxed(phy->base + TCA_GEN_STATUS) & TCA_GEN_PHY_TYPEC_FLIP));
	return SSPHY_KEY(normal);
}

/* the redriver's I2C client: its node is in the vendor DTB (i2c6, 0x30, "sprd,ptn38003a redriver"), unbound */
static struct i2c_client *sprd_ssphy_redriver(struct sprd_ssphy *phy)
{
#if IS_REACHABLE(CONFIG_I2C)
	struct device_node *np;

	if (phy->redriver || phy->no_redriver)
		return phy->redriver;
	np = of_find_compatible_node(NULL, NULL, "sprd,ptn38003a redriver");
	if (!np || !of_device_is_available(np))
		phy->no_redriver = true;
	else
		phy->redriver = of_find_i2c_device_by_node(np);
	of_node_put(np);
	return phy->redriver;
#else
	phy->no_redriver = true;
	return NULL;
#endif
}

/* through deep power saving into USB mode: the auto orientation detection runs once per entry (7.7.2) */
static int sprd_ssphy_redriver_arm(struct sprd_ssphy *phy, int mode, bool normal)
{
	struct i2c_client *c = sprd_ssphy_redriver(phy);
	int v, ret;

	if (!c)
		return phy->no_redriver ? -ENODEV : -EPROBE_DEFER;
	v = i2c_smbus_read_byte_data(c, PTN38003A_MODE);
	if (v < 0)
		return v;
	ret = i2c_smbus_write_byte_data(c, PTN38003A_MODE, sprd_ssphy_redriver_off(v));
	if (ret)
		return ret;
	usleep_range(1000, 2000);
	ret = i2c_smbus_write_byte_data(c, PTN38003A_MODE, sprd_ssphy_redriver_on(v, mode, normal));
	if (!ret)
		dev_info(phy->dev, "redriver: mode 0x%02x, now 0x%02x\n", v, sprd_ssphy_redriver_on(v, mode, normal));
	return ret;
}

/* ZTE's shutdown: deep power saving, so that whoever brings the port up next gets a new detection */
static void sprd_ssphy_redriver_park(struct sprd_ssphy *phy)
{
	int v;

	if (!phy->redriver)
		return;
	v = i2c_smbus_read_byte_data(phy->redriver, PTN38003A_MODE);
	if (v >= 0)
		i2c_smbus_write_byte_data(phy->redriver, PTN38003A_MODE, sprd_ssphy_redriver_off(v));
}

/*
 * After PHY init, a role change, VBUS or (as a host, polled each second) a Type-C attach: set the lanes and arm
 * the redriver as ZTE's kernel does at every attach. A detach only forgets what was set, so that the next attach
 * arms the redriver again.
 */
static void sprd_ssphy_orient_work(struct work_struct *work)
{
	struct sprd_ssphy *phy = container_of(to_delayed_work(work), struct sprd_ssphy, orient_work);
	int mode = READ_ONCE(orientation), v, ret;
	bool force, attached, typec;
	unsigned int next = 0;
	u32 st, key, boot = 0;
	const char *from;

	if (mode == ORIENT_OFF)
		return;
	mutex_lock(&phy->orient_lock);
	if (!atomic_read(&phy->inited))
		goto out;

	force = atomic_xchg(&phy->force, 0);
	typec = sprd_ssphy_typec_status(phy, &st);
	attached = !typec || sprd_ssphy_typec_attached(st);
	regmap_read(phy->aon_apb, REG_AON_APB_BOOT_MODE, &boot);
	key = SSPHY_KEY(sprd_ssphy_lanes_normal(mode, boot, typec, st, &from));
	if (!attached && !force) {
		phy->applied = 0;
	} else if (force || phy->applied != key) {
		/* forced, attached after a detach, or attached again the other way round without a detach seen */
		/*
		 * Arm the redriver before the TCA is touched: the two have to agree on the lane pair. Where the
		 * PTN38003A is missing, or does not answer at all (a U30 Air whose i2c 0x30 returns -EIO on every
		 * bus), flipping the TCA alone leaves no pair working - the host does not enumerate the device at
		 * all - while the single write PHY init made still falls back to USB 2. Keep that write then.
		 */
		ret = sprd_ssphy_redriver_arm(phy, mode, key == SSPHY_KEY(true));
		if (ret == -EPROBE_DEFER && phy->lookups++ < 30) {
			atomic_set(&phy->force, 1);
			next = 1000;
			key = sprd_ssphy_lanes(phy, mode, false, true);
		} else if (ret) {
			if (ret != -ENODEV && !phy->no_redriver_warned) {
				phy->no_redriver_warned = true;
				dev_warn(phy->dev,
					 "redriver: %d, nothing to follow a flip; the lanes stay as PHY init left them\n",
					 ret);
			}
			key = sprd_ssphy_lanes(phy, mode, false, false);
		} else {
			phy->check = true;
			next = 1500;
			key = sprd_ssphy_lanes(phy, mode, false, true);
		}
		phy->applied = attached ? key : 0;
	} else if (phy->check && phy->redriver) {
		phy->check = false;
		v = i2c_smbus_read_byte_data(phy->redriver, PTN38003A_MODE);
		if (v < 0)
			dev_warn(phy->dev, "redriver: %d\n", v);
		else if (!(v & PTN38003A_AUTO_ORIENT))
			dev_info(phy->dev, "redriver: orientation %s as set (0x%02x)\n",
				 v & PTN38003A_REVERSE ? "reverse" : "normal", v);
		else if (v & PTN38003A_ORIENT_DONE)
			dev_info(phy->dev, "redriver: detected orientation %s (0x%02x)\n",
				 v & PTN38003A_REVERSE ? "reverse" : "normal", v);
		else
			dev_info(phy->dev, "redriver: no orientation detected yet (0x%02x)\n", v);
	}

	/* as a host the port powers VBUS itself, so a device plugged in later shows only on CC */
	if (!next && typec && phy->is_host)
		next = 1000;
	if (next && !delayed_work_pending(&phy->orient_work))
		schedule_delayed_work(&phy->orient_work, msecs_to_jiffies(next));
out:
	mutex_unlock(&phy->orient_lock);
}

static int sprd_ssphy_init(struct usb_phy *x)
{
	struct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
	u32	reg, msk;
	int	ret = 0;
	int timeout;

	if (atomic_read(&phy->inited)) {
		dev_info(x->dev, "%s is already inited!\n", __func__);
		return 0;
	}

	
	/*
	 * Due to chip design, some chips may turn on vddusb by default,
	 * We MUST avoid turning it on twice.
	 */
	if (phy->vdd) {
		ret = regulator_enable(phy->vdd);
		if (ret) {
			dev_err(x->dev,
				"Failed to enable phy->vdd: %d\n", ret);
			return ret;
		}
	}

	
	/* select the IPA_SYS USB controller */
	msk = MASK_AON_APB_USB20_CTRL_MUX_REG;
	reg = msk;
	ret |= regmap_update_bits(phy->aon_apb, REG_AON_APB_AON_SOC_USB_CTRL,
			 msk, reg);

	/* enable analog */
	msk = MASK_AON_APB_CGM_OTG_REF_EN | MASK_AON_APB_CGM_DPHY_REF_EN;
	reg = msk;
	ret |= regmap_update_bits(phy->aon_apb, REG_AON_APB_CGM_REG1, msk, reg);

	/*enable analog:0x64900004*/
	reg = MASK_AON_APB_AON_USB2_TOP_EB | MASK_AON_APB_OTG_PHY_EB |
						MASK_AON_APB_ANA_EB;
	msk = reg;
	ret |= regmap_update_bits(phy->aon_apb, REG_AON_APB_APB_EB1, msk, reg);

	/* utmisrp_bvalid  sys vbus valid:0x64900D14*/
	reg = MASK_AON_APB_SYS_VBUSVALID;
	msk = reg;
	ret |= regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, reg);

	/*  usb eb and usb ref eb :0x25000004*/
	ret |= regmap_read(phy->ipa_apb, REG_IPA_APB_IPA_EB, &reg);
	reg |= MASK_IPA_APB_USB_EB | MASK_IPA_APB_USB_REF_EB;
	ret |= regmap_write(phy->ipa_apb, REG_IPA_APB_IPA_EB, reg);

	/* usb suspend eb :0x64900138*/
	reg = MASK_AON_APB_CGM_USB_SUSPEND_EN;
	msk = reg;
	ret |= regmap_update_bits(phy->aon_apb, REG_AON_APB_CGM_REG1, msk, reg);

	/*
	 * USB2 PHY power on: set pd_l/pd_s firstly, then set iso_sw.
	 * poweroff sequence is opposite
	 */
	msk = MASK_AON_APB_LVDSRF_PD_PD_L | MASK_AON_APB_LVDSRF_PS_PD_S;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_MIPI_CSI_POWER_CTRL, msk, 0);

	ret |= regmap_update_bits(phy->ana_g0l,
		REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_PHY,
		BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_ISO_SW_EN, 0);

	/* enable usb20 ISO AVDD1V8_USB*/
	msk = MASK_AON_APB_USB20_ISO_SW_EN;
	ret |= regmap_update_bits(phy->aon_apb, REG_AON_APB_AON_SOC_USB_CTRL,
			 msk, 0);

	/* ssphy power on @0x64900d14*/
	msk = MASK_AON_APB_PHY_TEST_POWERDOWN;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, 0);

	/*hsphy vbus valid */
	msk = MASK_AON_APB_OTG_VBUS_VALID_PHYREG;
	reg = msk;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_OTG_PHY_TEST, msk, reg);
	/*ssphy vbus valid */
	msk = MASK_AON_APB_SYS_VBUSVALID;
	reg = msk;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, reg);

	msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_VBUSVLDEXT;
	reg = msk;
	ret |= regmap_update_bits(phy->ana_g0l,
			REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL1,	msk, reg);

	regmap_write(phy->ana_g0l, REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_TRIMMING,
					phy->device_eye_pattern);

	/* Reset PHY */
	sprd_ssphy_reset_core(phy);

	/* wait phy_sram init down check bit2=1 */
	timeout = PHY_INIT_TIMEOUT;
	while (1) {
		ret |= regmap_read(phy->ipa_usb31_dp, PHY_SRAM_INIT_CHECK_DONE, &reg);
		if ((reg & BIT(2)) == BIT(2)) {
			break;
		} else {
			msleep(1);
			if (!--timeout) {
				dev_err(x->dev, "%s phy sram init failure\n", __func__);
				break;
			}
		}
	}

	usb_config_4_cts(phy);

	/* REG_TYPEC_CTRL: TYPEC_DISABLE_ACK */
	ret |= regmap_read(phy->ipa_usb31_dptx, TYPEC_DISABLE_ACK, &reg);
	reg |= BIT(0);
	ret |= regmap_write(phy->ipa_usb31_dptx, TYPEC_DISABLE_ACK, reg);

	/* TCA GCFG
	bit1:0 => 2b01 op_mode = controller synced mode
	bit3:2 => 2b00 reserved
	bit4 = 1 => USB device mode
	Bit31:5 => 0x0
	*/
	reg = readl_relaxed(phy->base + 0x010);
	reg &= ~(0xffffffc0);
	writel_relaxed(reg, phy->base + 0x010);
	reg &= ~(BIT(0) | BIT(4));
	if (phy->is_host)
		reg |= BIT(0);
	else
		reg |= BIT(0) | BIT(4);
	writel_relaxed(reg, phy->base + 0x010);

	/* TCA CTRLSYNCMODE CFG0 */
	reg = readl_relaxed(phy->base + 0x020);
	reg |= BIT(1) | BIT(2);
	writel_relaxed(reg, phy->base + 0x020);

	/*  TCA CTRLSYNCMODE CFG1 */
	reg = readl_relaxed(phy->base + 0x024);
	reg = 0x3d090;
	writel_relaxed(reg, phy->base + 0x024);

	/* clear TCA int status */
	reg = readl_relaxed(phy->base + 0x08);
	reg = 0xffff;
	writel_relaxed(reg, phy->base + 0x08);

	/* TCA INT EN
	xa_ack_event_en =1
	xa_timeout_event_en=1
	*/
	reg = readl_relaxed(phy->base + 0x04);
	reg |= BIT(0) | BIT(1);
	writel_relaxed(reg, phy->base + 0x04);

	/* usb3 switch port: the lanes for the plug's orientation */
	mutex_lock(&phy->orient_lock);
	sprd_ssphy_lanes(phy, READ_ONCE(orientation), true, true);
	mutex_unlock(&phy->orient_lock);

	if (!phy->pmic) {
		/*
		 *In FPGA platform, Disable low power will take some time
		 *before the DWC3 Core register is accessible.
		 */
		usleep_range(1000, 2000);
	}

	atomic_set(&phy->inited, 1);
	if (READ_ONCE(orientation) != ORIENT_OFF)
		sprd_ssphy_kick(phy, 0, true);

	return ret;
}


/* Turn off PHY and core */
static void sprd_ssphy_shutdown(struct usb_phy *x)
{
	struct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
	u32 msk = 0, reg = 0;

	if (!atomic_read(&phy->inited)) {
		dev_dbg(x->dev, "%s is already shut down\n", __func__);
		return;
	}

	cancel_delayed_work_sync(&phy->orient_work);
	mutex_lock(&phy->orient_lock);
	if (READ_ONCE(orientation) != ORIENT_OFF)
		sprd_ssphy_redriver_park(phy);
	phy->applied = 0;
	mutex_unlock(&phy->orient_lock);


		if (true) {
		msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_ISO_SW_EN;
		reg = msk;
		regmap_update_bits(phy->ana_g0l, REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_PHY,
			msk, reg);

		/*hsphy vbus invalid */
		msk = MASK_AON_APB_OTG_VBUS_VALID_PHYREG;
		regmap_update_bits(phy->aon_apb, REG_AON_APB_OTG_PHY_TEST, msk, 0);

		/* disable usb20 ISO*/
		msk = MASK_AON_APB_USB20_ISO_SW_EN;
		reg = msk;
		regmap_update_bits(phy->aon_apb, REG_AON_APB_AON_SOC_USB_CTRL,
				 msk, reg);

		/* hsphy power off */
		msk = MASK_AON_APB_LVDSRF_PD_PD_L | MASK_AON_APB_LVDSRF_PS_PD_S;
		reg = msk;
		regmap_update_bits(phy->aon_apb, REG_AON_APB_MIPI_CSI_POWER_CTRL, msk, reg);

		/* disable usb cgm ref */
		msk = MASK_AON_APB_CGM_OTG_REF_EN | MASK_AON_APB_CGM_DPHY_REF_EN;
		regmap_update_bits(phy->aon_apb, REG_AON_APB_CGM_REG1, msk, 0);

		/*disable analog:0x64900004*/
		msk = MASK_AON_APB_AON_USB2_TOP_EB | MASK_AON_APB_OTG_PHY_EB;
		regmap_update_bits(phy->aon_apb, REG_AON_APB_APB_EB1, msk, 0);
	}

	/*ssphy vbus invalid */
	msk = MASK_AON_APB_SYS_VBUSVALID;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, 0);

	/* Reset USB31 PHY */
	regmap_read(phy->ipa_dispc1_glb_apb, DISPC1_GLB_APB_RST, &reg);
	reg |= BIT(4);
	regmap_write(phy->ipa_dispc1_glb_apb, DISPC1_GLB_APB_RST, reg);

	usleep_range(1, 10);
	/* ssphy power off @0x64900d14*/
	msk = MASK_AON_APB_PHY_TEST_POWERDOWN;
	reg = msk;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, reg);

	/*
	 * Due to chip design, some chips may turn on vddusb by default,
	 * we MUST avoid turning it off twice.
	 */

	if (phy->vdd && regulator_is_enabled(phy->vdd))
		regulator_disable(phy->vdd);

	
	atomic_set(&phy->inited, 0);
	atomic_set(&phy->reset, 0);
}


static int sprd_ssphy_notify_connect(struct usb_phy *x,
				enum usb_device_speed speed)
{
	struct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
	u32 msk = 0, reg = 0;

	if (!atomic_read(&phy->inited)) {
		dev_info(x->dev, "%s phy is not inited!\n", __func__);
		return 0;
	}

	if (phy->is_host)
		return 0;

	/*hsphy vbus valid */
	msk = MASK_AON_APB_OTG_VBUS_VALID_PHYREG;
	reg = msk;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_OTG_PHY_TEST, msk, reg);
	/*ssphy vbus valid */
	msk = MASK_AON_APB_SYS_VBUSVALID;
	reg = msk;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, reg);

	msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_VBUSVLDEXT;
	reg = msk;
	regmap_update_bits(phy->ana_g0l,
			REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL1,	msk, reg);
	dev_info(x->dev, "ssphy set vbus valid!\n");
	return 0;
}

static int sprd_ssphy_notify_disconnect(struct usb_phy *x,
				enum usb_device_speed speed)
{
	struct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);
	u32 msk = 0;

	if (!atomic_read(&phy->inited)) {
		dev_info(x->dev, "%s phy is not inited!\n", __func__);
		return 0;
	}

	if (phy->is_host)
		return 0;

	/*hsphy vbus invalid */
	msk = MASK_AON_APB_OTG_VBUS_VALID_PHYREG;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_OTG_PHY_TEST, msk, 0);
	/*ssphy vbus invalid */
	msk = MASK_AON_APB_SYS_VBUSVALID;
	regmap_update_bits(phy->aon_apb, REG_AON_APB_USB31DPCOMBPHY_CTRL, msk, 0);

	msk = BIT_ANLG_PHY_G0L_ANALOG_USB20_USB20_VBUSVLDEXT;
	regmap_update_bits(phy->ana_g0l,
			REG_ANLG_PHY_G0L_ANALOG_USB20_USB20_UTMI_CTL1,	msk, 0);
	dev_info(x->dev, "ssphy set vbus invalid!\n");
	return 0;
}


/* VBUS from extcon-usb-gpio: report VBUS valid to the PHY (EXTCON_USB only, no charger-type cables needed) */
static int sprd_ssphy_vbus_notify(struct notifier_block *nb, unsigned long event, void *data)
{
	struct usb_phy *x = container_of(nb, struct usb_phy, vbus_nb);

	struct sprd_ssphy *phy = container_of(x, struct sprd_ssphy, phy);

	dev_info(x->dev, "vbus %s\n", event ? "on" : "off");
	if (event)
		sprd_ssphy_notify_connect(x, USB_SPEED_UNKNOWN);
	else
		sprd_ssphy_notify_disconnect(x, USB_SPEED_UNKNOWN);
	/* an attach: once the Type-C block has settled on a CC pin (tCCDebounce, 100 ms set by Unisoc) */
	if (READ_ONCE(orientation) != ORIENT_OFF)
		sprd_ssphy_kick(phy, event ? 300 : 0, event);
	return NOTIFY_OK;
}

static struct regmap *sprd_ssphy_pmic_regmap(struct device *dev)
{
	struct device_node *np = of_find_compatible_node(NULL, NULL, "sprd,ump962x-syscon");
	struct platform_device *pdev;
	struct regmap *map = NULL;

	if (!np)
		return NULL;
	pdev = of_find_device_by_node(np);
	of_node_put(np);
	if (pdev && pdev->dev.parent)
		map = dev_get_regmap(pdev->dev.parent, NULL);
	if (pdev)
		put_device(&pdev->dev);
	return map;
}

/*
 * Where VBUS comes from. The F50's device tree gives the PHY the extcon-usb-gpio device; the U30 Air's gives it the
 * PMIC's Type-C block (sprd,sc27xx-typec), which has no driver here, so usb_add_phy_dev() waited for it for ever
 * and there was no USB at all (no network, no serial console). Both boards have the VBUS GPIO node: point the
 * property at it when it names the Type-C block. The property stays with the node, so it is never freed.
 */
static void sprd_ssphy_vbus_source(struct device *dev)
{
	struct device_node *np = dev->of_node, *ext, *gpio;
	struct property *prop;
	bool typec;

	ext = of_parse_phandle(np, "extcon", 0);
	if (!ext)
		return;
	typec = of_device_is_compatible(ext, "sprd,sc27xx-typec");
	of_node_put(ext);
	if (!typec)
		return;

	gpio = of_find_compatible_node(NULL, NULL, "linux,extcon-usb-gpio");
	if (!gpio || !of_device_is_available(gpio) || !gpio->phandle) {
		of_node_put(gpio);
		dev_warn(dev, "extcon is the Type-C block and there is no VBUS GPIO: USB will not come up\n");
		return;
	}
	prop = kzalloc(sizeof(*prop) + sizeof(__be32), GFP_KERNEL);
	if (prop) {
		prop->name = kstrdup("extcon", GFP_KERNEL);
		prop->length = sizeof(__be32);
		prop->value = prop + 1;
		*(__be32 *)prop->value = cpu_to_be32(gpio->phandle);
		if (prop->name && !of_update_property(np, prop))
			dev_info(dev, "VBUS from %pOF (no driver for the Type-C block)\n", gpio);
		else
			dev_warn(dev, "could not point extcon at %pOF\n", gpio);
	}
	of_node_put(gpio);
}

/*
 * dwc3 tells the PHY about a role change through otg_set_vbus() - host: the host eye pattern, an A-type ID and the
 * D+/D- pull-downs; device: back. Without an otg structure it never did, and a host-mode port kept the device
 * settings (a failed first descriptor read, "error -71", and slow transfers).
 */
static int sprd_ssphy_otg_set_vbus(struct usb_otg *otg, bool on)
{
	struct sprd_ssphy *phy = container_of(otg->usb_phy, struct sprd_ssphy, phy);
	int ret = sprd_ssphy_set_vbus(otg->usb_phy, on);

	/* a new session in the other role: ZTE's kernel brought the PHY up again here */
	if (READ_ONCE(orientation) != ORIENT_OFF)
		sprd_ssphy_kick(phy, 100, true);
	return ret;
}

/* the PMIC's Type-C block: the node the U30 Air's PHY names, or the one both boards have (typec@380) */
static u32 sprd_ssphy_typec_base(void)
{
	struct device_node *np = of_find_compatible_node(NULL, NULL, "sprd,sc27xx-typec");
	u32 base = 0;

	if (np && of_device_is_available(np) && of_property_read_u32(np, "reg", &base))
		base = 0;
	of_node_put(np);
	return base;
}

static void sprd_ssphy_orient_stop(void *data)
{
	struct sprd_ssphy *phy = data;

	cancel_delayed_work_sync(&phy->orient_work);
	if (phy->redriver)
		put_device(&phy->redriver->dev);
}

static int sprd_ssphy_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node;
	struct sprd_ssphy *phy;
	int ret;

	phy = devm_kzalloc(dev, sizeof(*phy), GFP_KERNEL);
	if (!phy)
		return -ENOMEM;

	phy->pmic = sprd_ssphy_pmic_regmap(dev);
	if (!phy->pmic)
		return dev_err_probe(dev, -EPROBE_DEFER, "PMIC regmap not ready\n");

	phy->base = devm_platform_ioremap_resource_byname(pdev, "phy_glb_regs");
	if (IS_ERR(phy->base))
		return PTR_ERR(phy->base);

#define SYSCON(field, prop)							\
	do {									\
		phy->field = syscon_regmap_lookup_by_phandle(np, prop);		\
		if (IS_ERR(phy->field))						\
			return dev_err_probe(dev, PTR_ERR(phy->field), prop "\n");	\
	} while (0)
	SYSCON(aon_apb, "sprd,syscon-aon-apb");
	SYSCON(ana_g0l, "sprd,syscon-ana-g0l");
	SYSCON(ipa_apb, "sprd,syscon-ipa-apb");
	SYSCON(ipa_dispc1_glb_apb, "sprd,syscon-ipa-dispc1-glb-apb");
	SYSCON(ipa_usb31_dp, "sprd,syscon-ipa-usb31-dp");
	SYSCON(ipa_usb31_dptx, "sprd,syscon-ipa-usb31-dptx");
#undef SYSCON

	if (of_property_read_u32(np, "sprd,vdd-voltage", &phy->vdd_vol))
		phy->vdd_vol = 3300000;
	phy->vdd = devm_regulator_get_optional(dev, "vdd");
	if (IS_ERR(phy->vdd)) {
		if (PTR_ERR(phy->vdd) == -EPROBE_DEFER)
			return -EPROBE_DEFER;
		dev_warn(dev, "no vdd supply\n");
		phy->vdd = NULL;
	} else if (regulator_set_voltage(phy->vdd, phy->vdd_vol, phy->vdd_vol)) {
		dev_warn(dev, "cannot set vdd to %u uV\n", phy->vdd_vol);
	}

	if (of_property_read_u32(np, "sprd,hsphy-device-eye-pattern", &phy->device_eye_pattern))
		phy->device_eye_pattern = DEFAULT_DEVICE_EYE_PATTERN;
	if (of_property_read_u32(np, "sprd,hsphy-host-eye-pattern", &phy->host_eye_pattern))
		phy->host_eye_pattern = DEFAULT_HOST_EYE_PATTERN;
	if (of_property_read_u32(np, "sprd,ssphy-ctl5-eye-pattern", &phy->ssphy_ctl5_eye_pattern))
		phy->ssphy_ctl5_eye_pattern = DEFAULT_SSPHY_CTL5_EYE_PATTERN;
	if (of_property_read_u32(np, "sprd,ssphy-ctl6-eye-pattern", &phy->ssphy_ctl6_eye_pattern))
		phy->ssphy_ctl6_eye_pattern = DEFAULT_SSPHY_CTL6_EYE_PATTERN;

	/* select the IPA_SYS USB controller */
	regmap_update_bits(phy->aon_apb, REG_AON_APB_AON_SOC_USB_CTRL,
			   MASK_AON_APB_USB20_CTRL_MUX_REG, MASK_AON_APB_USB20_CTRL_MUX_REG);

	platform_set_drvdata(pdev, phy);
	mutex_init(&phy->orient_lock);
	INIT_DELAYED_WORK(&phy->orient_work, sprd_ssphy_orient_work);
	/* before usb_add_phy_dev(): devm undoes it after the VBUS notifier, which queues the work, is gone */
	ret = devm_add_action_or_reset(dev, sprd_ssphy_orient_stop, phy);
	if (ret)
		return ret;
	phy->typec_base = sprd_ssphy_typec_base();
	phy->dev = dev;
	phy->phy.dev = dev;
	phy->phy.label = "sprd-ssphy";
	phy->phy.init = sprd_ssphy_init;
	phy->phy.shutdown = sprd_ssphy_shutdown;
	phy->phy.set_vbus = sprd_ssphy_set_vbus;
	phy->phy.type = USB_PHY_TYPE_USB3;
	phy->phy.notify_connect = sprd_ssphy_notify_connect;
	phy->phy.notify_disconnect = sprd_ssphy_notify_disconnect;
	phy->phy.vbus_nb.notifier_call = sprd_ssphy_vbus_notify;
	phy->phy.otg = devm_kzalloc(dev, sizeof(*phy->phy.otg), GFP_KERNEL);
	if (!phy->phy.otg)
		return -ENOMEM;
	phy->phy.otg->usb_phy = &phy->phy;
	phy->phy.otg->set_vbus = sprd_ssphy_otg_set_vbus;

	sprd_ssphy_vbus_source(dev);
	ret = usb_add_phy_dev(&phy->phy);
	if (ret)
		return dev_err_probe(dev, ret, "cannot add phy\n");
	mutex_lock(&sprd_ssphy_instance_lock);
	sprd_ssphy_instance = phy;
	mutex_unlock(&sprd_ssphy_instance_lock);

	/* device mode only for now: route D+/D- from the charger detector to the USB PHY */
	sc27xx_dpdm_switch_to_phy(phy->pmic, true);
	dev_info(dev, "UMS9620 USB 3.1 PHY registered\n");
	return 0;
}

static void sprd_ssphy_remove(struct platform_device *pdev)
{
	struct sprd_ssphy *phy = platform_get_drvdata(pdev);

	mutex_lock(&sprd_ssphy_instance_lock);
	sprd_ssphy_instance = NULL;
	mutex_unlock(&sprd_ssphy_instance_lock);
	usb_remove_phy(&phy->phy);
}

/* reboot or power off: the redriver as ZTE's kernel leaves an unused port, for the next kernel's detection */
static void sprd_ssphy_platform_shutdown(struct platform_device *pdev)
{
	struct sprd_ssphy *phy = platform_get_drvdata(pdev);

	cancel_delayed_work_sync(&phy->orient_work);
	mutex_lock(&phy->orient_lock);
	if (READ_ONCE(orientation) != ORIENT_OFF)
		sprd_ssphy_redriver_park(phy);
	mutex_unlock(&phy->orient_lock);
}

static const struct of_device_id sprd_ssphy_match[] = {
	{ .compatible = "sprd,qogirn6pro-ssphy" },
	{ }
};
MODULE_DEVICE_TABLE(of, sprd_ssphy_match);

static struct platform_driver sprd_ssphy_driver = {
	.probe = sprd_ssphy_probe,
	.remove = sprd_ssphy_remove,
	.shutdown = sprd_ssphy_platform_shutdown,
	.driver = { .name = "sprd-ssphy", .of_match_table = sprd_ssphy_match },
};
module_platform_driver(sprd_ssphy_driver);

MODULE_DESCRIPTION("Unisoc UMS9620 USB 3.1 PHY driver");
MODULE_LICENSE("GPL");
