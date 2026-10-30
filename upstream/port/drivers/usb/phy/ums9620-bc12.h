/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * The U30 Air's BC1.2 detection, owned by the USB PHY (from kanoqwq b4748534; after ZTE's GPL source b50db5b6224c,
 * sprd-bc1p2.c and the qogirn6pro USB PHY and dwc3). Each VBUS event starts one detection on the PMIC's detector:
 * D+/D- stay with the detector until it reports DONE (status 0x239c, polled every 20 ms, at most 60 times). They go to
 * the PHY for a USB port (SDP, CDP) and stay on the charger side for a charger (DCP) or no answer. No answer is
 * detected once more, with the stock 960 ms delay; a real SDP is never redetected as a DCP. The result is the PHY's
 * chg_type/chg_state, and its charger notifier tells the charger driver (patch 0032). In the USB host role
 * (mu300-usb host, a powered dock) the host owns D+/D- and no detection runs.
 * The extcon notifier is atomic: it only starts a new generation and queues the work, which does all register
 * access. A result of an older generation (unplugged or role changed meanwhile) is never published. dpdm_lock keeps
 * a detection and a role change apart. Before this, mainline switched D+/D- to the PHY at probe; the charger read
 * the PMIC's result itself or, without one, started the BQ chip's own detection (IINDET), which drives D+/D- under a
 * live USB link: two detectors on the gadget's lines.
 */

/* the board with a battery: the U30 Air's charger policy node, the test of patches 0016, 0023 and 0030 */
static bool sprd_ssphy_has_battery(void)
{
	struct device_node *np = of_find_node_by_path("/charger_policy_service");

	of_node_put(np);
	return np != NULL;
}

#define UMP9620_BC12_STATUS 0x239c
#define UMP9620_BC12_CTRL2 0x243c
#define UMP9620_BC12_DONE BIT(11)
#define UMP9620_BC12_PRESENT BIT(2)
#define UMP9620_BC12_TYPES (BIT(7) | BIT(6) | BIT(5))
#define UMP9620_BC12_INTERVAL_MS 20
#define UMP9620_BC12_FIRST_SAMPLES 60
#define UMP9620_BC12_RETRY_SAMPLES (60 + (960 - 20) / 20)

static enum usb_charger_type sprd_ssphy_bc12_type(u32 status)
{
	if (!(status & UMP9620_BC12_DONE))
		return UNKNOWN_TYPE;
	switch (status & UMP9620_BC12_TYPES) {
	case BIT(7): return SDP_TYPE;
	case BIT(6): return DCP_TYPE;
	case BIT(5): return CDP_TYPE;
	default: return UNKNOWN_TYPE;
	}
}

static bool sprd_ssphy_bc12_publish(struct sprd_ssphy *phy,
			 enum usb_charger_type type, bool present, u32 generation)
{
	unsigned long flags;

	/* Publish even when presence did not change: detection completes later
	 * than VBUS, and consumers must receive the completed type too.
	 * charger_detect below returns this cache only, never starts detection.
	 */
	spin_lock_irqsave(&phy->bc12_event_lock, flags);
	if (generation != (u32)atomic_read(&phy->bc12_generation)) {
		spin_unlock_irqrestore(&phy->bc12_event_lock, flags);
		return false;
	}
	WRITE_ONCE(phy->phy.chg_type, type);
	WRITE_ONCE(phy->phy.chg_state,
		   present ? USB_CHARGER_PRESENT : USB_CHARGER_ABSENT);
	spin_unlock_irqrestore(&phy->bc12_event_lock, flags);
	schedule_work(&phy->phy.chg_work);
	return true;
}

static enum usb_charger_type sprd_ssphy_charger_detect(struct usb_phy *x)
{
	return READ_ONCE(x->chg_type);
}

static void sprd_ssphy_bc12_role(struct sprd_ssphy *phy)
{
	int ret;

	if (phy->is_host) {
		/* A USB data host owns DP/DM even with external sink power. */
		ret = regmap_update_bits(phy->pmic, UMP9620_BC12_CTRL2, BIT(0), 0);
		if (!ret)
			ret = sc27xx_dpdm_switch_to_phy(phy->pmic, true);
		if (ret)
			dev_err(phy->dev, "BC1.2 host handoff failed: %d\n", ret);
	}
	atomic_inc(&phy->bc12_generation);
	if (READ_ONCE(phy->bc12_ready) && !READ_ONCE(phy->bc12_stopping))
		mod_delayed_work(system_power_efficient_wq, &phy->bc12_work, 0);
}

static void sprd_ssphy_bc12_work(struct work_struct *work)
{
	struct sprd_ssphy *phy = container_of(to_delayed_work(work),
					    struct sprd_ssphy, bc12_work);
	enum usb_charger_type type = UNKNOWN_TYPE;
	u32 generation, status;
	unsigned long delay = msecs_to_jiffies(UMP9620_BC12_INTERVAL_MS);
	bool data, present;
	int ret;

	mutex_lock(&phy->dpdm_lock);
	if (READ_ONCE(phy->bc12_stopping))
		goto out;
	generation = atomic_read(&phy->bc12_generation);
	present = READ_ONCE(phy->vbus_present);
	if (phy->is_host) {
		/* Never drive BC1.2 signals onto a live host/dock data path. */
		sprd_ssphy_bc12_publish(phy, UNKNOWN_TYPE, present, generation);
		goto out;
	}
	if (generation != phy->bc12_seen) {
		phy->bc12_seen = generation;
		phy->bc12_samples = 0;
		phy->bc12_retry = false;
		ret = sc27xx_dpdm_switch_to_phy(phy->pmic, false);
		if (ret)
			goto failed;
		sprd_ssphy_notify_disconnect(&phy->phy, USB_SPEED_UNKNOWN);
		sprd_ssphy_bc12_publish(phy, UNKNOWN_TYPE, present, generation);
	}
	if (!present) {
		ret = regmap_update_bits(phy->pmic, UMP9620_BC12_CTRL2, BIT(0), 0);
		if (ret)
			goto failed;
		goto out;
	}
	ret = regmap_read(phy->pmic, UMP9620_BC12_STATUS, &status);
	if (ret)
		goto failed;
	/* A queued result from the previous cable/role must never be published. */
	if (generation != atomic_read(&phy->bc12_generation))
		goto changed;
	if (!(status & UMP9620_BC12_PRESENT) &&
	    (phy->bc12_samples || (status & UMP9620_BC12_DONE))) {
		ret = -ENOTCONN;
		goto failed;
	}
	if (status & UMP9620_BC12_DONE)
		type = sprd_ssphy_bc12_type(status);
	if ((status & UMP9620_BC12_DONE) ||
	    ++phy->bc12_samples >= (phy->bc12_retry ?
		UMP9620_BC12_RETRY_SAMPLES : UMP9620_BC12_FIRST_SAMPLES)) {
		ret = regmap_update_bits(phy->pmic, UMP9620_BC12_CTRL2, BIT(0), 0);
		if (ret)
			goto failed;
		if (type == UNKNOWN_TYPE && !phy->bc12_retry) {
			/* The stock controller retries UNKNOWN once, with 960ms
			 * detection delay. Do not redetect a valid SDP as DCP.
			 */
			ret = regmap_update_bits(phy->pmic, CHGR_DET_FGU_CTRL,
					 GENMASK(7, 4), 15 << 4);
			if (!ret)
				ret = regmap_update_bits(phy->pmic, UMP9620_BC12_CTRL2,
						 BIT(0), BIT(0));
			if (ret)
				goto failed;
			phy->bc12_retry = true;
			phy->bc12_samples = 0;
			goto again;
		}
		data = type == SDP_TYPE || type == CDP_TYPE;
		ret = sc27xx_dpdm_switch_to_phy(phy->pmic, data);
		if (ret)
			goto failed;
		if (generation != atomic_read(&phy->bc12_generation))
			goto changed;
		if (data)
			sprd_ssphy_notify_connect(&phy->phy, USB_SPEED_UNKNOWN);
		if (!sprd_ssphy_bc12_publish(phy, type, true, generation))
			goto changed;
		dev_info(phy->dev, "BC1.2 complete: type %d, DP/DM %s\n",
			 type, data ? "USB" : "charger");
		goto out;
	}
again:
	if (generation != atomic_read(&phy->bc12_generation))
		goto changed;
	mod_delayed_work(system_power_efficient_wq, &phy->bc12_work, delay);
	goto out;
failed:
	regmap_update_bits(phy->pmic, UMP9620_BC12_CTRL2, BIT(0), 0);
	/* Unknown keeps the conservative current budget, not a second detector. */
	sprd_ssphy_bc12_publish(phy, UNKNOWN_TYPE, false, generation);
	dev_err(phy->dev, "BC1.2 detection/handoff failed: %d\n", ret);
	goto out;
changed:
	mod_delayed_work(system_power_efficient_wq, &phy->bc12_work, 0);
out:
	mutex_unlock(&phy->dpdm_lock);
}
