// Run: TZ=UTC0 ucode -L openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem tests/traffic_core.uc
import * as c from 'traffic-core';
let checks = 0;
function check(value, label) { if (!value) die('FAIL: ' + label + '\n'); checks++; }
function stamp(y, m, d, h, min, sec) {
    return timelocal({ year:y, mon:m, mday:d, hour:h ?? 0, min:min ?? 0, sec:sec ?? 0, isdst:-1 });
}
function sample(rx, tx, boot, idx) { return { rx:rx, tx:tx, boot:boot || 'A', ifindex:idx || 3, device:'cell0' }; }
let now = stamp(2026, 10, 7), db = c.fresh(now);
c.advance(db, sample(1000, 500), now);
check(c.status(db, now).today_used == 0, 'activation baseline');
c.advance(db, sample(1100, 550), now + 10);
c.advance(db, sample(1100, 550), now + 20);
check(c.status(db, now + 20).today_used == 150, 'delta and duplicate sample');
c.advance(db, sample(5, 2), now + 30);
check(c.status(db, now + 30).today_used == 157, 'counter reset');
c.advance(db, null, now + 40);
c.advance(db, sample(10, 4), now + 50);
check(c.status(db, now + 50).today_used == 164, 'temporary missing device');
c.advance(db, sample(20, 10, 'B'), now + 60);
check(c.status(db, now + 60).today_used == 194, 'reboot current counters');
c.advance(db, sample(8, 3, 'B', 4), now + 70);
check(c.status(db, now + 70).today_used == 205, 'recreated device');
let cloned = json(sprintf('%J', db));
c.advance(cloned, sample(10, 4, 'B', 4), now + 80);
check(c.status(cloned, now + 80).today_used == 208, 'persistent round trip');

now = stamp(2026, 1, 31, 23, 59, 55); db = c.fresh(now);
c.advance(db, sample(0, 0), now);
c.advance(db, sample(1000, 200), now + 10);
check(db.days['2026-01-31'].rx == 500 && db.days['2026-02-01'].rx == 500, 'midnight split');
check(c.status(db, now + 10).month_used == 600, 'natural month rollover');
check(c.status(db, now + 10).cycle_used == 600, 'default cycle rollover');
let range = c.cycle(stamp(2026, 2, 28), 31);
check(range.start == '2026-02-28' && range.end == '2026-03-31', 'short month clamp');
range = c.cycle(stamp(2024, 2, 29), 31);
check(range.start == '2024-02-29' && range.end == '2024-03-31', 'leap year clamp');
range = c.cycle(stamp(2027, 1, 2), 15);
check(range.start == '2026-12-15' && range.end == '2027-01-15', 'cross-year cycle');

c.update_config(db, { monthly_gb:2, daily_gb:1, used_gb:1.5 }, now + 10);
check(c.status(db, now + 10).cycle_used == 1500000000, 'cycle usage calibration');
check(c.status(db, now + 10).today_used == 600, 'calibration does not corrupt day history');
check(c.status(db, now + 10).remaining == 500000000, 'decimal GB quota');
check(c.status(db, stamp(2026, 3, 1)).cycle_used == 0, 'calibration expires next cycle');
c.update_config(db, { count_mode:'rx', monthly_gb:0 }, now + 10);
check(c.status(db, now + 10).today_used == 500 && c.status(db, now + 10).remaining == null, 'direction and unlimited plan');
let rejected = false;
try { c.update_config(db, { reset_day:0 }, now); } catch (e) { rejected = true; }
check(rejected, 'invalid reset day rejected');
rejected = false;
try { c.update_config(db, { count_mode:'invalid' }, now); } catch (e) { rejected = true; }
check(rejected, 'invalid mode rejected');

db = c.fresh(0); c.advance(db, sample(0, 0), 0); c.advance(db, sample(300, 20), 10);
check(length(keys(db.days)) == 0 && db.pending_rx == 300, 'unsynced clock defers allocation');
c.advance(db, sample(400, 40), stamp(2026, 10, 7));
check(c.status(db, stamp(2026, 10, 7)).today_used == 440, 'NTP sync keeps pending bytes');
printf('traffic accounting: %d checks passed\n', checks);
