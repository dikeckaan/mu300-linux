/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Unisoc DDR DVFS (sprd,ddr-dvfs, the "scene-frequency" devfreq device): ported from the Unisoc 5.4 kernel
 * (drivers/devfreq/sprd/, Mingmin Ling <mingmin.ling@unisoc.com>). See sprd_ddr_dvfs_core.c.
 */
#ifndef __SPRD_DVFS_DRV_H__
#define __SPRD_DVFS_DRV_H__

#include <linux/devfreq.h>
#include <linux/platform_device.h>
#if __has_include(<linux/devfreq-governor.h>)
#include <linux/devfreq-governor.h>	/* 7.x */
#else
#include "governor.h"			/* 6.18: drivers/devfreq/governor.h (-I in Kbuild) */
#endif

struct dvfs_hw_callback {
	int (*hw_dvfs_vote)(const char *name);
	int (*hw_dvfs_unvote)(const char *name);
	int (*hw_dvfs_set_point)(const char *name, unsigned int freq);
	int (*hw_dvfs_get_point_info)(char **name, unsigned int *freq,
				      unsigned int *flag, int index);
	int (*dvfs_freq_request)(unsigned int freq);
};

enum DDR_DFS_STATE_STEP {
	scenario_dfs_enter = 1,
	exit_scene,
	auto_dfs_on_off,
	scaling_force_ddr_freq,
	scene_boost_enter,
	set_backdoor,
	dfs_on_off,
	change_point,
	scene_freq_set,
	get_overflow_t,
	set_overflow_t,
	get_underflow_t,
	set_underflow_t,
	get_dvfs_status_t,
	get_dvfs_auto_status_t,
	get_cur_freq_t,
	get_freq_table_t,
	send_freq_request_t,
};

#define DDR_DB_NODE_NUM 50
#define SCENE_MAX 25
struct DDR_DFS_STEP_T {
	enum DDR_DFS_STATE_STEP step;
	int status;
	u32 buff;
	char scene[SCENE_MAX];
	int pid;
};

struct ddr_dfs_step_list_t {
	struct ddr_dfs_step_list_t *next;
	struct DDR_DFS_STEP_T data;
};

struct governor_callback {
	int (*governor_vote)(const char *name);
	int (*governor_unvote)(const char *name);
	int (*governor_change_point)(const char *name, unsigned int freq);
	int (*get_point_info)(char **name, unsigned int *freq, unsigned int *flag, int index);
	int (*get_freq_num)(unsigned int *data);
	int (*get_overflow)(unsigned int *data, unsigned int sel);
	int (*set_overflow)(unsigned int value, unsigned int sel);
	int (*get_underflow)(unsigned int *data, unsigned int sel);
	int (*set_underflow)(unsigned int value, unsigned int sel);
	int (*get_dvfs_status)(unsigned int *data);
	int (*dvfs_enable)(void);
	int (*dvfs_disable)(void);
	int (*get_dvfs_auto_status)(unsigned int *data);
	int (*dvfs_auto_enable)(void);
	int (*dvfs_auto_disable)(void);
	int (*get_cur_freq)(unsigned int *data);
	int (*get_freq_table)(unsigned int *data, unsigned int sel);
	int (*ddrinfo_dfs_step_show)(char **arg, char **step_status,
				     char **scene, u32 *buff, int *pid, u32 i);
	void (*ddr_dfs_step_add)(enum DDR_DFS_STATE_STEP cur_step, int status,
				 char *scene, u32 buff, int pid);
};

/* the core (sprd_ddr_dvfs_core.c), for the vote back end (sprd_ddr_dvfs_sp.c) and the governor */
int dvfs_core_init(struct platform_device *pdev);
void dvfs_core_hw_callback_register(struct dvfs_hw_callback *hw_callback);
unsigned long get_max_freq(void);
int send_freq_request(unsigned int freq);
int get_request_freq(unsigned int *data);
int send_vote_request(unsigned int freq);
int release_forced_freq(void);
void dvfs_release_if_forced(void);
unsigned int dvfs_lowest_freq(void);
bool sprd_vote_forced(void);

/* the governor (sprd_governor_vote.c): scenes other kernel drivers may vote for, as on 5.4 */
int scene_dfs_request(char *scenario);
int scene_exit(char *scenario);
int change_scene_freq(char *scenario, unsigned int freq);
extern struct devfreq_governor sprd_vote;

#endif
