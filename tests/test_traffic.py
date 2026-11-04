"""mu300-traffic: the mobile data count (the panel's Data usage page). A fake / with sipa_eth0's counters, the boot
id and the uptime; the clock and the UTC offset are fixed per call (MU300_TRAFFIC_NOW, MU300_TRAFFIC_TZOFF). Every
byte counted once: the first reading is a base, a reboot or a re-created interface counts its new counters, a
counter that went down starts over; days split at local midnight by time, measured with the uptime (a clock jump
does not stretch an interval); bytes wait for NTP and are dated by their uptime; the billing cycle, the cap, its
warning and the cut; the service's checkpoints and its last save at a stop."""
import json
import os
import signal
import subprocess
import time
import unittest
from datetime import datetime, timedelta, timezone

from helpers import BIN, ShellTest

TOOL = BIN / 'mu300-traffic'
TZ3 = timezone(timedelta(hours=3))


def at(y, m, d, hh=0, mm=0, ss=0, off=3):
    """the epoch of a local time at UTC+off"""
    return int(datetime(y, m, d, hh, mm, ss, tzinfo=timezone(timedelta(hours=off))).timestamp())


class TrafficBase(ShellTest):
    def setUp(self):
        super().setUp()
        self.root = self.tmp / 'root'
        (self.root / 'proc/sys/kernel/random').mkdir(parents=True)
        (self.root / 'mnt/mu300-disk/.mu300').mkdir(parents=True)
        (self.root / 'run/mu300').mkdir(parents=True)
        self.store = self.root / 'mnt/mu300-disk/.mu300/traffic'
        self.stub('logger', 'shift 2; echo "$*" >> "$STUBLOG/log"')
        for c in ('ifdown', 'ifup', 'systemctl'):
            self.stub(c, f'echo "{c} $*" >> "$STUBLOG/calls"')
        self.synced(True)
        self.now = at(2026, 10, 10, 12)
        self.off = 10800

    def fresh(self):
        """a new device: nothing counted, no live ledger, no settings"""
        for p in (self.store, self.root / 'run/mu300/traffic'):
            subprocess.run(['rm', '-rf', str(p)])
        for f in ('log', 'calls'):
            (self.tmp / f).unlink(missing_ok=True)

    def synced(self, yes):
        f = self.root / 'run/mu300/clock-synced'
        if yes:
            f.write_text('')
        else:
            f.unlink(missing_ok=True)

    def counters(self, rx, tx, up, boot='aaaa-1', idx=7, dev='sipa_eth0'):
        (self.root / 'proc/sys/kernel/random/boot_id').write_text(boot + '\n')
        (self.root / 'proc/uptime').write_text(f'{up}.42 100.00\n')
        d = self.root / 'sys/class/net' / dev
        (d / 'statistics').mkdir(parents=True, exist_ok=True)
        (d / 'ifindex').write_text(f'{idx}\n')
        (d / 'statistics/rx_bytes').write_text(f'{rx}\n')
        (d / 'statistics/tx_bytes').write_text(f'{tx}\n')

    def no_interface(self, dev='sipa_eth0'):
        subprocess.run(['rm', '-rf', str(self.root / 'sys/class/net' / dev)])

    def run_tool(self, shell, *args, now=None, off=None, ok=True, **env):
        r = self.script(shell, TOOL, *args, MU300_SYSROOT=self.root, MU300_TRAFFIC_NOW=now or self.now,
                        MU300_TRAFFIC_TZOFF=self.off if off is None else off, **env)
        if ok:
            self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def sample(self, shell, rx, tx, up, now, **kw):
        """the counters are RX/TX at UP (uptime) and NOW; one reading taken and saved"""
        off = kw.pop('off', None)
        self.counters(rx, tx, up, **kw)
        self.run_tool(shell, 'save', now=now, off=off)

    def view(self, shell, now=None, off=None):
        return json.loads(self.run_tool(shell, 'json', now=now, off=off).stdout)

    def days(self, shell, now=None, off=None):
        return {d['date']: (d['rx'], d['tx']) for d in self.view(shell, now, off)['days']}

    def ledger(self):
        return (self.store / 'ledger').read_text()

    def set(self, shell, key, value):
        self.run_tool(shell, 'set', key, value)


class Counting(TrafficBase):
    def test_first_reading_is_a_base_and_later_ones_count(self):
        for shell in self.each_shell():
            self.fresh()
            # 5 GB already through the interface before counting started: not put on any day
            self.sample(shell, 5_000_000_000, 1_000_000, 100, self.now)
            self.assertEqual(self.days(shell), {})
            self.sample(shell, 5_000_300_000, 1_000_020, 160, self.now + 60)
            self.assertEqual(self.days(shell, self.now + 60), {'2026-10-10': (300_000, 20)})
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['today']['rx'], v['today']['tx'], v['cycle']['used']), (300_000, 20, 300_020))

    def test_a_view_adds_what_came_since_the_last_reading_without_writing(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            before = self.ledger()
            self.counters(4096, 1024, 130)
            self.assertEqual(self.days(shell, self.now + 30), {'2026-10-10': (4096, 1024)})
            self.assertEqual(self.ledger(), before)

    def test_a_reboot_counts_the_new_counters_once(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 1000, 100, 100, self.now)
            self.sample(shell, 9000, 900, 160, self.now + 60)      # 8000/800 in the first boot
            # a reboot: the live ledger is gone with /run, the disk copy is that of the last save
            subprocess.run(['rm', '-rf', str(self.root / 'run/mu300/traffic')])
            self.sample(shell, 500, 50, 40, self.now + 600, boot='bbbb-2', idx=9)
            self.sample(shell, 700, 70, 100, self.now + 660, boot='bbbb-2', idx=9)
            self.assertEqual(self.days(shell, self.now + 660), {'2026-10-10': (8000 + 700, 800 + 70)})

    def test_a_recreated_interface_or_a_lower_counter_starts_over(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 10_000, 1000, 100, self.now)
            self.sample(shell, 300, 30, 160, self.now + 60, idx=12)    # re-created: a new ifindex, new counters
            self.sample(shell, 50, 40, 220, self.now + 120, idx=12)    # lower rx: reset; tx went on (+10)
            self.assertEqual(self.days(shell, self.now + 120), {'2026-10-10': (350, 40)})

    def test_another_interface_is_only_a_base(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 100, 10, 100, self.now)
            self.sample(shell, 200, 20, 160, self.now + 60)
            self.set(shell, 'device', 'wwan0')
            self.sample(shell, 7_000_000, 7_000, 220, self.now + 120, dev='wwan0')    # its history: not counted
            self.sample(shell, 7_000_100, 7_010, 280, self.now + 180, dev='wwan0')
            self.assertEqual(self.days(shell, self.now + 180), {'2026-10-10': (200, 20)})

    def test_no_interface_counts_nothing_and_keeps_the_base(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 100, 10, 100, self.now)
            self.no_interface()
            self.run_tool(shell, 'save', now=self.now + 60)
            self.assertIn('base aaaa-1 7 sipa_eth0 100 10 100', self.ledger())
            v = self.view(shell, self.now + 60)
            self.assertEqual(v['available'], 0)
            self.sample(shell, 160, 20, 160, self.now + 120)
            self.assertEqual(self.days(shell, self.now + 120), {'2026-10-10': (60, 10)})


class LiveDevice(TrafficBase):
    """DEVICE=auto (the default; issue #369): the interface mobile data uses now - netifd's WAN device on OpenWrt,
    else the sipa_eth that is up (sipa_eth8 with the internal SIM), else the one counted last."""

    def oper(self, dev, state):
        d = self.root / 'sys/class/net' / dev
        d.mkdir(parents=True, exist_ok=True)
        (d / 'operstate').write_text(state + '\n')

    def setUp(self):
        super().setUp()
        self.stub('mu300-sim', 'echo 0')

    def test_the_internal_sims_bearer_is_counted(self):
        for shell in self.each_shell():
            self.fresh()
            self.counters(0, 0, 50, dev='sipa_eth0', idx=5)
            self.oper('sipa_eth0', 'down')
            self.oper('sipa_eth8', 'up')
            self.sample(shell, 1000, 100, 100, self.now, dev='sipa_eth8', idx=9)
            self.sample(shell, 6000, 600, 160, self.now + 60, dev='sipa_eth8', idx=9)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['device'], v['available']), ('sipa_eth8', 1))
            self.assertEqual(self.days(shell, self.now + 60), {'2026-10-10': (5000, 500)})

    def test_the_old_default_in_the_file_means_auto(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '50G')       # writes every setting, DEVICE included
            self.store.joinpath('conf').write_text(
                self.store.joinpath('conf').read_text().replace('DEVICE=auto', 'DEVICE=sipa_eth0'))
            self.oper('sipa_eth8', 'up')
            self.sample(shell, 1000, 100, 100, self.now, dev='sipa_eth8', idx=9)
            self.assertEqual(self.view(shell, self.now)['device'], 'sipa_eth8')
            self.set(shell, 'device', 'auto')
            self.assertIn('DEVICE=auto', self.store.joinpath('conf').read_text())

    def test_an_explicit_device_wins(self):
        for shell in self.each_shell():
            self.fresh()
            self.oper('sipa_eth8', 'up')
            self.set(shell, 'device', 'wwan0')
            self.sample(shell, 1000, 100, 100, self.now, dev='wwan0')
            self.assertEqual(self.view(shell, self.now)['device'], 'wwan0')

    def test_data_down_for_a_moment_keeps_the_device_counted_last(self):
        for shell in self.each_shell():
            self.fresh()
            self.oper('sipa_eth8', 'up')
            self.sample(shell, 1000, 100, 100, self.now, dev='sipa_eth8', idx=9)
            self.oper('sipa_eth8', 'down')                  # no sipa_eth is up now
            self.sample(shell, 3000, 300, 160, self.now + 60, dev='sipa_eth8', idx=9)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['device'], v['available']), ('sipa_eth8', 0))
            self.oper('sipa_eth8', 'up')
            self.sample(shell, 4000, 400, 220, self.now + 120, dev='sipa_eth8', idx=9)
            self.assertEqual(self.days(shell, self.now + 120), {'2026-10-10': (3000, 300)})

    def test_nothing_known_falls_back_to_the_active_slots_bearer(self):
        for shell in self.each_shell():
            self.fresh()
            self.stub('mu300-sim', 'echo 1')
            self.assertEqual(self.view(shell, self.now)['device'], 'sipa_eth8')

    def test_openwrt_follows_netifds_wan_device(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'etc').mkdir(exist_ok=True)
            (self.root / 'etc/openwrt_release').write_text("DISTRIB_ID='OpenWrt'\n")
            self.stub('uci', 'exit 1')
            self.stub('ubus', 'echo "$*" >> "$STUBLOG/ubus"; printf \'{\\n\\t"up": true,\\n\\t"l3_device": "sipa_eth9",\\n\\t"device": "sipa_eth9"\\n}\\n\'')
            self.oper('sipa_eth0', 'up')                    # up, but not the WAN's
            self.sample(shell, 1000, 100, 100, self.now, dev='sipa_eth9', idx=11)
            self.assertEqual(self.view(shell, self.now)['device'], 'sipa_eth9')
            self.assertIn('call network.interface.wan status', (self.tmp / 'ubus').read_text())


class Days(TrafficBase):
    def test_an_interval_over_midnight_is_split_by_time(self):
        for shell in self.each_shell():
            self.fresh()
            mid = at(2026, 10, 11)
            self.sample(shell, 0, 0, 1000, mid - 30)
            self.sample(shell, 6001, 3001, 1090, mid + 60)      # 90 s: 30 before midnight, 60 after
            d = self.days(shell, mid + 60)
            self.assertEqual(d, {'2026-10-10': (2000, 1000), '2026-10-11': (4001, 2001)})

    def test_midnight_is_local(self):
        for shell in self.each_shell():
            self.fresh()
            t = at(2026, 10, 11, 1, 0, 0)      # 01:00 at +3 is 22:00 UTC the day before
            self.sample(shell, 0, 0, 100, t - 60)
            self.sample(shell, 100, 0, 160, t)
            self.assertEqual(self.days(shell, t), {'2026-10-11': (100, 0)})
            self.fresh()
            self.sample(shell, 0, 0, 100, t - 60, off=0)
            self.sample(shell, 100, 0, 160, t, off=0)
            self.assertEqual(self.days(shell, t, off=0), {'2026-10-10': (100, 0)})

    def test_a_clock_jump_does_not_stretch_the_interval(self):
        for shell in self.each_shell():
            self.fresh()
            # NTP steps the clock forward two days between two readings 60 s of uptime apart: the 60 s end now
            t = at(2026, 10, 10, 23, 0)
            self.sample(shell, 0, 0, 1000, t)
            self.sample(shell, 6000, 0, 1060, t + 2 * 86400)
            self.assertEqual(self.days(shell, t + 2 * 86400), {'2026-10-12': (6000, 0)})
            # and back by a day: still the last 60 s, on the day the clock says now
            self.sample(shell, 6600, 0, 1120, t + 86400 + 60)
            self.assertEqual(self.days(shell, t + 2 * 86400), {'2026-10-11': (600, 0), '2026-10-12': (6000, 0)})

    def test_a_dst_change_keeps_every_byte_on_its_local_day(self):
        for shell in self.each_shell():
            self.fresh()
            # 2026-10-25 03:00 +03 back to 02:00 +02 (a European-style change, offsets given as the clock has them)
            t = at(2026, 10, 25, 2, 59, 0, off=3)
            self.sample(shell, 0, 0, 1000, t, off=10800)
            self.sample(shell, 1000, 0, 1120, t + 120, off=7200)
            mid = at(2026, 10, 26, 0, 0, 0, off=2)
            self.sample(shell, 1500, 0, 1120 + (mid - t - 120) + 60, mid + 60, off=7200)
            d = self.days(shell, mid + 60, off=7200)
            self.assertEqual(sum(rx for rx, _ in d.values()), 1500)
            self.assertEqual(sorted(d), ['2026-10-25', '2026-10-26'])

    def test_pending_bytes_wait_for_ntp_and_are_dated_by_uptime(self):
        for shell in self.each_shell():
            self.fresh()
            self.synced(False)
            # the clock says 2025 after the boot (sysfixtime); real time is 23:50 on 2026-10-10
            wrong = at(2025, 1, 1)
            self.sample(shell, 0, 0, 30, wrong)
            self.sample(shell, 4000, 400, 90, wrong + 60)      # uptime 30..90: 23:50:30..23:51:30 real
            v = self.view(shell, wrong + 60)
            self.assertEqual((v['clock'], v['days'], v['pending']), (0, [], {'rx': 4000, 'tx': 400}))
            self.assertEqual(v['cycle']['used'], 4400)        # counted at once towards the cycle and the cap
            # NTP at uptime 1290 (20 min later): 00:10:30 real
            self.synced(True)
            real = at(2026, 10, 10, 23, 50) + 1260
            self.sample(shell, 4500, 450, 1290, real)
            d = self.days(shell, real)
            self.assertEqual(sum(rx for rx, _ in d.values()), 4500)
            self.assertEqual(d['2026-10-10'][0] + d.get('2026-10-11', (0, 0))[0], 4500)
            self.assertNotIn('2025-01-01', d)
            self.assertEqual(self.view(shell, real)['pending'], {'rx': 0, 'tx': 0})
            self.assertNotIn('\np ', self.ledger())

    def test_pending_bytes_of_an_earlier_boot_go_to_the_day_ntp_comes(self):
        for shell in self.each_shell():
            self.fresh()
            self.synced(False)
            self.sample(shell, 0, 0, 30, at(2025, 1, 1))
            self.sample(shell, 900, 0, 90, at(2025, 1, 1) + 60)
            subprocess.run(['rm', '-rf', str(self.root / 'run/mu300/traffic')])
            self.synced(True)
            self.sample(shell, 100, 0, 50, self.now, boot='bbbb-2', idx=8)
            self.assertEqual(self.days(shell), {'2026-10-10': (1000, 0)})

    def test_six_hours_without_ntp_trusts_the_clock(self):
        for shell in self.each_shell():
            self.fresh()
            self.synced(False)
            self.sample(shell, 0, 0, 21000, self.now)
            self.sample(shell, 10, 0, 21700, self.now + 700)
            self.assertEqual(self.days(shell, self.now + 700), {'2026-10-10': (10, 0)})

    def test_days_are_kept_for_800_days(self):
        for shell in self.each_shell():
            self.fresh()
            old = ''.join(f'd 2024-0{m}-01 {m} 0\n' for m in range(1, 8))
            self.store.mkdir(parents=True)
            (self.store / 'ledger').write_text('mu300-traffic 1\nbase aaaa-1 7 sipa_eth0 0 0 100\n' + old)
            self.sample(shell, 1, 0, 160, self.now)     # 2026-10-10: 800 days back is 2024-08-01
            self.assertNotIn('2024-07-01', self.ledger())
            self.assertNotIn('d 2024-01-01', self.ledger())

    def test_a_damaged_ledger_line_is_dropped(self):
        for shell in self.each_shell():
            self.fresh()
            self.store.mkdir(parents=True)
            (self.store / 'ledger').write_text('mu300-traffic 1\nbase aaaa-1 7 sipa_eth0 0 0 100\n'
                                               'd 2026-10-09 12 x\nd 2026-10-08 5 5\ngarbage\n')
            self.sample(shell, 1, 0, 160, self.now)
            self.assertEqual(self.days(shell), {'2026-10-08': (5, 5), '2026-10-10': (1, 0)})


class Cycle(TrafficBase):
    def cyc(self, shell, now, reset):
        self.set(shell, 'reset-day', str(reset))
        c = self.view(shell, now)['cycle']
        return c['start'], c['last'], c['days_left']

    def test_reset_day(self):
        for shell in self.each_shell():
            self.fresh()
            self.counters(0, 0, 100)
            self.assertEqual(self.cyc(shell, at(2026, 10, 10, 12), 1), ('2026-10-01', '2026-10-31', 22))
            self.assertEqual(self.cyc(shell, at(2026, 10, 10, 12), 15), ('2026-09-15', '2026-10-14', 5))
            self.assertEqual(self.cyc(shell, at(2026, 10, 15, 0, 0, 1), 15), ('2026-10-15', '2026-11-14', 31))
            # 31: the month's last day
            self.assertEqual(self.cyc(shell, at(2027, 2, 28, 9), 31), ('2027-02-28', '2027-03-30', 31))
            self.assertEqual(self.cyc(shell, at(2027, 2, 27, 9), 31), ('2027-01-31', '2027-02-27', 1))
            self.assertEqual(self.cyc(shell, at(2028, 2, 29, 9), 30), ('2028-02-29', '2028-03-29', 30))
            self.assertEqual(self.cyc(shell, at(2026, 12, 31, 23, 59), 1), ('2026-12-01', '2026-12-31', 1))

    def test_cycles_sum_their_days(self):
        for shell in self.each_shell():
            self.fresh()
            self.store.mkdir(parents=True)
            (self.store / 'ledger').write_text('mu300-traffic 1\nbase aaaa-1 7 sipa_eth0 0 0 100\n'
                                               'd 2026-08-20 1 0\nd 2026-09-14 2 0\nd 2026-09-15 4 0\n'
                                               'd 2026-10-09 8 0\n')
            self.counters(0, 0, 100)
            self.set(shell, 'reset-day', '15')
            cyc = self.view(shell)['cycles']
            self.assertEqual([(c['start'], c['last'], c['rx']) for c in cyc],
                             [('2026-09-15', '2026-10-14', 12), ('2026-08-15', '2026-09-14', 3)])
            text = self.run_tool(shell, 'cycles').stdout
            self.assertIn('2026-09-15 - 2026-10-14', text)

    def test_used_corrects_this_cycle_only(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 1 << 30, 0, 160, self.now + 60)
            self.run_tool(shell, 'used', '10G', now=self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual(v['cycle']['used'], 10 << 30)
            self.assertEqual(v['cycle']['adj'], 9 << 30)
            self.sample(shell, (1 << 30) + 100, 0, 220, self.now + 120)
            self.assertEqual(self.view(shell, self.now + 120)['cycle']['used'], (10 << 30) + 100)
            self.assertEqual(self.view(shell, at(2026, 11, 1, 12))['cycle']['used'], 0)    # next cycle

    def test_clear_forgets_and_keeps_counting(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 500, 0, 160, self.now + 60)
            self.assertNotEqual(self.run_tool(shell, 'clear', ok=False).returncode, 0)    # needs --yes
            self.counters(800, 0, 220)
            self.run_tool(shell, 'clear', '--yes', now=self.now + 120)
            self.assertEqual(self.days(shell, self.now + 120), {})
            self.sample(shell, 850, 0, 280, self.now + 180)
            self.assertEqual(self.days(shell, self.now + 180), {'2026-10-10': (50, 0)})

    def test_settings_are_checked(self):
        for shell in self.each_shell():
            self.fresh()
            for key, value in (('reset-day', '0'), ('reset-day', '32'), ('cap', '-1'), ('cap', '5X'),
                               ('warn', '101'), ('cut', 'yes'), ('device', '../x'), ('nope', '1')):
                self.assertNotEqual(self.run_tool(shell, 'set', key, value, ok=False).returncode, 0, (key, value))
            self.set(shell, 'cap', '1.5G')
            self.assertIn('CAP=1610612736\n', (self.store / 'conf').read_text())
            # a file edited by hand with nonsense: the defaults
            (self.store / 'conf').write_text('RESET_DAY=$(reboot)\nCAP=12abc\nWARN=0\n')
            self.counters(0, 0, 100)
            v = self.view(shell)
            self.assertEqual((v['reset_day'], v['cap']['bytes'], v['cap']['warn']), (1, 0, 90))


class CapBase(TrafficBase):
    def setUp(self):
        super().setUp()
        (self.root / 'etc').mkdir()
        (self.root / 'etc/openwrt_release').write_text("DISTRIB_ID='OpenWrt'\n")

    def calls(self):
        p = self.tmp / 'calls'
        time.sleep(0.2)     # the cut runs in the background
        return p.read_text().splitlines() if p.exists() else []

    def log(self):
        p = self.tmp / 'log'
        return p.read_text() if p.exists() else ''

    def round(self, shell, rx, up, now=None, **kw):
        """one round of the service (run's round, through `save`, which acts the same way)"""
        self.counters(rx, 0, up, **kw)
        return self.run_tool(shell, 'save', now=now or self.now + up)


class Cap(CapBase):
    def test_warning_and_cut_once(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'cap', '1000')
            self.set(shell, 'warn', '80')
            self.set(shell, 'cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 850, 160)
            self.assertEqual(self.view(shell, self.now + 160)['cap']['level'], 'warn')
            self.assertIn('80% of the monthly cap', self.log())
            self.assertEqual(self.calls(), [])
            self.round(shell, 1000, 220)
            v = self.view(shell, self.now + 220)
            self.assertEqual((v['cap']['level'], v['cap']['cut_active']), ('over', 1))
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.assertIn('monthly cap is reached', self.log())
            # mobile-data down marks it; the next rounds do nothing more
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 1010, 280)
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.assertEqual(self.log().count('the monthly cap is reached ('), 1)

    def test_turned_back_on_by_hand_it_stays_on_until_a_reboot(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'cap', '1000')
            self.set(shell, 'cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)
            self.assertEqual(self.calls(), ['ifdown wan'])
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 2000, 220)
            (self.root / 'run/mu300-mobile-data-down').unlink()     # the user: data up
            self.round(shell, 2100, 280)
            self.round(shell, 2200, 340)
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.assertEqual(self.view(shell, self.now + 340)['cap']['cut_active'], 0)

    def test_a_reboot_cuts_again_and_the_next_cycle_restores(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'cap', '1000')
            self.set(shell, 'cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)
            subprocess.run(['rm', '-rf', str(self.root / 'run/mu300/traffic')])
            self.round(shell, 10, 30, now=self.now + 600, boot='bbbb-2', idx=9)    # netifd dialled at boot
            self.assertEqual(self.calls(), ['ifdown wan', 'ifdown wan'])
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 10, 90, now=at(2026, 11, 1, 0, 1), boot='bbbb-2', idx=9)
            self.assertEqual(self.calls(), ['ifdown wan', 'ifdown wan', 'ifup wan'])
            self.assertIn('back on', self.log())

    def test_raising_the_cap_or_cut_off_restores(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'cap', '1000')
            self.set(shell, 'cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.set(shell, 'cap', '1G')
            self.round(shell, 2000, 220)
            self.assertEqual(self.calls(), ['ifdown wan', 'ifup wan'])

    def test_without_cut_nothing_is_turned_off(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '1000')
            self.round(shell, 0, 100)
            self.round(shell, 5000, 160)
            self.assertEqual(self.view(shell, self.now + 160)['cap']['level'], 'over')
            self.assertEqual(self.calls(), [])

    def test_ubuntu_stops_the_service(self):
        (self.root / 'etc/openwrt_release').unlink()
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'cap', '1000')
            self.set(shell, 'cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)
            self.assertEqual(self.calls(), ['systemctl stop mu300-mobile-data.service'])

    def test_text_view(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '50G')
            self.round(shell, 0, 100)
            self.round(shell, 3 << 30, 160)
            out = self.run_tool(shell, now=self.now + 160).stdout
            self.assertIn('today         2026-10-10  down 3.0 GB, up 0 B', out)
            self.assertIn('this cycle    2026-10-01 - 2026-10-31  3.0 GB used of 50.0 GB (6%), 47.0 GB left, 22 days left', out)
            self.assertIn('2026-10-10  down    3.0 GB', self.run_tool(shell, 'days', now=self.now + 160).stdout)


class Plan(CapBase):
    """the daily quota (its own warning and cut, until midnight), the count mode and the plan's name"""

    def test_defaults_are_unchanged(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 900, 100, 160, self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['plan'], v['count'], v['cycle']['used']), ('', 'total', 1000))
            self.assertEqual(v['daily'], {'bytes': 0, 'used': 1000, 'cut': 0, 'level': 'none', 'cut_active': 0})
            self.assertNotIn('dalert', self.ledger())
            out = self.run_tool(shell, now=self.now + 60).stdout
            self.assertNotIn('daily quota', out)
            self.assertNotIn('plan ', out)

    def test_daily_quota_warns_cuts_and_comes_back_at_midnight(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'daily', '1000')
            self.set(shell, 'warn', '80')
            self.round(shell, 0, 100)
            self.round(shell, 850, 160)
            self.assertIn('80% of the daily quota is used', self.log())
            self.round(shell, 1200, 220)
            v = self.view(shell, self.now + 220)
            self.assertEqual((v['daily']['level'], v['daily']['cut_active'], v['cap']['level']), ('over', 0, 'none'))
            self.assertEqual(self.calls(), [])            # daily-cut is off by default: a warning only
            self.assertIn('the daily quota is reached', self.log())
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'daily', '1000')
            self.set(shell, 'daily-cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 1200, 160)
            self.assertEqual(self.view(shell, self.now + 160)['daily']['cut_active'], 1)
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.assertIn('daily quota until midnight', self.log())
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 1300, 220)
            self.assertEqual(self.calls(), ['ifdown wan'])
            # the next day: back on
            self.round(shell, 1300, 280, now=at(2026, 10, 11, 0, 5))
            self.assertEqual(self.calls(), ['ifdown wan', 'ifup wan'])

    def test_back_on_only_when_neither_limit_holds_it(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'daily', '1000')
            self.set(shell, 'daily-cut', 'on')
            self.set(shell, 'cap', '1500')
            self.set(shell, 'cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)              # both reached: one ifdown
            self.assertEqual(self.calls(), ['ifdown wan'])
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 2000, 220, now=at(2026, 10, 11, 0, 5))    # the day is over, the cycle is not
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.set(shell, 'cut', 'off')
            self.round(shell, 2000, 280, now=at(2026, 10, 11, 0, 6))
            self.assertEqual(self.calls(), ['ifdown wan', 'ifup wan'])

    def test_count_mode(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '1000')
            self.round(shell, 0, 100)
            self.round(shell, 700, 160)
            self.counters(700, 600, 220)
            self.run_tool(shell, 'save', now=self.now + 220)
            self.assertEqual(self.view(shell, self.now + 220)['cap']['level'], 'over')
            self.set(shell, 'count', 'rx')
            v = self.view(shell, self.now + 220)
            self.assertEqual((v['count'], v['cycle']['used'], v['cap']['level'], v['cycle']['rx'], v['cycle']['tx']),
                             ('rx', 700, 'ok', 700, 600))
            self.assertEqual(v['cycles'][0]['used'], 700)
            self.set(shell, 'count', 'tx')
            self.assertEqual(self.view(shell, self.now + 220)['daily']['used'], 600)
            # a correction belongs to its mode
            self.run_tool(shell, 'used', '5000', now=self.now + 220)
            self.assertEqual(self.view(shell, self.now + 220)['cycle']['used'], 5000)
            self.assertIn('adj 2026-10-01 4400 tx', self.ledger())
            self.assertIn('counted       uploads only', self.run_tool(shell, now=self.now + 220).stdout)
            self.set(shell, 'count', 'total')
            self.assertEqual(self.view(shell, self.now + 220)['cycle']['used'], 1300)
            self.assertNotEqual(self.run_tool(shell, 'set', 'count', 'both', ok=False).returncode, 0)

    def test_plan_name(self):
        for shell in self.each_shell():
            self.fresh()
            self.counters(0, 0, 100)
            name = 'Turkcell 50GB "gece" \\ \u6708\u5957\u9910'
            self.set(shell, 'plan', name)
            self.assertEqual(self.view(shell)['plan'], name)
            self.assertIn('plan          ' + name, self.run_tool(shell).stdout)
            for bad in ('a\nb', 'x' * 97, 'tab\there'):
                self.assertNotEqual(self.run_tool(shell, 'set', 'plan', bad, ok=False).returncode, 0, bad)
            self.assertEqual(self.view(shell)['plan'], name)
            self.set(shell, 'plan', '')
            self.assertEqual(self.view(shell)['plan'], '')
            # a file edited by hand: a control character is refused, the name is none
            conf = (self.store / 'conf').read_text().replace('PLAN=\n', 'PLAN=x\x1b[2Jy\n')
            (self.store / 'conf').write_text(conf)
            self.assertEqual(self.view(shell)['plan'], '')


class Service(TrafficBase):
    def start(self, shell, **env):
        e = self.env(MU300_SYSROOT=self.root, MU300_TRAFFIC_NOW=self.now, MU300_TRAFFIC_TZOFF=self.off, **env)
        return subprocess.Popen(shell + [str(TOOL), 'run'], env=e, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)

    def wait_for(self, cond, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.1)
        return False

    def test_a_stop_saves_at_once_and_the_disk_is_written_rarely(self):
        for shell in self.each_shell():
            self.fresh()
            self.counters(1000, 100, 100)
            self.store.mkdir(parents=True)
            (self.store / 'conf').write_text('INTERVAL=10\nCHECKPOINT=1800\n')
            p = self.start(shell)
            try:
                live = self.root / 'run/mu300/traffic/ledger'
                self.assertTrue(self.wait_for(lambda: (self.store / 'ledger').exists()))
                first = (self.store / 'ledger').read_text()
                self.counters(5000, 500, 200)
                time.sleep(0.5)
                p.send_signal(signal.SIGTERM)
                _, err = p.communicate(timeout=5)
            finally:
                if p.poll() is None:
                    p.kill()
                    p.communicate()
            self.assertEqual(p.returncode, 0, err)
            self.assertIn('base aaaa-1 7 sipa_eth0 1000 100 100', first)
            self.assertIn('d 2026-10-10 4000 400', (self.store / 'ledger').read_text())
            self.assertEqual(live.read_text(), (self.store / 'ledger').read_text())
            self.assertFalse((self.root / 'run/mu300/traffic/pid').exists())

    def test_one_service_at_a_time(self):
        for shell in self.each_shell():
            self.fresh()
            self.counters(0, 0, 100)
            (self.root / 'run/mu300/traffic').mkdir(parents=True)
            (self.root / 'run/mu300/traffic/pid').write_text(f'{os.getpid()}\n')
            r = self.run_tool(shell, 'run', ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('already running', r.stderr)

    def test_a_stale_lock_is_taken_over(self):
        for shell in self.each_shell():
            self.fresh()
            self.counters(0, 0, 100)
            lock = self.root / 'run/mu300/traffic/lock'
            lock.mkdir(parents=True)
            (lock / 'pid').write_text('999999\n')
            self.run_tool(shell, 'save')
            self.assertFalse(lock.exists())

    def test_the_summary_is_for_the_dashboard(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '1000')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 950, 0, 160, self.now + 60)
            s = (self.root / 'run/mu300/traffic/summary').read_text()
            for line in ('level=warn', 'used=950', 'cap=1000', 'today_rx=950', 'clock=1', 'cycle_start=2026-10-01',
                         'remaining=50', 'yearly=0', 'yearly_level=none', 'yearly_used=950', 'yearly_remaining=0',
                         'yearly_cut=0'):
                self.assertIn(line + '\n', s)


class Json(TrafficBase):
    def test_json_is_valid_with_nothing_counted(self):
        for shell in self.each_shell():
            self.fresh()
            self.no_interface()
            (self.root / 'proc/sys/kernel/random/boot_id').write_text('aaaa-1\n')
            (self.root / 'proc/uptime').write_text('5.00 1.00\n')
            v = self.view(shell)
            self.assertEqual((v['available'], v['days'], v['cap']['level'], v['since']), (0, [], 'none', None))
            self.assertEqual(len(v['cycles']), 1)

    def test_store_falls_back_to_etc_without_the_linux_disk(self):
        for shell in self.each_shell():
            self.fresh()
            subprocess.run(['rm', '-rf', str(self.root / 'mnt')])
            self.sample(shell, 0, 0, 100, self.now)
            self.assertTrue((self.root / 'etc/mu300/traffic/ledger').exists())
            (self.root / 'mnt/mu300-disk/.mu300').mkdir(parents=True)


class Remaining(TrafficBase):
    """the remaining shown by the operator: cap.remaining (cap - used) and the correction the other way around
    (used = cap - remaining), in the count mode it was made in, as "used" is"""

    def test_remaining_is_the_cap_less_used(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 200, 160, self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['cap']['bytes'], v['cap']['remaining']), (0, 0))
            self.set(shell, 'cap', '1000')
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['cycle']['used'], v['cap']['remaining']), (500, 500))
            self.sample(shell, 1300, 200, 220, self.now + 120)
            self.assertEqual(self.view(shell, self.now + 120)['cap']['remaining'], -500)   # over the cap: negative

    def test_used_remaining_corrects_the_cycle(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '1000')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 200, 160, self.now + 60)
            self.run_tool(shell, 'set', 'used-remaining', '600', now=self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['cycle']['used'], v['cycle']['adj']), (400, -100))    # used = 1000 - 600
            self.assertIn('adj 2026-10-01 -100\n', self.ledger())
            # the correction belongs to the count mode it was made in, as "used" does
            self.set(shell, 'count', 'tx')
            self.assertEqual(self.view(shell, self.now + 60)['cycle']['used'], 200)
            self.run_tool(shell, 'set', 'used-remaining', '700', now=self.now + 60)
            self.assertEqual(self.view(shell, self.now + 60)['cycle']['used'], 300)    # used = 1000 - 700
            self.assertIn('adj 2026-10-01 100 tx\n', self.ledger())
            self.set(shell, 'count', 'total')
            self.assertEqual(self.view(shell, self.now + 60)['cycle']['used'], 500)    # the tx correction is gone

    def test_refused_without_a_cap_and_for_a_remaining_over_the_cap(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            r = self.run_tool(shell, 'set', 'used-remaining', '100', ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('no cap is set', r.stderr)
            self.set(shell, 'cap', '1000')
            r = self.run_tool(shell, 'set', 'used-remaining', '2000', ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('more than the cap', r.stderr)
            self.assertEqual(self.view(shell)['cycle']['adj'], 0)     # nothing was written
            self.assertNotEqual(self.run_tool(shell, 'set', 'used-remaining', '1.5G', ok=False).returncode, 0)

    def test_the_used_correction_and_the_yearly_one_are_separate(self):
        # used corrects the cycle only; yearly-used corrects the year only (the operator shows the two apart)
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'cap', '1000')
            self.set(shell, 'yearly', '2000')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 0, 160, self.now + 60)
            self.run_tool(shell, 'used', '500', now=self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['cycle']['used'], v['yearly']['used']), (500, 300))
            self.run_tool(shell, 'yearly-used', '800', now=self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['cycle']['used'], v['yearly']['used']), (500, 800))


class Yearly(CapBase):
    """the yearly plan: the same count as the monthly cap for one billing year (yearly-start MM-DD), its own warning
    percentage and cut, off by default - and no ledger line of its own unless it is set"""

    def test_off_by_default_and_no_ledger_line_of_its_own(self):
        for shell in self.each_shell():
            self.fresh()
            self.round(shell, 0, 100)
            self.round(shell, 900, 160)
            v = self.view(shell, self.now + 160)
            self.assertEqual(v['yearly'], {'start_day': '01-01', 'start': '2026-01-01', 'last': '2026-12-31',
                                           'days_left': 83, 'bytes': 0, 'used': 900, 'remaining': 0, 'cut': 0,
                                           'level': 'none', 'cut_active': 0})
            for line in ('yadj ', 'ycut ', 'yalert '):
                self.assertNotIn('\n' + line, self.ledger())
            self.assertIn('yearly        none', self.run_tool(shell, now=self.now + 160).stdout)
            self.assertEqual(v['cap']['remaining'], 0)

    def test_warning_and_cut_once(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'yearly', '1000')
            self.set(shell, 'warn', '80')
            self.set(shell, 'yearly-cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 850, 160)
            v = self.view(shell, self.now + 160)
            self.assertEqual((v['yearly']['level'], v['yearly']['remaining'], v['yearly']['cut']), ('warn', 150, 1))
            self.assertIn('80% of the yearly cap', self.log())
            self.assertEqual(self.calls(), [])
            self.round(shell, 1000, 220)
            v = self.view(shell, self.now + 220)
            self.assertEqual((v['yearly']['level'], v['yearly']['remaining'], v['yearly']['cut_active']), ('over', 0, 1))
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.assertIn('the yearly cap is reached', self.log())
            # mobile-data down marks it: a further round cuts nothing more and does not warn again
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 1010, 280)
            self.assertEqual(self.calls(), ['ifdown wan'])
            self.assertEqual(self.log().count('the yearly cap is reached ('), 1)
            self.assertIn('\nycut ', self.ledger())
            self.assertIn('\nyalert 2026-01-01 over', self.ledger())

    def test_a_reboot_cuts_again_and_the_next_year_restores(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'yearly', '1000')
            self.set(shell, 'yearly-cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)
            subprocess.run(['rm', '-rf', str(self.root / 'run/mu300/traffic')])
            self.round(shell, 10, 30, now=self.now + 600, boot='bbbb-2', idx=9)
            self.assertEqual(self.calls(), ['ifdown wan', 'ifdown wan'])
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.round(shell, 10, 90, now=at(2027, 1, 1, 0, 1), boot='bbbb-2', idx=9)
            self.assertEqual(self.calls(), ['ifdown wan', 'ifdown wan', 'ifup wan'])
            self.assertIn('back on', self.log())
            self.assertEqual(self.view(shell, at(2027, 1, 1, 0, 1))['yearly']['cut_active'], 0)

    def test_raising_the_yearly_cap_or_cut_off_restores(self):
        for shell in self.each_shell():
            self.fresh()
            (self.root / 'run/mu300-mobile-data-down').unlink(missing_ok=True)
            self.set(shell, 'yearly', '1000')
            self.set(shell, 'yearly-cut', 'on')
            self.round(shell, 0, 100)
            self.round(shell, 2000, 160)
            (self.root / 'run/mu300-mobile-data-down').write_text('')
            self.set(shell, 'yearly', '1G')       # 1073741824 bytes: well over what was counted
            self.round(shell, 2000, 220)
            self.assertEqual(self.calls(), ['ifdown wan', 'ifup wan'])
            self.set(shell, 'yearly-cut', 'off')
            self.assertEqual(self.view(shell, self.now + 220)['yearly']['cut'], 0)

    def test_anniversary_rolls_over(self):
        for shell in self.each_shell():
            self.fresh()
            self.store.mkdir(parents=True)
            (self.store / 'ledger').write_text('mu300-traffic 1\nbase aaaa-1 7 sipa_eth0 0 0 100\n'
                                              'd 2026-09-30 100 0\nd 2026-10-01 200 0\n'
                                              'd 2027-09-30 300 0\nd 2027-10-01 400 0\n')
            self.counters(0, 0, 100)
            self.set(shell, 'yearly-start', '10-01')
            self.set(shell, 'yearly', '1000')
            v = self.view(shell, at(2027, 9, 30, 12))
            self.assertEqual((v['yearly']['start_day'], v['yearly']['used'], v['yearly']['remaining']), ('10-01', 500, 500))
            self.assertEqual((v['yearly']['start'], v['yearly']['last'], v['yearly']['days_left']),
                             ('2026-10-01', '2027-09-30', 1))
            # the correction of a year ends with it
            self.run_tool(shell, 'yearly-used', '700', now=at(2027, 9, 30, 12))
            self.assertEqual(self.view(shell, at(2027, 9, 30, 12))['yearly']['used'], 700)
            v = self.view(shell, at(2027, 10, 1, 12))
            self.assertEqual((v['yearly']['used'], v['yearly']['remaining']), (400, 600))
            self.assertEqual((v['yearly']['start'], v['yearly']['last']), ('2027-10-01', '2028-09-30'))
            self.assertEqual(v['cycle']['adj'], 0)

    def test_the_anniversary_of_29_february(self):
        for shell in self.each_shell():
            self.fresh()
            self.store.mkdir(parents=True)
            (self.store / 'ledger').write_text('mu300-traffic 1\nbase aaaa-1 7 sipa_eth0 0 0 100\n'
                                              'd 2027-02-27 100 0\nd 2027-02-28 200 0\n')
            self.counters(0, 0, 100)
            self.set(shell, 'yearly-start', '02-29')
            self.set(shell, 'yearly', '1000')
            # 2027 has no 29 February: the billing year that starts in 2027 starts on 28 February
            v = self.view(shell, at(2027, 3, 1, 12))['yearly']
            self.assertEqual((v['used'], v['start'], v['last']), (200, '2027-02-28', '2028-02-28'))
            v = self.view(shell, at(2028, 2, 28, 12))['yearly']
            self.assertEqual((v['used'], v['start']), (200, '2027-02-28'))
            v = self.view(shell, at(2028, 2, 29, 12))['yearly']
            self.assertEqual((v['used'], v['start'], v['last']), (0, '2028-02-29', '2029-02-27'))

    def test_yearly_used_corrects_the_year(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'yearly', '2000')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 0, 160, self.now + 60)
            self.run_tool(shell, 'yearly-used', '800', now=self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['yearly']['used'], v['yearly']['remaining']), (800, 1200))
            self.assertIn('yadj 2026-01-01 500\n', self.ledger())
            r = self.run_tool(shell, 'yearly-used', 'nope', ok=False)
            self.assertNotEqual(r.returncode, 0)

    def test_yearly_used_remaining_corrects_the_year(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'yearly', '2000')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 0, 160, self.now + 60)
            self.run_tool(shell, 'set', 'yearly-used-remaining', '1000', now=self.now + 60)
            v = self.view(shell, self.now + 60)
            self.assertEqual((v['yearly']['used'], v['yearly']['remaining']), (1000, 1000))
            self.assertIn('yadj 2026-01-01 700\n', self.ledger())
            # a remaining over the yearly cap is refused, and writes nothing
            r = self.run_tool(shell, 'set', 'yearly-used-remaining', '3000', ok=False)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('more than the yearly cap', r.stderr)
            self.assertEqual(self.view(shell, self.now + 60)['yearly']['used'], 1000)

    def test_refused_without_a_yearly_cap(self):
        for shell in self.each_shell():
            self.fresh()
            self.sample(shell, 0, 0, 100, self.now)
            for args in (('yearly-used', '500'), ('set', 'yearly-used-remaining', '500')):
                r = self.run_tool(shell, *args, ok=False)
                self.assertNotEqual(r.returncode, 0, args)
                self.assertIn('no yearly cap is set', r.stderr, args)
            self.assertNotIn('\nyadj ', self.ledger())

    def test_yearly_count_mode(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'yearly', '1000')
            self.set(shell, 'count', 'rx')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 700, 600, 160, self.now + 60)
            self.assertEqual(self.view(shell, self.now + 60)['yearly']['used'], 700)
            self.run_tool(shell, 'yearly-used', '500', now=self.now + 60)
            self.assertEqual(self.view(shell, self.now + 60)['yearly']['used'], 500)
            self.assertIn('yadj 2026-01-01 -200 rx\n', self.ledger())
            self.set(shell, 'count', 'tx')
            self.assertEqual(self.view(shell, self.now + 60)['yearly']['used'], 600)   # the rx correction is gone
            self.set(shell, 'count', 'total')
            self.assertEqual(self.view(shell, self.now + 60)['yearly']['used'], 1300)

    def test_settings_are_checked(self):
        for shell in self.each_shell():
            self.fresh()
            for key, value in (('yearly', '-1'), ('yearly', '5X'), ('yearly-start', '13-01'), ('yearly-start', '02-30'),
                               ('yearly-start', '04-31'), ('yearly-start', '1-01'), ('yearly-start', '01-32'),
                               ('yearly-start', '02-29x'), ('yearly-cut', 'yes'), ('yearly-cut', '1')):
                self.assertNotEqual(self.run_tool(shell, 'set', key, value, ok=False).returncode, 0, (key, value))
            self.set(shell, 'yearly', '1.5T')
            self.assertIn('YEARLY=1649267441664\n', (self.store / 'conf').read_text())
            self.set(shell, 'yearly-start', '02-29')
            self.assertIn('YEARLY_START=02-29\n', (self.store / 'conf').read_text())
            self.set(shell, 'yearly-cut', 'on')
            self.assertIn('YEARLY_CUT=1\n', (self.store / 'conf').read_text())
            # a file edited by hand with a day no month has: the default
            (self.store / 'conf').write_text('YEARLY=0\nYEARLY_START=02-30\n')
            self.counters(0, 0, 100)
            self.assertEqual(self.view(shell)['yearly']['start_day'], '01-01')

    def test_old_conf_and_old_ledger_still_read(self):
        for shell in self.each_shell():
            self.fresh()
            self.store.mkdir(parents=True)
            (self.store / 'conf').write_text('RESET_DAY=1\nCAP=1000\nWARN=80\nCUT=0\nDAILY=0\nDAILY_CUT=0\n'
                                             'COUNT=total\nPLAN=\nDEVICE=auto\n')
            (self.store / 'ledger').write_text('mu300-traffic 1\nsince 1790000000\n'
                                               'base aaaa-1 7 sipa_eth0 0 0 100\nd 2026-10-01 500 0\n')
            self.counters(0, 0, 100)
            v = self.view(shell)
            self.assertEqual((v['cap']['bytes'], v['cap']['remaining'], v['yearly']['bytes']), (1000, 500, 0))
            self.assertEqual([d['date'] for d in v['days']], ['2026-10-01'])
            self.run_tool(shell, 'save')
            self.assertNotIn('\nyadj ', self.ledger())   # an old ledger is not given new lines for nothing

    def test_text_view(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'yearly', '1G')
            self.set(shell, 'yearly-start', '07-01')
            self.round(shell, 0, 100)
            self.round(shell, 1 << 30, 160)
            out = self.run_tool(shell, now=self.now + 160).stdout
            self.assertIn('this year     2026-07-01 - 2027-06-30  1.0 GB used of 1.0 GB (100%)', out)
            self.assertIn('yearly cap    1.0 GB, warning at 90%; at the yearly cap mobile data stays on', out)
            self.assertIn('the yearly cap is reached', out)

    def test_clear_forgets_the_yearly_correction(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'yearly', '2000')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 0, 160, self.now + 60)
            self.run_tool(shell, 'yearly-used', '800', now=self.now + 60)
            self.run_tool(shell, 'clear', '--yes', now=self.now + 60)
            self.assertNotIn('\nyadj ', self.ledger())
            self.assertEqual(self.view(shell, self.now + 60)['yearly']['used'], 0)


class YearlyOff(TrafficBase):
    """a yearly plan switched off again leaves no ledger line behind, and the year's count is the days'"""

    def test_off_drops_the_yearly_lines_and_keeps_counting(self):
        for shell in self.each_shell():
            self.fresh()
            self.set(shell, 'yearly', '1000')
            self.set(shell, 'yearly-cut', 'on')
            self.sample(shell, 0, 0, 100, self.now)
            self.sample(shell, 300, 0, 160, self.now + 60)
            self.sample(shell, 1000, 0, 220, self.now + 120)      # over the yearly cap: the cut is written
            self.assertIn('\nycut ', self.ledger())
            self.set(shell, 'yearly', 'off')
            self.sample(shell, 1100, 0, 280, self.now + 180)
            v = self.view(shell, self.now + 180)
            self.assertEqual((v['yearly']['bytes'], v['yearly']['cut'], v['yearly']['cut_active']), (0, 1, 0))
            self.assertEqual(v['yearly']['used'], 1100)           # the year still counts, it has no cap
            for line in ('yadj ', 'ycut ', 'yalert '):
                self.assertNotIn('\n' + line, self.ledger())



if __name__ == '__main__':
    unittest.main()
