/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * The DDR DFS protocol of the UMS9620's PM_SYS firmware, as far as sprd_ddr_dfs uses it: plain C with no kernel
 * header, so that tests/test_sprd_ddr_dfs.py compiles and runs it on the host.
 *
 * A request is one smsg on SMSG_CH_PM_CTRL of type SMSG_TYPE_DFS: flag = command, value = argument. The firmware
 * answers with one smsg of type SMSG_TYPE_DFS_RSP: flag = result code, value = data. Frequencies are in MHz.
 * What the U30 Air's firmware does with them (measured):
 *   VOTE f            the AP's floor while auto DFS runs: the firmware scales between f and the top on its own
 *                     (bandwidth overflow/underflow); the lowest entry of the table means no floor
 *   SET_DDR_FREQ f    pins f and turns auto DFS off
 *   AUTO_ENABLE       auto DFS on; ENABLE/DISABLE turn DFS as a whole on and off, the frequency stays where it is
 *   INQ_DDR_TABLE i   entry i of the table, 0 past the end; INQ_AP_FREQ is the AP's current vote
 * While DFS is off, VOTE and SET_DDR_FREQ are accepted and change nothing.
 */
#ifndef DDR_DFS_H
#define DDR_DFS_H

#define DDR_DFS_VOTE		0x0000
#define DDR_DFS_ENABLE		0x0300
#define DDR_DFS_DISABLE		0x0305
#define DDR_DFS_AUTO_ENABLE	0x0310
#define DDR_DFS_AUTO_DISABLE	0x0315
#define DDR_DFS_INQ_DDR_FREQ	0x0500
#define DDR_DFS_INQ_AP_FREQ	0x0502
#define DDR_DFS_INQ_DDR_TABLE	0x0505
#define DDR_DFS_INQ_STATUS	0x050A
#define DDR_DFS_INQ_AUTO_STATUS	0x050B
#define DDR_DFS_SET_DDR_FREQ	0x0600

#define DDR_DFS_MAX_FREQS	16

/* the firmware's result code as an errno (negative), 0 for every success code */
static inline int ddr_dfs_errno(unsigned int code)
{
	switch (code) {
	case 0x0000:	/* adjusted */
	case 0x0300:	/* on/off done */
	case 0x0500:	/* inquiry done */
	case 0x0600:	/* set done */
	case 0x070F:	/* parameter set */
		return 0;
	case 0x0002:	/* busy */
		return -16;	/* EBUSY */
	case 0x0005:	/* DFS is off */
		return -1;	/* EPERM */
	case 0x0F0F:	/* unknown command */
		return -95;	/* EOPNOTSUPP */
	default:	/* verify failed, no change, failed... */
		return -5;	/* EIO */
	}
}

/*
 * The usable table from the firmware's raw entries: the nonzero ones, which must rise. Returns their number, or 0
 * when they do not rise (a table this driver does not understand).
 */
static inline unsigned int ddr_dfs_table(const unsigned int *raw, unsigned int n, unsigned int *table)
{
	unsigned int i, count = 0;

	for (i = 0; i < n && count < DDR_DFS_MAX_FREQS; i++) {
		if (!raw[i])
			continue;
		if (count && raw[i] <= table[count - 1])
			return 0;
		table[count++] = raw[i];
	}
	return count;
}

/* the entry for a request of MHZ: the lowest one at or above it, the top one above the table */
static inline unsigned int ddr_dfs_pick(const unsigned int *table, unsigned int count, unsigned long mhz)
{
	unsigned int i;

	for (i = 0; i < count; i++)
		if (table[i] >= mhz)
			return table[i];
	return table[count - 1];
}

/* what the firmware reported at load */
struct ddr_dfs_state {
	unsigned int enabled;	/* INQ_STATUS */
	unsigned int autodfs;	/* INQ_AUTO_STATUS */
	unsigned int freq;	/* INQ_DDR_FREQ */
	unsigned int vote;	/* INQ_AP_FREQ */
};

struct ddr_dfs_req {
	unsigned int cmd, value;
};

/*
 * The requests that bring the firmware back to FOUND from any state this driver leaves it in (DFS on, auto DFS on
 * or a pinned frequency, any vote); REQ holds at least four. Returns their number. The vote goes first: while DFS
 * is on, the frequency the firmware ends at is then the found one (auto DFS) or the pinned one. DISABLE goes last:
 * once DFS is off, a pin changes nothing.
 */
static inline unsigned int ddr_dfs_restore(const struct ddr_dfs_state *found, struct ddr_dfs_req *req)
{
	unsigned int n = 0;

	req[n].cmd = DDR_DFS_VOTE;
	req[n++].value = found->vote;
	if (found->autodfs) {
		req[n].cmd = DDR_DFS_AUTO_ENABLE;
		req[n++].value = 0;
	} else {
		req[n].cmd = DDR_DFS_SET_DDR_FREQ;
		req[n++].value = found->freq;
	}
	if (!found->enabled) {
		req[n].cmd = DDR_DFS_DISABLE;
		req[n++].value = 0;
	}
	return n;
}

#endif
