// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc DDR DVFS, the platform driver and its vote back end (sprd,ddr-dvfs; votes are carried out by pm_sys).
 * The scenes and their frequencies come from the device tree (sprd-scene, sprd-freq); a scene's vote raises the
 * DDR to at least its frequency while it is held.
 *
 * Ported from the Unisoc 5.4 kernel (drivers/devfreq/sprd/sprd_ddr_dvfs_sp.c, Mingmin Ling
 * <mingmin.ling@unisoc.com>); for mainline the lock is the driver's own (it was a global named "lock") and the
 * vote table is walked under it; the driver cannot be unbound or unloaded (see sprd_ddr_dvfs_core.c); and, like sprd_cp_dvfs, it is loaded by name after the modem stack
 * (extra-modules), not by udev for the device tree node, so that it never pulls the SIPC core in out of order.
 */
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/spinlock.h>
#include "sprd_ddr_dvfs.h"

struct vote_data {
	const char *name;
	unsigned int freq;
	unsigned int flag;
};

static struct vote_data *g_vote_data;
static int scene_num;
static unsigned int request_freq;
static DEFINE_SPINLOCK(vote_lock);
static DEFINE_MUTEX(vote_mutex);

static struct vote_data *find_point(const char *name)
{
	int i;

	for (i = 0; i < scene_num && g_vote_data[i].name; i++)
		if (!strcmp(g_vote_data[i].name, name))
			return &g_vote_data[i];
	return NULL;
}

static int check_and_vote(unsigned int target_freq)
{
	static unsigned int last_freq;
	int err, i;

	mutex_lock(&vote_mutex);
	spin_lock(&vote_lock);
	for (i = 0; i < scene_num; i++) {
		struct vote_data *point = &g_vote_data[i];

		if (point->flag >= 1 && point->freq > target_freq)
			target_freq = point->freq == 0xbacd ? get_max_freq() : point->freq;
	}
	spin_unlock(&vote_lock);
	if (!target_freq)
		target_freq = dvfs_lowest_freq();	/* pm_sys ignores 0 (see the core) */

	err = 0;
	if (target_freq != last_freq) {
		err = send_vote_request(target_freq);
		if (!err)
			last_freq = target_freq;
	}
	mutex_unlock(&vote_mutex);
	return err;
}

static int dvfs_freq_request(unsigned int freq)
{
	int err;

	if (!g_vote_data)
		return -EINVAL;
	err = check_and_vote(freq);
	if (err == 0)
		request_freq = freq;
	return err;
}

static int dvfs_vote(const char *name)
{
	struct vote_data *point;

	if (!g_vote_data)
		return -EINVAL;
	point = find_point(name);
	if (!point)
		return -EINVAL;
	spin_lock(&vote_lock);
	WARN_ON(point->flag);
	point->flag++;
	spin_unlock(&vote_lock);
	return check_and_vote(request_freq);
}

static int dvfs_unvote(const char *name)
{
	struct vote_data *point;

	if (!g_vote_data)
		return -EINVAL;
	point = find_point(name);
	if (!point)
		return -EINVAL;
	spin_lock(&vote_lock);
	if (point->flag > 0)
		point->flag--;
	spin_unlock(&vote_lock);
	return check_and_vote(request_freq);
}

static int dvfs_set_point(const char *name, unsigned int freq)
{
	struct vote_data *point;

	if (!g_vote_data)
		return -EINVAL;
	point = find_point(name);
	if (!point)
		return -EINVAL;
	spin_lock(&vote_lock);
	point->freq = freq;
	spin_unlock(&vote_lock);
	return check_and_vote(request_freq);
}

static int dvfs_get_point_info(char **name, unsigned int *freq, unsigned int *flag, int index)
{
	struct vote_data *point;

	if (!g_vote_data || index < 0 || index >= scene_num)
		return -EINVAL;
	point = &g_vote_data[index];
	if (!point->name)
		return -EINVAL;
	*name = (char *)point->name;
	*freq = point->freq;
	*flag = point->flag;
	return 0;
}

static struct dvfs_hw_callback callbacks = {
	.hw_dvfs_vote = dvfs_vote,
	.hw_dvfs_unvote = dvfs_unvote,
	.hw_dvfs_set_point = dvfs_set_point,
	.hw_dvfs_get_point_info = dvfs_get_point_info,
	.dvfs_freq_request = dvfs_freq_request,
};

static int dvfs_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *node = dev->of_node;
	int err, i;

	scene_num = of_property_count_strings(node, "sprd-scene");
	if (scene_num <= 0) {
		scene_num = 0;
		g_vote_data = NULL;
	} else {
		g_vote_data = devm_kcalloc(dev, scene_num, sizeof(*g_vote_data), GFP_KERNEL);
		if (!g_vote_data)
			return -ENOMEM;
	}
	for (i = 0; i < scene_num; i++) {
		err = of_property_read_string_index(node, "sprd-scene", i, &g_vote_data[i].name);
		if (err < 0 || !strlen(g_vote_data[i].name)) {
			dev_err(dev, "failed parse sprd-scene\n");
			goto bad_dt;
		}
		err = of_property_read_u32_index(node, "sprd-freq", i, &g_vote_data[i].freq);
		if (err < 0) {
			dev_err(dev, "failed parse sprd-freq\n");
			goto bad_dt;
		}
	}
	request_freq = 0;

	err = dvfs_core_init(pdev);
	if (err < 0)
		goto bad_dt;
	dvfs_core_hw_callback_register(&callbacks);
	return 0;

bad_dt:
	g_vote_data = NULL;
	scene_num = 0;
	return err ? err : -EINVAL;
}

static const struct of_device_id dvfs_match[] = {
	{ .compatible = "sprd,ddr-dvfs" },
	{},
};

static struct platform_driver sprd_ddr_dvfs_driver = {
	.probe = dvfs_probe,
	.driver = {
		.name = "sprd-ddr-dvfs",
		.of_match_table = dvfs_match,
		.suppress_bind_attrs = true,
	},
};

/* no module_exit: pm_sys opens its DFS channel once per boot, so the driver stays once loaded (see the core) */
static int __init sprd_ddr_dvfs_init(void)
{
	return platform_driver_register(&sprd_ddr_dvfs_driver);
}
module_init(sprd_ddr_dvfs_init);

MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Unisoc DDR DVFS (pm_sys), ported from the Unisoc 5.4 kernel");
