// SPDX-License-Identifier: GPL-2.0-only
/* Copyright (C) 2019 Spreadtrum Communications Inc.
 *
 * This software is licensed under the terms of the GNU General Public
 * License version 2, as published by the Free Software Foundation, and
 * may be copied, distributed, and modified under those terms.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */

#ifdef pr_fmt
#undef pr_fmt
#endif
#define pr_fmt(fmt) "sipa_dele: " fmt

#include <linux/delay.h>
#include <linux/slab.h>
#include <linux/device.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/mm.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_runtime.h>
#include <linux/sipa.h>
#include <linux/sipc.h>

#include "sipa_dele_priv.h"

static struct cp_delegator *s_cp_delegator;
static void cp_dele_on_commad(void *priv, u16 flag, u32 data)
{
	struct sipa_delegator *delegator = priv;
	int ret;

	pr_info("prod_id:%d, on_cmd, flag = %d\n", delegator->prod_id, flag);

	switch (flag) {
	case SMSG_FLG_DELE_ENABLE:
		delegator->pd_eb_flag = true;
check_again:
		ret = pm_runtime_get_sync(delegator->pdev);
		if (ret) {
			pm_runtime_put(delegator->pdev);
			pr_warn("sipa_dele get pd fail ret = %d\n", ret);
			mdelay(1);
			goto check_again;
		} else {
			delegator->pd_get_flag = true;
			sipa_set_enabled(true);
			sipa_dele_start_done_work(delegator,
						  SMSG_FLG_DELE_ENABLE,
						  SMSG_VAL_DELE_REQ_SUCCESS);
			pr_info("sipa_dele get pd success ret = %d\n", ret);
		}

		break;
	case SMSG_FLG_DELE_DISABLE:
		delegator->pd_eb_flag = false;
		sipa_set_enabled(false);
		pm_runtime_put(delegator->pdev);
		delegator->pd_get_flag = false;
		break;
	default:
		break;
	}

	pr_info("sipa pd_eb_flag = %d, pd_get_flag = %d\n",
		delegator->pd_eb_flag, delegator->pd_get_flag);

	/* do default operations */
	sipa_dele_on_commad(priv, flag, data);
}

static int cp_dele_local_req_r_prod(void *user_data)
{
	/* do enable ipa  operation */

	return sipa_dele_local_req_r_prod(user_data);
}

static int cp_dele_restart_handler(struct sipa_delegator *delegator)
{
	if (delegator->pd_eb_flag && delegator->pd_get_flag) {
		pr_info("sipa will power off\n");
		sipa_set_enabled(false);
		pm_runtime_put(delegator->pdev);
		delegator->pd_eb_flag = false;
		delegator->pd_get_flag = false;
	}

	if (delegator->cons_ref_cnt) {
		pr_info("sipa will release resource\n");
		delegator->cons_ref_cnt--;
		sipa_rm_release_resource(delegator->cons_user);
	}

	return 0;
}

static ssize_t sipa_dele_reset_show(struct device *dev,
				    struct device_attribute *attr,
				    char *buf)
{
	char *a = "modem reset\n";

	return sprintf(buf, "\n%s\n", a);
}

static ssize_t sipa_dele_reset_store(struct device *dev,
				     struct device_attribute *attr,
				     const char *buf,
				     size_t count)
{
	u8 cmd;
	struct sipa_delegator *delegator = &s_cp_delegator->delegator;

	if (sscanf(buf, "%4hhx\n", &cmd) != 1)
		return -EINVAL;

	if (cmd == 1) {
		dev_info(delegator->pdev, "modem_reset\n");
		cp_dele_restart_handler(delegator);
	}

	return count;
}

static DEVICE_ATTR_RW(sipa_dele_reset);

static struct attribute *sipa_dele_attrs[] = {
	&dev_attr_sipa_dele_reset.attr,
	NULL,
};
ATTRIBUTE_GROUPS(sipa_dele);

static int sipa_dele_init_sysfs(struct cp_delegator *cp_delegator)
{
	int ret;
	struct sipa_delegator *delegator = &cp_delegator->delegator;

	ret = sysfs_create_groups(&delegator->pdev->kobj,
				  sipa_dele_groups);
	if (ret) {
		dev_err(delegator->pdev, "sipa_dele fail to create sysfs\n");
		sysfs_remove_groups(&delegator->pdev->kobj,
				    sipa_dele_groups);
		return ret;
	}

	return 0;
}

int cp_delegator_init(struct sipa_delegator_create_params *params)
{
	int ret;

	/*
	 * MU300: not devm. The connection thread starts inside sipa_delegator_start() and cannot be stopped while it
	 * waits on the channel, so a probe that fails after that point must not free what the thread is using.
	 */
	s_cp_delegator = kzalloc(sizeof(*s_cp_delegator), GFP_KERNEL);
	if (!s_cp_delegator)
		return -ENOMEM;
	ret = sipa_delegator_init(&s_cp_delegator->delegator,
				  params);
	if (ret)
		return ret;

	s_cp_delegator->delegator.on_cmd = cp_dele_on_commad;
	s_cp_delegator->delegator.local_request_prod = cp_dele_local_req_r_prod;
	s_cp_delegator->delegator.pd_eb_flag = false;
	s_cp_delegator->delegator.pd_get_flag = false;
	s_cp_delegator->delegator.smsg_cnt = 0;
	/* MU300: its result used to be ignored, so a PROD_CP it had deleted again went unnoticed */
	ret = sipa_delegator_start(&s_cp_delegator->delegator);
	if (ret)
		return ret;
	pm_runtime_enable(s_cp_delegator->delegator.pdev);

	/*
	 * MU300: the Wi-Fi offload path, which this device does not use (the CONS_WIFI resources stay released): a
	 * failure here is reported, not fatal - failing the probe left the running delegate without its device.
	 */
	ret = sipa_rm_add_dependency(SIPA_RM_RES_CONS_WIFI_UL,
				     s_cp_delegator->delegator.prod_id);
	if (ret && ret != -EINPROGRESS)
		dev_warn(params->pdev, "CONS_WIFI_UL -> PROD_CP: %d\n", ret);

	ret = sipa_rm_add_dependency(SIPA_RM_RES_CONS_WIFI_DL,
				     s_cp_delegator->delegator.prod_id);
	if (ret && ret != -EINPROGRESS)
		dev_warn(params->pdev, "CONS_WIFI_DL -> PROD_CP: %d\n", ret);

	sipa_dele_init_sysfs(s_cp_delegator);

	return 0;
}
