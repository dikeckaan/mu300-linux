// SPDX-License-Identifier: GPL-2.0-only
/*
 * sprd_ddr_dfs: DDR frequency scaling of the UMS9620 boards, done by the PM_SYS co-processor's firmware.
 *
 * The firmware keeps the DDR at one point (1866 MHz on the U30 Air) until the AP turns DFS and its auto DFS on;
 * then it scales between the AP's vote and the top of its table on bandwidth overflow/underflow. It is driven over
 * SIPC (SMSG_CH_PM_CTRL to PM_SYS; the protocol is in ddr_dfs.h). This driver binds to the stock device tree's
 * "sprd,ddr-dvfs" node (/scene-frequency), opens the channel from a thread of its own (the firmware answers once
 * pm_sys runs, seconds into the boot; the probe never waits for it), reads the table and the state the firmware is
 * in, turns DFS on and registers a devfreq device with the table.
 *
 * The devfreq governor "sprd_ddr_auto" (the default) leaves the scaling to the firmware: auto DFS on, min_freq is
 * the vote (a floor), max_freq has no effect - the firmware takes no ceiling. Any other governor (performance,
 * powersave, userspace) pins its frequency with SET_DDR_FREQ, which turns auto DFS off; switching back to
 * sprd_ddr_auto turns it on again. No polling: devfreq acts on governor and min/max changes only, cur_freq asks the
 * firmware.
 *
 * Removal brings the firmware back to the state found at load (ddr_dfs_restore()). The channel stays open: the
 * firmware answers the OPEN handshake once per boot and ignores CLOSE, so a closed channel could not be opened
 * again; a later load finds it open in sipc and uses it as it is.
 *
 * After the Unisoc 5.4 driver (drivers/devfreq/sprd/sprd_ddr_dvfs_core.c, GPL-2.0), without its scenes, boost API
 * and debug ring. No MODULE_DEVICE_TABLE: the module is loaded by name (upstream/module-order.txt), never by the
 * node's modalias. Only the UMS9620 is accepted.
 */
#include <linux/completion.h>
#include <linux/devfreq.h>
/* the governor API is public from 7.x on; 6.18 keeps it in drivers/devfreq (found through the -I of include/) */
#if __has_include(<linux/devfreq-governor.h>)
#include <linux/devfreq-governor.h>
#else
#include <../drivers/devfreq/governor.h>
#endif
#include <linux/jiffies.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_opp.h>
#include <linux/sipc.h>
/* struct smsg_ipc: whether an earlier load left the channel open (sprd_modem's sipc, built from the same tree) */
#include "sipc_priv.h"

#include "ddr_dfs.h"

#define DDR_DFS_GOVERNOR	"sprd_ddr_auto"
#define DDR_DFS_TIMEOUT		msecs_to_jiffies(2000)	/* the firmware answers within a few ms */
#define HZ_PER_MHZ_UL		1000000UL

struct ddr_dfs {
	struct device *dev;
	struct mutex lock;		/* one request and its reply at a time */
	struct completion started;	/* the start thread has finished */
	bool stopping;			/* removal is under way: the start thread does no more */
	bool opening;			/* the start thread waits for the OPEN handshake */
	bool live;			/* DFS was turned on and the devfreq device registered */
	bool autodfs;			/* sprd_ddr_auto governs: the firmware scales */
	struct ddr_dfs_state found;
	unsigned int raw;		/* entries to ask for (freq-num) */
	unsigned int count;
	unsigned int table[DDR_DFS_MAX_FREQS];	/* MHz, rising */
	struct devfreq_dev_profile profile;
	struct devfreq *devfreq;
};

/* one request, its reply in *DATA; the lock is held */
static int ddr_dfs_xfer(struct ddr_dfs *d, unsigned int cmd, unsigned int value, unsigned int *data)
{
	struct smsg m;
	int err;

	lockdep_assert_held(&d->lock);
	/* a reply that came after its request timed out must not answer this one */
	do {
		smsg_set(&m, SMSG_CH_PM_CTRL, 0, 0, 0);
	} while (!smsg_recv(SIPC_ID_PM_SYS, &m, 0));

	smsg_set(&m, SMSG_CH_PM_CTRL, SMSG_TYPE_DFS, cmd, value);
	err = smsg_send(SIPC_ID_PM_SYS, &m, DDR_DFS_TIMEOUT);
	if (err < 0)
		return err;
	smsg_set(&m, SMSG_CH_PM_CTRL, 0, 0, 0);
	err = smsg_recv(SIPC_ID_PM_SYS, &m, DDR_DFS_TIMEOUT);
	if (err < 0)
		return err;
	if (m.type != SMSG_TYPE_DFS_RSP)
		return -EPROTO;
	if (data)
		*data = m.value;
	return ddr_dfs_errno(m.flag);
}

static int ddr_dfs_req(struct ddr_dfs *d, unsigned int cmd, unsigned int value, unsigned int *data)
{
	int err;

	mutex_lock(&d->lock);
	err = ddr_dfs_xfer(d, cmd, value, data);
	mutex_unlock(&d->lock);
	if (err)
		dev_err(d->dev, "request %#06x %u: %d\n", cmd, value, err);
	return err;
}

static int ddr_dfs_target(struct device *dev, unsigned long *freq, u32 flags)
{
	struct ddr_dfs *d = dev_get_drvdata(dev);
	unsigned int mhz = ddr_dfs_pick(d->table, d->count, DIV_ROUND_UP(*freq, HZ_PER_MHZ_UL));
	int err;

	/* auto DFS: the vote is the floor; otherwise the governor's frequency is pinned (and auto DFS off) */
	err = ddr_dfs_req(d, d->autodfs ? DDR_DFS_VOTE : DDR_DFS_SET_DDR_FREQ, mhz, NULL);
	if (!err)
		*freq = mhz * HZ_PER_MHZ_UL;
	return err;
}

static int ddr_dfs_get_cur_freq(struct device *dev, unsigned long *freq)
{
	struct ddr_dfs *d = dev_get_drvdata(dev);
	unsigned int mhz;
	int err;

	err = ddr_dfs_req(d, DDR_DFS_INQ_DDR_FREQ, 0, &mhz);
	if (!err)
		*freq = mhz * HZ_PER_MHZ_UL;
	return err;
}

/* the lowest frequency, raised by the core to min_freq: the vote */
static int ddr_dfs_gov_target(struct devfreq *df, unsigned long *freq)
{
	*freq = 0;
	return 0;
}

static int ddr_dfs_gov_event(struct devfreq *df, unsigned int event, void *data)
{
	struct ddr_dfs *d = dev_get_drvdata(df->dev.parent);
	int err;

	switch (event) {
	case DEVFREQ_GOV_START:
		err = ddr_dfs_req(d, DDR_DFS_AUTO_ENABLE, 0, NULL);
		if (err)
			return err;
		d->autodfs = true;
		mutex_lock(&df->lock);
		err = update_devfreq(df);
		mutex_unlock(&df->lock);
		return err;
	case DEVFREQ_GOV_STOP:
		/* the next governor pins its frequency, which turns auto DFS off */
		d->autodfs = false;
		return 0;
	default:
		return 0;
	}
}

static struct devfreq_governor ddr_dfs_governor = {
	.name = DDR_DFS_GOVERNOR,
	.flags = DEVFREQ_GOV_FLAG_IRQ_DRIVEN,
	.get_target_freq = ddr_dfs_gov_target,
	.event_handler = ddr_dfs_gov_event,
};

/* the channel is open in sipc already: a load before this one opened it */
static bool ddr_dfs_channel_open(void)
{
	struct smsg_ipc *ipc = smsg_ipcs[SIPC_ID_PM_SYS];
	u8 i = sipc_channel2index(SMSG_CH_PM_CTRL);

	return ipc && ipc->channels[i] && ipc->states[i] == CHAN_STATE_OPENED;
}

static int ddr_dfs_open(struct ddr_dfs *d)
{
	int err;

	if (ddr_dfs_channel_open())
		return 0;
	if (!smsg_ipcs[SIPC_ID_PM_SYS])
		return -ENODEV;	/* no SIPC to pm_sys: sipc-core is not loaded, or no device for it */
	mutex_lock(&d->lock);
	if (d->stopping) {
		mutex_unlock(&d->lock);
		return -ESHUTDOWN;
	}
	d->opening = true;
	mutex_unlock(&d->lock);
	/* waits for pm_sys's answer however long it takes; removal ends the wait with smsg_ch_close() */
	err = smsg_ch_open(SIPC_ID_PM_SYS, SMSG_CH_PM_CTRL, -1);
	mutex_lock(&d->lock);
	d->opening = false;
	mutex_unlock(&d->lock);
	return err;
}

static int ddr_dfs_query(struct ddr_dfs *d)
{
	unsigned int raw[DDR_DFS_MAX_FREQS];
	unsigned int i;
	int err;

	for (i = 0; i < d->raw; i++) {
		err = ddr_dfs_req(d, DDR_DFS_INQ_DDR_TABLE, i, &raw[i]);
		if (err)
			return err;
	}
	d->count = ddr_dfs_table(raw, d->raw, d->table);
	if (!d->count) {
		dev_err(d->dev, "the firmware's frequency table does not rise\n");
		return -EINVAL;
	}
	err = ddr_dfs_req(d, DDR_DFS_INQ_STATUS, 0, &d->found.enabled);
	if (!err)
		err = ddr_dfs_req(d, DDR_DFS_INQ_AUTO_STATUS, 0, &d->found.autodfs);
	if (!err)
		err = ddr_dfs_req(d, DDR_DFS_INQ_DDR_FREQ, 0, &d->found.freq);
	if (!err)
		err = ddr_dfs_req(d, DDR_DFS_INQ_AP_FREQ, 0, &d->found.vote);
	return err;
}

static void ddr_dfs_restore_found(struct ddr_dfs *d)
{
	struct ddr_dfs_req req[4];
	unsigned int i, n = ddr_dfs_restore(&d->found, req);

	for (i = 0; i < n; i++)
		ddr_dfs_req(d, req[i].cmd, req[i].value, NULL);
}

static int ddr_dfs_register(struct ddr_dfs *d)
{
	unsigned int i;
	int err;

	for (i = 0; i < d->count; i++) {
		err = dev_pm_opp_add(d->dev, d->table[i] * HZ_PER_MHZ_UL, 0);
		if (err)
			goto opps;
	}
	d->profile.polling_ms = 0;
	d->profile.initial_freq = d->found.freq * HZ_PER_MHZ_UL;
	d->profile.target = ddr_dfs_target;
	d->profile.get_cur_freq = ddr_dfs_get_cur_freq;
	d->devfreq = devfreq_add_device(d->dev, &d->profile, DDR_DFS_GOVERNOR, NULL);
	if (IS_ERR(d->devfreq)) {
		err = PTR_ERR(d->devfreq);
		goto opps;
	}
	return 0;
opps:
	dev_pm_opp_remove_all_dynamic(d->dev);
	return err;
}

static int ddr_dfs_start(void *data)
{
	struct ddr_dfs *d = data;
	unsigned int i, cur;
	int err;

	err = ddr_dfs_open(d);
	if (err) {
		if (err != -EIO && err != -ESHUTDOWN)	/* -EIO: removal closed the channel during the wait */
			dev_err(d->dev, "SIPC channel to pm_sys: %d\n", err);
		goto out;
	}
	err = ddr_dfs_query(d);
	if (err)
		goto out;
	mutex_lock(&d->lock);
	if (d->stopping) {
		mutex_unlock(&d->lock);
		goto out;
	}
	d->live = true;
	mutex_unlock(&d->lock);
	if (!d->found.enabled) {
		err = ddr_dfs_req(d, DDR_DFS_ENABLE, 0, NULL);
		if (err)
			goto restore;
	}
	err = ddr_dfs_register(d);
	if (err) {
		dev_err(d->dev, "devfreq: %d\n", err);
		goto restore;
	}
	if (ddr_dfs_req(d, DDR_DFS_INQ_DDR_FREQ, 0, &cur))
		cur = 0;
	dev_info(d->dev, "%u-%u MHz (%u steps), found DFS %s, auto %s, %u MHz, vote %u; now auto, %u MHz\n",
		 d->table[0], d->table[d->count - 1], d->count, d->found.enabled ? "on" : "off",
		 d->found.autodfs ? "on" : "off", d->found.freq, d->found.vote, cur);
	for (i = 0; i < d->count; i++)
		dev_dbg(d->dev, "step %u: %u MHz\n", i, d->table[i]);
	goto out;
restore:
	mutex_lock(&d->lock);
	d->live = false;
	mutex_unlock(&d->lock);
	ddr_dfs_restore_found(d);
out:
	complete(&d->started);
	return 0;
}

static int ddr_dfs_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct task_struct *t;
	struct ddr_dfs *d;
	u32 num = 8;

	if (!of_machine_is_compatible("sprd,ums9620"))
		return -ENODEV;
	of_property_read_u32(dev->of_node, "freq-num", &num);
	if (!num || num > DDR_DFS_MAX_FREQS)
		return dev_err_probe(dev, -EINVAL, "freq-num %u\n", num);
	d = devm_kzalloc(dev, sizeof(*d), GFP_KERNEL);
	if (!d)
		return -ENOMEM;
	d->dev = dev;
	d->raw = num;
	mutex_init(&d->lock);
	init_completion(&d->started);
	platform_set_drvdata(pdev, d);
	t = kthread_run(ddr_dfs_start, d, "ddr-dfs");
	return PTR_ERR_OR_ZERO(t);
}

static void ddr_dfs_remove(struct platform_device *pdev)
{
	struct ddr_dfs *d = platform_get_drvdata(pdev);

	mutex_lock(&d->lock);
	d->stopping = true;
	/* still waiting for pm_sys: end the wait (the firmware never answered, so nothing is open on its side) */
	if (d->opening)
		smsg_ch_close(SIPC_ID_PM_SYS, SMSG_CH_PM_CTRL, DDR_DFS_TIMEOUT);
	mutex_unlock(&d->lock);
	wait_for_completion(&d->started);
	if (!d->live)
		return;
	devfreq_remove_device(d->devfreq);
	dev_pm_opp_remove_all_dynamic(d->dev);
	ddr_dfs_restore_found(d);
}

static const struct of_device_id ddr_dfs_match[] = {
	{ .compatible = "sprd,ddr-dvfs" },
	{ }
};

static struct platform_driver ddr_dfs_driver = {
	.probe = ddr_dfs_probe,
	.remove = ddr_dfs_remove,
	.driver = {
		.name = "sprd-ddr-dfs",
		.of_match_table = ddr_dfs_match,
	},
};

static int __init ddr_dfs_init(void)
{
	int err = devfreq_add_governor(&ddr_dfs_governor);

	if (err)
		return err;
	err = platform_driver_register(&ddr_dfs_driver);
	if (err)
		devfreq_remove_governor(&ddr_dfs_governor);
	return err;
}

static void __exit ddr_dfs_exit(void)
{
	platform_driver_unregister(&ddr_dfs_driver);
	devfreq_remove_governor(&ddr_dfs_governor);
}
module_init(ddr_dfs_init);
module_exit(ddr_dfs_exit);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("UMS9620 DDR frequency scaling through the PM_SYS firmware");
