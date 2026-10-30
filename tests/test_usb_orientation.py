"""The USB 3 lanes follow the plug (#54, FINDINGS 195): upstream/port/drivers/usb/phy/phy-sprd-ums9620-ssphy.c sets
the TCA's lane flip from the AON's USB_SW (or the PMIC's CC pin) and arms the PTN38003A redriver at every attach, as
ZTE's kernel does at each PHY init. Static rules, and the orientation code compiled against a fake SoC, PMIC and
redriver."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SSPHY = ROOT / 'upstream/port/drivers/usb/phy/phy-sprd-ums9620-ssphy.c'


def function(text, name):
    start = re.search(r'^static [^\n]*\b' + name + r'\(', text, re.M).start()
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end] + '\n'


def block(text, head):
    start = text.index(head)
    return text[start:text.index('\n};\n', start) + 4]


class Static(unittest.TestCase):
    def setUp(self):
        self.drv = SSPHY.read_text()

    def test_the_vendor_device_tree_unchanged(self):
        # the nodes ZTE's DTBs have (F50 and U30 Air): the redriver on i2c6 and the PMIC's Type-C block
        self.assertIn('"sprd,ptn38003a redriver"', self.drv)
        self.assertIn('"sprd,sc27xx-typec"', self.drv)
        self.assertNotIn('orientation-switch', self.drv)

    def test_never_a_boot_gate(self):
        # nothing new holds the PHY back: no deferral on the redriver or the Type-C block, I2C looked up later
        probe = function(self.drv, 'sprd_ssphy_probe')
        self.assertNotIn('sprd_ssphy_redriver', probe)
        before = subprocess.run(['git', 'show', 'origin/main:upstream/port/drivers/usb/phy/phy-sprd-ums9620-ssphy.c'],
                                cwd=ROOT, capture_output=True, text=True)
        if before.returncode == 0:
            self.assertEqual(probe.count('EPROBE_DEFER'), function(before.stdout, 'sprd_ssphy_probe').count('EPROBE_DEFER'))
        self.assertIn('IS_REACHABLE(CONFIG_I2C)', function(self.drv, 'sprd_ssphy_redriver'))
        kconfig = (ROOT / 'upstream/port/install.py').read_text()
        self.assertIn('select USB_PHY\\n\\tselect MFD_SYSCON', kconfig)

    def test_an_escape_hatch(self):
        self.assertIn('static int orientation = ORIENT_AUTO;', self.drv)
        self.assertIn('module_param_cb(orientation, &orientation_ops, NULL, 0644);', self.drv)
        self.assertIn('{ "off", "auto", "cc" }', self.drv)
        # off: the TCA once at init from USB_SW, as before; no work, no redriver
        work = function(self.drv, 'sprd_ssphy_orient_work')
        self.assertLess(work.index('if (mode == ORIENT_OFF)'), work.index('mutex_lock'))
        for name in ('sprd_ssphy_vbus_notify', 'sprd_ssphy_otg_set_vbus', 'sprd_ssphy_platform_shutdown'):
            self.assertIn('!= ORIENT_OFF', function(self.drv, name), name)

    def test_triggers(self):
        init = function(self.drv, 'sprd_ssphy_init')
        # init always writes the TCA, whatever the guard says; the guard only governs the attach-time flip
        self.assertIn('sprd_ssphy_lanes(phy, READ_ONCE(orientation), true, true);', init)
        work = function(self.drv, 'sprd_ssphy_orient_work')
        self.assertIn('key = sprd_ssphy_lanes(phy, mode, false, false);', work)
        self.assertLess(init.index('atomic_set(&phy->inited, 1);'), init.index('sprd_ssphy_kick(phy, 0, true);'))
        self.assertIn('sprd_ssphy_kick(phy, event ? 300 : 0, event);', function(self.drv, 'sprd_ssphy_vbus_notify'))
        self.assertIn('sprd_ssphy_kick(phy, 100, true);', function(self.drv, 'sprd_ssphy_otg_set_vbus'))
        shutdown = function(self.drv, 'sprd_ssphy_shutdown')
        self.assertLess(shutdown.index('cancel_delayed_work_sync'), shutdown.index('sprd_ssphy_redriver_park'))
        self.assertIn('.shutdown = sprd_ssphy_platform_shutdown,', self.drv)
        # the work is cancelled by devm after the VBUS notifier that queues it is gone
        probe = function(self.drv, 'sprd_ssphy_probe')
        self.assertLess(probe.index('devm_add_action_or_reset(dev, sprd_ssphy_orient_stop'),
                        probe.index('ret = usb_add_phy_dev'))

    def test_kick_is_safe_in_atomic_context(self):
        # extcon calls the VBUS notifier from its own context: only an atomic flag and a queued work
        kick = function(self.drv, 'sprd_ssphy_kick')
        self.assertNotIn('mutex', kick)
        self.assertIn('mod_delayed_work', kick)


HARNESS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
typedef unsigned int u32;
typedef unsigned char u8;
#define BIT(n) (1U << (n))
#define GENMASK(h, l) (((~0U) << (l)) & (~0U >> (31 - (h))))
#define __iomem
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define READ_ONCE(x) (x)
#define IS_REACHABLE(x) 0
#define REG_AON_APB_BOOT_MODE 0x002C
#define MASK_AON_APB_USB_SW 0x0400
#define PHY_INIT_TIMEOUT 500
#define EPROBE_DEFER 517
typedef struct { int counter; } atomic_t;
struct mutex { int held; };
struct device { int x; };
struct usb_phy { int x; };
struct regulator { int x; };
struct work_struct { int x; };
struct delayed_work { struct work_struct work; int pending; unsigned int delay; };
struct regmap { u32 r[0x1000]; };
struct i2c_client { u8 r[256]; u8 wrote[16]; int n; int fail; };
#define to_delayed_work(w) container_of(w, struct delayed_work, work)
static int atomic_read(atomic_t *a) { return a->counter; }
static void atomic_set(atomic_t *a, int v) { a->counter = v; }
static int atomic_xchg(atomic_t *a, int v) { int o = a->counter; a->counter = v; return o; }
static int held;
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held = 1; held = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held = 0; held = 0; }
static unsigned int msecs_to_jiffies(unsigned int ms) { return ms; }
static int delayed_work_pending(struct delayed_work *w) { return w->pending; }
static void schedule_delayed_work(struct delayed_work *w, unsigned int d) { w->pending = 1; w->delay = d; }
static void msleep(int ms) { (void)ms; }
static void usleep_range(int a, int b) { (void)a; (void)b; }
static int regmap_read(struct regmap *m, u32 reg, u32 *v) { *v = m->r[reg]; return 0; }
static u32 tca[0x40], tca_writes;
static u32 readl_relaxed(const void *p) { return *(const u32 *)p; }
static void writel_relaxed(u32 v, void *p)
{
	*(u32 *)p = v;
	if (p == (char *)tca + 0x14) {		/* TCPC: the controller acks, the PHY reports the flip */
		tca_writes++;
		tca[0x08 / 4] |= BIT(0);
		tca[0x34 / 4] = v & BIT(2) ? 0 : BIT(2);
	}
}
static char last[1024], warned[256];
static int infos;
#define dev_info(d, ...) (snprintf(last + strlen(last), sizeof(last) - strlen(last), __VA_ARGS__), infos++)
#define dev_warn(d, ...) snprintf(warned, sizeof(warned), __VA_ARGS__)
#define dev_err(d, ...) ((void)0)
static int i2c_smbus_read_byte_data(struct i2c_client *c, u8 reg) { return c->fail ? -EIO : c->r[reg]; }
static int i2c_smbus_write_byte_data(struct i2c_client *c, u8 reg, u8 v)
{
	if (c->fail)
		return -EIO;
	assert(reg == 0x04 && c->n < 16);
	c->wrote[c->n++] = v;
	c->r[reg] = (v & ~BIT(6)) | (c->r[reg] & BIT(6));	/* "orientation done" is read-only */
	if (!(v & BIT(7)))
		c->r[reg] &= ~BIT(6);
	return 0;
}
'''

FAKE_REDRIVER = r'''
static struct i2c_client redriver;
static int redriver_where;	/* 0 there, 1 not in the device tree, 2 its bus not probed yet */
static struct i2c_client *sprd_ssphy_redriver(struct sprd_ssphy *phy)
{
	if (redriver_where == 1)
		phy->no_redriver = true;
	else if (redriver_where == 0)
		phy->redriver = &redriver;
	return phy->redriver;
}
'''

MAIN = r'''
static struct regmap aon, pmic;
static struct sprd_ssphy phy;

static void run(void)
{
	phy.orient_work.pending = 0;
	last[0] = 0;
	sprd_ssphy_orient_work(&phy.orient_work.work);
	assert(!held);
}

static void kick(void) { atomic_set(&phy.force, 1); }

int main(void)
{
	const char *from;

	/* the decision: ZTE's USB_SW, set = flipped; the CC pin only in "cc" mode and only while attached */
	assert(sprd_ssphy_lanes_normal(ORIENT_AUTO, 0, true, 2 | BIT(5), &from) && !strcmp(from, "USB_SW"));
	assert(!sprd_ssphy_lanes_normal(ORIENT_AUTO, BIT(10), true, 2 | BIT(5), &from));
	assert(sprd_ssphy_lanes_normal(ORIENT_CC, BIT(10), true, 2 | BIT(5), &from) && !strcmp(from, "CC"));
	assert(!sprd_ssphy_lanes_normal(ORIENT_CC, 0, true, 5, &from) && !strcmp(from, "CC"));
	assert(!sprd_ssphy_lanes_normal(ORIENT_CC, BIT(10), true, 0 | BIT(5), &from) && !strcmp(from, "USB_SW"));
	assert(sprd_ssphy_lanes_normal(ORIENT_CC, 0, false, 0, &from) && !strcmp(from, "USB_SW"));

	/* TCPC and SYSMODE_CFG as ZTE's init writes them: 0x13 / 0x17, low power cleared, bit 2 in both */
	assert(sprd_ssphy_tcpc(0, false) == 0x13 && sprd_ssphy_tcpc(0, true) == 0x17);
	assert(sprd_ssphy_tcpc(0x0c, false) == 0x13 && sprd_ssphy_tcpc(0x100, true) == 0x117);
	assert(sprd_ssphy_sysmode(0x8, true) == 0xc && sprd_ssphy_sysmode(0xc, false) == 0x8);

	/* the redriver: ZTE's 0x81 from deep power saving; off keeps DFP/UFP, AUX polarity and orientation bits */
	assert(sprd_ssphy_redriver_on(0x00, ORIENT_AUTO, true) == 0x81);
	assert(sprd_ssphy_redriver_on(0xd1, ORIENT_AUTO, false) == 0x81);
	assert(sprd_ssphy_redriver_on(0x28, ORIENT_AUTO, true) == 0xa9);
	assert(sprd_ssphy_redriver_on(0x81, ORIENT_CC, false) == 0x11 && sprd_ssphy_redriver_on(0x91, ORIENT_CC, true) == 0x01);
	assert(sprd_ssphy_redriver_off(0xd1) == 0x50 && sprd_ssphy_redriver_off(0x39) == 0x38);

	phy.base = (void *)tca;
	phy.aon_apb = &aon;
	phy.pmic = &pmic;
	phy.typec_base = 0x380;
	atomic_set(&phy.inited, 1);
	orientation = ORIENT_AUTO;

	/* boot, F50 powered by a USB 3 adapter plugged in the flipped way: init set the TCA already, so the work
	 * leaves it and only arms the redriver, through deep power saving (the left-over detection is not reused) */
	aon.r[0x2c] = BIT(10);
	pmic.r[0x380 + 0x1c] = 2;			/* attached as a sink, on CC2 */
	tca[0x14 / 4] = 0x13;
	redriver.r[4] = 0xc1;				/* POR auto detection done, normal: the wrong way */
	kick();
	run();
	assert(tca_writes == 0 && redriver.n == 2 && redriver.wrote[0] == 0x40 && redriver.wrote[1] == 0x81);
	assert(strstr(last, "USB 3 lanes flipped (from USB_SW; USB_SW 1, Type-C CC2"));
	assert(strstr(last, "redriver: mode 0xc1, now 0x81"));
	assert(phy.check && phy.orient_work.pending && phy.orient_work.delay == 1500);

	/* 1.5 s later: what the redriver found */
	redriver.r[4] = 0xd1;
	run();
	assert(strstr(last, "redriver: detected orientation reverse (0xd1)") && redriver.n == 2);
	assert(!phy.orient_work.pending);		/* a device: VBUS tells of the next attach */

	/* the host role: polled each second; unplugged: nothing written, only forgotten */
	phy.is_host = true;
	kick();
	run();
	assert(redriver.n == 4 && tca_writes == 0);
	run();						/* the check */
	assert(phy.orient_work.pending && phy.orient_work.delay == 1000);
	pmic.r[0x380 + 0x1c] = 0;
	aon.r[0x2c] = 0;
	run();
	assert(phy.applied == 0 && redriver.n == 4 && tca_writes == 0 && phy.orient_work.delay == 1000);

	/* a device plugged in the other way round: TCA flipped back to normal, the redriver armed again */
	pmic.r[0x380 + 0x1c] = 5 | BIT(5);
	run();
	assert(tca_writes == 1 && tca[0x14 / 4] == 0x17 && (tca[0x18 / 4] & BIT(2)));
	assert(redriver.n == 6 && redriver.wrote[5] == 0x81);
	assert(strstr(last, "USB 3 lanes normal (from USB_SW; USB_SW 0, Type-C CC1, TCA flip status 0)"));
	/* still there: nothing again */
	run();
	run();
	assert(tca_writes == 1 && redriver.n == 6);

	/* the same device turned round without a detach seen between two polls */
	pmic.r[0x380 + 0x1c] = 5;
	aon.r[0x2c] = BIT(10);
	run();
	assert(tca_writes == 2 && tca[0x14 / 4] == 0x13 && redriver.n == 8);

	/* "cc": the PMIC's pin for both, the redriver told the orientation instead of detecting it */
	orientation = ORIENT_CC;
	aon.r[0x2c] = 0;				/* USB_SW disagreeing is not looked at */
	kick();
	run();
	assert(tca[0x14 / 4] == 0x13 && redriver.wrote[redriver.n - 1] == 0x11);
	assert(strstr(last, "USB 3 lanes flipped (from CC;"));
	run();
	assert(strstr(last, "redriver: orientation reverse as set (0x11)"));
	orientation = ORIENT_AUTO;

	/* off: the work does nothing at all */
	orientation = ORIENT_OFF;
	kick();
	int n = redriver.n, t = tca_writes;
	run();
	assert(redriver.n == n && tca_writes == t && atomic_read(&phy.force));
	orientation = ORIENT_AUTO;

	/* a board without the redriver node: lanes only, no warning, no retry */
	memset(&phy.redriver, 0, sizeof(phy.redriver));
	phy.redriver = NULL;
	redriver_where = 1;
	phy.is_host = false;
	warned[0] = 0;
	kick();
	run();
	assert(!warned[0] && !phy.orient_work.pending && !phy.check);

	/* i2c6 not probed yet: tried again each second, a bounded number of times */
	phy.no_redriver = false;
	redriver_where = 2;
	kick();
	run();
	assert(phy.orient_work.pending && phy.orient_work.delay == 1000 && atomic_read(&phy.force));
	for (int i = 0; i < 40; i++)
		run();
	assert(!phy.orient_work.pending && phy.lookups == 31);
	redriver_where = 0;
	kick();
	run();
	assert(phy.redriver == &redriver && phy.check);

	/* an I2C error is reported and nothing is checked; the TCA keeps the write PHY init made */
	phy.check = false;
	redriver.fail = 1;
	t = tca_writes;
	kick();
	run();
	assert(strstr(warned, "redriver: -5") && !phy.check && tca_writes == t);
	redriver.fail = 0;

	/* no Type-C block in the device tree: every trigger sets the lanes, no polling as a host */
	phy.typec_base = 0;
	phy.is_host = true;
	kick();
	run();
	run();
	assert(!phy.orient_work.pending);

	/* not initialised (shut down): nothing */
	atomic_set(&phy.inited, 0);
	n = redriver.n;
	kick();
	run();
	assert(redriver.n == n);
	puts("ok");
	return 0;
}
'''


@unittest.skipUnless(shutil.which('cc'), 'needs a C compiler')
class Orientation(unittest.TestCase):
    def test_orientation_against_a_fake_soc(self):
        drv = SSPHY.read_text()
        defines = ''.join(l + '\n' for l in drv.splitlines()
                          if l.startswith('#define') and '\\' not in l and 'DISPC1' not in l)
        enum = re.search(r'^enum \{ ORIENT_OFF[^\n]*\n', drv, re.M).group(0)
        parts = [HARNESS, defines, enum, 'static int orientation;\n', block(drv, 'struct sprd_ssphy {'),
                 FAKE_REDRIVER]
        for name in ('sprd_ssphy_typec_attached', 'sprd_ssphy_lanes_normal', 'sprd_ssphy_tcpc', 'sprd_ssphy_sysmode',
                     'sprd_ssphy_redriver_off', 'sprd_ssphy_redriver_on', 'sprd_ssphy_tca_set',
                     'sprd_ssphy_typec_status', 'sprd_ssphy_lanes', 'sprd_ssphy_redriver_arm',
                     'sprd_ssphy_orient_work'):
            parts.append(function(drv, name))
        with tempfile.TemporaryDirectory() as d:
            src, exe = Path(d) / 't.c', Path(d) / 't'
            src.write_text(''.join(parts) + MAIN)
            r = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wno-unused-function', '-Wno-unused-parameter',
                                '-Wno-unused-variable', '-Wno-unused-macros', '-o', str(exe), str(src)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr[-3000:])
            r = subprocess.run([str(exe)], capture_output=True, text=True)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'ok'), r.stderr)


if __name__ == '__main__':
    unittest.main()
