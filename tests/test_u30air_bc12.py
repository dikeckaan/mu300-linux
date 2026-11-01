"""The U30 Air's BC1.2 charger detection, owned by the USB PHY (upstream/port/drivers/usb/phy/phy-sprd-ums9620-ssphy.c,
ums9620-bc12.h) and taken by the charger (upstream/patches/0032): kanoqwq's b4748534 and his tests/u30air_bc12.py.

The PHY's real detection code is compiled with register and event stand-ins: SDP/CDP/DCP, a detection still running,
the one stock retry of "no answer", its time limit, a read or switch error, an unplug while a result is read, a late
result of an older plug, the host role, a stop, and the boards without a battery. No device is touched; this does not
replace a charger, a computer and OTG on a real U30 Air.

The charger half is checked in the patch text; with MU300_KERNEL_TREE=<a tree with the patches applied> its real
bq2560x_chg_detect() is compiled and run too."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP

PHY = TOP / 'upstream/port/drivers/usb/phy'
PATCHES = TOP / 'upstream/patches'


def patch(prefix):
    found = sorted(PATCHES.glob(prefix + '-*.patch'))
    assert len(found) == 1, found
    return found[0].read_text()


def added(text):
    return '\n'.join(l[1:] for l in text.splitlines() if l.startswith('+') and not l.startswith('+++'))


def removed(text):
    return '\n'.join(l[1:] for l in text.splitlines() if l.startswith('-') and not l.startswith('---'))


def after(text):
    """the hunks as they read once applied: context and added lines"""
    return '\n'.join(l[1:] for l in text.splitlines()
                     if (l.startswith('+') and not l.startswith('+++')) or l.startswith(' '))


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


def compile_and_run(test, code, extra=()):
    with tempfile.TemporaryDirectory(prefix='u30-bc12-') as tmp:
        src, exe = Path(tmp) / 'test.c', Path(tmp) / 'test'
        src.write_text(code)
        r = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wno-sign-compare',
                            '-Wno-unused-parameter', '-Wno-unused-function', *extra, str(src), '-o', str(exe)],
                           capture_output=True, text=True)
        test.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        test.assertEqual(r.returncode, 0, r.stdout + r.stderr)


PHY_HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>
#define BIT(n) (1U<<(n))
#define GENMASK(h,l) (((1U<<((h)-(l)+1))-1)<<(l))
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define NOTIFY_OK 1
#define USB_SPEED_UNKNOWN 0
#define CHGR_DET_FGU_CTRL 0x23a0
#define system_power_efficient_wq NULL
#define dev_info(...) ((void)0)
#define dev_err(...) ((void)0)
#define to_delayed_work(p) container_of(p,struct delayed_work,work)
#define spin_lock_irqsave(l,f) ((void)(l),(f)=0)
#define spin_unlock_irqrestore(l,f) ((void)(l),(void)(f))
typedef unsigned int u32;
struct device_node {int unused;};
static struct device_node *of_find_node_by_path(const char *p){(void)p;return NULL;}
static void of_node_put(struct device_node *n){(void)n;}
struct work_struct {int unused;};
struct delayed_work {struct work_struct work;};
struct notifier_block {int unused;};
enum usb_charger_type {UNKNOWN_TYPE,SDP_TYPE,DCP_TYPE,CDP_TYPE};
enum {USB_CHARGER_ABSENT,USB_CHARGER_PRESENT};
struct usb_phy {enum usb_charger_type chg_type;int chg_state;struct work_struct chg_work;struct notifier_block vbus_nb;void *dev;};
struct sprd_ssphy {
    struct usb_phy phy;void *pmic,*dev;int dpdm_lock,bc12_event_lock;
    bool bc12_enabled,bc12_ready,bc12_stopping,vbus_present,is_host;
    int bc12_generation;u32 bc12_seen;unsigned int bc12_samples;bool bc12_retry;
    struct delayed_work bc12_work;
};
static int atomic_read(int *p){return *p;}
static void atomic_inc(int *p){++*p;}
static void mutex_lock(int *p){assert(!*p);*p=1;}
static void mutex_unlock(int *p){assert(*p);*p=0;}
static unsigned long msecs_to_jiffies(unsigned long n){return n;}
static bool queued,usb_owner;
static u32 reg_status,reg_ctrl=0x2f0,reg_retry;
static int publications,connects,disconnects,attempts,updates,fail_update,fail_read;
static unsigned long wait_ms;
static struct sprd_ssphy *event_during_read;
static int mod_delayed_work(void *q,struct delayed_work *w,unsigned long delay){
    (void)q;(void)w;queued=true;wait_ms+=delay;return 0;
}
static void schedule_work(struct work_struct *w){(void)w;++publications;}
static int sc27xx_dpdm_switch_to_phy(void *map,bool enable){
    (void)map;if(fail_update && ++updates==fail_update)return -EIO;
    usb_owner=enable;return 0;
}
static int regmap_update_bits(void *map,u32 reg,u32 mask,u32 val){
    (void)map;
    if(fail_update && ++updates==fail_update)return -EIO;
    u32 *r=reg==CHGR_DET_FGU_CTRL?&reg_ctrl:&reg_retry;
    *r=(*r&~mask)|(val&mask);
    if(reg==0x243c && (val&1)){++attempts;reg_status&=~BIT(11);}
    return 0;
}
static int regmap_read(void *map,u32 reg,u32 *val){
    (void)map;assert(reg==0x239c);if(fail_read)return -EIO;
    *val=reg_status;
    if(event_during_read){
        event_during_read->vbus_present=false;
        ++event_during_read->bc12_generation;
        event_during_read=NULL;
    }
    return 0;
}
static int sprd_ssphy_notify_connect(struct usb_phy *p,int speed){(void)p;(void)speed;++connects;return 0;}
static int sprd_ssphy_notify_disconnect(struct usb_phy *p,int speed){(void)p;(void)speed;++disconnects;return 0;}
'''

PHY_MAIN = r'''
static struct sprd_ssphy phy;
static void tick(void){queued=false;sprd_ssphy_bc12_work(&phy.bc12_work.work);}
static void reset(void){
    phy=(struct sprd_ssphy){.bc12_enabled=true,.bc12_ready=true,.bc12_generation=1};
    queued=false;usb_owner=true;reg_ctrl=0x2f0;reg_retry=0;
    publications=connects=disconnects=attempts=updates=0;
    fail_update=fail_read=0;wait_ms=0;event_during_read=NULL;
}
static void attach(u32 status){
    reg_status=status;
    assert(sprd_ssphy_vbus_notify(&phy.phy.vbus_nb,1,NULL)==NOTIFY_OK);
    assert(queued);tick();
}
int main(void){
    /* a finished detection: a computer is never detected again, an SDP never gets more current */
    const u32 bits[]={BIT(7),BIT(6),BIT(5)};
    const int types[]={SDP_TYPE,DCP_TYPE,CDP_TYPE};
    for(int i=0;i<3;i++){
        reset();attach(BIT(2)|BIT(11)|bits[i]);
        assert(phy.phy.chg_type==types[i]&&!queued&&!attempts);
        assert(usb_owner==(types[i]!=DCP_TYPE));
        assert(sprd_ssphy_charger_detect(&phy.phy)==types[i]);
        assert((reg_ctrl&~(BIT(14)|BIT(0)))==0x2f0);   /* the detector's delay fields are left alone */
    }
    /* still running: the detector keeps D+/D- until DONE */
    reset();attach(BIT(2));assert(queued&&!usb_owner&&phy.phy.chg_type==UNKNOWN_TYPE);
    reg_status=BIT(2)|BIT(11)|BIT(5);tick();assert(!queued&&usb_owner&&phy.phy.chg_type==CDP_TYPE);
    /* no answer: detected once more, with the stock 960 ms delay */
    reset();attach(BIT(2)|BIT(11));assert(attempts==1&&queued&&!usb_owner);
    assert((reg_ctrl&GENMASK(7,4))==(15<<4));
    reg_status=BIT(2)|BIT(11)|BIT(6);tick();assert(!queued&&attempts==1&&!usb_owner&&phy.phy.chg_type==DCP_TYPE);
    /* any other combination of type bits stays UNKNOWN, never a DCP */
    for(unsigned int b=0;b<8;b++){
        if(b==1||b==2||b==4)continue;
        reset();attach(BIT(2)|BIT(11)|(b<<5));
        reg_status=BIT(2)|BIT(11)|(b<<5);tick();
        assert(!queued&&!usb_owner&&phy.phy.chg_type==UNKNOWN_TYPE&&attempts==1);
    }
    /* a detector that never finishes: bounded, no polling for ever */
    reset();attach(BIT(2));int ticks=1;
    while(queued){tick();assert(++ticks<200);}
    assert(attempts==1&&!usb_owner&&phy.phy.chg_type==UNKNOWN_TYPE);
    assert(wait_ms>1000&&wait_ms<4000);
    /* a read or switch error never hands unchecked lines to USB */
    reset();fail_read=1;attach(BIT(2));assert(!queued&&!usb_owner&&!connects);
    reset();fail_update=1;attach(BIT(2));assert(!queued&&!connects&&phy.phy.chg_type==UNKNOWN_TYPE);
    /* unplugged while a finished result is read */
    reset();event_during_read=&phy;attach(BIT(2)|BIT(11)|BIT(6));
    assert(queued&&!usb_owner&&phy.phy.chg_type==UNKNOWN_TYPE);tick();
    assert(!queued&&phy.phy.chg_state==USB_CHARGER_ABSENT);
    /* a late result of the plug before never overwrites the next one's */
    u32 old=phy.bc12_generation;
    sprd_ssphy_vbus_notify(&phy.phy.vbus_nb,1,NULL);
    assert(!sprd_ssphy_bc12_publish(&phy,DCP_TYPE,true,old));
    reg_status=BIT(2)|BIT(11)|BIT(7);tick();assert(usb_owner&&phy.phy.chg_type==SDP_TYPE);
    /* the host role (also a powered dock) owns D+/D-: no detection there */
    reset();phy.is_host=true;mutex_lock(&phy.dpdm_lock);sprd_ssphy_bc12_role(&phy);mutex_unlock(&phy.dpdm_lock);
    attach(BIT(2));assert(!queued&&usb_owner&&!attempts&&phy.phy.chg_type==UNKNOWN_TYPE);
    phy.is_host=false;mutex_lock(&phy.dpdm_lock);sprd_ssphy_bc12_role(&phy);mutex_unlock(&phy.dpdm_lock);
    reg_status=BIT(2)|BIT(11)|BIT(5);tick();assert(!queued&&usb_owner&&phy.phy.chg_type==CDP_TYPE);
    /* a stop, and the boards without a battery: no detection at all */
    reset();phy.bc12_stopping=true;tick();assert(!queued&&!publications);
    reset();phy.bc12_enabled=false;sprd_ssphy_vbus_notify(&phy.phy.vbus_nb,1,NULL);
    assert(connects==1&&!queued&&!attempts&&usb_owner);
    puts("PASS");
    return 0;
}
'''


class PhyOwner(unittest.TestCase):
    def setUp(self):
        self.source = (PHY / 'phy-sprd-ums9620-ssphy.c').read_text()
        self.header = (PHY / 'ums9620-bc12.h').read_text()

    @unittest.skipUnless(shutil.which('cc'), 'needs a C compiler')
    def test_the_detection(self):
        notify = function(self.source, 'static int sprd_ssphy_vbus_notify(')
        compile_and_run(self, PHY_HARNESS + self.header + notify + PHY_MAIN)

    def test_only_the_board_with_a_battery(self):
        self.assertIn('phy->bc12_enabled = sprd_ssphy_has_battery();', self.source)
        self.assertIn('of_find_node_by_path("/charger_policy_service")', self.header)
        # the boards without one: D+/D- to USB at probe, as before
        probe = function(self.source, 'static int sprd_ssphy_probe(')
        self.assertIn('\t\tsc27xx_dpdm_switch_to_phy(phy->pmic, true);', probe)

    def test_usb_is_never_lost_to_a_failed_setup(self):
        # kanoqwq's version failed the probe (no USB at all); here the PHY falls back to the direct path
        probe = function(self.source, 'static int sprd_ssphy_probe(')
        self.assertNotIn('BC1.2 detector setup\\n");', probe.replace('dev_err(dev, "BC1.2 detector setup failed', ''))
        self.assertNotIn('BC1.2 requires VBUS extcon', probe)
        self.assertEqual(probe.count('phy->bc12_enabled = false;'), 2)

    def test_the_role_change_always_unlocks(self):
        set_vbus = function(self.source, 'static int sprd_ssphy_set_vbus(')
        self.assertEqual(set_vbus.count('mutex_lock(&phy->dpdm_lock);'), 1)
        self.assertEqual(set_vbus.count('mutex_unlock(&phy->dpdm_lock);'), 1)
        self.assertNotIn('return', set_vbus[set_vbus.index('mutex_lock'):set_vbus.index('mutex_unlock')])

    def test_stop_and_shutdown(self):
        stop = function(self.source, 'static void sprd_ssphy_bc12_stop(')
        for step in ('devm_extcon_unregister_notifier', 'cancel_delayed_work_sync(&phy->bc12_work)',
                     'cancel_work_sync(&phy->phy.chg_work)'):
            self.assertIn(step, stop)
        self.assertIn('.shutdown = sprd_ssphy_shutdown_device', self.source)


class ChargerConsumer(unittest.TestCase):
    def setUp(self):
        self.text = patch('0032')

    def test_kano_is_the_author(self):
        self.assertTrue(self.text.startswith('From: kanoqwq <kanoqwq@qq.com>\n'))
        self.assertIn('b4748534', self.text)

    def test_no_second_detector(self):
        gone = removed(self.text)
        plus = added(self.text)
        for old in ('BQ256XX_IINDET_EN', 'sprd_pmic_detect_charger_type(', 'bq2560x_chg_iindpm(',
                    'devm_extcon_register_notifier', 'msecs_to_jiffies(event ? 500 : 0)'):
            self.assertIn(old, gone)
            self.assertNotIn(old, plus)
        self.assertIn('READ_ONCE(bq->bc12_phy->chg_type)', plus)
        self.assertIn('usb_register_notifier(bq->bc12_phy, &bq->vbus_nb);', plus)
        # still detecting or nothing found: a USB port's current
        self.assertIn('\t\tiindpm = 500000;\n\t\tbreak;\n\t}', after(self.text))

    def test_the_work_exists_before_the_power_supply_and_waits_for_the_chip(self):
        plus = after(self.text)
        self.assertIn('if (!READ_ONCE(bq->bc12_ready))\n\t\treturn;', plus)
        a = plus.index('ret = devm_delayed_work_autocancel(dev, &bq->vbus_work, bq2560x_chg_vbus_work);')
        b = plus.index('ret = bq256xx_power_supply_init(bq, &psy_cfg, dev);')
        self.assertLess(a, b)
        cleanup = function(plus, 'static void bq2560x_chg_phy_cleanup(')
        self.assertLess(cleanup.index('usb_unregister_notifier'), cleanup.index('cancel_delayed_work_sync'))

    def test_pd_and_rp_unchanged(self):
        self.assertNotIn('pd_contract', removed(self.text))
        self.assertNotIn('bq2560x_chg_typec_iindpm', removed(self.text))

    @unittest.skipUnless(shutil.which('cc') and os.environ.get('MU300_KERNEL_TREE'),
                         'needs a C compiler and MU300_KERNEL_TREE (a tree with the patches applied)')
    def test_the_detect_function(self):
        charger = (Path(os.environ['MU300_KERNEL_TREE']) / 'drivers/power/supply/bq256xx_charger.c').read_text()
        detect = function(charger, 'static void bq2560x_chg_detect(')
        pmic_type = function(charger, 'static int bq2560x_chg_pmic_type(')
        self.assertNotIn('IINDET', re.sub(r'/\*.*?\*/', '', detect, flags=re.S))
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#define IS_REACHABLE(x) 0
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define BQ256XX_CHARGER_CONTROL_0 1
#define BQ256XX_CHG_CONFIG_MASK 0x10
#define BQ256XX_OTG_CONFIG 0x20
#define BQ256XX_CHARGER_STATUS_0 8
#define BQ256XX_PG_STAT_MASK 4
#define BQ256XX_VBUS_STAT_MASK 0xe0
#define BQ256XX_VBUS_STAT_USB_OTG 0xe0
static void test_log(const char *fmt, ...){(void)fmt;}
#define dev_info(d,...) ((void)(d),test_log(__VA_ARGS__))
#define dev_warn(d,...) ((void)(d),test_log(__VA_ARGS__))
enum {UNKNOWN_TYPE,SDP_TYPE,DCP_TYPE,CDP_TYPE};
enum {POWER_SUPPLY_USB_TYPE_UNKNOWN,POWER_SUPPLY_USB_TYPE_SDP,POWER_SUPPLY_USB_TYPE_DCP,POWER_SUPPLY_USB_TYPE_CDP};
enum {USB_CHARGER_ABSENT,USB_CHARGER_PRESENT};
struct usb_phy {int chg_state,chg_type;};
struct bq256xx_device;
struct chip_info {int (*bq256xx_set_iindpm)(struct bq256xx_device*,int);};
struct bq256xx_device {void *dev,*regmap,*charger,*pmic;int lock,usb_type;bool chg_off,pd_contract,bc12_ready;
    const struct chip_info *chip_info;struct usb_phy *bc12_phy;};
static int current,sets,errors,rp,reads;
static unsigned int registers[16];
static void mutex_lock(int*p){assert(!*p);*p=1;}
static void mutex_unlock(int*p){assert(*p);*p=0;}
static int regmap_read(void*p,unsigned r,unsigned*v){(void)p;++reads;if(errors)return -EIO;*v=registers[r];return 0;}
static int regmap_update_bits(void*p,unsigned r,unsigned m,unsigned v){(void)p;assert(r==1);if(errors)return -EIO;
    registers[r]=(registers[r]&~m)|(v&m);return 0;}
static int set_current(struct bq256xx_device*b,int v){assert(b->lock);current=v;++sets;return 0;}
static int bq2560x_chg_typec_iindpm(struct bq256xx_device*b,unsigned int*v){assert(b->lock);*v=0;return rp;}
static void power_supply_changed(void*p){(void)p;}
''' + pmic_type + detect + r'''
int main(void){
 struct chip_info chip={set_current};struct usb_phy phy={USB_CHARGER_PRESENT,UNKNOWN_TYPE};
 struct bq256xx_device b={.bc12_ready=true,.chip_info=&chip,.bc12_phy=&phy};
 const int types[]={UNKNOWN_TYPE,SDP_TYPE,CDP_TYPE,DCP_TYPE};
 const int usb[]={POWER_SUPPLY_USB_TYPE_UNKNOWN,POWER_SUPPLY_USB_TYPE_SDP,POWER_SUPPLY_USB_TYPE_CDP,POWER_SUPPLY_USB_TYPE_DCP};
 const int currents[]={500000,500000,1500000,2000000};
 registers[1]=0x8a;registers[8]=4|0x20;
 for(int i=0;i<4;i++){
  phy.chg_type=types[i];rp=0;bq2560x_chg_detect(&b);
  assert(current==currents[i]&&b.usb_type==usb[i]);
  assert(registers[1]==0x9a);
 }
 /* the Type-C Rp current, whatever BC1.2 found */
 phy.chg_type=SDP_TYPE;rp=1500000;bq2560x_chg_detect(&b);assert(current==1500000);
 /* a PD contract's current is left alone */
 int n=sets;b.pd_contract=true;current=2000000;rp=0;
 bq2560x_chg_detect(&b);assert(sets==n&&current==2000000);b.pd_contract=false;
 /* charging stopped from userspace stays stopped; the boost is never touched */
 b.chg_off=true;bq2560x_chg_detect(&b);assert(!(registers[1]&0x10));b.chg_off=false;
 registers[1]=0xaa;n=sets;bq2560x_chg_detect(&b);assert(registers[1]==0xaa&&sets==n);
 registers[1]=0x8a;registers[8]=0;n=sets;bq2560x_chg_detect(&b);assert(sets==n);
 registers[8]=4|0x20;errors=1;n=sets;bq2560x_chg_detect(&b);assert(sets==n);errors=0;
 /* before the chip is set up: nothing */
 b.bc12_ready=false;n=reads;bq2560x_chg_detect(&b);assert(reads==n);
 /* no VBUS for the PHY: unknown, a USB port's current */
 b.bc12_ready=true;phy.chg_state=USB_CHARGER_ABSENT;phy.chg_type=DCP_TYPE;
 bq2560x_chg_detect(&b);assert(current==500000&&b.usb_type==POWER_SUPPLY_USB_TYPE_UNKNOWN);
 return 0;
}
'''
        compile_and_run(self, code)


if __name__ == '__main__':
    unittest.main()
