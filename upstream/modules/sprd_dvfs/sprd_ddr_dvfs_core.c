// SPDX-License-Identifier: GPL-2.0
/*
 * Unisoc DDR DVFS core: the "scene-frequency" devfreq device (sprd,ddr-dvfs) of the UMS9620.
 *
 * The DDR frequency is changed by the PM co-processor (pm_sys), not by the AP: this driver talks to it over SIPC
 * (SIPC_ID_PM_SYS, channel SMSG_CH_PM_CTRL), turns its DFS and its automatic, bandwidth-driven scaling on, reads the
 * frequency table and the current frequency, and passes on what user space or a kernel driver asks for (a forced
 * frequency, a minimum, scene votes). Frequencies are in MHz, as on 5.4.
 *
 * Ported from the Unisoc 5.4 kernel (drivers/devfreq/sprd/sprd_ddr_dvfs_core.c, Mingmin Ling
 * <mingmin.ling@unisoc.com>): the same messages in the same order. What changed for mainline: the frequency table
 * the devfreq core gets is an unsigned long array of the non-zero levels (the vendor code handed it its u32 array
 * cast to unsigned long *); frequencies are read into an unsigned int and widened rather than written through a cast
 * pointer; the start-up runs in a work item; the module cannot be removed (pm_sys answers the channel's open once per
 * boot: after a close it never answers again, so a reload would find nothing); a "0" forced frequency withdraws the
 * force (devfreq clamped it to the lowest level and forced that); devfreq's min_freq/max_freq are gone, the scaling
 * limits are used instead. scaling=0 (module parameter)
 * leaves pm_sys's DFS as the bootloader left it: the device is there and reports, nothing is switched on.
 */
#include <linux/delay.h>
#include <linux/devfreq.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/pm_opp.h>
#include <linux/slab.h>
#include <linux/sort.h>
#include <linux/workqueue.h>
#include <linux/sipc.h>
#include "sprd_ddr_dvfs.h"

static bool scaling = true;
module_param(scaling, bool, 0444);
MODULE_PARM_DESC(scaling, "turn pm_sys's DDR DFS and its automatic scaling on, as 5.4 does (0: keep the bootloader's state)");

enum dvfs_master_cmd {
	DVFS_CMD_NORMAL		= 0x0000,
	DVFS_CMD_ENABLE		= 0x0300,
	DVFS_CMD_DISABLE	= 0x0305,
	DVFS_CMD_AUTO_ENABLE	= 0x0310,
	DVFS_CMD_AUTO_DISABLE	= 0x0315,
	DVFS_CMD_INQ_DDR_FREQ	= 0x0500,
	DVFS_CMD_INQ_DDR_TABLE	= 0x0505,
	DVFS_CMD_INQ_STATUS	= 0x050A,
	DVFS_CMD_INQ_AUTO_STATUS = 0x050B,
	DVFS_CMD_INQ_OVERFLOW	= 0x0510,
	DVFS_CMD_INQ_UNDERFLOW	= 0x0520,
	DVFS_CMD_SET_DDR_FREQ	= 0x0600,
	DVFS_CMD_PARA_OVERFLOW	= 0x0710,
	DVFS_CMD_PARA_UNDERFLOW	= 0x0720,
};

enum dvfs_slave_cmd {
	DVFS_RET_ADJ_OK		= 0x0000,
	DVFS_RET_ADJ_VER_FAIL	= 0x0001,
	DVFS_RET_ADJ_BUSY	= 0x0002,
	DVFS_RET_ADJ_NOCHANGE	= 0x0003,
	DVFS_RET_ADJ_FAIL	= 0x0004,
	DVFS_RET_DISABLE	= 0x0005,
	DVFS_RET_ON_OFF_SUCCEED	= 0x0300,
	DVFS_RET_ON_OFF_FAIL	= 0x0303,
	DVFS_RET_INQ_SUCCEED	= 0x0500,
	DVFS_RET_INQ_FAIL	= 0x0503,
	DVFS_RET_SET_SUCCEED	= 0x0600,
	DVFS_RET_SET_FAIL	= 0x0603,
	DVFS_RET_PARA_OK	= 0x070F,
	DVFS_RET_DEBUG_OK	= 0x0F00,
	DVFS_RET_INVALID_CMD	= 0x0F0F
};

struct freq_para {
	unsigned int overflow;
	unsigned int underflow;
	unsigned int vol;
};

struct dvfs_data {
	struct device *dev;
	struct devfreq *devfreq;
	struct devfreq_dev_profile profile;
	struct work_struct init_work;
	bool channel_open;
	struct mutex sync_mutex;
	unsigned int freq_num;
	unsigned int *freq_table;	/* pm_sys's table by index, 0 for an unused level */
	unsigned long *df_table;	/* the non-zero levels, ascending, for the devfreq core */
	struct freq_para *paras;
	unsigned int force_freq;
	unsigned int request_freq;
	struct dvfs_hw_callback *hw_callback;
	struct governor_callback *gov_callback;
	unsigned int init_done;
	struct delayed_work topfreq_unvote_work;
	struct mutex dfs_step_mutex;
};
static struct dvfs_data *g_dvfs_data;
static const char *default_governor = "sprd-governor";

static struct ddr_dfs_step_list_t *ddr_cur_step_g;
static struct ddr_dfs_step_list_t *ddr_dfs_step_s;
static struct ddr_dfs_step_list_t ddr_step_arr[DDR_DB_NODE_NUM];

static struct ddr_dfs_step_list_t *ddr_step_list_init(struct ddr_dfs_step_list_t arr[], u32 node_num)
{
	struct ddr_dfs_step_list_t *p = arr;
	u32 i;

	for (i = 1; i < node_num; i++) {
		p->next = arr + i;
		p = p->next;
	}
	p->next = arr;
	return p;
}

static void ddr_dfs_step_add(enum DDR_DFS_STATE_STEP cur_step, int status, char *scene, u32 buff, int pid)
{
	mutex_lock(&g_dvfs_data->dfs_step_mutex);
	ddr_cur_step_g = ddr_cur_step_g->next;
	ddr_cur_step_g->data.step = cur_step;
	ddr_cur_step_g->data.status = status;
	memset(ddr_cur_step_g->data.scene, 0, SCENE_MAX);
	if (scene)
		memcpy(ddr_cur_step_g->data.scene, scene, min_t(u32, buff, SCENE_MAX - 1));
	ddr_cur_step_g->data.buff = buff;
	ddr_cur_step_g->data.pid = pid;
	mutex_unlock(&g_dvfs_data->dfs_step_mutex);
}

static const char *const step_names[] = {
	[scenario_dfs_enter] = "scenario_dfs_enter", [exit_scene] = "exit_scene",
	[auto_dfs_on_off] = "auto_dfs_on_off", [scaling_force_ddr_freq] = "scaling_force_ddr_freq",
	[scene_boost_enter] = "scene_boost_enter", [set_backdoor] = "set_backdoor", [dfs_on_off] = "dfs_on_off",
	[change_point] = "change_point", [scene_freq_set] = "scene_freq_set", [get_overflow_t] = "get_overflow_t",
	[set_overflow_t] = "set_overflow_t", [get_underflow_t] = "get_underflow_t",
	[set_underflow_t] = "set_underflow_t", [get_dvfs_status_t] = "get_dvfs_status_t",
	[get_dvfs_auto_status_t] = "get_dvfs_auto_status_t", [get_cur_freq_t] = "get_cur_freq_t",
	[get_freq_table_t] = "get_freq_table_t", [send_freq_request_t] = "send_freq_request_t",
};

/* called under devfreq->lock by the governor's ddrinfo_dfs_step attribute */
static int ddrinfo_dfs_step_show(char **arg, char **step_status, char **scene, u32 *buff, int *pid, u32 i)
{
	enum DDR_DFS_STATE_STEP step;

	if (i == 0)
		ddr_dfs_step_s = ddr_cur_step_g;
	ddr_dfs_step_s = ddr_dfs_step_s->next;
	step = ddr_dfs_step_s->data.step;
	*arg = (step > 0 && step < ARRAY_SIZE(step_names) && step_names[step]) ? (char *)step_names[step] :
		"NONE_STEP";
	switch (step) {
	case scenario_dfs_enter:
	case exit_scene:
	case set_overflow_t:
	case set_underflow_t:
		*scene = ddr_dfs_step_s->data.scene;
		break;
	default:
		*scene = NULL;
	}
	*step_status = ddr_dfs_step_s->data.status == 0 ? "pass" : "fail";
	*buff = ddr_dfs_step_s->data.buff;
	*pid = ddr_dfs_step_s->data.pid;
	return i >= DDR_DB_NODE_NUM - 1;
}

static int dvfs_msg_recv(struct smsg *msg, int timeout)
{
	int err = smsg_recv(SIPC_ID_PM_SYS, msg, timeout);

	if (err < 0) {
		dev_err(g_dvfs_data->dev, "dvfs receive failed:%d\n", err);
		return err;
	}
	if (msg->channel == SMSG_CH_PM_CTRL && msg->type == SMSG_TYPE_DFS_RSP)
		return 0;
	return -EINVAL;
}

static int dvfs_msg_send(struct smsg *msg, unsigned int cmd, int timeout, unsigned int value)
{
	int err;

	smsg_set(msg, SMSG_CH_PM_CTRL, SMSG_TYPE_DFS, cmd, value);
	err = smsg_send(SIPC_ID_PM_SYS, msg, timeout);
	dev_dbg(g_dvfs_data->dev, "send: channel=%d, type=%d, flag=0x%x, value=0x%x\n",
		msg->channel, msg->type, msg->flag, msg->value);
	if (err < 0) {
		dev_err(g_dvfs_data->dev, "dvfs send failed, freq:%u, cmd:0x%x\n", value, cmd);
		return err;
	}
	return 0;
}

static int dvfs_msg_parse_ret(struct smsg *msg)
{
	struct device *dev = g_dvfs_data->dev;

	switch (msg->flag) {
	case DVFS_RET_ADJ_OK:
	case DVFS_RET_ON_OFF_SUCCEED:
	case DVFS_RET_INQ_SUCCEED:
	case DVFS_RET_SET_SUCCEED:
	case DVFS_RET_PARA_OK:
	case DVFS_RET_DEBUG_OK:
		return 0;
	case DVFS_RET_ADJ_VER_FAIL:
		dev_info(dev, "dvfs verify fail!current freq:%u\n", msg->value);
		return -EIO;
	case DVFS_RET_ADJ_BUSY:
		dev_info(dev, "dvfs busy!current freq:%u\n", msg->value);
		return -EBUSY;
	case DVFS_RET_ADJ_NOCHANGE:
		dev_info(dev, "dvfs no change!current freq:%u\n", msg->value);
		return -EFAULT;
	case DVFS_RET_ADJ_FAIL:
		dev_info(dev, "dvfs fail!current freq:%u\n", msg->value);
		return -EFAULT;
	case DVFS_RET_DISABLE:
		dev_info(dev, "dvfs is disabled!current freq:%u\n", msg->value);
		return -EPERM;
	case DVFS_RET_ON_OFF_FAIL:
		dev_err(dev, "dvfs enable verify failed\n");
		return -EINVAL;
	case DVFS_RET_INQ_FAIL:
		dev_err(dev, "dvfs inquire failed\n");
		return -EINVAL;
	case DVFS_RET_SET_FAIL:
		dev_err(dev, "dvfs set failed\n");
		return -EINVAL;
	case DVFS_RET_INVALID_CMD:
		dev_info(dev, "no this command\n");
		return -EINVAL;
	default:
		dev_info(dev, "dvfs invalid cmd:%x!current freq:%u\n", msg->flag, msg->value);
		return -EINVAL;
	}
}

/* one request and its answer; callers that change state hold sync_mutex, as on 5.4 */
static int dvfs_msg(unsigned int *data, unsigned int value, unsigned int cmd, unsigned int wait)
{
	struct smsg msg;
	int err;

	if (!g_dvfs_data->channel_open)
		return -ENODEV;
	err = dvfs_msg_send(&msg, cmd, msecs_to_jiffies(100), value);
	if (err < 0)
		return err;
	err = dvfs_msg_recv(&msg, msecs_to_jiffies(wait));
	if (err < 0)
		return err;
	err = dvfs_msg_parse_ret(&msg);
	*data = msg.value;
	return err;
}

static int dvfs_enable(void)
{
	unsigned int data;

	return dvfs_msg(&data, 0, DVFS_CMD_ENABLE, 2000);
}

static int dvfs_disable(void)
{
	unsigned int data;

	return dvfs_msg(&data, 0, DVFS_CMD_DISABLE, 2000);
}

static int dvfs_auto_enable(void)
{
	unsigned int data;

	return dvfs_msg(&data, 0, DVFS_CMD_AUTO_ENABLE, 2000);
}

static int dvfs_auto_disable(void)
{
	unsigned int data;

	return dvfs_msg(&data, 0, DVFS_CMD_AUTO_DISABLE, 2000);
}

static int get_dvfs_status(unsigned int *data)
{
	return dvfs_msg(data, 0, DVFS_CMD_INQ_STATUS, 500);
}

static int get_dvfs_auto_status(unsigned int *data)
{
	return dvfs_msg(data, 0, DVFS_CMD_INQ_AUTO_STATUS, 500);
}

static int force_freq_request(unsigned int freq)
{
	unsigned int data;
	int err;

	if (!g_dvfs_data->init_done)
		return -EINVAL;
	mutex_lock(&g_dvfs_data->sync_mutex);
	err = dvfs_msg(&data, freq, DVFS_CMD_SET_DDR_FREQ, 500);
	if (err == 0)
		g_dvfs_data->force_freq = freq;
	mutex_unlock(&g_dvfs_data->sync_mutex);
	return err;
}

/*
 * Withdraw a forced frequency (bypassing devfreq's clamp of 0 to the lowest level). pm_sys turns its automatic
 * scaling off for a forced frequency and leaves it off after SET_DDR_FREQ 0 (the DDR then stays at its lowest
 * level), so it is turned on again here where this driver turned it on.
 */
int release_forced_freq(void)
{
	int err = force_freq_request(0);

	if (!err && scaling)
		err = dvfs_auto_enable();
	return err;
}

/* sprd-governor taking over from a governor that forced a frequency (userspace, performance, powersave) */
void dvfs_release_if_forced(void)
{
	if (g_dvfs_data && g_dvfs_data->init_done && g_dvfs_data->force_freq)
		release_forced_freq();
}

/*
 * pm_sys ignores a vote (DVFS_CMD_NORMAL) of 0: the vendor code's "no vote" left the last one standing, so the
 * "boot-opt" scene held the DDR at its top level for good. The lowest level stands for "no vote" instead.
 */
unsigned int dvfs_lowest_freq(void)
{
	return g_dvfs_data && g_dvfs_data->profile.max_state ? g_dvfs_data->df_table[0] : 0;
}

unsigned long get_max_freq(void)
{
	return g_dvfs_data->devfreq ? g_dvfs_data->devfreq->scaling_max_freq : 0;
}

int send_freq_request(unsigned int freq)
{
	unsigned int i;
	int err;

	if (!g_dvfs_data || !g_dvfs_data->init_done)
		return -EINVAL;
	/* 0 withdraws the request; anything else must be one of pm_sys's levels */
	for (i = 0; freq && i < g_dvfs_data->freq_num; i++)
		if (g_dvfs_data->freq_table[i] == freq)
			break;
	if (freq && i == g_dvfs_data->freq_num)
		return -EINVAL;
	err = g_dvfs_data->hw_callback->dvfs_freq_request(freq);
	if (err == 0) {
		mutex_lock(&g_dvfs_data->sync_mutex);
		g_dvfs_data->request_freq = freq;
		mutex_unlock(&g_dvfs_data->sync_mutex);
	}
	return err;
}

int get_request_freq(unsigned int *data)
{
	if (!g_dvfs_data || !g_dvfs_data->init_done)
		return -EINVAL;
	*data = g_dvfs_data->request_freq;
	return 0;
}

int send_vote_request(unsigned int freq)
{
	unsigned int data;
	int err;

	if (!g_dvfs_data || !g_dvfs_data->init_done)
		return -EINVAL;
	mutex_lock(&g_dvfs_data->sync_mutex);
	err = dvfs_msg(&data, freq, DVFS_CMD_NORMAL, 500);
	mutex_unlock(&g_dvfs_data->sync_mutex);
	return err;
}

static int get_freq_table(unsigned int *data, unsigned int sel)
{
	if (sel >= g_dvfs_data->freq_num)
		return -EINVAL;
	if (g_dvfs_data->init_done != 1)
		return dvfs_msg(data, sel, DVFS_CMD_INQ_DDR_TABLE, 500);
	*data = g_dvfs_data->freq_table[sel];
	return 0;
}

static int get_cur_freq(unsigned int *data)
{
	return dvfs_msg(data, 0, DVFS_CMD_INQ_DDR_FREQ, 500);
}

static int get_overflow(unsigned int *data, unsigned int sel)
{
	if (sel >= g_dvfs_data->freq_num)
		return -EINVAL;
	if (g_dvfs_data->init_done != 1)
		return dvfs_msg(data, sel, DVFS_CMD_INQ_OVERFLOW, 500);
	*data = g_dvfs_data->paras[sel].overflow;
	return 0;
}

static int get_underflow(unsigned int *data, unsigned int sel)
{
	if (sel >= g_dvfs_data->freq_num)
		return -EINVAL;
	if (g_dvfs_data->init_done != 1)
		return dvfs_msg(data, sel, DVFS_CMD_INQ_UNDERFLOW, 500);
	*data = g_dvfs_data->paras[sel].underflow;
	return 0;
}

static int set_overflow(unsigned int value, unsigned int sel)
{
	unsigned int data;
	int err;

	if (sel >= g_dvfs_data->freq_num)
		return -EINVAL;
	mutex_lock(&g_dvfs_data->sync_mutex);
	err = dvfs_msg(&data, value, DVFS_CMD_PARA_OVERFLOW + sel, 500);
	if (err == 0 && g_dvfs_data->init_done == 1)
		g_dvfs_data->paras[sel].overflow = value;
	mutex_unlock(&g_dvfs_data->sync_mutex);
	return err;
}

static int set_underflow(unsigned int value, unsigned int sel)
{
	unsigned int data;
	int err;

	if (sel >= g_dvfs_data->freq_num)
		return -EINVAL;
	mutex_lock(&g_dvfs_data->sync_mutex);
	err = dvfs_msg(&data, value, DVFS_CMD_PARA_UNDERFLOW + sel, 500);
	if (err == 0 && g_dvfs_data->init_done == 1)
		g_dvfs_data->paras[sel].underflow = value;
	mutex_unlock(&g_dvfs_data->sync_mutex);
	return err;
}

static int get_freq_num(unsigned int *data)
{
	*data = g_dvfs_data->freq_num;
	return 0;
}

static int gov_vote(const char *name)
{
	if (!g_dvfs_data->init_done)
		return -EINVAL;
	return g_dvfs_data->hw_callback->hw_dvfs_vote(name);
}

static int gov_unvote(const char *name)
{
	if (!g_dvfs_data->init_done)
		return -EINVAL;
	return g_dvfs_data->hw_callback->hw_dvfs_unvote(name);
}

static int gov_change_point(const char *name, unsigned int freq)
{
	if (!g_dvfs_data->init_done)
		return -EINVAL;
	return g_dvfs_data->hw_callback->hw_dvfs_set_point(name, freq);
}

static int get_point_info(char **name, unsigned int *freq, unsigned int *flag, int index)
{
	if (!g_dvfs_data->hw_callback)
		return -EINVAL;
	return g_dvfs_data->hw_callback->hw_dvfs_get_point_info(name, freq, flag, index);
}

static struct governor_callback g_gov_callback = {
	.governor_vote = gov_vote,
	.governor_unvote = gov_unvote,
	.governor_change_point = gov_change_point,
	.get_point_info = get_point_info,
	.get_freq_num = get_freq_num,
	.get_overflow = get_overflow,
	.set_overflow = set_overflow,
	.get_underflow = get_underflow,
	.set_underflow = set_underflow,
	.get_dvfs_status = get_dvfs_status,
	.dvfs_enable = dvfs_enable,
	.dvfs_disable = dvfs_disable,
	.get_dvfs_auto_status = get_dvfs_auto_status,
	.dvfs_auto_enable = dvfs_auto_enable,
	.dvfs_auto_disable = dvfs_auto_disable,
	.get_cur_freq = get_cur_freq,
	.get_freq_table = get_freq_table,
	.ddrinfo_dfs_step_show = ddrinfo_dfs_step_show,
	.ddr_dfs_step_add = ddr_dfs_step_add,
};

/*
 * Under sprd-governor the frequency is pm_sys's own choice unless scaling_force_ddr_freq names one: the devfreq core
 * still calls target() whenever it re-evaluates (a min_freq/max_freq write), and clamps the governor's "no force"
 * (0) to the lowest level, which would pin the DDR there. So without a force nothing is sent. Other governors
 * (userspace, performance, powersave) force their frequency, as on 5.4.
 */
static int dvfs_freq_target(struct device *dev, unsigned long *freq, u32 flags)
{
	struct devfreq *df = g_dvfs_data->devfreq;
	unsigned int cur;
	int err;

	if (df && df->governor == &sprd_vote && !sprd_vote_forced()) {
		if (!get_cur_freq(&cur))
			*freq = cur;
		return 0;
	}
	err = force_freq_request(*freq);

	if (err < 0)
		dev_err(dev, "set freq fail: %d\n", err);
	return err;
}

static int dvfs_get_dev_status(struct device *dev, struct devfreq_dev_status *state)
{
	unsigned int f;
	int err;

	err = get_cur_freq(&f);
	if (err < 0)
		dev_err(dev, "get cur freq fail: %d\n", err);
	else
		state->current_frequency = f;
	state->private_data = g_dvfs_data->gov_callback;
	return err;
}

static int dvfs_get_cur_freq(struct device *dev, unsigned long *freq)
{
	unsigned int f;
	int err;

	err = get_cur_freq(&f);
	if (err < 0)
		dev_err(dev, "get cur freq fail: %d\n", err);
	else
		*freq = f;
	return err;
}

static int cmp_ulong(const void *a, const void *b)
{
	unsigned long x = *(const unsigned long *)a, y = *(const unsigned long *)b;

	return x < y ? -1 : x > y;
}

static void topfreq_unvote_work_handler(struct work_struct *work)
{
	scene_exit("boot-opt");
	dev_info(g_dvfs_data->dev, "dfs_init boot-opt scene cancel\n");
}

/* the start-up: pm_sys answers only once its side is up, which may be well after probe */
static void dvfs_init_work(struct work_struct *work)
{
	struct dvfs_data *data = container_of(work, struct dvfs_data, init_work);
	struct device *dev = data->dev;
	const char *gov_name;
	char *scene;
	unsigned int f, st = 0, ast = 0, n = 0, sf, sflag;
	unsigned int i;
	int err;

	while (smsg_ch_open(SIPC_ID_PM_SYS, SMSG_CH_PM_CTRL, msecs_to_jiffies(1000)))
		msleep(500);
	data->channel_open = true;

	if (get_dvfs_status(&st) == 0 && get_dvfs_auto_status(&ast) == 0 && get_cur_freq(&f) == 0)
		dev_info(dev, "pm_sys DFS %s, automatic scaling %s, DDR at %u MHz\n", st ? "on" : "off",
			 ast ? "on" : "off", f);
	if (scaling) {
		while (dvfs_enable())
			msleep(500);
	}

	for (i = 0; i < data->freq_num; i++) {
		err = get_freq_table(&data->freq_table[i], i);
		if (err < 0) {
			dev_err(dev, "failed to get frequence index: %u\n", i);
			return;
		}
		if (data->paras[i].overflow != 0)
			err = set_overflow(data->paras[i].overflow, i);
		else
			err = get_overflow(&data->paras[i].overflow, i);
		if (err < 0) {
			dev_err(dev, "overflow of level %u: %d\n", i, err);
			return;
		}
		if (data->paras[i].underflow != 0)
			err = set_underflow(data->paras[i].underflow, i);
		else
			err = get_underflow(&data->paras[i].underflow, i);
		if (err < 0) {
			dev_err(dev, "underflow of level %u: %d\n", i, err);
			return;
		}
		/* pm_sys has no voltage interface: the OPPs carry 5.4's placeholder */
		if (data->paras[i].vol == 0)
			data->paras[i].vol = 750;
		if (data->freq_table[i] != 0) {
			err = dev_pm_opp_add(dev, data->freq_table[i], data->paras[i].vol);
			if (err < 0 && err != -EEXIST) {
				dev_err(dev, "failed to add opp: %uMHZ-%uuv\n", data->freq_table[i], data->paras[i].vol);
				return;
			}
			data->df_table[n++] = data->freq_table[i];
		}
	}
	if (!n) {
		dev_err(dev, "pm_sys reported no DDR frequency\n");
		return;
	}
	sort(data->df_table, n, sizeof(*data->df_table), cmp_ulong, NULL);
	data->profile.freq_table = data->df_table;
	data->profile.max_state = n;

	err = get_cur_freq(&f);
	if (err < 0) {
		dev_err(dev, "failed to get initial freq\n");
		return;
	}
	data->profile.initial_freq = f;

	err = devfreq_add_governor(&sprd_vote);
	if (err < 0) {
		dev_err(dev, "failed to add governor\n");
		return;
	}
	if (of_property_read_string(dev->of_node, "governor", &gov_name))
		gov_name = default_governor;

	data->devfreq = devfreq_add_device(dev, &data->profile, gov_name, NULL);
	if (IS_ERR(data->devfreq)) {
		dev_err(dev, "add freq devices fail: %ld\n", PTR_ERR(data->devfreq));
		data->devfreq = NULL;
		return;
	}

	if (scaling) {
		err = dvfs_auto_enable();
		if (err < 0) {
			dev_err(dev, "dvfs auto enable failed\n");
			return;
		}
	}
	data->init_done = 1;

	/* 5.4 holds the DDR at its top level for the first 30 s through the "boot-opt" scene, where the device tree
	 * names one (sprd-scene); these boards' device tree names none */
	if (!get_point_info(&scene, &sf, &sflag, 0) && !scene_dfs_request("boot-opt")) {
		dev_info(dev, "dfs_init scene set boot-opt\n");
		schedule_delayed_work(&data->topfreq_unvote_work, msecs_to_jiffies(30000));
	}
	dev_info(dev, "%u DDR levels, %lu-%lu MHz, now %u MHz, automatic scaling %s\n", n, data->df_table[0],
		 data->df_table[n - 1], f, scaling ? "on" : "left as it was");
}

int dvfs_core_init(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *node = dev->of_node;
	struct dvfs_data *data;
	unsigned int freq_num, i;

	if (g_dvfs_data) {
		dev_err(dev, "dvfs core can used by single device only\n");
		return -EINVAL;
	}
	if (of_property_read_u32(node, "freq-num", &freq_num) || !freq_num || freq_num > 32) {
		dev_warn(dev, "failed read freqnum\n");
		freq_num = 8;
	}

	data = devm_kzalloc(dev, sizeof(*data), GFP_KERNEL);
	if (!data)
		return -ENOMEM;
	data->freq_table = devm_kcalloc(dev, freq_num, sizeof(*data->freq_table), GFP_KERNEL);
	data->df_table = devm_kcalloc(dev, freq_num, sizeof(*data->df_table), GFP_KERNEL);
	data->paras = devm_kcalloc(dev, freq_num, sizeof(*data->paras), GFP_KERNEL);
	if (!data->freq_table || !data->df_table || !data->paras)
		return -ENOMEM;

	data->dev = dev;
	data->freq_num = freq_num;
	mutex_init(&data->sync_mutex);
	mutex_init(&data->dfs_step_mutex);
	data->gov_callback = &g_gov_callback;
	ddr_cur_step_g = ddr_step_list_init(ddr_step_arr, DDR_DB_NODE_NUM);

	for (i = 0; i < freq_num; i++) {
		if (of_property_read_u32_index(node, "overflow", i, &data->paras[i].overflow) ||
		    of_property_read_u32_index(node, "underflow", i, &data->paras[i].underflow))
			break;
	}

	INIT_DELAYED_WORK(&data->topfreq_unvote_work, topfreq_unvote_work_handler);
	INIT_WORK(&data->init_work, dvfs_init_work);
	data->profile.polling_ms = 0;
	data->profile.target = dvfs_freq_target;
	data->profile.get_dev_status = dvfs_get_dev_status;
	data->profile.get_cur_freq = dvfs_get_cur_freq;

	g_dvfs_data = data;
	platform_set_drvdata(pdev, data);
	return 0;
}

void dvfs_core_hw_callback_register(struct dvfs_hw_callback *hw_callback)
{
	g_dvfs_data->hw_callback = hw_callback;
	queue_work(system_long_wq, &g_dvfs_data->init_work);
}
