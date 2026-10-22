"""mu300-sysd (FINDINGS 208): the buttons, the LED tick and the thermal guard in one event-driven ucode daemon, and
its helper's uevent option (mu300-keys -u).

The daemon is held to the scripts it replaces by their own tests: test_device_scripts' Buttons (mu300-buttons) and
ThermalGuard (thermal-guard) run again with a stand-in for the shell they start the script with, which starts the
daemon instead - for the keys until its helper's output ends (MU300_SYSD_ONCE), for the guard one round (--round).
On top, what is new: the LED tick on events and on time instead of a look every 5 s (a uevent, the hint's due time,
the end of a key's wake; a 1 % step of the battery starts nothing), the thermal rounds on their own timer, the helper
started again, --check, the init scripts' choice between the daemon and the old loops, and mu300-keys -u itself
(built here with the machine's C compiler; Linux only).

Needs a ucode with the uloop, socket and fs modules (MU300_TEST_UCODE, e.g. /root/ucbuild/full/bin/ucode-run)."""
import os
import select
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import test_device_scripts as old
from helpers import BIN, TOP, ShellTest, ucode, ucode_paths

SYSD = BIN / 'mu300-sysd'
INIT = TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d'
KEYS_SRC = TOP / 'tools' / 'keys' / 'mu300-keys.c'
CC = shutil.which('gcc') or shutil.which('cc')
LINUX = sys.platform.startswith('linux')
KEYS = None
_build = None


def setUpModule():
    global KEYS, _build
    if not (CC and LINUX):
        return
    _build = tempfile.mkdtemp(prefix='mu300-keys-build-')
    out = Path(_build) / 'mu300-keys'
    r = subprocess.run([CC, '-O2', '-Wall', '-Wextra', '-Werror', '-o', str(out), str(KEYS_SRC)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('mu300-keys.c does not build without warnings:\n' + r.stderr)
    KEYS = out


def tearDownModule():
    if _build:
        shutil.rmtree(_build, ignore_errors=True)


def has_modules(u):
    code = "import * as a from 'uloop'; import * as b from 'socket'; import * as c from 'fs'; print('ok');"
    try:
        return subprocess.run(u + ['-e', code], capture_output=True, text=True, timeout=10).stdout == 'ok'
    except (OSError, subprocess.TimeoutExpired):
        return False


UCODE = ucode()
OK = bool(UCODE and has_modules(UCODE))
NEEDS = 'a ucode with uloop, socket and fs is needed (MU300_TEST_UCODE)'


def sysd_argv():
    return UCODE + ucode_paths() + [str(SYSD)]


def wait_for(pred, timeout=8.0, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    return pred()


def sysd_shell(tmp):
    """A stand-in for the shell the old tests start mu300-buttons and thermal-guard with: mu300-sysd instead (the
    keys and the LED tick until the helper's output ends, with the hint's minute of mu300-buttons; one thermal round),
    its log lines where those tests' logger stub put the guard's. Anything else runs under /bin/sh."""
    w = tmp / 'sysd-shell'
    argv = ' '.join(shlex.quote(a) for a in sysd_argv())
    w.write_text(f'''#!/bin/sh
case ${{1:-}} in
    */mu300-buttons) shift; MU300_SYSD_ONCE=1 MU300_SYSD_PARTS="keys led" MU300_SYSD_LED_HINT_MAX=60 \\
        MU300_SYSD_LOG="$STUBLOG/sysd.log" exec {argv} "$@" ;;
    */thermal-guard) shift; MU300_SYSD_LOG="$STUBLOG/log" exec {argv} --round "$@" ;;
    *) exec /bin/sh "$@" ;;
esac
''')
    w.chmod(0o755)
    return [str(w)]


# ------------------------------------------------------------------ the old daemons' tests, against mu300-sysd
@unittest.skipUnless(OK, NEEDS)
class ButtonsUnderSysd(old.Buttons):
    """every test of mu300-buttons, with mu300-sysd reading the same keys"""
    def setUp(self):
        super().setUp()
        self.shells = [sysd_shell(self.tmp)]


@unittest.skipUnless(OK, NEEDS)
class ThermalGuardUnderSysd(old.ThermalGuard):
    """every test of thermal-guard, one round of mu300-sysd each"""
    def setUp(self):
        super().setUp()
        self.shells = [sysd_shell(self.tmp)]


# ------------------------------------------------------------------ the daemon itself
class Clock(threading.Thread):
    """the fake /proc/uptime, running with the real clock from START (the LED files hold uptimes)"""
    def __init__(self, path, start):
        super().__init__(daemon=True)
        self.path, self.base, self.t0, self.stop = Path(path), start, time.monotonic(), False
        self.tick()

    def now(self):
        return self.base + time.monotonic() - self.t0

    def tick(self):
        tmp = self.path.with_suffix('.part')
        tmp.write_text(f'{self.now():.2f} 0.00\n')
        tmp.replace(self.path)

    def run(self):
        while not self.stop:
            self.tick()
            time.sleep(0.05)


@unittest.skipUnless(OK and LINUX, NEEDS)
class Daemon(ShellTest):
    """mu300-sysd running, its helper a stub that passes on what the test writes into a FIFO"""
    def setUp(self):
        super().setUp()
        self.procs, self.feed, self.clock = [], None, None
        self.fifo = self.tmp / 'keys.fifo'
        os.mkfifo(self.fifo)
        self.stub('mu300-keys', 'echo "mu300-keys $*" >> "$STUBLOG/helper"; exec cat "$STUBLOG/keys.fifo"')

    def tearDown(self):
        if self.clock:
            self.clock.stop = True
        if self.feed:
            self.feed.close()
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(5)
                except subprocess.TimeoutExpired:
                    p.kill()
            if os.environ.get('MU300_TEST_VERBOSE'):
                print('\n--- sysd stderr:\n' + p.stderr.read())
            p.stderr.close()
        super().tearDown()

    def start(self, feed=True, **env):
        p = subprocess.Popen(sysd_argv(), env=self.env(MU300_SYSD_LOG=self.tmp / 'sysd.log', **env),
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        self.procs.append(p)
        if feed:   # the FIFO opens once the helper reads it
            fd = wait_for(lambda: self._open_fifo(), 8)
            self.assertTrue(fd, 'the helper never started')
            self.feed = os.fdopen(fd, 'w')
        return p

    def _open_fifo(self):
        try:
            return os.open(self.fifo, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            return None

    def send(self, line):
        self.feed.write(line + '\n')
        self.feed.flush()

    def calls(self):
        f = self.tmp / 'calls'
        return f.read_text().splitlines() if f.exists() else []

    def log(self):
        f = self.tmp / 'sysd.log'
        return f.read_text() if f.exists() else ''

    # --- the LED tick
    def u30air(self):
        root = self.tmp / 'root'
        for n in ('sc27xx:red', 'sc27xx:green', 'sc27xx:blue', 'zte-ldo0'):   # zte-ldo0: SIM 1's network LED
            d = root / 'sys/class/leds' / n
            d.mkdir(parents=True, exist_ok=True)
            (d / 'brightness').write_text('0\n')
            (d / 'max_brightness').write_text('255\n')
            (d / 'trigger').write_text('[none] timer\n')
        ps = root / 'sys/class/power_supply'
        for d, files in (('sc27xx-fgu', {'capacity': 80, 'status': 'Discharging'}), ('bq256xx-charger', {'online': 0})):
            (ps / d).mkdir(parents=True, exist_ok=True)
            for k, v in files.items():
                (ps / d / k).write_text(f'{v}\n')
        (root / 'proc').mkdir(parents=True, exist_ok=True)
        (root / 'run/mu300').mkdir(parents=True, exist_ok=True)
        (root / 'run/mu300/device').write_text('u30air\n')
        return root

    def test_the_led_tick_runs_on_events_and_on_time_only(self):
        """mu300-led tick starts when a uevent, the hint's due time or the end of a key's wake gives it something to
        do: never every 5 s, and not for a 1 % step of the battery that the LED does not show"""
        root = self.u30air()
        ps = root / 'sys/class/power_supply'
        (self.tmp / 'led.conf').write_text('LED_TIMEOUT=3\n')   # a 3 s timeout keeps the test short
        self.stub('mu300-led', f'echo "mu300-led $*" >> "$STUBLOG/calls"; exec "{BIN}/mu300-led" "$@"')
        self.stub('mu300-power', 'echo "mu300-power $*" >> "$STUBLOG/calls"')
        env = dict(MU300_RUN=self.tmp / 'run', MU300_SYSROOT=root, MU300_BIN=BIN, MU300_LED_CONF=self.tmp / 'led.conf',
                   MU300_SYSD_PARTS='keys led', MU300_SYSD_SAFETY=3600)
        self.clock = Clock(root / 'proc/uptime', 100)
        self.clock.start()
        r = subprocess.run(['sh', str(BIN / 'mu300-led'), 'data', 'on'], env=self.env(**env), capture_output=True,
                           text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

        def ticks():
            return self.calls().count('mu300-led tick')

        def lit():
            return (root / 'sys/class/leds/zte-ldo0/brightness').read_text().strip()

        self.assertEqual(lit(), '0')                               # no key yet: dark
        self.start(**env)
        self.send('0 tick')                                        # a look now: no hint yet
        self.assertTrue(wait_for(lambda: ticks() == 1), self.calls())
        # a 1 % step: the uevent is looked at, the LED shows the same, nothing starts
        (ps / 'sc27xx-fgu/capacity').write_text('79\n')
        self.send('uevent change power_supply sc27xx-fgu')
        time.sleep(1.5)
        self.assertEqual(ticks(), 1)
        # a key: its wake, no tick for it, and a tick when its timeout runs out (the hint, written while dark, is due
        # only in 10 minutes)
        self.send('116 short')
        self.assertTrue(wait_for(lambda: lit() == '255'), self.calls())
        self.assertIn('mu300-led wake', self.calls())
        time.sleep(0.5)
        self.assertEqual(ticks(), 1)
        self.assertTrue(wait_for(lambda: lit() == '0', 6), self.calls())
        self.assertEqual(ticks(), 2)
        # 59 %: the battery LED turns blue
        (ps / 'sc27xx-fgu/capacity').write_text('59\n')
        self.send('uevent change power_supply sc27xx-fgu')
        self.assertTrue(wait_for(lambda: (root / 'run/mu300/led/.battery').read_text().split()[0] == 'blue'))
        self.assertEqual(ticks(), 3)
        # plugged in: everything lit at once, and it stays lit
        (ps / 'bq256xx-charger/online').write_text('1\n')
        self.send('uevent change power_supply bq256xx-charger')
        self.assertTrue(wait_for(lambda: ticks() == 4 and lit() == '255'), self.calls())
        time.sleep(4)
        self.assertEqual((ticks(), lit()), (4, '255'))
        # unplugged: the timeout starts again, and runs out on time
        (ps / 'bq256xx-charger/online').write_text('0\n')
        self.send('uevent change power_supply bq256xx-charger')
        self.assertTrue(wait_for(lambda: ticks() == 5), self.calls())
        self.assertEqual(lit(), '255')
        self.assertTrue(wait_for(lambda: lit() == '0', 6), self.calls())
        self.assertEqual(ticks(), 6)
        # at rest nothing starts
        time.sleep(2.5)
        self.assertEqual(ticks(), 6)
        self.assertEqual(self.calls().count('mu300-led wake'), 1)

    def test_a_lost_uevent_is_caught_by_the_safety_look(self):
        root = self.u30air()
        self.stub('mu300-led', f'echo "mu300-led $*" >> "$STUBLOG/calls"; exec "{BIN}/mu300-led" "$@"')
        env = dict(MU300_RUN=self.tmp / 'run', MU300_SYSROOT=root, MU300_BIN=BIN, MU300_LED_CONF=self.tmp / 'none',
                   MU300_SYSD_PARTS='keys led', MU300_SYSD_SAFETY=1)
        self.clock = Clock(root / 'proc/uptime', 100)
        self.clock.start()
        self.start(**env)
        self.send('0 tick')
        self.assertTrue(wait_for(lambda: self.calls().count('mu300-led tick') == 1))
        time.sleep(2.5)                                            # looks, nothing changed
        self.assertEqual(self.calls().count('mu300-led tick'), 1)
        (root / 'sys/class/power_supply/sc27xx-fgu/capacity').write_text('5\n')   # no uevent
        battery = root / 'run/mu300/led/.battery'
        self.assertTrue(wait_for(lambda: battery.read_text().split() == ['red', 'steady', '1'], 4))
        self.assertEqual(self.calls().count('mu300-led tick'), 2)

    def led_daemon(self, online, status):
        """sysd's LED part on a U30 Air's supplies (the charger ONLINE, the gauge STATUS), the safety look 3600 s on
        the battery and 1 s on the charger, after its first tick"""
        root = self.u30air()
        ps = root / 'sys/class/power_supply'
        (ps / 'bq256xx-charger/online').write_text(f'{online}\n')
        (ps / 'sc27xx-fgu/status').write_text(f'{status}\n')
        self.stub('mu300-led', f'echo "mu300-led $*" >> "$STUBLOG/calls"; exec "{BIN}/mu300-led" "$@"')
        env = dict(MU300_RUN=self.tmp / 'run', MU300_SYSROOT=root, MU300_BIN=BIN, MU300_LED_CONF=self.tmp / 'none',
                   MU300_SYSD_PARTS='keys led', MU300_SYSD_SAFETY=3600, MU300_SYSD_SAFETY_PLUGGED=1)
        self.clock = Clock(root / 'proc/uptime', 100)
        self.clock.start()
        self.start(**env)
        self.send('0 tick')
        self.assertTrue(wait_for(lambda: self.calls().count('mu300-led tick') == 1))
        return root

    def test_on_the_charger_the_safety_look_comes_sooner(self):
        """the U30 Air's charger has no interrupt wired: charging -> full changes the battery LED without a uevent
        (FINDINGS 208), so on the charger the hint is looked at every SAFETY_PLUGGED s (30)"""
        root = self.led_daemon(1, 'Charging')
        time.sleep(2.5)                                            # looks, nothing changed
        self.assertEqual(self.calls().count('mu300-led tick'), 1)
        (root / 'sys/class/power_supply/sc27xx-fgu/status').write_text('Full\n')    # no uevent
        self.assertTrue(wait_for(lambda: self.calls().count('mu300-led tick') == 2, 4))

    def test_on_the_battery_a_plug_is_an_extcon_uevent(self):
        """on the battery the look waits for SAFETY s (90; 3600 here) or a uevent: the plug's is extcon-gpio's"""
        root = self.led_daemon(0, 'Discharging')
        (root / 'sys/class/power_supply/bq256xx-charger/online').write_text('1\n')   # plugged, no uevent yet
        time.sleep(2.5)
        self.assertEqual(self.calls().count('mu300-led tick'), 1)
        self.send('uevent change extcon extcon0')
        self.assertTrue(wait_for(lambda: self.calls().count('mu300-led tick') == 2, 3))
        self.assertEqual((root / 'run/mu300/led/.plugged').read_text().strip(), '1')

    def test_the_helper_is_asked_for_power_supply_uevents_and_started_again(self):
        self.stub('mu300-keys', 'echo "mu300-keys $*" >> "$STUBLOG/helper"')   # ends at once
        self.start(feed=False, MU300_SYSD_PARTS='keys led', MU300_SYSD_SAFETY=3600)
        helper = self.tmp / 'helper'
        self.assertTrue(wait_for(lambda: helper.exists() and len(helper.read_text().splitlines()) >= 2, 8))
        self.assertEqual(helper.read_text().splitlines()[0], 'mu300-keys -l 3000 -u power_supply,extcon')
        self.assertIn('mu300-keys ended (0); again in', self.log())

    # --- thermal
    def test_the_kernel_zone_found_is_looked_at_again_every_round(self):
        """the zone found last round is looked at alone: one that is switched off or goes away (rmmod) makes the
        guard cap at the next round all the same"""
        root = self.tmp / 'root'
        th = root / 'sys/class/thermal'
        for i, cpu in enumerate((0, 4, 7)):
            d = th / f'cooling_device{i}'
            d.mkdir(parents=True)
            (d / 'type').write_text(f'cpufreq-cpu{cpu}\n')
        for i, kind in enumerate(('lit0-thmzone', 'soc-thmzone')):
            z = th / f'thermal_zone{i}'
            z.mkdir()
            (z / 'type').write_text(kind + '\n')
            (z / 'temp').write_text('88000\n')
            (z / 'mode').write_text('enabled\n')
        soc = th / 'thermal_zone1'
        for i, (tt, tv) in enumerate((('passive', 70000), ('passive', 85000), ('critical', 110000))):
            (soc / f'trip_point_{i}_type').write_text(tt + '\n')
            (soc / f'trip_point_{i}_temp').write_text(f'{tv}\n')
        for i in range(3):
            (soc / f'cdev{i}').symlink_to(f'../cooling_device{i}')
        p = root / 'sys/devices/system/cpu/cpufreq/policy0'
        p.mkdir(parents=True)
        (p / 'scaling_available_frequencies').write_text('614400 1105000 1404000 2002000 \n')
        (p / 'cpuinfo_max_freq').write_text('2002000\n')
        (p / 'scaling_max_freq').write_text('2002000\n')
        (root / 'run/mu300').mkdir(parents=True)
        (root / 'run/mu300/device').write_text('f50\n')
        b = self.tmp / 'bin'
        b.mkdir()
        shutil.copy(BIN / 'mu300-device', b / 'mu300-device')
        (b / 'mu300-led').write_text('#!/bin/sh\necho "mu300-led $*" >> "$STUBLOG/calls"\n')
        (b / 'mu300-led').chmod(0o755)

        def cap():
            return (p / 'scaling_max_freq').read_text().strip()

        self.start(feed=False, MU300_SYSD_PARTS='thermal', MU300_SYSROOT=root, MU300_BIN=b, MU300_THERMAL_INTERVAL=1)
        self.assertTrue(wait_for(lambda: 'soc-thmzone throttles the CPUs: watching only' in self.log()))
        time.sleep(2.5)                                            # hot, but the kernel throttles: no cap
        self.assertEqual(cap(), '2002000')
        (soc / 'mode').write_text('disabled\n')
        self.assertTrue(wait_for(lambda: cap() == '1404000', 4), self.log())
        self.assertIn('kernel thermal zone soc-thmzone gone: capping cpufreq again', self.log())
        (soc / 'mode').write_text('enabled\n')                    # back: the cap this guard set is lifted
        self.assertTrue(wait_for(lambda: cap() == '2002000', 4), self.log())
        shutil.rmtree(soc)                                          # rmmod
        self.assertTrue(wait_for(lambda: cap() == '1404000', 4), self.log())

    def test_thermal_rounds_run_on_their_own_timer(self):
        """the guard's rounds keep going as timers: the alarm and the caps come and go with the readings, the
        power-off at CRIT stays; nothing is started while nothing changes"""
        root = self.tmp / 'root'
        z = root / 'sys/class/thermal/thermal_zone0'
        z.mkdir(parents=True)
        (z / 'temp').write_text('60000\n')
        p = root / 'sys/devices/system/cpu/cpufreq/policy0'
        p.mkdir(parents=True)
        (p / 'scaling_available_frequencies').write_text('614400 1105000 2002000 \n')
        (p / 'cpuinfo_max_freq').write_text('2002000\n')
        (p / 'scaling_max_freq').write_text('2002000\n')
        (root / 'run/mu300').mkdir(parents=True)
        (root / 'run/mu300/device').write_text('f50\n')
        b = self.tmp / 'bin'
        b.mkdir()
        shutil.copy(BIN / 'mu300-device', b / 'mu300-device')
        (b / 'mu300-led').write_text('#!/bin/sh\necho "mu300-led $*" >> "$STUBLOG/calls"\n')
        (b / 'mu300-led').chmod(0o755)
        self.stub('poweroff', 'echo poweroff >> "$STUBLOG/calls"')
        self.start(feed=False, MU300_SYSD_PARTS='thermal', MU300_SYSROOT=root, MU300_BIN=b,
                   MU300_THERMAL_INTERVAL=1, MU300_THERMAL_MAX_INTERVAL_ALONE=1)
        self.assertTrue(wait_for(lambda: 'no kernel thermal zone throttles the CPUs' in self.log()))
        time.sleep(1.5)
        self.assertEqual(self.calls(), [])
        (z / 'temp').write_text('86000\n')
        self.assertTrue(wait_for(lambda: self.calls() == ['mu300-led alarm on'], 4), self.calls())
        self.assertTrue(wait_for(lambda: (p / 'scaling_max_freq').read_text().strip() == '614400', 4))
        self.assertTrue((root / 'run/mu300/thermal-capped').exists())
        (z / 'temp').write_text('74000\n')
        self.assertTrue(wait_for(lambda: self.calls()[-1:] == ['mu300-led alarm off'], 4), self.calls())
        self.assertTrue(wait_for(lambda: (p / 'scaling_max_freq').read_text().strip() == '2002000', 4))
        self.assertTrue(wait_for(lambda: not (root / 'run/mu300/thermal-capped').exists(), 4))
        (z / 'temp').write_text('106000\n')
        self.assertTrue(wait_for(lambda: 'poweroff' in self.calls(), 4), self.calls())
        self.assertIn('critical temperature 106000 mC, powering off', self.log())


# ------------------------------------------------------------------ --check and the init scripts
@unittest.skipUnless(OK, NEEDS)
class Check(ShellTest):
    def check(self, keys):
        return subprocess.run(sysd_argv() + ['--check'], env=self.env(MU300_KEYS_BIN=keys), capture_output=True,
                              text=True, timeout=30)

    @unittest.skipUnless(LINUX and CC, 'needs a C compiler on Linux')
    def test_a_helper_with_uevents_passes(self):
        r = self.check(KEYS)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_an_older_helper_or_none_fails(self):
        self.stub('mu300-keys', 'echo "usage: mu300-keys [-l MS] [-t SEC]" >&2; exit 2')
        r = self.check('mu300-keys')
        self.assertEqual(r.returncode, 1)
        self.assertIn('does not know -u', r.stderr)
        r = self.check(self.tmp / 'none')
        self.assertEqual(r.returncode, 1)


class Init(ShellTest):
    """/etc/init.d/mu300-sysd runs the daemon where sysd_on says so; mu300-buttons and mu300-post's thermal-guard
    step aside exactly then (the same test in all three)"""
    HARNESS = 'procd_open_instance() { echo "instance $*"; }\nprocd_set_param() { echo "param $*"; }\n' \
              'procd_close_instance() { :; }\n'

    def start(self, name, on):
        text = (INIT / name).read_text().replace('[ -x /opt/mu300/bin/mu300-keys ]', 'true')
        tail = f'\nsysd_on() {{ return {0 if on else 1}; }}\nstart_service\n'
        r = self.sh(self.shells[0], self.HARNESS + text + tail)
        self.assertEqual(r.returncode, 0, r.stderr)
        return [l.split()[1] for l in r.stdout.splitlines() if l.startswith('instance ')], r.stdout

    def test_the_daemon_or_the_old_loops(self):
        self.assertEqual(self.start('mu300-sysd', True)[0], ['sysd'])
        self.assertEqual(self.start('mu300-sysd', False)[0], [])
        self.assertEqual(self.start('mu300-buttons', True)[0], [])
        self.assertEqual(self.start('mu300-buttons', False)[0], ['buttons'])
        on, off = self.start('mu300-post', True)[0], self.start('mu300-post', False)[0]
        self.assertNotIn('thermalguard', on)
        self.assertEqual([i for i in off if i != 'thermalguard'], on)
        self.assertIn('thermalguard', off)
        out = self.start('mu300-sysd', True)[1]
        self.assertIn('param command /usr/bin/ucode /opt/mu300/bin/mu300-sysd\n', out)
        self.assertIn('param respawn 3600 5 0', out)

    def test_one_test_everywhere(self):
        rule = 'sysd_on() { [ -e /etc/mu300/sysd ] && /usr/bin/ucode /opt/mu300/bin/mu300-sysd --check >/dev/null 2>&1; }'
        for name in ('mu300-sysd', 'mu300-buttons', 'mu300-post'):
            self.assertIn('\n' + rule + '\n', (INIT / name).read_text(), name)


# ------------------------------------------------------------------ mu300-keys -u
@unittest.skipUnless(LINUX and CC, 'needs a C compiler on Linux')
class KeysUevents(unittest.TestCase):
    def test_usage_names_the_option(self):
        r = subprocess.run([str(KEYS), '-?'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertIn('usage: mu300-keys [-l MS] [-t SEC] [-u SUBSYSTEM[,SUBSYSTEM...]]', r.stderr)

    def test_without_keys_and_without_u_it_ends_as_before(self):
        if list(Path('/dev/input').glob('event*')):
            self.skipTest('this machine has input devices')
        r = subprocess.run([str(KEYS), '-t', '1'], capture_output=True, text=True, timeout=10)
        self.assertEqual((r.returncode, r.stdout), (1, ''))
        self.assertIn('no input device with keys', r.stderr)

    def listen(self, *subsystems):
        p = subprocess.Popen([str(KEYS), '-u', ','.join(subsystems)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.addCleanup(self.end, p)
        time.sleep(0.3)
        if p.poll() is not None:
            self.skipTest('no keys and no uevent socket here: ' + p.stderr.read().decode())
        return p

    def end(self, p):
        if p.poll() is None:
            p.kill()
        p.wait(5)
        for f in (p.stdout, p.stderr):
            f.close()

    def test_it_ends_when_its_reader_goes_away(self):
        p = self.listen('power_supply')
        p.stdout.close()
        self.assertEqual(p.wait(5), 0)

    def test_kernel_uevents_of_the_subsystems_asked_for_and_nobody_else_s(self):
        if os.geteuid() != 0 or not os.access('/sys/class/net/lo/uevent', os.W_OK):
            self.skipTest('needs root and a writable /sys/class/net/lo/uevent')
        p = self.listen('power_supply', 'net')

        def line(timeout):
            r, _, _ = select.select([p.stdout], [], [], timeout)
            return p.stdout.readline().decode() if r else None

        # a datagram to the uevent group from a process: not the kernel's, not reported
        s = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)   # NETLINK_KOBJECT_UEVENT
        s.bind((0, 0))
        fake = b'change@/devices/virtual/net/lo\0ACTION=change\0DEVPATH=/devices/virtual/net/lo\0SUBSYSTEM=net\0'
        try:
            s.sendto(fake, (0, 1))
        except OSError as e:
            self.skipTest(f'cannot send to the uevent group: {e}')
        finally:
            s.close()
        self.assertIsNone(line(0.5))
        # the kernel's own: a synthetic "change" of the loopback device
        Path('/sys/class/net/lo/uevent').write_text('change\n')
        self.assertEqual(line(5), 'uevent change net lo\n')
