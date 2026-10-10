"""Small device scripts, against a fake / (MU300_SYSROOT) and stub commands: mu300-device, mu300-lan-ip, mu300-led,
mu300-ttl. They run on Ubuntu (dash, bash) and OpenWrt (busybox ash)."""
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import threading
import time
import unittest
import zlib
from pathlib import Path

from helpers import BIN, TOP, ShellTest


class Device(ShellTest):
    def root(self, device=None, dt_u30=False):
        r = self.tmp / 'root'
        (r / 'run' / 'mu300').mkdir(parents=True, exist_ok=True)
        if device is not None:
            (r / 'run' / 'mu300' / 'device').write_text(device + '\n')
        if dt_u30:
            (r / 'proc' / 'device-tree' / 'charger_policy_service').mkdir(parents=True, exist_ok=True)
        return r

    def test_mu300_device(self):
        cases = [(None, False, 'f50'), (None, True, 'u30air'), ('u30air', False, 'u30air'),
                 ('f50', True, 'f50')]  # what init wrote wins over the device tree
        for device, dt, want in cases:
            r = self.root(device, dt)
            for shell in self.each_shell():
                out = self.script(shell, BIN / 'mu300-device', MU300_SYSROOT=r).stdout.strip()
                self.assertEqual(out, want, (device, dt))
            (r / 'run' / 'mu300' / 'device').unlink(missing_ok=True)

    def test_lan_ip(self):
        for device, want in (('f50', '192.168.77.1'), ('u30air', '192.168.78.1'), ('', '192.168.77.1')):
            r = self.root(device)
            for shell in self.each_shell():
                out = self.script(shell, BIN / 'mu300-lan-ip', MU300_SYSROOT=r, MU300_BIN=BIN).stdout.strip()
                self.assertEqual(out, want, device)


class At(ShellTest):
    """mu300-at against a fake daemon directory: a FIFO `cmd` and a thread that answers through the answer file."""

    def setUp(self):
        super().setUp()
        self.dir = self.tmp / 'at'
        self.dir.mkdir()
        os.mkfifo(self.dir / 'cmd')
        (self.tmp / 'bb').mkdir()
        self.sleeper = self.tmp / 'bb' / 'busybox'
        self.sleeper.write_text('#!/usr/bin/env python3\nimport sys, time\n'
                                'assert sys.argv[1] == "sleep"\ntime.sleep(float(sys.argv[2]))\n')
        self.sleeper.chmod(0o755)

    def daemon(self, reply, count=1, open_delay=0, answer_delay=0):
        """Answer COUNT commands with REPLY the way mu300-atd does: open the FIFO afresh for each command (after
        OPEN_DELAY: the daemon is busy draining), read `T answer-file command`, write the answer file after
        ANSWER_DELAY. A command whose writer has gone before the open is lost, as with the real daemon."""
        def run():
            for _ in range(count):
                time.sleep(open_delay)
                line = ''
                while not line:          # like the daemon: an empty read (no writer yet) just reopens
                    with open(self.dir / 'cmd') as f:
                        line = f.readline().rstrip('\n')
                _t, answer, _cmd = line.split(' ', 2)
                time.sleep(answer_delay)
                with open(answer, 'w', newline='') as a:
                    a.write(reply)
        th = threading.Thread(target=run, daemon=True)
        th.start()
        return th

    def at(self, shell, *args):
        return self.script(shell, BIN / 'mu300-at', *args, MU300_AT_DIR=self.dir, MU300_BUSYBOX=self.sleeper)

    def test_answer_needs_a_final_result_code(self):
        for shell in self.each_shell():
            self.daemon('\r\n')
            r = self.at(shell, 'AT')
            self.assertEqual(r.returncode, 1)
            self.assertIn('modem returned no final response', r.stderr)
            self.daemon('+CSQ: 20,99\r\nOK\r\n')
            r = self.at(shell, 'AT+CSQ')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.replace('\r', ''), '+CSQ: 20,99\nOK\n')   # text mode folds CRLF

    def test_no_daemon_does_not_hang(self):
        for shell in self.each_shell():
            t0 = time.monotonic()
            r = self.at(shell, '-t', 1, 'AT')
            self.assertLess(time.monotonic() - t0, 3 + 0.5)
            self.assertEqual(r.returncode, 1)
            self.assertIn('no answer from the daemon', r.stderr)
            self.assertFalse((self.dir / 'lock').exists())

    def test_dead_owner_says_only_no_answer(self):
        # owner/pid naming a process that is gone (the daemon died, or the modem never came up): the client says
        # "no answer" and nothing else - mobile-data copies its stderr into radio.log
        (self.dir / 'owner').mkdir()
        (self.dir / 'owner' / 'pid').write_text('999999\n')
        for shell in self.each_shell():
            r = self.at(shell, '-t', 1, 'AT')
            self.assertEqual(r.returncode, 1)
            self.assertEqual(r.stderr.strip(), 'mu300-at: no answer from the daemon', shell)

    def test_command_survives_a_busy_daemon(self):
        # the daemon opens the FIFO only 0.5 s after the client wrote: the command must still be there
        for shell in self.each_shell():
            self.daemon('OK\r\n', open_delay=0.5)
            r = self.at(shell, '-t', 2, 'AT')
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_live_daemon_gets_a_long_budget(self):
        # a live mu300-atd (owner/pid) may drain before it collects: an answer after T + 2 s is still taken
        owner = subprocess.Popen(['sh', '-c', 'sleep 60; :', 'mu300-atd'])
        try:
            (self.dir / 'owner').mkdir()
            (self.dir / 'owner' / 'pid').write_text(f'{owner.pid}\n')
            if not Path(f'/proc/{owner.pid}/cmdline').exists():
                self.skipTest('no /proc')
            for shell in self.each_shell():
                self.daemon('OK\r\n', answer_delay=3.5)
                r = self.at(shell, '-t', 1, 'AT')
                self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            owner.kill()
            owner.wait()

    def test_a_caller_budget_caps_the_wait(self):
        # final review minor 4: a caller with a hard limit of its own (the LuCI panel; rpcd ends a call at 30 s)
        # caps the wait with MU300_AT_BUDGET, even for a live daemon; it never lengthens it, and junk is ignored
        owner = subprocess.Popen(['sh', '-c', 'sleep 60; :', 'mu300-atd'])
        try:
            (self.dir / 'owner').mkdir()
            (self.dir / 'owner' / 'pid').write_text(f'{owner.pid}\n')
            if not Path(f'/proc/{owner.pid}/cmdline').exists():
                self.skipTest('no /proc')
            for shell in self.each_shell():
                for budget, ok in (('2', False), ('x', True), ('60', True)):
                    with self.subTest(budget=budget):
                        th = self.daemon('OK\r\n', answer_delay=3.5)
                        t0 = time.monotonic()
                        r = self.script(shell, BIN / 'mu300-at', '-t', 1, 'AT', MU300_AT_DIR=self.dir,
                                        MU300_BUSYBOX=self.sleeper, MU300_AT_BUDGET=budget)
                        self.assertEqual(r.returncode == 0, ok, r.stderr)
                        if not ok:
                            self.assertLess(time.monotonic() - t0, 3)
                            self.assertIn('no answer from the daemon', r.stderr)
                        th.join(timeout=10)
                        for f in self.dir.glob('answer.*'):
                            f.unlink()
        finally:
            owner.kill()
            owner.wait()

    def test_signal_stops_the_client_and_frees_the_lock(self):
        for shell in self.each_shell():
            p = subprocess.Popen(shell + [str(BIN / 'mu300-at'), '-t', '20', 'AT'], stderr=subprocess.PIPE,
                                 env=self.env(MU300_AT_DIR=self.dir, MU300_BUSYBOX=self.sleeper))
            for _ in range(200):
                if (self.dir / 'lock').exists():
                    break
                time.sleep(0.02)
            time.sleep(0.3)
            p.terminate()
            self.assertEqual(p.wait(timeout=10), 143)
            p.stderr.close()
            self.assertFalse((self.dir / 'lock').exists())
            self.assertEqual(list(self.dir.glob('answer.*')), [])

    def test_vanished_fifo_is_not_replaced_by_a_file(self):
        for shell in self.each_shell():
            (self.dir / 'cmd').unlink()
            r = self.at(shell, 'AT')           # no FIFO: the direct path, which has no tty here
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse((self.dir / 'cmd').exists())
            os.mkfifo(self.dir / 'cmd')

    def test_fast_round_trip(self):
        for shell in self.each_shell():
            self.daemon('OK\r\n', 20)
            t0 = time.monotonic()
            for _ in range(20):
                self.assertEqual(self.at(shell, 'AT').returncode, 0)
            self.assertLess(time.monotonic() - t0, 3)


class Atd(ShellTest):
    """mu300-atd on a pseudo terminal pair: the test is the modem (the pty master), the daemon runs for real."""

    FAST = 0.95   # a round trip without the one second drain wait: read -t 1 alone cannot be faster than this

    def setUp(self):
        super().setUp()
        self.dir = self.tmp / 'at'
        self.procs = []
        self.masters = []
        self.slave_fds = []

    def tearDown(self):
        for p in self.procs:
            p.terminate()                 # the daemon's INT/TERM trap stops its drainers
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
        for fd in self.masters + self.slave_fds:
            os.close(fd)
        super().tearDown()

    def pty(self, name):
        """A character device RUN/NAME (a symlink to a pty slave) and the master fd behind it."""
        master, slave = pty.openpty()
        self.masters.append(master)
        self.slave_fds.append(slave)      # keep the slave open: no hangup
        link = self.run_dir / name
        link.symlink_to(os.ttyname(slave))
        return link, master

    def start(self, shell, nr0=True, **env):
        """Start the daemon on tty_nr1 (and a tty_nr0 if NR0); wait until it owns the channel and every drainer it
        started has made its log. Returns the URC logs and the nr1 master."""
        self.run_dir = self.tmp / f'run{len(self.procs)}'   # one per daemon: each_shell starts several
        self.run_dir.mkdir()
        self.dir = self.run_dir / 'at'
        dev, master = self.pty('tty_nr1')
        if nr0:
            self.pty('tty_nr0')
        e = self.env(MU300_AT_DEV=dev, MU300_AT_DIR=self.dir, **env)
        if 'MU300_AT_URC_CHANNELS' not in env:
            e.pop('MU300_AT_URC_CHANNELS', None)
        self.err = self.run_dir / 'atd.err'
        with self.err.open('w') as err:
            self.procs.append(subprocess.Popen(shell + [str(BIN / 'mu300-atd')], stderr=err, env=e))
        # "... is ours, draining N other channel(s)" comes once every drainer has been started
        n = None
        for _ in range(500):
            m = re.search(r'is ours, draining\s+(\d+) other', self.err.read_text())
            if m:
                n = int(m.group(1))
                break
            time.sleep(0.02)
        self.assertIsNotNone(n, 'the daemon did not come up: ' + self.err.read_text())
        urc = self.dir / 'urc'
        for _ in range(500):              # a drainer makes its log in the background
            logs = sorted(p.name for p in urc.iterdir())
            if len(logs) >= n:
                break
            time.sleep(0.02)
        return logs, master

    def send(self, master, cmd, reply, t=1, before_reply=None):
        """Hand the daemon CMD (as a client does), answer on the pty when it arrives; seconds until the answer file.
        The answer itself is left in self.answer. BEFORE_REPLY, if given, runs between the two."""
        answer = self.tmp / 'answer'
        answer.unlink(missing_ok=True)
        t0 = time.monotonic()
        with open(self.dir / 'cmd', 'w') as f:
            f.write(f'{t} {answer} {cmd}\n')
        buf = b''
        while cmd.encode() + b'\r' not in buf:
            if not select.select([master], [], [], 10)[0]:
                break
            buf += os.read(master, 256)
        if before_reply:
            before_reply()
        if reply is not None:
            os.write(master, reply)
        while not answer.exists() and time.monotonic() - t0 < 40:
            time.sleep(0.02)
        elapsed = time.monotonic() - t0
        self.answer = answer.read_text() if answer.exists() else None
        return elapsed

    def whole_seconds(self):
        """The daemon's shell reads in whole seconds only (bash 3.2): every drain then waits the full second."""
        return 'takes whole seconds' in self.err.read_text()

    def test_log_lines_after_open_reach_stderr(self):
        for shell in self.each_shell():
            self.start(shell)
            self.assertIn('is ours, draining', self.err.read_text())

    def test_unset_urc_channels_open_nr0(self):
        for shell in self.each_shell():
            logs, _m = self.start(shell)
            self.assertEqual(logs, ['tty_nr0.log'])

    def test_empty_urc_channels_open_none(self):
        for shell in self.each_shell():
            logs, _m = self.start(shell, MU300_AT_URC_CHANNELS='')
            self.assertRegex(self.err.read_text(), r'draining\s+0 other')
            self.assertEqual(logs, [])

    def test_no_drain_wait_after_a_clean_reply(self):
        for shell in self.each_shell():
            _l, m = self.start(shell, nr0=False)
            self.send(m, 'AT', b'\r\nOK\r\n')                 # the first command drains slowly: nothing known yet
            if self.whole_seconds():
                continue
            for reply in (b'\r\nOK\r\n', b'\r\nERROR\r\n', b'\r\nOK\r\n'):   # the last one times the drain after ERROR
                self.assertLess(self.send(m, 'AT', reply), self.FAST)

    def test_slow_drain_after_a_timeout(self):
        for shell in self.each_shell():
            _l, m = self.start(shell, nr0=False)
            self.send(m, 'AT', b'\r\nOK\r\n')
            self.send(m, 'AT+X', None, t=1)                      # no answer: the timeout path
            self.assertGreater(self.send(m, 'AT', b'\r\nOK\r\n'), 0.9)
            if not self.whole_seconds():
                self.assertLess(self.send(m, 'AT', b'\r\nOK\r\n'), self.FAST)   # and a clean one makes it fast again

    def test_stray_lines_while_idle_do_not_shift_the_answers(self):
        # A line that arrives after a clean reply and before the next command - a late final code, a URC, an
        # unsolicited NO CARRIER - is drained into the nr1 log, never taken as the next command's answer.
        for shell in self.each_shell():
            _l, m = self.start(shell, nr0=False)
            self.send(m, 'AT', b'\r\nOK\r\n')
            # (a) a late trailing final code, the moment the reply that ended in OK has been handed over
            self.send(m, 'AT+A', b'\r\n+A: 1\r\nOK\r\n')
            self.assertEqual(self.answer, '+A: 1\nOK\n')
            os.write(m, b'\r\nOK\r\n')
            self.send(m, 'AT+B', b'\r\n+B: 2\r\nOK\r\n')
            self.assertEqual(self.answer, '+B: 2\nOK\n')
            # (b) URCs and an unsolicited final code while the channel is idle, before the next command
            os.write(m, b'\r\n+CMTI: "SM",3\r\n\r\nNO CARRIER\r\n')
            time.sleep(0.2)
            self.send(m, 'AT+C', b'\r\n+C: 3\r\nOK\r\n')
            self.assertEqual(self.answer, '+C: 3\nOK\n')
            self.send(m, 'AT+D', b'\r\nERROR\r\n')
            self.assertEqual(self.answer, 'ERROR\n')
            self.assertEqual((self.dir / 'urc' / 'tty_nr1.log').read_text().split('\n'),
                             ['OK', '+CMTI: "SM",3', 'NO CARRIER', ''])

    def test_a_reply_after_a_second_boundary_is_still_taken(self):
        # The reply budget counts whole seconds: "now + T" used to end at the next second boundary, so a T=1
        # command answered just after it came back empty, even though the modem took 0.1 s at most.
        def past_the_boundary():
            frac = time.time() % 1
            if frac > 0.1:       # else a boundary may lie between the daemon's clock read and now: no test this time
                time.sleep(1 - frac + 0.05)
        for shell in self.each_shell():
            _l, m = self.start(shell, nr0=False)
            for _ in range(3):
                self.send(m, 'AT+E', b'\r\n+E: 5\r\nOK\r\n', before_reply=past_the_boundary)
                self.assertEqual(self.answer, '+E: 5\nOK\n')


class MobileData(ShellTest):
    """mobile-data's at(): which daemon directory the command goes to (K17). The function is cut out of the script and
    its absolute paths pointed at the scratch directory, so nothing else of mobile-data runs."""

    def run_at(self, shell, nr2, nr1=True):
        run = self.tmp / 'run'
        shutil.rmtree(run, ignore_errors=True)
        for flag, name in ((nr1, 'mu300-at'), (nr2, 'mu300-at2')):
            d = run / name
            d.mkdir(parents=True, exist_ok=True)
            if flag:
                os.mkfifo(d / 'cmd')
        self.stub('mu300-at', 'echo "dir=$MU300_AT_DIR args=$*" >> "$STUBLOG/calls"')
        text = (BIN / 'mobile-data').read_text()
        body = text[text.index('\nat() {'):text.index('\n}\n', text.index('\nat() {')) + 3]
        body = body.replace('/run/', f'{run}/').replace('/opt/mu300/bin/mu300-at', 'mu300-at')
        (self.tmp / 'calls').unlink(missing_ok=True)
        r = self.sh(shell, body + '\nat "AT+CSQ" 4', MU300_AT_DIR='')
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.tmp / 'calls').read_text().strip()

    def test_at_prefers_the_nr2_daemon(self):
        for shell in self.each_shell():
            out = self.run_at(shell, nr2=True)
            self.assertRegex(out, r'^dir=\S*/run/mu300-at2 args=-t 4 AT\+CSQ$', shell)
            # the nr1 daemon takes over while nr2's is not there (yet): mu300-at's own default directory
            out = self.run_at(shell, nr2=False)
            self.assertEqual(out, 'dir= args=-t 4 AT+CSQ', shell)

    # mobile-data's functions with MU300_LIB=1 (K56, K59-K62). mobile-data is a bash script (#!/bin/bash, on OpenWrt
    # too), so these run under bash only; under alpine they still use busybox's tail, wc, sleep and awk.
    # `at` is replaced by the modem below, which answers from a table and writes each command it was sent to
    # $STUBLOG/at as "<seconds since the start> <command>".
    MODEM = r'''
at() {
    echo "$SECONDS $1" >> "$STUBLOG/at"
    case $1 in
        'AT+CEREG?') printf '%s\nOK\n' "${CEREG:-+CEREG: 2,2}" ;;
        'AT+CFUN?') printf '+CFUN: 1\nOK\n' ;;
        AT+CGCONTRDP=*)
            # the address arrives once CGACT=1 has been sent $ADDR_AFTER times
            if [ "$(grep -c 'AT+CGACT=1' "$STUBLOG/at")" -ge "${ADDR_AFTER:-1}" ]; then
                printf '%s\nOK\n' "${RDP:-+CGCONTRDP: 1,5,\"apn\",\"10.1.2.3.255.255.255.0\",\"10.1.2.1\",\"8.8.8.8\",\"1.1.1.1\"}"
            else
                printf '+CGCONTRDP: 1,5,"apn","0.0.0.0.0.0.0.0","0.0.0.0","0.0.0.0","0.0.0.0"\nOK\n'
            fi ;;
        AT+CGDATA=*) printf 'CONNECT\n' ;;
        AT+CGPADDR=*) printf '+CGPADDR: 1,"10.1.2.3"\nOK\n' ;;
        'AT+COPS?') printf '+COPS: 0,0,"Test Net",7\nOK\n' ;;
        *) printf 'OK\n' ;;
    esac
}
'''

    def lib(self, code, modem=None, **env):
        """Run CODE with bash after sourcing mobile-data (MU300_LIB=1) and replacing `at` by MODEM (or MODEM).
        /run is the scratch directory's run/; mu300-led and mu300-at are stubs on PATH. The mu300-at stub is the nr1
        daemon's client that radio_on's RIL handshake calls directly: it logs "nr1 <command>" to $STUBLOG/at and
        answers $SMMSWAP (OK by default; "none" is a timeout, "busy" the client lock held)."""
        if not shutil.which('bash'):
            self.skipTest('no bash')
        text = (BIN / 'mobile-data').read_text()
        text = text.replace('/run/', f'{self.tmp}/run/').replace('/opt/mu300/bin/mu300-led', 'mu300-led')
        text = text.replace('/opt/mu300/bin/mu300-at ', 'mu300-at ')
        # K47: the delegate loader is a stub that logs "- sipa-dele-start wait=<MU300_DELE_WAIT>" in the AT order and
        # exits $DELE_RC (0 by default); /proc/modules is the scratch directory's proc-modules
        text = text.replace('/opt/mu300/bin/sipa-dele-start', 'sipa-dele-start')
        text = text.replace('/proc/modules', f'{self.tmp}/proc-modules')
        text = text.replace('/tmp/mu300-sipa-dele.log', f'{self.tmp}/sipa-dele.log')
        # R35: /lib/modules is the scratch directory's lib-modules, where this kernel has sipa-dele.ko unless a test
        # removes it; bootmark is a stub that appends its mark to $STUBLOG/marks
        text = text.replace('/lib/modules/', f'{self.tmp}/lib-modules/')
        text = text.replace('/opt/mu300/bin/bootmark', f'{self.tmp}/bootmark')
        if not (self.tmp / 'bootmark').exists():
            ko = self.tmp / 'lib-modules' / os.uname().release / 'sipa-dele.ko'
            ko.parent.mkdir(parents=True, exist_ok=True)
            ko.write_text('')
            (self.tmp / 'bootmark').write_text('#!/bin/sh\necho "$*" >> "$STUBLOG/marks"\n')
            (self.tmp / 'bootmark').chmod(0o755)
        lib = self.tmp / 'mobile-data.lib'
        lib.write_text(text)
        (self.tmp / 'run').mkdir(exist_ok=True)
        for f in ('at', 'led', 'rf', 'nr1env'):
            (self.tmp / f).unlink(missing_ok=True)
        self.stub('mu300-led', 'echo "$*" >> "$STUBLOG/led"')
        self.stub('sipa-dele-start', 'echo "- sipa-dele-start wait=$MU300_DELE_WAIT" >> "$STUBLOG/at"\n'
                  'echo "sipa-dele-start: stub"\nexit "${DELE_RC:-0}"')
        self.stub('mu300-at', '[ "$1" = -t ] && shift 2\necho "nr1 $1" >> "$STUBLOG/at"\n'
                  'echo "dir=$MU300_AT_DIR wait=$MU300_AT_LOCK_WAIT" > "$STUBLOG/nr1env"\n'
                  'case ${SMMSWAP:-OK} in none) echo "mu300-at: no answer from the daemon" >&2; exit 1 ;;\n'
                  '    busy) echo "mu300-at: busy" >&2; exit 1 ;; esac\n'
                  'echo "${SMMSWAP:-OK}"')
        r = self.sh(['bash'], f'MU300_LIB=1; . "{lib}"\n{modem or self.MODEM}\nSECONDS=0\n{code}', **env)
        sent = (self.tmp / 'at').read_text().splitlines() if (self.tmp / 'at').exists() else []
        return r, sent

    def test_registered_from_urc(self):
        """nr0 announces the registration: wait_registered sees it in the URC log and asks nothing in the first 5 s."""
        log = self.tmp / 'stty_nr0.log'
        # the modem's last word before the call was "searching"; the registration is appended a second later
        log.write_text('+CEREG: 2\n')
        r, sent = self.lib('(sleep 1; printf \'+CEREG: 1,"1A2B","0123ABCD",7\\n\' >> "$MU300_URC_LOG") &\n'
                           'rc=0; wait_registered || rc=$?; echo "rc=$rc t=$SECONDS"',
                           MU300_URC_LOG=log, MU300_REGISTER_WAIT=20, CEREG='+CEREG: 2,2')
        self.assertRegex(r.stdout, r'rc=0 t=[0-4]\b', r.stderr)
        self.assertFalse([s for s in sent if 'AT+CEREG?' in s], sent)
        # mu300-atd starts the log over at its size cap: a registration written after the cut still counts
        log.write_text('+CEREG: 2\n' * 50)
        r, sent = self.lib('(sleep 1; : > "$MU300_URC_LOG"; printf \'+CEREG: 5\\n\' >> "$MU300_URC_LOG") &\n'
                           'rc=0; wait_registered || rc=$?; echo "rc=$rc t=$SECONDS"',
                           MU300_URC_LOG=log, MU300_REGISTER_WAIT=20, CEREG='+CEREG: 2,2')
        self.assertRegex(r.stdout, r'rc=0 t=[0-4]\b', r.stderr)
        self.assertFalse([s for s in sent if 'AT+CEREG?' in s], sent)

    def test_old_urc_does_not_count(self):
        """A registration announced before the call proves nothing now: the query decides, and is sent at once."""
        log = self.tmp / 'stty_nr0.log'
        log.write_text('+CEREG: 2\n+CEREG: 1,"1A2B","0123ABCD",7\n')
        r, sent = self.lib('rc=0; wait_registered || rc=$?; echo "rc=$rc t=$SECONDS"',
                           MU300_URC_LOG=log, MU300_REGISTER_WAIT=20, CEREG='+CEREG: 2,1,"1A2B","0123ABCD",7')
        self.assertRegex(r.stdout, r'rc=0 t=[01]\b', r.stderr)
        self.assertTrue([s for s in sent if 'AT+CEREG?' in s], sent)
        # nothing new arrives and the query says "searching": not registered when the budget is spent. "+CEREG: 1,2"
        # is the query form with <n>=1 and <stat>=2, not a registration.
        r, sent = self.lib('rc=0; wait_registered || rc=$?; echo "rc=$rc t=$SECONDS"',
                           MU300_URC_LOG=log, MU300_REGISTER_WAIT=6, CEREG='+CEREG: 1,2')
        self.assertRegex(r.stdout, r'rc=1 t=[6-8]\b', r.stderr)
        # the fallback asks every 5 s, not every 2
        self.assertEqual(len([s for s in sent if 'AT+CEREG?' in s]), 2, sent)

    def test_fetch_addr_bounded(self):
        """+CGCONTRDP keeps answering 0.0.0.0: fetch_addr gives up within its budget (in seconds, not rounds), and
        does not sleep past it (queries at 0 and 2 s; a third would start after the budget, so none is waited for)."""
        r, _ = self.lib('rc=0; fetch_addr 3 || rc=$?; echo "rc=$rc t=$SECONDS rdp=$rdp"', ADDR_AFTER=99)
        self.assertRegex(r.stdout, r'rc=1 t=[23] rdp=$', r.stderr)
        r, _ = self.lib('rc=0; fetch_addr 3 || rc=$?; echo "rc=$rc rdp=$rdp"', ADDR_AFTER=0)
        self.assertIn('rc=0 rdp=+CGCONTRDP: 1,5,"apn","10.1.2.3.255.255.255.0"', r.stdout, r.stderr)

    def test_address_after_one_cgact_reassert(self):
        """up (netifd mode): no AT+CGACT? first, one idempotent CGACT=1 reassert when the address is late, never
        CGACT=0, and the decision is in radio.log (K60, K62)."""
        r, sent = self.lib('up_locked', MU300_NETIFD=1, MU300_AT_DEV='/dev/null', MU300_URC_LOG=self.tmp / 'none',
                           CEREG='+CEREG: 2,1,"1A2B","0123ABCD",7', ADDR_AFTER=2, MU300_CFUN_WAIT=0,
                           MU300_ADDR_WAIT_FIRST=2, MU300_ADDR_WAIT_RETRY=6)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('IP=10.1.2.3\nPREFIX=24\nDNS1=8.8.8.8\nDNS2=1.1.1.1\n', r.stdout)
        cmds = [s.split(' ', 1)[1] for s in sent]
        # K58: the IMS bearer SMS needs, once the radio is on and before the registration wait
        self.assertLess(cmds.index('AT+CFUN?'), cmds.index('AT+CAVIMS=1'), cmds)
        self.assertLess(cmds.index('AT+CAVIMS=1'), cmds.index('AT+CEREG?'), cmds)
        self.assertEqual(cmds.count('AT+CGACT=1,1'), 2, cmds)
        self.assertNotIn('AT+CGACT?', cmds)
        self.assertFalse([c for c in cmds if c.startswith('AT+CGACT=0')], cmds)
        radio = (self.tmp / 'run' / 'mu300' / 'radio.log').read_text()
        self.assertRegex(radio, r'(?m)^t=\S* +registered\b')
        self.assertIn('reasserting', radio)

    def test_sipa_dele_between_registration_and_cgact(self):
        """K47: the IPA delegate is loaded by the dial itself, after the registration and before the PDP context
        (AT+CGACT=1), with a 20 s wait; when it does not load, the dial stops there and activates nothing; once it
        is loaded, a later dial does not call the loader again."""
        env = dict(MU300_NETIFD=1, MU300_AT_DEV='/dev/null', MU300_URC_LOG=self.tmp / 'none', MU300_CFUN_WAIT=0,
                   CEREG='+CEREG: 2,1,"1A2B","0123ABCD",7')
        r, sent = self.lib('up_locked', **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('IP=10.1.2.3\n', r.stdout)
        self.assertNotIn('stub', r.stdout)                      # its output does not reach netifd's parser
        cmds = [s.split(' ', 1)[1] for s in sent]
        self.assertEqual(cmds.count('sipa-dele-start wait=20'), 1, cmds)
        dele = cmds.index('sipa-dele-start wait=20')
        last_cereg = len(cmds) - 1 - cmds[::-1].index('AT+CEREG?')
        self.assertLess(last_cereg, dele, cmds)                    # after the registration
        self.assertLess(dele, cmds.index('AT+CGACT=1,1'), cmds)    # before the PDP context
        # the loader refuses (the packet domain never came up, or insmod failed): no CGACT, exit 1, said why
        r, sent = self.lib('up_locked', DELE_RC=1, **env)
        cmds = [s.split(' ', 1)[1] for s in sent]
        self.assertEqual(r.returncode, 1, r.stdout)
        self.assertIn('sipa-dele-start wait=20', cmds)
        self.assertFalse([c for c in cmds if c.startswith('AT+CGACT')], cmds)
        self.assertNotIn('IP=', r.stdout)
        self.assertIn('IPA delegate', r.stderr)
        self.assertIn('IPA delegate', (self.tmp / 'run' / 'mu300' / 'radio.log').read_text())
        # already in /proc/modules (a reconnect): straight on to the context, the loader is not called
        (self.tmp / 'proc-modules').write_text('sipa_dele 16384 0 - Live 0x0000000000000000 (O)\n')
        r, sent = self.lib('up_locked', DELE_RC=1, **env)
        cmds = [s.split(' ', 1)[1] for s in sent]
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse([c for c in cmds if c.startswith('sipa-dele-start')], cmds)
        self.assertIn('AT+CGACT=1,1', cmds)

    def test_up_applies_the_ttl(self):
        """Every bring-up (netifd, the watchdog's reconnect) re-applies mu300-ttl's rule: the tc backend's filters
        belong to the interface. Its output never reaches netifd's parser, and its failure fails nothing."""
        env = dict(MU300_NETIFD=1, MU300_AT_DEV='/dev/null', MU300_URC_LOG=self.tmp / 'none', MU300_CFUN_WAIT=0,
                   CEREG='+CEREG: 2,1,"1A2B","0123ABCD",7', MU300_TTL_CMD=self.stubs / 'ttl')
        for rc in (0, 1):
            self.stub('ttl', f'echo "$*" >> "$STUBLOG/ttl.log"; echo noise; echo err >&2; exit {rc}')
            (self.tmp / 'ttl.log').unlink(missing_ok=True)
            r, _ = self.lib('up_locked', **env)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('IP=10.1.2.3\n', r.stdout)
            self.assertNotIn('noise', r.stdout)
            self.assertEqual((self.tmp / 'ttl.log').read_text(), 'apply\n')

    def test_sipa_dele_only_with_the_module(self):
        """R35: a kernel without sipa-dele.ko (neither in /lib/modules/<release> nor under extra/) dials without the
        loader, and the boot timeline has no dial-sipa-dele mark; with the module (either place) the loader runs and
        the mark is written."""
        env = dict(MU300_NETIFD=1, MU300_AT_DEV='/dev/null', MU300_URC_LOG=self.tmp / 'none', MU300_CFUN_WAIT=0,
                   CEREG='+CEREG: 2,1,"1A2B","0123ABCD",7')
        self.lib(':')                                   # makes lib-modules and the bootmark stub
        mods = self.tmp / 'lib-modules' / os.uname().release
        (mods / 'sipa-dele.ko').unlink()
        r, sent = self.lib('up_locked', **env)
        cmds = [s.split(' ', 1)[1] for s in sent]
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('IP=10.1.2.3\n', r.stdout)
        self.assertFalse([c for c in cmds if c.startswith('sipa-dele-start')], cmds)
        self.assertIn('AT+CGACT=1,1', cmds)
        marks = (self.tmp / 'marks').read_text().split()
        self.assertIn('dial-registered', marks)
        self.assertNotIn('dial-sipa-dele', marks)
        self.assertIn('no sipa-dele.ko', self.radio_log())
        (mods / 'extra').mkdir()
        (mods / 'extra' / 'sipa-dele.ko').write_text('')
        (self.tmp / 'marks').unlink()
        r, sent = self.lib('up_locked', **env)
        cmds = [s.split(' ', 1)[1] for s in sent]
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('sipa-dele-start wait=20', cmds)
        self.assertIn('dial-sipa-dele', (self.tmp / 'marks').read_text().split())

    # R35: up()'s lock, the radio lock's scheme. up_locked is replaced by a round that logs "start" and "end" to
    # $STUBLOG/rounds around $ROUND s (1) of sleep.
    ROUND = ('up_locked() { echo start >> "$STUBLOG/rounds"; sleep "${ROUND:-1}"; echo end >> "$STUBLOG/rounds"; }\n')

    def up_lock_files(self):
        return sorted(p.name for p in (self.tmp / 'run').iterdir() if p.name.startswith('mu300-mobile-data-up'))

    def test_up_lock_holder_is_named_from_the_start(self):
        """R35: the bring-up lock never exists without its owner's pid, and is gone after the round."""
        r, _ = self.lib(self.ROUND + 'ROUND=2; ( up ) & h=$!\n'
                        f'sleep 1; echo "owner=$(readlink "{self.tmp}/run/mu300-mobile-data-up.owner") h=$h"; wait $h')
        m = re.search(r'owner=(\d+) h=(\d+)', r.stdout)
        self.assertTrue(m, r.stdout + r.stderr)
        self.assertEqual(m.group(1), m.group(2))
        self.assertEqual(self.up_lock_files(), [])

    def test_two_waiters_on_a_dead_up_lock(self):
        """R35: the bring-up's owner was killed in its round (nothing released). Two callers of up find the lock at
        the same moment: exactly one takes it over, the other waits for that one's round to end, and nothing of the
        lock is left afterwards (the old directory lock let the second remove the lock the first had just taken)."""
        r, _ = self.lib(self.ROUND + self.SLOW_DEAD +
                        'ROUND=5; ( up ) >/dev/null 2>&1 & h=$!\n'
                        'sleep 1; kill -9 $h; wait $h 2>/dev/null || true\n'
                        'ROUND=1\n'
                        '( DEAD_DELAY=0.2; up ) & a=$!; ( DEAD_DELAY=0.8; up ) & b=$!\n'
                        'ra=0; wait $a || ra=$?; rb=0; wait $b || rb=$?; echo "ra=$ra rb=$rb"')
        self.assertIn('ra=0 rb=0', r.stdout, r.stderr)
        rounds = [line.split()[0] for line in (self.tmp / 'rounds').read_text().splitlines()]
        # the killed owner's start, then two rounds one after the other, never two at once
        self.assertEqual(rounds, ['start', 'start', 'end', 'start', 'end'], rounds)
        self.assertEqual(self.up_lock_files(), [])

    def test_up_lock_wait_gives_up(self):
        """R35: a bring-up that holds the lock past the wait (MU300_UP_LOCK_WAIT, 150 s by default) makes the
        second caller give up and say whose it is; down() leaves a running bring-up's AT channel alone."""
        r, sent = self.lib(self.ROUND + 'ROUND=4; ( up ) & h=$!\n'
                           'sleep 1; rc=0; up 2>"$STUBLOG/err" || rc=$?; MU300_AT_DEV=/dev/null down\n'
                           'echo "rc=$rc h=$h"; wait $h', MU300_UP_LOCK_WAIT=1)
        m = re.search(r'rc=(\d+) h=(\d+)', r.stdout)
        self.assertTrue(m, r.stdout + r.stderr)
        self.assertEqual(m.group(1), '1')
        self.assertIn(f'(pid {m.group(2)})', (self.tmp / 'err').read_text())
        self.assertFalse([s for s in sent if 'AT+CGACT=0' in s], sent)

    def test_led_from_cereg(self):
        """4G or 5G from the AcT field of AT+CEREG? (K56), not from AT+COPS?."""
        for act, want in (('13', 'data 5g'), ('7', 'data on'), ('11', 'data 5g')):
            r, sent = self.lib('led_up', CEREG=f'+CEREG: 2,1,"1A2B","0123ABCD",{act}')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.tmp / 'led').read_text().strip(), want, act)
            self.assertEqual([s.split(' ', 1)[1] for s in sent], ['AT+CEREG?'], act)

    def test_systemd_path_keeps_v6_up(self):
        """K63 is rejected: on the systemd path (Ubuntu) an IPv6 address from the network still runs v6_up, and none
        switches IPv6 off."""
        text = (BIN / 'mobile-data').read_text()
        start = text.index('\nup_locked() {')
        body = text[start:text.index('\ndown() {', start)]   # the nft here-documents have their own '}' lines
        netifd = body.index('if [ "${MU300_NETIFD:-0}" = 1 ]; then')
        self.assertIn('[ -n "$iid" ] || v6_off', body[:netifd])
        self.assertIn('[ -n "$iid" ] && v6_up "$iid"', body[netifd:])
        self.assertNotIn('MU300_PDP_TYPE:-IP}" != IP', body)   # the fork's replacement for v6_up

    # radio_on (K57, K65, K66). The radio's state: "+CFUN: $CFUN" (0 by default, "none" = no answer) until AT+SFUN=4
    # has been answered, then $RF_LAG more "+CFUN: 0" and "+CFUN: 1" from then on. AT+SFUN=4 takes $SFUN_DELAY s.
    RADIO = r'''
at() {
    echo "$SECONDS $1" >> "$STUBLOG/at"
    case $1 in
        'AT+CFUN?')
            [ "${CFUN:-}" = none ] && { echo "mu300-at: modem returned no final response" >&2; return 1; }
            if [ -e "$STUBLOG/rf" ]; then
                k=$(cat "$STUBLOG/rf")
                if [ "$k" -gt 0 ]; then echo $((k - 1)) > "$STUBLOG/rf"; printf '+CFUN: 0\nOK\n'
                else printf '+CFUN: 1\nOK\n'; fi
            else
                printf '+CFUN: %s\nOK\n' "${CFUN:-0}"
            fi ;;
        'AT+SFUN=4') sleep "${SFUN_DELAY:-0}"; echo "${RF_LAG:-0}" > "$STUBLOG/rf"; printf 'OK\n' ;;
        *) printf 'OK\n' ;;
    esac
}
'''

    def radio(self, code, urc='+CEREG: 2\n', **env):
        """CODE against RADIO, with nr0's URC log already written (URC=None: no log) and no plugin unless the test
        names one (MU300_PLUGIN_LOCK)."""
        log = self.tmp / 'stty_nr0.log'
        log.unlink(missing_ok=True)
        if urc is not None:
            log.write_text(urc)
        env.setdefault('MU300_PLUGIN_LOCK', self.tmp / 'no-plugin')
        r, sent = self.lib(code, modem=self.RADIO, MU300_URC_LOG=log, **env)
        return r, sent, [s.split(' ', 1)[1] for s in sent]

    def radio_log(self):
        p = self.tmp / 'run' / 'mu300' / 'radio.log'
        return p.read_text() if p.exists() else ''

    def test_ril_handshake_once_per_boot(self):
        """AT+SMMSWAP=0 is nr1's first command, sent through the nr1 daemon once per boot (K57)."""
        marker = self.tmp / 'run' / 'mu300-ril-handshake'
        r, sent, cmds = self.radio('radio_on; radio_on; echo ok', RF_LAG=0)
        self.assertIn('ok', r.stdout, r.stderr)
        self.assertEqual(cmds.count('AT+SMMSWAP=0'), 1, cmds)
        self.assertEqual(cmds[0], 'AT+SMMSWAP=0', cmds)
        self.assertTrue(sent[0].startswith('nr1 '), sent)       # mu300-at to nr1, not at() (nr2)
        self.assertEqual((self.tmp / 'nr1env').read_text().strip(), f'dir={self.tmp}/run/mu300-at wait=1')
        self.assertTrue(marker.exists())
        self.assertEqual(cmds.count('AT+SFUN=4'), 1, cmds)       # the second call found the radio on
        # no answer to the handshake: the round ends there, nothing else is sent and the next round tries again
        marker.unlink()
        r, sent, cmds = self.radio('rc=0; radio_on || rc=$?; echo "rc=$rc"', SMMSWAP='none')
        self.assertIn('rc=1', r.stdout, r.stderr)
        self.assertEqual(cmds, ['AT+SMMSWAP=0'])
        self.assertFalse(marker.exists())
        self.assertIn('RIL handshake', self.radio_log())

    def test_ril_handshake_error_is_an_answer(self):
        """Final review minor 2: a firmware that refuses AT+SMMSWAP=0 still answers from a live channel. The refusal
        is logged, the handshake counts as done for this boot, and the round goes on to CFUN; only no answer at all
        (a timeout, the lock busy, no final result code) ends the round."""
        marker = self.tmp / 'run' / 'mu300-ril-handshake'
        for answer in ('ERROR', '+CME ERROR: 4'):
            with self.subTest(answer=answer):
                marker.unlink(missing_ok=True)
                (self.tmp / 'run' / 'mu300' / 'radio.log').unlink(missing_ok=True)
                r, sent, cmds = self.radio('rc=0; radio_on || rc=$?; echo "rc=$rc"', SMMSWAP=answer, RF_LAG=0)
                self.assertIn('rc=0', r.stdout, r.stderr)
                self.assertEqual(cmds[:3], ['AT+SMMSWAP=0', 'AT+CFUN?', 'AT+SFUN=4'], cmds)
                self.assertTrue(marker.exists())
                self.assertIn(f'refused the RIL handshake (AT+SMMSWAP=0): {answer}', self.radio_log())
        for answer in ('busy', 'garbage'):
            with self.subTest(answer=answer):
                marker.unlink(missing_ok=True)
                r, sent, cmds = self.radio('rc=0; radio_on || rc=$?; echo "rc=$rc"', SMMSWAP=answer)
                self.assertIn('rc=1', r.stdout, r.stderr)
                self.assertEqual(cmds, ['AT+SMMSWAP=0'])
                self.assertFalse(marker.exists())

    def test_waits_for_nr0_first(self):
        """Nothing is sent before nr0 has said something (the CP is still starting); the wait is bounded."""
        r, sent, cmds = self.radio(f'(sleep 1; echo "+CEREG: 2" > "{self.tmp}/stty_nr0.log") &\nradio_on; echo ok',
                                   urc=None, MU300_CFUN_WAIT=10)
        self.assertIn('ok', r.stdout, r.stderr)
        first = [s for s in sent if s[0].isdigit()][0]
        self.assertGreaterEqual(int(first.split()[0]), 1, sent)
        # nr0 never speaks: go ahead after MU300_CFUN_WAIT s anyway
        r, sent, cmds = self.radio('radio_on; echo "ok t=$SECONDS"', urc=None, MU300_CFUN_WAIT=1)
        self.assertRegex(r.stdout, r'ok t=[12]\b', r.stderr)
        self.assertIn('AT+SFUN=4', cmds)

    def test_no_sfun_when_cfun_is_unanswered(self):
        """A channel that does not answer AT+CFUN? gets no AT+SFUN either (K57)."""
        r, sent, cmds = self.radio('rc=0; radio_on || rc=$?; echo "rc=$rc"', CFUN='none')
        self.assertIn('rc=1', r.stdout, r.stderr)
        self.assertFalse([c for c in cmds if c.startswith('AT+SFUN')], cmds)
        self.assertIn('no answer to AT+CFUN?', self.radio_log())

    def test_radio_comes_up_late_without_a_power_cycle(self):
        """After AT+SFUN=4 the radio says 0 twice and then 1: wait for it, no SFUN=2 off/on cycle (K57)."""
        r, sent, cmds = self.radio('rc=0; radio_on || rc=$?; echo "rc=$rc t=$SECONDS"', RF_LAG=2)
        self.assertRegex(r.stdout, r'rc=0 t=[4-6]\b', r.stderr)
        self.assertEqual(cmds.count('AT+SFUN=4'), 1, cmds)
        self.assertNotIn('AT+SFUN=2', cmds)
        self.assertEqual(cmds.count('AT+CFUN?'), 4, cmds)     # before, then 0, 0, 1
        self.assertRegex(self.radio_log(), r'radio on [4-6] s after AT\+SFUN=4')
        # already on (and the handshake done this boot): one question, nothing switched
        r, sent, cmds = self.radio('radio_on; echo ok', CFUN=1)
        self.assertEqual(cmds, ['AT+CFUN?'])

    def test_two_radio_on_one_state_machine(self):
        """The warm-up and the dial meet: the second radio_on waits for the first instead of running its own CFUN/SFUN
        sequence beside it, and then finds the radio on (K57)."""
        r, sent, cmds = self.radio('radio_on & a=$!; radio_on & b=$!\n'
                                   'ra=0; wait $a || ra=$?; rb=0; wait $b || rb=$?; echo "ra=$ra rb=$rb"',
                                   SFUN_DELAY=1)
        self.assertIn('ra=0 rb=0', r.stdout, r.stderr)
        self.assertEqual(cmds.count('AT+SMMSWAP=0'), 1, cmds)
        self.assertEqual(cmds.count('AT+SFUN=4'), 1, cmds)
        self.assertEqual(cmds.count('AT+CFUN?'), 3, cmds)    # the first: 0, then 1; the second: 1
        self.assertEqual(self.radio_lock_files(), [])

    def radio_lock_files(self):
        return sorted(p.name for p in (self.tmp / 'run').iterdir() if p.name.startswith('mu300-radio-on'))

    # R32: radio_on's lock. A wrapped lock_owner_alive takes $DEAD_DELAY s (0.5) more over every "dead" verdict and
    # $ALIVE_DELAY s (0) over every "alive" one: two waiters can both see the dead owner before either acts on it.
    SLOW_DEAD = ('eval "orig_$(declare -f lock_owner_alive)"\n'
                 'lock_owner_alive() { if orig_lock_owner_alive "$@"; then sleep "${ALIVE_DELAY:-0}"; return 0; fi;'
                 ' sleep "${DEAD_DELAY:-0.5}"; return 1; }\n')

    def test_two_waiters_on_a_dead_owners_lock(self):
        """R32: the lock's owner was killed in the middle of its round (SIGKILL: nothing released). Two radio_on
        callers find it at the same moment: exactly one of them takes it over and runs the radio state machine,
        the other waits for that one and finds the radio on; nothing of the lock is left afterwards. The second one
        acts on its "dead" verdict only once the first has taken the lock over (the old lock removed that one)."""
        r, sent, cmds = self.radio(
            self.SLOW_DEAD +
            'SFUN_DELAY=5; ( radio_on ) >/dev/null 2>&1 & h=$!\n'
            'sleep 1; kill -9 $h; wait $h 2>/dev/null || true\n'
            'SFUN_DELAY=1\n'
            '( DEAD_DELAY=0.2; radio_on ) & a=$!; ( DEAD_DELAY=0.8; radio_on ) & b=$!\n'
            'ra=0; wait $a || ra=$?; rb=0; wait $b || rb=$?; echo "ra=$ra rb=$rb"', CFUN=0)
        self.assertIn('ra=0 rb=0', r.stdout, r.stderr)
        # the killed owner's AT+SFUN=4, then one more from the one that took over; never a third
        self.assertEqual(cmds.count('AT+SFUN=4'), 2, cmds)
        self.assertEqual(self.radio_lock_files(), [])

    def test_lock_holder_is_named_from_the_start(self):
        """R32: the lock never exists without its owner's pid (no window in which a waiter reads an empty owner
        and calls the lock dead)."""
        r, sent, cmds = self.radio(
            'SFUN_DELAY=2; ( radio_on ) >/dev/null 2>&1 & h=$!\n'
            f'sleep 1; echo "owner=$(readlink "{self.tmp}/run/mu300-radio-on.owner") h=$h"; wait $h')
        m = re.search(r'owner=(\d+) h=(\d+)', r.stdout)
        self.assertTrue(m, r.stdout + r.stderr)
        self.assertEqual(m.group(1), m.group(2))
        self.assertEqual(self.radio_lock_files(), [])

    def test_radio_lock_wait_is_in_seconds(self):
        """R32: MU300_RADIO_LOCK_WAIT is a deadline in real seconds, not a number of polls: with a slow liveness
        check (0.3 s each) a 2 s wait still ends after about 2 s."""
        r, sent, cmds = self.radio(
            self.SLOW_DEAD +
            'SFUN_DELAY=8; ( radio_on ) >/dev/null 2>&1 & h=$!\n'
            'sleep 1; ALIVE_DELAY=0.3; t0=$SECONDS; rc=0; radio_on || rc=$?; t=$((SECONDS - t0))\n'
            'kill -9 $h; echo "rc=$rc t=$t"', MU300_RADIO_LOCK_WAIT=2)
        self.assertRegex(r.stdout, r'rc=1 t=[23]\b', r.stderr)
        self.assertIn('still running; giving up', self.radio_log())

    def test_early_lock_replay_hook(self):
        """K65: the plugin's lock replay runs after the handshake and the radio-off answer, before AT+SFUN=4; only
        when the plugin is installed and has not replayed yet; a failed replay never stops the radio."""
        hook = self.tmp / 'lock'
        hook.write_text('#!/bin/sh\necho "- hook $*" >> "$STUBLOG/at"\nexit "${HOOK_RC:-0}"\n')
        hook.chmod(0o755)
        pending = self.tmp / 'run' / 'unisoc-modem-early-hook-pending'
        pending.parent.mkdir(exist_ok=True)
        pending.touch()
        r, sent, cmds = self.radio('radio_on; echo ok', MU300_PLUGIN_LOCK=hook)
        self.assertIn('ok', r.stdout, r.stderr)
        self.assertEqual(cmds[:4], ['AT+SMMSWAP=0', 'AT+CFUN?', 'hook replay early', 'AT+SFUN=4'], cmds)
        self.assertFalse(pending.exists())          # the plugin's generic worker may use nr1 now
        # no plugin: no hook
        r, sent, cmds = self.radio('radio_on; echo ok')
        self.assertNotIn('hook replay early', cmds)
        self.assertIn('AT+SFUN=4', cmds)
        # the plugin already replayed its locks this boot
        (self.tmp / 'run' / 'unisoc-modem-lock-replay-done').touch()
        r, sent, cmds = self.radio('radio_on; echo ok', MU300_PLUGIN_LOCK=hook)
        self.assertNotIn('hook replay early', cmds)
        (self.tmp / 'run' / 'unisoc-modem-lock-replay-done').unlink()
        # a failed replay: said in radio.log, the radio comes on all the same
        r, sent, cmds = self.radio('radio_on; echo ok', MU300_PLUGIN_LOCK=hook, HOOK_RC=1)
        self.assertIn('ok', r.stdout, r.stderr)
        self.assertIn('AT+SFUN=4', cmds)
        self.assertIn('early lock replay unverified; late fallback remains armed', self.radio_log())
        # a failed radio_on keeps the marker: the worker stays away from nr1 until a round succeeds
        pending.touch()
        r, sent, cmds = self.radio('radio_on || echo failed', CFUN='none', MU300_PLUGIN_LOCK=hook)
        self.assertIn('failed', r.stdout, r.stderr)
        self.assertNotIn('hook replay early', cmds)
        self.assertTrue(pending.exists())

    # suspend/resume: mu300-power takes the modem down while nobody uses the device. radio_on and up are replaced by a
    # line in the AT log (their own sequences are tested elsewhere); down is the real one, on the scratch run/.
    # radio_on also notes whether the mode file is still there; AT+SPENDC? answers "+ENDC: $ENDC" (1 by default).
    SUSPEND_STUBS = ('radio_on() { at RADIO_ON; [ ! -e "$SUSPEND" ] || at SUSPEND_FILE_STILL_THERE; }\n'
                     'up() { at UP; [ ! -e "$SUSPEND" ] || at SUSPEND_FILE_STILL_THERE; }\n')

    def suspend_lib(self, code, **env):
        modem = self.MODEM.replace("        'AT+COPS?')",
                                   "        'AT+SPENDC?') printf '+ENDC: %s\\nOK\\n' \"${ENDC:-1}\" ;;\n        'AT+COPS?')")
        return self.lib(self.SUSPEND_STUBS + code, modem=modem, MU300_AT_DEV='/dev/null', **env)

    def test_suspend_off_takes_the_radio_down_and_stops_the_watcher(self):
        r, sent = self.suspend_lib('do_suspend off; do_suspend off')
        self.assertEqual(r.returncode, 0, r.stderr)
        run = self.tmp / 'run'
        self.assertEqual((run / 'mu300-mobile-data.suspend').read_text().strip(), 'off')
        self.assertTrue((run / 'mu300-mobile-data-down').exists())
        # the second call found the file and did nothing more
        self.assertEqual(len([c for c in sent if 'AT+SFUN=5' in c]), 1, sent)
        self.assertFalse((run / 'mu300-radio-on.owner').exists())   # the radio lock is released

    def test_suspend_lte_switches_endc_off_and_resume_restores(self):
        """EN-DC off is AT+SPENDC=2 and on is 1 (the lock adapter's values); no stack restart, radio_on or dial."""
        r, sent = self.suspend_lib('do_suspend lte\n'
                                   f'cat "{self.tmp}/run/mu300-mobile-data.suspend"; ls "{self.tmp}/run"\n'
                                   'echo ---; resume; echo resumed')
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout.split('---')[0]
        self.assertIn('lte\nmu300-mobile-data.suspend', out)
        self.assertNotIn('mu300-mobile-data-down', out)   # data stays up on LTE
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())
        cmds = [c.split(' ', 1)[1] for c in sent]
        self.assertEqual(cmds, ['AT+SPENDC?', 'AT+SPENDC=2', 'AT+SPENDC=1'])
        self.assertFalse((self.tmp / 'run' / 'mu300-radio-on.owner').exists())

    def test_resume_lte_leaves_endc_off_when_the_user_had_it_off(self):
        r, sent = self.suspend_lib('do_suspend lte; ls "$SUSPEND_ENDC" >/dev/null && echo noted; resume; echo resumed', ENDC='2')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('noted', r.stdout)
        cmds = [c.split(' ', 1)[1] for c in sent]
        self.assertEqual(cmds, ['AT+SPENDC?'])   # already off: nothing written, nothing restored
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend-endc').exists())
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())

    def test_resume_off_brings_radio_and_data_back_and_drops_the_mode_file_last(self):
        r, sent = self.suspend_lib('do_suspend off; resume')
        self.assertEqual(r.returncode, 0, r.stderr)
        cmds = [c.split(' ', 1)[1] for c in sent]
        self.assertEqual(cmds[-4:], ['RADIO_ON', 'SUSPEND_FILE_STILL_THERE', 'UP', 'SUSPEND_FILE_STILL_THERE'])
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data-down').exists())

    def test_suspend_waits_for_a_radio_dial_in_flight(self):
        """The raw AT sequence takes the radio lock: with it held (and no wait) nothing is sent and no mode is left."""
        r, sent = self.suspend_lib(f'ln -s $$ "{self.tmp}/run/mu300-radio-on.owner"; rc=0; do_suspend lte || rc=$?; echo rc=$rc',
                                   MU300_RADIO_LOCK_WAIT='0')
        self.assertIn('rc=1', r.stdout, r.stderr)
        self.assertEqual(sent, [])
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())

    # netifd (OpenWrt, MU300_NETIFD=1) owns the WAN's address, routes, DNS and firewall: suspend off takes it down
    # with ifdown and resume brings it back with ifup; neither touches sipa_eth0 itself. ifdown/ifup are stubs.
    def netifd_stubs(self):
        for name in ('ifdown', 'ifup', 'ip', 'nft'):
            self.stub(name, f'echo "{name} $* suspend=$([ -e "$MU300_RUN_DIR/mu300-mobile-data.suspend" ] && echo yes || echo no)" >> "$STUBLOG/calls"')

    def test_suspend_off_under_netifd_is_ifdown(self):
        self.netifd_stubs()
        r, sent = self.suspend_lib('do_suspend off', MU300_NETIFD='1', MU300_RUN_DIR=self.tmp / 'run')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = (self.tmp / 'calls').read_text()
        self.assertIn('ifdown wan', calls)
        self.assertNotIn('ip ', calls); self.assertNotIn('nft', calls)   # down() was not run
        cmds = [c.split(' ', 1)[1] for c in sent]
        self.assertEqual(cmds, ['AT+SFUN=5'])
        self.assertEqual((self.tmp / 'run' / 'mu300-mobile-data.suspend').read_text().strip(), 'off')

    def test_resume_under_netifd_redials_with_ifup(self):
        self.netifd_stubs()
        r, sent = self.suspend_lib('do_suspend off; resume', MU300_NETIFD='1', MU300_RUN_DIR=self.tmp / 'run')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = (self.tmp / 'calls').read_text()
        # netifd's dial runs `mobile-data up` in a process of its own: the mode file is gone before the ifup
        self.assertIn('ifup wan suspend=no', calls)
        cmds = [c.split(' ', 1)[1] for c in sent]
        self.assertIn('RADIO_ON', cmds); self.assertNotIn('UP', cmds)
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data-down').exists())

    def test_resume_nodial_switches_the_radio_on_and_leaves_the_dial_to_the_watcher(self):
        self.netifd_stubs()
        (self.tmp / 'run').mkdir(exist_ok=True)
        (self.tmp / 'run' / 'mu300-mobile-data-down').touch()
        r, sent = self.suspend_lib('do_suspend off; resume nodial', MU300_RUN_DIR=self.tmp / 'run')
        self.assertEqual(r.returncode, 0, r.stderr)
        cmds = [c.split(' ', 1)[1] for c in sent]
        self.assertIn('RADIO_ON', cmds); self.assertNotIn('UP', cmds)
        self.assertNotIn('ifup', (self.tmp / 'calls').read_text() if (self.tmp / 'calls').exists() else '')
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data-down').exists())
        # lte: EN-DC back on, the files gone, still no dial
        r, sent = self.suspend_lib('do_suspend lte; resume nodial')
        self.assertEqual([c.split(' ', 1)[1] for c in sent][-1], 'AT+SPENDC=1')
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend').exists())
        self.assertFalse((self.tmp / 'run' / 'mu300-mobile-data.suspend-endc').exists())

    def test_up_refuses_while_suspended_off_except_from_resume(self):
        (self.tmp / 'run').mkdir(exist_ok=True)
        (self.tmp / 'run' / 'mu300-mobile-data.suspend').write_text('off\n')
        # the real up; up_locked stands for the dial
        code = 'up_locked() { at DIAL; }\n'
        for env in ({}, {'MU300_NETIFD': '1'}):
            r, sent = self.lib(code + 'rc=0; up || rc=$?; echo rc=$rc', MU300_AT_DEV='/dev/null', **env)
            self.assertIn('rc=1', r.stdout, r.stderr)
            self.assertIn('suspended', r.stderr)
            self.assertEqual(sent, [])
        r, sent = self.lib(code + 'rc=0; ( _resuming=1; up ) || rc=$?; echo rc=$rc', MU300_AT_DEV='/dev/null')
        self.assertIn('rc=0', r.stdout, r.stderr)
        self.assertEqual([c.split(' ', 1)[1] for c in sent], ['DIAL'])
        # resume's own dial passes (redial sets the flag); suspend lte leaves up alone
        r, sent = self.lib(code + 'radio_on() { at RADIO_ON; }; resume', MU300_AT_DEV='/dev/null')
        self.assertEqual([c.split(' ', 1)[1] for c in sent], ['RADIO_ON', 'DIAL'], r.stderr)
        (self.tmp / 'run' / 'mu300-mobile-data.suspend').write_text('lte\n')
        r, sent = self.lib(code + 'up', MU300_AT_DEV='/dev/null')
        self.assertEqual([c.split(' ', 1)[1] for c in sent], ['DIAL'], r.stderr)

    def test_watch_skips_rounds_while_suspended(self):
        (self.tmp / 'run').mkdir(exist_ok=True)
        (self.tmp / 'run' / 'mu300-mobile-data.suspend').write_text('off\n')
        r, sent = self.lib('watch', MU300_AT_DEV='/dev/null', MU300_WATCH_INTERVAL='0', MU300_WATCH_ROUNDS='2')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sent, [])

    # 2026-10-07: `mobile-data suspend off` after `suspend lte` never returned on the U30 Air, and the device stayed dark
    # for hours. suspend/resume now end within MU300_SUSPEND_DEADLINE whatever the modem does. Here the real at() talks
    # to an nr2 daemon whose client never answers (a mu300-at that sleeps): the whole command must come back in time,
    # non-zero, every process it started gone, and the files must hand the modem back to the watcher.
    def silent_modem(self):
        hang = self.tmp / 'hang'
        hang.mkdir(exist_ok=True)
        (hang / 'mu300-at').write_text('#!/bin/sh\necho "$* lockwait=$MU300_AT_LOCK_WAIT budget=$MU300_AT_BUDGET" >> "$STUBLOG/hangat"\n'
                                       'echo $$ >> "$STUBLOG/hung.pids"\nexec sleep 1000\n')
        (hang / 'mu300-at').chmod(0o755)
        (self.tmp / 'run' / 'mu300-at2').mkdir(parents=True, exist_ok=True)
        if not (self.tmp / 'run' / 'mu300-at2' / 'cmd').exists():
            os.mkfifo(self.tmp / 'run' / 'mu300-at2' / 'cmd')
        return 'unset -f at; . "$STUBLOG/mobile-data.lib"; PATH="$STUBLOG/hang:$PATH"\n'

    def assert_all_killed(self):
        import time
        pids = [int(p) for p in (self.tmp / 'hung.pids').read_text().split()]
        for pid in pids:
            for _ in range(50):
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                self.fail(f'pid {pid} still runs')

    def test_suspend_and_resume_end_in_time_with_a_modem_that_never_answers(self):
        cases = [('', 'suspend off', {}),
                 ('lte', 'suspend off', {}),                 # the incident: suspend lte, then suspend off
                 ('', 'suspend lte', {}),
                 ('off', 'resume', {}),
                 ('lte', 'resume', {}),
                 ('off', 'resume nodial', {}),
                 ('', 'suspend off', {'MU300_NETIFD': '1'})]
        for before, cmd, env in cases:
            with self.subTest(before=before, cmd=cmd, **env):
                run = self.tmp / 'run'
                for f in ('mu300-mobile-data.suspend', 'mu300-mobile-data-down', 'mu300-mobile-data.endc-restore',
                          'hung.pids', 'hangat'):
                    (run / f).unlink(missing_ok=True); (self.tmp / f).unlink(missing_ok=True)
                code = self.silent_modem()
                if before:
                    (run / 'mu300-mobile-data.suspend').write_text(before + '\n')
                if 'netifd' in str(env) or env:
                    self.stub('ifdown', 'exit 0'); self.stub('ifup', 'exit 0')
                r, _ = self.lib(code + f'SECONDS=0; rc=0; bounded {cmd} || rc=$?; echo "rc=$rc took=$SECONDS"',
                                MU300_SUSPEND_DEADLINE='3', MU300_MD_STEP_DEADLINE='2', MU300_CFUN_WAIT='0',
                                MU300_URC_LOG=str(self.tmp / 'urc.log'), **env)
                m = re.search(r'rc=(\d+) took=(\d+)', r.stdout)
                self.assertTrue(m, r.stdout + r.stderr)
                self.assertNotEqual(m.group(1), '0', r.stderr)
                self.assertLessEqual(int(m.group(2)), 8, r.stderr)
                self.assertIn('the modem is left to the watcher', r.stderr)
                # consistent: no mode file and no "down" flag, so the watcher restores whatever is off
                self.assertFalse((run / 'mu300-mobile-data.suspend').exists())
                self.assertFalse((run / 'mu300-mobile-data-down').exists())
                # EN-DC may be off by our hand after a failed lte step: noted, so a later resume switches it back on
                self.assertEqual((run / 'mu300-mobile-data.endc-restore').exists(), 'lte' in (before, cmd.split()[-1]))
                self.assert_all_killed()
                # every AT went through mu300-at with a short timeout, client-lock wait and budget
                for line in (self.tmp / 'hangat').read_text().splitlines():
                    m = re.match(r'-t (\d+) .* lockwait=(\d+) budget=(\d+)$', line)
                    self.assertTrue(m, line)
                    self.assertLessEqual(int(m.group(1)), 20, line)
                    self.assertLessEqual(int(m.group(2)), 10, line)
                    self.assertLessEqual(int(m.group(3)), 22, line)
                    self.assertGreaterEqual(int(m.group(3)), int(m.group(1)) + 2, line)   # budget >= T + 2

    def test_endc_left_off_by_a_failed_lte_step_is_restored_by_the_next_resume(self):
        run = self.tmp / 'run'
        run.mkdir(exist_ok=True)
        marker = run / 'mu300-mobile-data.endc-restore'
        # the modem says ERROR: the marker stays and resume fails, so mu300-power tries again
        marker.touch()
        err = self.MODEM.replace("        *) printf 'OK\\n' ;;", "        'AT+SPENDC=1') printf 'ERROR\\n' ;;\n        *) printf 'OK\\n' ;;")
        r, sent = self.lib(self.SUSPEND_STUBS + 'rc=0; resume || rc=$?; echo rc=$rc', modem=err, MU300_AT_DEV='/dev/null')
        self.assertIn('rc=1', r.stdout, r.stderr)
        self.assertTrue(marker.exists())
        # OK: EN-DC back on, the marker gone; no mode file was needed for it
        r, sent = self.suspend_lib('rc=0; resume || rc=$?; echo rc=$rc')
        self.assertIn('rc=0', r.stdout, r.stderr)
        self.assertEqual([c.split(' ', 1)[1] for c in sent], ['AT+SPENDC=1'])
        self.assertFalse(marker.exists())
        # the watcher does not stand aside for it
        marker.touch()
        r, sent = self.lib('watch', MU300_AT_DEV='/dev/null', MU300_WATCH_INTERVAL='0', MU300_WATCH_ROUNDS='1')
        self.assertTrue(sent, r.stderr)

    def test_an_error_to_endc_on_leaves_the_restore_marker(self):
        """Re-review D4: mu300-at exits 0 on ERROR. A resume lte whose AT+SPENDC=1 is answered ERROR must leave the
        restore marker (the files go, the watcher keeps working) and fail, so the next resume tries again."""
        run = self.tmp / 'run'
        run.mkdir(exist_ok=True)
        stubdir = self.tmp / 'errat'
        stubdir.mkdir(exist_ok=True)
        (stubdir / 'mu300-at').write_text('#!/bin/sh\n[ "$1" = -t ] && shift 2\necho "$1" >> "$STUBLOG/errat.log"\n'
                                          'case $1 in AT+SPENDC=1) echo ERROR ;; esac\nexit 0\n')
        (stubdir / 'mu300-at').chmod(0o755)
        (run / 'mu300-at2').mkdir(parents=True, exist_ok=True)
        if not (run / 'mu300-at2' / 'cmd').exists():
            os.mkfifo(run / 'mu300-at2' / 'cmd')
        (run / 'mu300-mobile-data.suspend').write_text('lte\n')
        r, _ = self.lib('unset -f at; . "$STUBLOG/mobile-data.lib"; PATH="$STUBLOG/errat:$PATH"\n'
                        'rc=0; bounded resume || rc=$?; echo rc=$rc', MU300_URC_LOG=str(self.tmp / 'urc.log'))
        self.assertNotIn('rc=0', r.stdout, r.stderr)
        self.assertIn('AT+SPENDC=1', (self.tmp / 'errat.log').read_text())
        self.assertTrue((run / 'mu300-mobile-data.endc-restore').exists())
        self.assertFalse((run / 'mu300-mobile-data.suspend').exists())

    def test_a_failed_suspend_keeps_a_down_flag_that_was_there_before(self):
        run = self.tmp / 'run'
        run.mkdir(exist_ok=True)
        (run / 'mu300-mobile-data-down').touch()   # `mobile-data down` by hand: the watcher stays aside
        code = self.silent_modem()
        r, _ = self.lib(code + 'rc=0; bounded suspend off || rc=$?; echo rc=$rc', MU300_SUSPEND_DEADLINE='3',
                        MU300_MD_STEP_DEADLINE='1', MU300_URC_LOG=str(self.tmp / 'urc.log'))
        self.assertNotIn('rc=0', r.stdout)
        self.assertTrue((run / 'mu300-mobile-data-down').exists())
        self.assertFalse((run / 'mu300-mobile-data.suspend').exists())

    def test_bounded_suspend_succeeds_and_ignores_a_hangup(self):
        """The command outlives the terminal that started it (an SSH session over the Wi-Fi it took down)."""
        r, sent = self.suspend_lib('( sleep 0.3; kill -HUP $$ ) & at() { sleep 1; echo "$SECONDS $1" >> "$STUBLOG/at"; echo OK; }\n'
                                   'rc=0; bounded suspend off || rc=$?; echo "rc=$rc"')
        self.assertIn('rc=0', r.stdout, r.stderr)
        self.assertIn('modem suspended (off)', r.stderr)
        self.assertEqual((self.tmp / 'run' / 'mu300-mobile-data.suspend').read_text().strip(), 'off')

    def test_the_commands_go_through_the_deadline(self):
        text = (BIN / 'mobile-data').read_text()
        case = text[text.index('\ncase "${1:-status}" in'):]
        self.assertIn('suspend) bounded suspend', case)
        self.assertIn('bounded resume', case)

    def test_radio_on_subcommand(self):
        """K66: `mobile-data radio-on` switches the radio on and asks for the IMS bearer (K58), nothing more."""
        text = (BIN / 'mobile-data').read_text()
        case = text[text.index('\ncase "${1:-status}" in'):]
        self.assertRegex(case, r'\n    radio-on\)')
        r, sent, cmds = self.radio('main() { set -- radio-on' + case + '\n}\nmain; echo ok',
                                   MU300_AT_DEV='/dev/null')
        self.assertIn('ok', r.stdout, r.stderr)
        self.assertEqual(cmds, ['AT+SMMSWAP=0', 'AT+CFUN?', 'AT+SFUN=4', 'AT+CFUN?', 'AT+CAVIMS=1'])

    def test_background_at_owns_the_lock_itself(self):
        """R30: at() on the direct path (no daemon) in a background subshell writes its own pid into the AT lock, not
        the parent's: the lock owner has to be the process that is reading the channel."""
        r, _ = self.lib('unset -f at; . "$STUBLOG/mobile-data.lib"\n'
                        '( at AT 2 >/dev/null ) & bg=$!\n'
                        f'sleep 0.5; echo "owner=$(cat "{self.tmp}/run/mu300-at/owner/pid") bg=$bg parent=$$"; wait',
                        MU300_AT_DEV='/dev/null')
        m = re.search(r'owner=(\d+) bg=(\d+) parent=(\d+)', r.stdout)
        self.assertTrue(m, r.stdout + r.stderr)
        self.assertEqual(m.group(1), m.group(2))
        self.assertNotEqual(m.group(1), m.group(3))


class RadioLocked(ShellTest):
    """mobile-data radio-locked CMD / radio-busy: another program's radio sequence (the LuCI panel's) runs under the
    radio lock radio_on takes, held by mobile-data itself; a held lock is "busy" (75), nothing run (final review
    minor 3). mobile-data is copied (still named mobile-data: lock_owner_alive knows the holder by that name) with
    /run/ in the scratch directory."""

    def setUp(self):
        super().setUp()
        if not shutil.which('bash'):
            self.skipTest('no bash')
        (self.tmp / 'run').mkdir()
        self.md = self.tmp / 'mobile-data'
        self.md.write_text((BIN / 'mobile-data').read_text().replace('/run/', f'{self.tmp}/run/'))
        self.md.chmod(0o755)
        self.link = self.tmp / 'run' / 'mu300-radio-on.owner'

    def run_md(self, *args, **env):
        return subprocess.run(['bash', str(self.md)] + list(args), capture_output=True, text=True, timeout=30,
                              env=self.env(**env))

    def test_runs_the_command_holding_the_lock(self):
        r = self.run_md('radio-locked', 'sh', '-c', f'readlink "{self.link}"; exit 3')
        self.assertEqual(r.returncode, 3, r.stderr)        # the command's own status
        self.assertTrue(r.stdout.strip().isdigit(), r.stdout)
        self.assertFalse(os.path.lexists(self.link))         # dropped again
        self.assertEqual(self.run_md('radio-busy').returncode, 1)

    def test_a_held_lock_is_busy_and_nothing_runs(self):
        holder = subprocess.Popen(['bash', str(self.md), 'radio-locked', 'sleep', '3'], env=self.env())
        try:
            deadline = time.monotonic() + 10
            while not os.path.lexists(self.link) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(os.readlink(self.link), str(holder.pid))
            r = self.run_md('radio-busy')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, str(holder.pid)))
            t0 = time.monotonic()
            r = self.run_md('radio-locked', 'touch', str(self.tmp / 'ran'))
            self.assertEqual(r.returncode, 75, r.stderr)
            self.assertIn('busy', r.stderr)
            self.assertLess(time.monotonic() - t0, 5)         # no wait by default
            self.assertFalse((self.tmp / 'ran').exists())
            # TERM: the holder keeps the lock while its command still runs, and drops it on its way out
            holder.terminate()
            time.sleep(0.5)
            self.assertTrue(os.path.lexists(self.link))
            holder.wait(timeout=10)
            self.assertFalse(os.path.lexists(self.link))
        finally:
            if holder.poll() is None:
                holder.kill()
                holder.wait()

    def test_a_dead_holder_is_taken_over(self):
        dead = subprocess.Popen(['true'])
        dead.wait()
        os.symlink(str(dead.pid), self.link)
        self.assertEqual(self.run_md('radio-busy').returncode, 1)
        r = self.run_md('radio-locked', 'touch', str(self.tmp / 'ran'))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.tmp / 'ran').exists())


class SipaDele(ShellTest):
    """K45, K46: extra-modules and sipa-dele-start, copied with /lib/modules, /proc/modules, /opt/mu300/bin and
    /dev/stty_nr1 pointed at the scratch directory (and /dev/null); uname, insmod, modprobe, dmesg, sleep, mu300-at
    and sipa-dele-start are stubs that write what they were asked to $STUBLOG/calls."""

    def setUp(self):
        super().setUp()
        self.mods = self.tmp / 'lib' / 'modules' / '5.4.test'
        self.mods.mkdir(parents=True)
        self.stub('uname', 'echo 5.4.test')
        self.stub('insmod', 'echo "insmod $*" >> "$STUBLOG/calls"\nexit "${INSMOD_RC:-0}"')
        self.stub('modprobe', 'echo "modprobe $*" >> "$STUBLOG/calls"')
        # the sbuf lines from the modem loader's start may have left the ring buffer long ago: not asked for
        self.stub('dmesg', 'echo "[  80.1] sipa_dele: channel 5-120 send open msg"')
        self.stub('sleep', ':')
        self.stub('mu300-at', 'echo "mu300-at $*" >> "$STUBLOG/calls"\nprintf "%s\\nOK\\n" "${CGATT:-+CGATT: 1}"')
        self.stub('sipa-dele-start', 'echo "sipa-dele-start" >> "$STUBLOG/calls"')

    def copy(self, name):
        text = (BIN / name).read_text()
        for a, b in (('/lib/modules/', f'{self.tmp}/lib/modules/'), ('/proc/modules', f'{self.tmp}/proc-modules'),
                     ('/opt/mu300/bin/', f'{self.stubs}/'), ('/dev/stty_nr1', '/dev/null')):
            text = text.replace(a, b)
        p = self.tmp / name
        p.write_text(text)
        return p

    def run_script(self, shell, name, modules='', **env):
        (self.tmp / 'proc-modules').write_text(modules)
        (self.tmp / 'calls').unlink(missing_ok=True)
        r = self.script(shell, self.copy(name), **env)
        time.sleep(0.3)   # anything started in the background has written its line by now
        calls = (self.tmp / 'calls').read_text() if (self.tmp / 'calls').exists() else ''
        return r, calls

    def test_extra_modules_never_starts_the_delegate(self):
        """K45: on every system (OpenWrt's flat modules and Ubuntu's extra/), extra-modules leaves the delegate to
        mobile-data: it neither starts sipa-dele-start nor inserts the module itself."""
        for ko in (self.mods / 'sipa-dele.ko', self.mods / 'extra' / 'sipa-dele.ko'):
            ko.parent.mkdir(exist_ok=True)
            ko.write_text('')
            for shell in self.each_shell():
                r, calls = self.run_script(shell, 'extra-modules')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn('modprobe mali_kbase', calls)       # it did run
                self.assertNotIn('sipa-dele-start', calls)
                self.assertNotIn('sipa-dele', calls.replace('sipa-dele-start', ''))
            ko.unlink()

    def test_refuses_after_the_wait(self):
        """K46: the packet domain never comes up: exit 1 after MU300_DELE_WAIT s, the module is not inserted."""
        (self.mods / 'sipa-dele.ko').write_text('')
        for shell in self.each_shell():
            t = time.monotonic()
            r, calls = self.run_script(shell, 'sipa-dele-start', MU300_DELE_WAIT=1, CGATT='+CGATT: 0')
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('mu300-at -t 8 AT+CGATT?', calls)
            self.assertNotIn('insmod', calls)
            self.assertIn('refusing', r.stdout)
            self.assertLess(time.monotonic() - t, 8)   # a deadline in seconds (sleep is a no-op here)

    def test_loads_once_the_packet_domain_is_attached(self):
        """+CGATT: 1: the module is inserted from where the system keeps it (flat on OpenWrt, extra/ on Ubuntu)."""
        for sub in ('', 'extra'):
            ko = self.mods / sub / 'sipa-dele.ko'
            ko.parent.mkdir(exist_ok=True)
            ko.write_text('')
            for shell in self.each_shell():
                r, calls = self.run_script(shell, 'sipa-dele-start', MU300_DELE_WAIT=20)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertEqual([c for c in calls.splitlines() if c.startswith('insmod')], [f'insmod {ko}'])
            ko.unlink()

    def test_failures_and_nothing_to_do(self):
        """insmod fails: exit 1 (the dial must not go on). Already loaded, or no module in this kernel: exit 0,
        nothing inserted."""
        (self.mods / 'sipa-dele.ko').write_text('')
        for shell in self.each_shell():
            r, calls = self.run_script(shell, 'sipa-dele-start', MU300_DELE_WAIT=20, INSMOD_RC=1)
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn('FAILED', r.stdout)
            r, calls = self.run_script(shell, 'sipa-dele-start', 'sipa_dele 16384 0 - Live 0x0 (O)\n',
                                       MU300_DELE_WAIT=20)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(calls, '')
        (self.mods / 'sipa-dele.ko').unlink()
        for shell in self.each_shell():
            r, calls = self.run_script(shell, 'sipa-dele-start', MU300_DELE_WAIT=20)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertNotIn('insmod', calls)


class Bootmark(ShellTest):
    """bootmark (K42): one "t=<uptime> words" line per call on tmpfs, -r empties, never fails."""

    def test_two_calls_two_lines_and_reset_empties(self):
        up = self.tmp / 'uptime'
        up.write_text('12.34 56.78\n')
        os.environ['MU300_UPTIME'] = str(up)
        self.addCleanup(os.environ.pop, 'MU300_UPTIME', None)
        for shell in self.each_shell():
            f = self.tmp / 'run' / 'boot-timeline'   # its directory does not exist yet: bootmark creates it
            shutil.rmtree(f.parent, ignore_errors=True)
            for words in ('first mark', 'second'):
                r = self.script(shell, BIN / 'bootmark', *words.split(), MU300_TIMELINE=str(f))
                self.assertEqual(r.returncode, 0, shell)
            lines = f.read_text().splitlines()
            self.assertEqual(len(lines), 2, shell)
            self.assertRegex(lines[0], r'^t=12\.34 +first mark$', shell)
            self.assertRegex(lines[1], r'^t=12\.34 +second$', shell)
            self.script(shell, BIN / 'bootmark', '-r', 'fresh', MU300_TIMELINE=str(f))
            self.assertEqual(len(f.read_text().splitlines()), 1, shell)
            self.assertIn(' fresh', f.read_text(), shell)
            self.script(shell, BIN / 'bootmark', '-r', MU300_TIMELINE=str(f))
            self.assertEqual(f.read_text().strip(), '', shell)

    def test_unwritable_path_is_exit_zero(self):
        for shell in self.each_shell():
            for path in ('/proc/nonexistent/x/boot-timeline', str(self.tmp)):   # no such directory; a directory
                r = self.script(shell, BIN / 'bootmark', 'x', MU300_TIMELINE=path)
                self.assertEqual(r.returncode, 0, (shell, path))
                r = self.script(shell, BIN / 'bootmark', '-r', 'x', MU300_TIMELINE=path)
                self.assertEqual(r.returncode, 0, (shell, path))

    def test_the_default_is_on_tmpfs_and_the_callers_guard_it(self):
        self.assertIn('${MU300_TIMELINE:-/run/mu300/boot-timeline}', (BIN / 'bootmark').read_text())
        self.assertTrue(os.access(BIN / 'bootmark', os.X_OK))
        for f in (BIN / 'android-vendor-start', BIN / 'mobile-data',
                  TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d' / 'mu300-atd'):
            text = f.read_text()
            self.assertRegex(text, r'\[ -x /opt/mu300/bin/bootmark \] && /opt/mu300/bin/bootmark .*\|\| true', f.name)
            # no bare call: every bootmark call sits behind the guard or inside mark()
            self.assertNotRegex(text, r'(?m)^\s*/opt/mu300/bin/bootmark', f.name)
        self.assertIn('bootmark S19-atd-init', (TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d' / 'mu300-atd').read_text())


class VendorStart(ShellTest):
    """android-vendor-start (K40, K41): the partition links without forks, and no sleep after logdw."""

    def test_link_partitions_from_a_fake_sysfs(self):
        text = (BIN / 'android-vendor-start').read_text()
        body = text[text.index('\nlink_partitions() {'):text.index('\n}\n', text.index('\nlink_partitions() {')) + 3]
        sysdir, dev = self.tmp / 'sys', self.tmp / 'dev'
        (dev / 'block' / 'by-name').mkdir(parents=True)
        for name, uevent in (('mmcblk0p1', 'MAJOR=179\nMINOR=1\nPARTNAME=boot_a\nDEVTYPE=partition\n'),
                             ('mmcblk0p2', 'MAJOR=179\nMINOR=2\nPARTNAME=system a=b\n'),
                             ('mmcblk0p3', 'MAJOR=179\nMINOR=3\n')):    # no PARTNAME: only the block link
            (sysdir / name).mkdir(parents=True)
            (sysdir / name / 'uevent').write_text(uevent)
        (sysdir / 'mmcblk0boot0').mkdir()   # not a partition: not matched by mmcblk0p*
        for shell in self.each_shell():
            r = self.sh(shell, body + f'\nlink_partitions {sysdir} {dev}')
            self.assertEqual(r.returncode, 0, (shell, r.stderr))
            links = {p.relative_to(dev).as_posix(): os.readlink(p) for p in dev.rglob('*') if p.is_symlink()}
            self.assertEqual(links, {
                'block/mmcblk0p1': f'{dev}/mmcblk0p1', 'block/mmcblk0p2': f'{dev}/mmcblk0p2',
                'block/mmcblk0p3': f'{dev}/mmcblk0p3',
                'block/by-name/boot_a': f'{dev}/mmcblk0p1', 'block/by-name/system a=b': f'{dev}/mmcblk0p2'}, shell)
            # a second run over existing links is fine, and an absent sysfs is not an error
            self.assertEqual(self.sh(shell, body + f'\nlink_partitions {sysdir} {dev}').returncode, 0, shell)
            self.assertEqual(self.sh(shell, body + f'\nlink_partitions {self.tmp}/none {dev}').returncode, 0, shell)
            shutil.rmtree(dev / 'block'); (dev / 'block' / 'by-name').mkdir(parents=True)

    def test_slot_without_the_initramfs_file(self):
        # a boot image from before the slot work publishes no /run/mu300/linux-slot: under set -e the script must
        # go on with the slot from the command line, not end before modem_control (seen on F50 #1: no modem)
        text = (BIN / 'android-vendor-start').read_text()
        m = re.search(r'# --- slot begin\n(.*?)# --- slot end', text, re.S)
        self.assertIsNotNone(m, 'android-vendor-start has no slot block')
        cmd = self.tmp / 'cmdline'
        run = self.tmp / 'run'
        for shell in self.each_shell():
            for slot, want in (('a', 'L=a AS=b'), ('b', 'L=b AS=a')):
                cmd.write_text(f'console=ttyS1 androidboot.slot_suffix=_{slot} quiet')
                r = self.sh(shell, f'set -e\nsrc={cmd}\n' + m.group(1) + 'echo "L=$L AS=$AS"', MU300_RUN=run)
                self.assertEqual(r.stdout.strip(), want, (shell, r.stderr))
            (run / 'mu300').mkdir(parents=True, exist_ok=True)
            (run / 'mu300' / 'linux-slot').write_text('a\n')
            cmd.write_text('androidboot.slot_suffix=_b')
            r = self.sh(shell, f'set -e\nsrc={cmd}\n' + m.group(1) + 'echo "L=$L AS=$AS"', MU300_RUN=run)
            self.assertEqual(r.stdout.strip(), 'L=a AS=b', shell)
            shutil.rmtree(run)

    def test_no_forks_in_the_loop_and_no_sleep_after_logdw(self):
        text = (BIN / 'android-vendor-start').read_text()
        body = text[text.index('\nlink_partitions() {'):text.index('\n}\n', text.index('\nlink_partitions() {'))]
        for cmd in ('basename', 'dirname', 'sed', '$(', '`'):
            self.assertNotIn(cmd, body)
        self.assertNotRegex(text, r'logdw[^\n]*sleep 1')
        self.assertNotRegex(text, r'(?m)^\s*\[ -S /dev/socket/logdw \] \|\|')


class Os(ShellTest):
    """mu300-os against a fake disk area: three systems, and a kept copy is never offered."""
    def setUp(self):
        super().setUp()
        self.disk = self.tmp / 'disk'
        for name in ('ubuntu', 'openwrt', 'openwrt-luci', 'openwrt-luci.old'):
            init = self.disk / name / 'sbin' / 'init'
            init.parent.mkdir(parents=True)
            init.write_text('#!/bin/sh\n'); init.chmod(0o755)
            (self.disk / name / 'etc').mkdir()
        self.root = self.tmp / 'root'
        (self.root / 'etc' / 'mu300').mkdir(parents=True)
        (self.root / 'etc' / 'mu300' / 'default-boot').write_text('linux\n')
        self.stub('mountpoint', 'exit 0')

    def os(self, shell, *args):
        return self.script(shell, BIN / 'mu300-os', *args, MU300_DISK=self.disk, MU300_SYSROOT=self.root)

    def test_lists_the_third_system(self):
        for shell in self.each_shell():
            out = self.os(shell).stdout
            self.assertIn('openwrt-luci: installed', out)
            self.assertNotIn('.old', out)

    def test_choosing_it(self):
        for shell in self.each_shell():
            (self.disk / 'openwrt-luci' / 'etc' / 'mu300' / 'default-boot').unlink(missing_ok=True)
            r = self.os(shell, 'openwrt-luci')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.disk / '.mu300' / 'boot-os').read_text().strip(), 'openwrt-luci')
            self.assertEqual((self.disk / 'openwrt-luci' / 'etc' / 'mu300' / 'default-boot').read_text().strip(), 'linux')

    def test_a_kept_copy_cannot_be_chosen(self):
        for shell in self.each_shell():
            r = self.os(shell, 'openwrt-luci.old')
            self.assertEqual(r.returncode, 1)
            self.assertFalse((self.disk / '.mu300' / 'boot-os').exists())


class Led(ShellTest):
    # the U30 Air's: power is the battery LED's white (the PMIC's green channel), the network LED blue on 4G
    # (net_blue), white on 5G (zte-ldo0), red without service (keyboard-backlight); the Wi-Fi LED's colours are LDOs too
    LEDS = ['sc27xx:blue', 'sc27xx:red', 'sc27xx:green', 'net_blue', 'keyboard-backlight', 'zte-ldo0', 'zte-ldo1', 'zte-ldo2']

    def setUp(self):
        super().setUp()
        self.root = self.tmp / 'root'
        self.setUp_leds()
        (self.root / 'run' / 'mu300').mkdir(parents=True)
        (self.root / 'proc').mkdir()
        self.conf = self.tmp / 'led.conf'
        self.uptime(100)
        self.stub('iw', 'cat "$STUBLOG/iw.out" 2>/dev/null')

    def setUp_leds(self):
        for n in self.LEDS:
            d = self.root / 'sys' / 'class' / 'leds' / n
            d.mkdir(parents=True, exist_ok=True)
            (d / 'brightness').write_text('0\n')
            (d / 'max_brightness').write_text('255\n')
            (d / 'trigger').write_text('[none] timer\n')

    def uptime(self, s):
        (self.root / 'proc' / 'uptime').write_text(f'{s}.42 1234.00\n')

    def reset(self):
        for n in self.LEDS:
            (self.root / 'sys/class/leds' / n / 'brightness').write_text('0\n')
        for f in (self.root / 'run/mu300').glob('led/*'):
            f.unlink()
        for f in (self.root / 'run/mu300').glob('led/.awake-until'):
            f.unlink()
        self.conf.unlink(missing_ok=True)

    def state(self):
        return {n: (self.root / 'sys/class/leds' / n / 'brightness').read_text().strip() for n in self.LEDS}

    def led(self, shell, device, *args):
        (self.root / 'run/mu300/device').write_text(device + '\n')
        return self.script(shell, BIN / 'mu300-led', *args, MU300_SYSROOT=self.root, MU300_BIN=BIN,
                           MU300_LED_CONF=self.conf)

    def test_u30air(self):
        for shell in self.each_shell():
            self.reset()
            self.assertEqual(self.led(shell, 'u30air', 'power', 'on').returncode, 0)
            self.assertEqual(self.led(shell, 'u30air', 'data', 'error').returncode, 0)
            s = self.state()
            self.assertEqual((s['sc27xx:green'], s['keyboard-backlight'], s['net_blue']), ('255', '255', '0'))
            self.led(shell, 'u30air', 'data', 'on')
            s = self.state()
            self.assertEqual((s['keyboard-backlight'], s['net_blue']), ('0', '255'))
            self.led(shell, 'u30air', 'data', '5g')
            s = self.state()
            self.assertEqual((s['keyboard-backlight'], s['net_blue'], s['zte-ldo0']), ('0', '0', '255'))
            self.led(shell, 'u30air', 'data', 'on')           # back to 4G
            s = self.state()
            self.assertEqual((s['net_blue'], s['zte-ldo0']), ('255', '0'))
            self.led(shell, 'u30air', 'data', '5g')
            self.led(shell, 'u30air', 'data', 'error')
            s = self.state()
            self.assertEqual((s['keyboard-backlight'], s['net_blue'], s['zte-ldo0']), ('255', '0', '0'))
            self.led(shell, 'u30air', 'data', 'off')
            self.assertEqual(self.state()['net_blue'], '0')
            self.assertEqual(self.state()['sc27xx:blue'], '0')  # the F50's LED is not touched

    def test_wifi_colour_follows_the_band(self):
        for shell in self.each_shell():
            self.reset()
            self.led(shell, 'u30air', 'power', 'on')
            for iw, lit, dark in (('channel 36 (5180 MHz), width: 80 MHz', 'zte-ldo2', 'zte-ldo1'),
                                  ('channel 6 (2437 MHz), width: 20 MHz', 'zte-ldo1', 'zte-ldo2')):
                (self.tmp / 'iw.out').write_text(f'Interface wlan0\n\ttype AP\n\t{iw}\n')
                self.led(shell, 'u30air', 'wifi', 'on')
                s = self.state()
                self.assertEqual((s[lit], s[dark]), ('255', '0'), iw)
            self.led(shell, 'u30air', 'wifi', 'off')
            self.assertEqual((self.state()['zte-ldo2'], self.state()['zte-ldo1']), ('0', '0'))
            # the hotspot just started and has no channel yet: its setting decides
            (self.tmp / 'iw.out').write_text('Interface wlan0\n\ttype AP\n')
            conf = self.tmp / 'hotspot.conf'
            for band, lit in (('2.4', 'zte-ldo1'), ('5', 'zte-ldo2')):
                conf.write_text(f'SSID=x\nPSK=12345678\nBAND={band}\n')
                (self.root / 'run/mu300/device').write_text('u30air\n')
                self.script(shell, BIN / 'mu300-led', 'wifi', 'on', MU300_SYSROOT=self.root, MU300_BIN=BIN,
                            MU300_LED_CONF=self.conf, MU300_HOTSPOT_CONF=conf)
                self.assertEqual(self.state()[lit], '255', band)

    def test_timeout(self):
        for shell in self.each_shell():
            self.reset()
            self.uptime(100)
            self.led(shell, 'u30air', 'power', 'on')          # boot: lit for 60 s
            self.led(shell, 'u30air', 'data', 'on')
            self.uptime(150)
            self.led(shell, 'u30air', 'sleep', '--if-due')    # not yet
            self.assertEqual(self.state()['net_blue'], '255')
            self.uptime(161)
            self.led(shell, 'u30air', 'sleep', '--if-due')
            self.assertEqual({v for v in self.state().values()}, {'0'})
            # a change while dark is kept, and shown on the next wake
            self.led(shell, 'u30air', 'data', 'error')
            self.assertEqual(self.state()['keyboard-backlight'], '0')
            self.led(shell, 'u30air', 'wake')
            s = self.state()
            self.assertEqual((s['sc27xx:green'], s['keyboard-backlight'], s['net_blue']), ('255', '255', '0'))
            # and the timeout counts from the wake
            self.uptime(161 + 59)
            self.led(shell, 'u30air', 'sleep', '--if-due')
            self.assertEqual(self.state()['sc27xx:green'], '255')
            self.uptime(161 + 61)
            self.led(shell, 'u30air', 'sleep', '--if-due')
            self.assertEqual(self.state()['sc27xx:green'], '0')

    def test_idle_darkens_everything_but_a_key_still_shows_them(self):
        """2026-10-07: under the idle flag a key press lit nothing, and the device looked powered off for hours. A
        key's wake now shows the LEDs for LED_TIMEOUT (a minute when it is 0) in idle too; then dark again."""
        for shell in self.each_shell():
            for timeout, lit_for in (('', 60), ('LED_TIMEOUT=0\n', 60), ('LED_TIMEOUT=20\n', 20)):
                self.reset()
                self.uptime(100)
                if timeout:
                    self.conf.write_text(timeout)
                self.led(shell, 'u30air', 'power', 'on')
                self.led(shell, 'u30air', 'data', 'on')
                self.assertEqual(self.state()['net_blue'], '255')
                self.assertEqual(self.led(shell, 'u30air', 'idle', 'on').returncode, 0)
                self.assertEqual((self.state()['sc27xx:green'], self.state()['net_blue']), ('0', '0'))
                self.led(shell, 'u30air', 'data', '5g')                    # remembered, not shown
                self.led(shell, 'u30air', 'power', 'on')
                self.assertEqual(set(self.state().values()), {'0'}, timeout)
                self.led(shell, 'u30air', 'sleep', '--if-due')             # nothing to put out
                self.assertEqual(set(self.state().values()), {'0'}, timeout)
                # a key: lit, idle or not
                self.uptime(200)
                self.led(shell, 'u30air', 'wake')
                s = self.state()
                self.assertEqual((s['sc27xx:green'], s['zte-ldo0'], s['net_blue']), ('255', '255', '0'), timeout)
                self.led(shell, 'u30air', 'data', 'on')                    # a change meanwhile shows too
                self.assertEqual(self.state()['net_blue'], '255', timeout)
                self.uptime(200 + lit_for - 1)
                self.led(shell, 'u30air', 'sleep', '--if-due')
                self.assertEqual(self.state()['sc27xx:green'], '255', timeout)
                self.uptime(200 + lit_for + 1)
                self.led(shell, 'u30air', 'sleep', '--if-due')
                self.assertEqual(set(self.state().values()), {'0'}, timeout)   # still idle: dark again
                self.led(shell, 'u30air', 'data', 'on')
                self.assertEqual(self.state()['net_blue'], '0', timeout)
                # idle off: as LED_TIMEOUT says (0: always on; else from the last wake)
                self.led(shell, 'u30air', 'wake')
                self.led(shell, 'u30air', 'idle', 'off')
                s = self.state()
                self.assertEqual((s['sc27xx:green'], s['net_blue']), ('255', '255'), timeout)

    def test_idle_off_after_the_timeout_stays_dark(self):
        for shell in self.each_shell():
            self.reset()
            self.uptime(100)
            self.led(shell, 'u30air', 'power', 'on')
            self.led(shell, 'u30air', 'idle', 'on')
            self.uptime(100 + 120)
            self.led(shell, 'u30air', 'idle', 'off')
            self.assertEqual(set(self.state().values()), {'0'})
            self.led(shell, 'u30air', 'wake')
            self.assertEqual(self.state()['sc27xx:green'], '255')

    def test_charge_blinks_the_power_led(self):
        for shell in self.each_shell():
            self.reset()
            d = self.root / 'sys/class/leds/sc27xx:green'
            self.assertEqual(self.led(shell, 'u30air', 'charge', 'on').returncode, 0)
            self.assertEqual((d / 'trigger').read_text().strip(), 'timer')
            self.assertEqual((d / 'delay_on').read_text().strip(), '1000')
            self.assertEqual((d / 'delay_off').read_text().strip(), '1000')
            self.assertEqual(self.led(shell, 'u30air', 'charge', 'off').returncode, 0)
            self.assertEqual((d / 'trigger').read_text().strip(), 'none')
            self.assertEqual(self.state()['sc27xx:green'], '0')
            # a device without a power LED: nothing to blink, no error
            self.assertEqual(self.led(shell, 'f50', 'charge', 'on').returncode, 0)

    def test_no_timeout(self):
        for shell in self.each_shell():
            for device, conf in (('u30air', 'LED_TIMEOUT=0\n'), ('f50', '')):
                self.reset()
                if conf:
                    self.conf.write_text(conf)
                self.uptime(100)
                self.led(shell, device, 'power', 'on')
                self.led(shell, device, 'data', 'on')
                self.uptime(100000)
                self.led(shell, device, 'sleep', '--if-due')
                lit = 'net_blue' if device == 'u30air' else 'sc27xx:blue'
                self.assertEqual(self.state()[lit], '255', device)

    def test_f50(self):
        # ZTE's F50 (read from its Android): one network light on the PMIC's RGB LED - blue on 4G, white (the green
        # channel) on 5G, red without service - and the Wi-Fi light on the keypad backlight sink, at ZTE's 48
        rgb = ('sc27xx:red', 'sc27xx:green', 'sc27xx:blue')
        for shell in self.each_shell():
            self.reset()
            for args in (('power', 'on'), ('wake',), ('sleep',), ('power', 'off')):
                # no power LED and no timeout on an F50: no error, nothing lit
                self.assertEqual(self.led(shell, 'f50', *args).returncode, 0, args)
            self.assertEqual(set(self.state().values()), {'0'})
            for args, lit in ((('data', 'error'), 'sc27xx:red'), (('data', 'on'), 'sc27xx:blue'),
                              (('data', '5g'), 'sc27xx:green'), (('data', 'on'), 'sc27xx:blue'),
                              (('data', 'error'), 'sc27xx:red'), (('data', '5g'), 'sc27xx:green')):
                self.assertEqual(self.led(shell, 'f50', *args).returncode, 0, args)
                s = self.state()
                self.assertEqual({n: s[n] for n in rgb}, {n: '255' if n == lit else '0' for n in rgb}, args)
            self.led(shell, 'f50', 'data', 'off')
            self.assertEqual({self.state()[n] for n in rgb}, {'0'})
            for iw in ('channel 36 (5180 MHz), width: 80 MHz', 'channel 6 (2437 MHz), width: 20 MHz'):
                (self.tmp / 'iw.out').write_text(f'Interface wlan0\n\tssid F50\n\ttype AP\n\t{iw}\n')
                self.led(shell, 'f50', 'wifi', 'on')       # one colour, whichever band
                self.assertEqual(self.state()['keyboard-backlight'], '48', iw)
                self.led(shell, 'f50', 'wifi', 'off')
                self.assertEqual(self.state()['keyboard-backlight'], '0', iw)
            # none of the U30 Air's own LEDs switched
            self.led(shell, 'f50', 'data', 'on')
            self.led(shell, 'f50', 'wifi', 'on')
            s = self.state()
            self.assertEqual((s['net_blue'], s['zte-ldo0'], s['zte-ldo1'], s['zte-ldo2']), ('0', '0', '0', '0'))

    def test_wifi_sync_follows_a_slow_hotspot(self):
        # LuCI turned Wi-Fi on, hostapd comes up seconds later: "wifi sync S" keeps looking and lights it then
        import threading
        ap = 'Interface wlan0\n\tssid F50\n\ttype AP\n\tchannel 36 (5180 MHz), width: 80 MHz\n'
        for shell in self.each_shell():
            self.reset()
            (self.tmp / 'iw.out').write_text('Interface wlan0\n\ttype AP\n')
            t = threading.Timer(1.0, lambda: (self.tmp / 'iw.out').write_text(ap))
            t.start()
            try:
                self.assertEqual(self.led(shell, 'f50', 'wifi', 'sync', '4').returncode, 0)
            finally:
                t.cancel()
            self.assertEqual(self.state()['keyboard-backlight'], '48')

    def test_wifi_sync(self):
        # OpenWrt has no hook when LuCI turns Wi-Fi off or on: "wifi sync" reads whether wlan0 is a running AP
        for shell in self.each_shell():
            for device, lit, level in (('f50', 'keyboard-backlight', '48'), ('u30air', 'zte-ldo2', '255')):
                self.reset()
                self.conf.write_text('LED_TIMEOUT=0\n')
                (self.tmp / 'iw.out').write_text('Interface wlan0\n\tssid F50\n\ttype AP\n'
                                                  '\tchannel 36 (5180 MHz), width: 80 MHz\n')
                self.assertEqual(self.led(shell, device, 'wifi', 'sync').returncode, 0)
                self.assertEqual(self.state()[lit], level, device)
                for iw in ('Interface wlan0\n\ttype AP\n', 'Interface wlan0\n\ttype managed\n', ''):
                    (self.tmp / 'iw.out').write_text(iw)       # an AP without SSID is a stopped hostapd
                    self.led(shell, device, 'wifi', 'on')
                    self.led(shell, device, 'wifi', 'sync')
                    self.assertEqual(self.state()[lit], '0', (device, iw))

    def test_events_follow_hostapd_on_ubus(self):
        # OpenWrt: "events" lights the Wi-Fi LED from hostapd's ubus object as it comes and goes, whoever stopped or
        # started the access point. The fake ubusd: "listen" plays STUBLOG/events, one line each 0.3 s, and before
        # each line sets what "call hostapd.wlan0 get_status" answers (STUBLOG/status, empty: no such object).
        self.stub('ubus', r'''case $1 in
listen) while IFS='|' read -r st ev; do printf '%s' "$st" > "$STUBLOG/status"; echo "$ev"; sleep 0.3; done \
            < "$STUBLOG/events"; sleep 0.5 ;;
call) echo "call $2" >> "$STUBLOG/ubus.calls"
      st=$(cat "$STUBLOG/status"); [ -n "$st" ] || exit 4
      printf '{\n\t"status": "%s",\n\t"bss": [ "wlan0" ]\n}\n' "$st" ;;
esac''')
        rm = '{ "ubus.object.remove": {"id":2011872946,"path":"hostapd.wlan0"} }'
        add = '{ "ubus.object.add": {"id":-1383968478,"path":"hostapd.wlan0"} }'
        other = '{ "ubus.object.add": {"id":77,"path":"network.interface.wan"} }'
        (self.tmp / 'iw.out').write_text('Interface wlan0\n\tssid F50\n\ttype AP\n')
        for shell in self.each_shell():
            for events, lit in (
                    # wifi down: the object goes (iw still shows the SSID at that moment)
                    ([('', rm)], '0'),
                    # wifi up after a down: remove, add, remove, add (netifd's two passes); it ends on
                    ([('', rm), ('ENABLED', add), ('', rm), ('ENABLED', add)], '48'),
                    # an access point that hostapd set up but disabled is off; one still on its way (DFS) is on
                    ([('DISABLED', add)], '0'), ([('DFS', add)], '48')):
                with self.subTest(events=events):
                    self.reset()
                    self.conf.write_text('LED_TIMEOUT=0\n')
                    (self.tmp / 'status').write_text('ENABLED' if events[0][1] == rm else '')
                    (self.tmp / 'ubus.calls').unlink(missing_ok=True)
                    (self.tmp / 'events').write_text(''.join(f'{s}|{e}\n' for s, e in events + [(events[-1][0], other)]))
                    self.assertEqual(self.led(shell, 'f50', 'events').returncode, 0)
                    self.assertEqual(self.state()['keyboard-backlight'], lit)
                    # one status read at the start and one per hostapd event, none for the other object
                    self.assertEqual(len((self.tmp / 'ubus.calls').read_text().splitlines()), 1 + len(events))
        # Ubuntu has no ubus: systemd's hotspot unit lights it (ExecStartPost, ExecStopPost)
        (self.stubs / 'ubus').unlink()
        r = self.script(self.shells[0], BIN / 'mu300-led', 'events', MU300_SYSROOT=self.root, MU300_BIN=BIN,
                        PATH='%s:/usr/bin:/bin' % self.stubs)
        self.assertNotEqual(r.returncode, 0)
        unit = (BIN.parents[2] / 'etc/systemd/system/mu300-hotspot.service').read_text()
        self.assertIn('ExecStopPost=-/opt/mu300/bin/mu300-led wifi off', unit)

    def test_stale_siren_stops(self):
        # a siren the pid file does not name (left behind by a restart) stops by itself: two of them flashed
        # together, white lit throughout
        for shell in self.each_shell():
            self.reset()
            pid = self.root / 'run/mu300/led-siren.pid'
            self.led(shell, 'u30air', 'alarm', 'on')
            p = int(pid.read_text())
            pid.write_text('1\n')                                 # someone else's now
            deadline = time.time() + 3
            while time.time() < deadline:
                try:
                    os.kill(p, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.1)
            else:
                os.kill(p, 15)
                self.fail('the stale siren kept running')
            pid.unlink()

    def test_vendor_ldo_switches_on_5_4(self):
        # the 5.4 kernel has no zte-ldoN LEDs: ZTE's zte_ldo_leds switches the same LDOs through vddcamaN_status
        for shell in self.each_shell():
            self.reset()
            for n in ('zte-ldo0', 'zte-ldo1', 'zte-ldo2'):
                shutil.rmtree(self.root / 'sys/class/leds' / n)
            vendor = self.root / 'sys/devices/platform/zte_ldo_leds'
            vendor.mkdir(parents=True, exist_ok=True)
            for i in range(3):
                (vendor / f'vddcama{i}_status').write_text('0\n')
            self.led(shell, 'u30air', 'power', 'on')
            self.led(shell, 'u30air', 'data', '5g')
            (self.tmp / 'iw.out').write_text('Interface wlan0\n\ttype AP\n\tchannel 36 (5180 MHz)\n')
            self.led(shell, 'u30air', 'wifi', 'on')
            self.assertEqual([(vendor / f'vddcama{i}_status').read_text().strip() for i in range(3)], ['1', '0', '1'])
            self.led(shell, 'u30air', 'sleep')
            self.assertEqual([(vendor / f'vddcama{i}_status').read_text().strip() for i in range(3)], ['0', '0', '0'])
            shutil.rmtree(self.root / 'sys/devices')
            self.setUp_leds()

    def test_alarm_siren(self):
        # too hot: red, white and blue take turns on the PMIC's LED until the alarm is off, then the LEDs are as before
        for shell in self.each_shell():
            for device in ('u30air', 'f50'):
                self.reset()
                self.conf.write_text('LED_TIMEOUT=0\n')
                self.led(shell, device, 'power', 'on')
                self.led(shell, device, 'data', 'on')
                pid = self.root / 'run/mu300/led-siren.pid'
                try:
                    self.assertEqual(self.led(shell, device, 'alarm', 'on').returncode, 0)
                    self.assertTrue(pid.exists())
                    self.led(shell, device, 'alarm', 'on')        # a second one starts no second siren
                    # one colour at a time: white (the U30 Air's green channel) never mixed in
                    want = {('255', '0', '0'), ('0', '255', '0'), ('0', '0', '255')}
                    seen = set()
                    deadline = time.time() + 4
                    while time.time() < deadline and not want <= seen:
                        s = self.state()
                        seen.add((s['sc27xx:red'], s['sc27xx:green'], s['sc27xx:blue']))
                        time.sleep(0.03)
                    self.assertLessEqual(want, seen, device)
                finally:
                    self.led(shell, device, 'alarm', 'off')
                self.assertFalse(pid.exists())
                time.sleep(0.4)                                   # a killed siren writes no more
                s = self.state()
                self.assertEqual(s['sc27xx:red'], '0')
                # the F50's RGB LED is its network light: blue (4G) again; the U30 Air's white is its power LED
                self.assertEqual(s['sc27xx:blue'], '255' if device == 'f50' else '0', device)
                self.assertEqual(s['sc27xx:green'], '255' if device == 'u30air' else '0', device)
                self.assertEqual(self.led(shell, device, 'alarm', 'off').returncode, 0)   # off twice

    def test_missing_leds_and_bad_usage(self):
        for shell in self.each_shell():
            empty = self.tmp / 'empty'
            (empty / 'run/mu300').mkdir(parents=True, exist_ok=True)
            (empty / 'run/mu300/device').write_text('u30air\n')
            r = self.script(shell, BIN / 'mu300-led', 'data', 'on', MU300_SYSROOT=empty, MU300_BIN=BIN)
            self.assertEqual(r.returncode, 0)  # an LED the device has not is skipped
            self.assertEqual(self.led(shell, 'u30air', 'blink').returncode, 2)


class WifiBand(ShellTest):
    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'hotspot.conf'

    def band(self, shell, *args):
        return self.script(shell, BIN / 'mu300-wifi-band', *args, MU300_HOTSPOT_CONF=self.conf)

    def test_toggle(self):
        for shell in self.each_shell():
            self.conf.write_text("SSID=U30 AIR\nPSK=pa$$ 'w\"d\nBAND=5\nCHANNEL=40\nCOUNTRY=TR\n")
            self.conf.chmod(0o600)
            self.assertEqual(self.band(shell).stdout.strip(), 'hotspot: 5 GHz')
            r = self.band(shell, 'toggle')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'hotspot: 2.4 GHz'), r.stderr)
            self.assertEqual(self.conf.read_text(),
                             "SSID=U30 AIR\nPSK=pa$$ 'w\"d\nBAND=2.4\nCHANNEL=auto\nCOUNTRY=TR\n")
            self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)
            self.band(shell, 'toggle')
            self.assertIn('BAND=5\n', self.conf.read_text())
            self.band(shell, '2.4')
            self.band(shell, '2.4')
            self.assertEqual(self.conf.read_text().count('BAND='), 1)

    def test_missing_keys_and_file(self):
        for shell in self.each_shell():
            self.conf.write_text('SSID=x\nPSK=12345678\n')   # an old file without BAND/CHANNEL: 5 GHz
            self.assertEqual(self.band(shell).stdout.strip(), 'hotspot: 5 GHz')
            self.band(shell, 'toggle')
            self.assertEqual(self.conf.read_text(), 'SSID=x\nPSK=12345678\nBAND=2.4\nCHANNEL=auto\n')
            self.conf.unlink()
            self.assertEqual(self.band(shell, '5').returncode, 1)
            self.assertEqual(self.band(shell, '6').returncode, 2)


class Buttons(ShellTest):
    def test_actions(self):
        self.stub('mu300-keys', 'cat "$STUBLOG/keys.in"')
        for name in ('mu300-led', 'mu300-wifi-band', 'systemctl', 'logger', 'poweroff', 'mu300-power'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"; [ "{name} $*" != "systemctl is-active --quiet mu300-hotspot" ]')
        # Every press lights the LEDs first (a key always shows life, whatever the state), then wakes mu300-power with
        # the key's name in the background (only wifi ends a charging boot; other keys count as power), which the
        # rest does not wait for: its order against the band and hotspot toggles is free.
        WP, WW = 'mu300-power wake power', 'mu300-power wake wifi'
        cases = [('116 short', [WP]),
                 ('138 short', [WW, 'mu300-wifi-band toggle']),
                 ('138 long', [WW, 'systemctl is-active --quiet mu300-hotspot', 'systemctl start mu300-hotspot']),
                 ('0 tick', None),   # a tick is no press: it must not wake, only let the LEDs time out
                 # held power: no mu300-power wake (the radios would come back on the way down); the shutdown marker
                 ('116 long', ['systemctl poweroff']),
                 ('115 short', [WP])]
        marker = self.tmp / 'run/mu300/power/shutdown'
        for shell in self.each_shell():
            for event, want in cases:
                (self.tmp / 'keys.in').write_text(event + '\n')
                (self.tmp / 'calls').unlink(missing_ok=True)
                marker.unlink(missing_ok=True)
                r = self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run')
                self.assertEqual(r.returncode, 0, r.stderr)
                calls = (self.tmp / 'calls').read_text().splitlines() if (self.tmp / 'calls').exists() else []
                calls = [c for c in calls if not c.startswith('logger')]
                if want is None:
                    self.assertEqual(calls, ['mu300-led sleep --if-due'], event)
                else:
                    self.assertEqual(calls[0], 'mu300-led wake', event)
                    self.assertEqual(sorted(calls[1:]), sorted(want), event)
                    if 'systemctl is-active --quiet mu300-hotspot' in want:
                        self.assertLess(calls.index('systemctl is-active --quiet mu300-hotspot'),
                                        calls.index('systemctl start mu300-hotspot'))
                self.assertEqual(marker.exists(), event == '116 long', event)

    def test_keys_light_the_leds_in_idle_without_any_daemon(self):
        """2026-10-07: the LEDs held dark by `mu300-led idle on`, the state file "active", and every key lit nothing.
        With the real mu300-led and a mu300-power that hangs, each press still lights them, at once."""
        import time
        root = self.tmp / 'root'
        for n in ('sc27xx:green', 'net_blue'):
            d = root / 'sys/class/leds' / n
            d.mkdir(parents=True, exist_ok=True)
            (d / 'brightness').write_text('0\n'); (d / 'max_brightness').write_text('255\n'); (d / 'trigger').write_text('none\n')
        (root / 'proc').mkdir(parents=True, exist_ok=True)
        (root / 'proc/uptime').write_text('500.00 0.00\n')
        (root / 'run/mu300/led').mkdir(parents=True, exist_ok=True)
        (root / 'run/mu300/device').write_text('u30air\n')
        (root / 'run/mu300/led/sc27xx:green').write_text('1\n'); (root / 'run/mu300/led/net_blue').write_text('1\n')
        (root / 'run/mu300/led/.idle').touch()
        (self.tmp / 'run/mu300/power').mkdir(parents=True, exist_ok=True)
        (self.tmp / 'run/mu300/power/state').write_text('active\n')
        self.stub('mu300-keys', 'cat "$STUBLOG/keys.in"')
        self.stub('mu300-power', 'echo "mu300-power $*" >> "$STUBLOG/calls"; sleep 3')   # no daemon, a slow wake
        for name in ('mu300-wifi-band', 'systemctl', 'logger'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"')
        (self.tmp / 'keys.in').write_text('116 short\n138 short\n')
        for shell in self.each_shell():
            for n in ('sc27xx:green', 'net_blue'):
                (root / 'sys/class/leds' / n / 'brightness').write_text('0\n')
            (self.tmp / 'calls').unlink(missing_ok=True)
            env = self.env(MU300_RUN=self.tmp / 'run', MU300_SYSROOT=root, MU300_BIN=BIN, MU300_LED_CONF=self.tmp / 'none')
            env['PATH'] = f'{self.stubs}{os.pathsep}{BIN}{os.pathsep}{env["PATH"]}'
            p = subprocess.Popen(shell + [str(BIN / 'mu300-buttons')], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1.5)   # well inside the slow wake
            lit = {n: (root / 'sys/class/leds' / n / 'brightness').read_text().strip() for n in ('sc27xx:green', 'net_blue')}
            p.communicate(timeout=30)
            self.assertEqual(lit, {'sc27xx:green': '255', 'net_blue': '255'})
            calls = (self.tmp / 'calls').read_text()
            # the Wi-Fi press on a device held dark only wakes it: no band toggle
            self.assertNotIn('mu300-wifi-band', calls)
            self.assertIn('mu300-power wake power', calls); self.assertIn('mu300-power wake wifi', calls)

    def test_a_hung_direction_probe_is_bounded(self):
        """Ubuntu's systemctl is-active can hang: the hold's direction is decided within the probe deadline."""
        import time
        self.stub('mu300-keys', 'cat "$STUBLOG/keys.in"')
        for name in ('mu300-led', 'logger', 'mu300-power'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"')
        self.stub('systemctl', 'echo "systemctl $*" >> "$STUBLOG/calls"; [ "$1" != is-active ] || exec sleep 60')
        (self.tmp / 'keys.in').write_text('138 long\n')
        for shell in self.each_shell():
            (self.tmp / 'calls').unlink(missing_ok=True)
            t0 = time.time()
            r = self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run', MU300_BUTTONS_PROBE_DEADLINE=1)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertLess(time.time() - t0, 10)
            self.assertIn('systemctl start mu300-hotspot', (self.tmp / 'calls').read_text())   # no answer: not up

    def test_the_hold_marker_is_there_before_the_wake_of_the_same_press(self):
        """Review D2: the wake started by a Wi-Fi hold must find the user's marker already, or its restore sees the
        hotspot still up (or deactivating) and starts it again."""
        self.stub('mu300-keys', 'cat "$STUBLOG/keys.in"')
        for name in ('mu300-led', 'logger'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"')
        self.stub('mu300-power', 'echo "mu300-power $* marker=$([ -e "$MU300_RUN/mu300/power/hotspot-off" ] && echo yes || echo no)" >> "$STUBLOG/calls"')
        self.stub('systemctl', 'echo "systemctl $*" >> "$STUBLOG/calls"')   # active: the hold turns it off
        (self.tmp / 'keys.in').write_text('138 long\n')
        for shell in self.each_shell():
            (self.tmp / 'calls').unlink(missing_ok=True)
            self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run')
            calls = (self.tmp / 'calls').read_text()
            self.assertIn('mu300-power wake wifi marker=yes', calls)
            self.assertIn('systemctl stop mu300-hotspot', calls)

    def test_a_hung_toggle_does_not_hold_the_next_press(self):
        """The hotspot toggle runs in the background under a deadline: the next press shows life at once."""
        import time
        self.stub('mu300-keys', 'echo "138 long"; sleep 1; echo "116 short"; sleep 2')
        for name in ('logger', 'mu300-power'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"')
        self.stub('mu300-led', 'echo "mu300-led $* $(date +%s)" >> "$STUBLOG/calls"')
        self.stub('systemctl', 'echo "systemctl $*" >> "$STUBLOG/calls"; [ "$1" != stop ] || { sleep 30; echo "stop done" >> "$STUBLOG/calls"; }')
        for shell in self.each_shell():
            (self.tmp / 'calls').unlink(missing_ok=True)
            t0 = time.time()
            r = self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run', MU300_BUTTONS_DEADLINE=2)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertLess(time.time() - t0, 15)
            calls = (self.tmp / 'calls').read_text()
            self.assertEqual(calls.count('mu300-led wake'), 2, calls)
            self.assertNotIn('stop done', calls)   # killed at its deadline

    def test_the_hotspot_toggle_leaves_a_marker_while_off(self):
        """mu300-power's wake and self-check leave a hotspot alone that the user turned off with the key."""
        self.stub('mu300-keys', 'cat "$STUBLOG/keys.in"')
        for name in ('mu300-led', 'logger', 'mu300-power'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"')
        (self.tmp / 'keys.in').write_text('138 long\n')
        marker = self.tmp / 'run/mu300/power/hotspot-off'
        for shell in self.each_shell():
            self.stub('systemctl', 'echo "systemctl $*" >> "$STUBLOG/calls"')   # active: the hold stops it
            self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run')
            self.assertTrue(marker.exists())
            self.stub('systemctl', 'echo "systemctl $*" >> "$STUBLOG/calls"; [ "$1" != is-active ]')
            self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run')
            self.assertFalse(marker.exists())

    def test_first_wifi_press_while_asleep_only_wakes(self):
        self.stub('mu300-keys', 'cat "$STUBLOG/keys.in"')
        for name in ('mu300-led', 'mu300-wifi-band', 'systemctl', 'logger', 'mu300-power'):
            self.stub(name, f'echo "{name} $*" >> "$STUBLOG/calls"')
        (self.tmp / 'run/mu300/power').mkdir(parents=True)
        for state, acts in (('idle', False), ('charging-boot', False), ('active', True)):
            (self.tmp / 'run/mu300/power/state').write_text(state + '\n')
            for shell in self.each_shell():
                for event in ('138 short', '138 long'):
                    (self.tmp / 'keys.in').write_text(event + '\n')
                    (self.tmp / 'calls').unlink(missing_ok=True)
                    r = self.script(shell, BIN / 'mu300-buttons', MU300_RUN=self.tmp / 'run')
                    self.assertEqual(r.returncode, 0, r.stderr)
                    calls = (self.tmp / 'calls').read_text()
                    self.assertIn('mu300-power wake', calls, (state, event))
                    self.assertEqual(acts, ('mu300-wifi-band toggle' in calls or 'systemctl start' in calls or 'systemctl is-active' in calls), (state, event))


class TreeKill(ShellTest):
    """tree_kill (mu300-power, mu300-buttons, mobile-data): a process seen in the tree by one look and gone from it by
    the next (reparented: its parent exited meanwhile) is killed too - the union of every look, not the last one."""

    @staticmethod
    def func(path):
        m = re.search(r'^tree_kill\(\) \{.*?^\}$', path.read_text(), re.S | re.M)
        assert m, path
        return m.group(0)

    def test_every_process_seen_is_killed(self):
        # the first look sees 100 -> 101 -> 102; every later one finds 102 reparented to 1 (out of the tree)
        fake = ('proc_table() { n=$(cat "$STUBLOG/n" 2>/dev/null || echo 0); echo $((n + 1)) > "$STUBLOG/n"\n'
                '  if [ "$n" = 0 ]; then printf "100 1\\n101 100\\n102 101\\n"; else printf "100 1\\n101 100\\n102 1\\n"; fi; }\n'
                'kill() { echo "$*" >> "$STUBLOG/kills"; }\n')
        bash = shutil.which('bash')
        for name in ('mu300-power', 'mu300-buttons', 'mobile-data'):
            if name == 'mobile-data' and not bash:
                continue
            for shell in ([[bash]] if name == 'mobile-data' else self.each_shell()):
                for f in ('n', 'kills'):
                    (self.tmp / f).unlink(missing_ok=True)
                r = self.sh(shell, self.func(BIN / name) + '\n' + fake + 'tree_kill 100\n')
                self.assertEqual(r.returncode, 0, (name, r.stderr))
                kills = (self.tmp / 'kills').read_text().split('\n')
                for pid in ('100', '101', '102'):
                    self.assertIn(f'-KILL {pid}', kills, (name, shell))


class WcnReopen(ShellTest):
    """wcn-reopen (the WCN chip was reset, #94): Wi-Fi reopened in whichever mode it was in."""
    def setUp(self):
        super().setUp()
        self.root = self.tmp / 'root'
        (self.root / 'sys/class/net/wlan0').mkdir(parents=True)
        (self.root / 'run').mkdir()
        # systemctl: is-active answers from $STUBLOG/active-UNIT; every other call is recorded
        self.stub('systemctl', 'if [ "$1" = -q ] && [ "$2" = is-active ]; then [ -e "$STUBLOG/active-$3" ]; exit; fi\n'
                               'echo "systemctl $*" >> "$STUBLOG/calls"')
        self.stub('ip', 'case "$*" in "link show wlan0") cat "$STUBLOG/link" ;; *) echo "ip $*" >> "$STUBLOG/calls" ;; esac')

    def run_reopen(self, shell, hotspot=False, client=False, up=True):
        for f in ('calls', 'active-mu300-hotspot.service'):
            (self.tmp / f).unlink(missing_ok=True)
        (self.root / 'run/mu300-wifi-client.active').unlink(missing_ok=True)
        if hotspot:
            (self.tmp / 'active-mu300-hotspot.service').write_text('')
        if client:
            (self.root / 'run/mu300-wifi-client.active').write_text('')
        flags = 'BROADCAST,MULTICAST,UP,LOWER_UP' if up else 'BROADCAST,MULTICAST'
        (self.tmp / 'link').write_text(f'5: wlan0: <{flags}> mtu 1500 qdisc mq state UP\n')
        r = self.script(shell, BIN / 'wcn-reopen', MU300_SYSROOT=self.root)
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.tmp / 'calls'
        return calls.read_text().splitlines() if calls.exists() else []

    def test_hotspot_is_restarted(self):
        for shell in self.each_shell():
            self.assertEqual(self.run_reopen(shell, hotspot=True), ['systemctl restart mu300-hotspot.service'])

    def test_a_client_gets_wlan0_down_and_up_and_joins_again(self):
        # restarting the client alone left the chip off (wifi-client never takes wlan0 down): the watchdog rebooted
        for shell in self.each_shell():
            self.assertEqual(self.run_reopen(shell, client=True),
                             ['systemctl stop mu300-wifi-client.service', 'ip link set wlan0 down',
                              'ip link set wlan0 up', 'systemctl start mu300-wifi-client.service'])

    def test_neither_up_powers_the_chip_on_and_starts_nothing(self):
        for shell in self.each_shell():
            with self.subTest(wlan0='up'):
                self.assertEqual(self.run_reopen(shell), ['ip link set wlan0 down', 'ip link set wlan0 up'])
            with self.subTest(wlan0='down'):
                self.assertEqual(self.run_reopen(shell, up=False),
                                 ['ip link set wlan0 down', 'ip link set wlan0 up', 'ip link set wlan0 down'])

    def test_the_udev_rule_starts_the_service(self):
        rule = (TOP / 'rootfs/overlay/etc/udev/rules.d/70-mu300-wcn.rules').read_text()
        self.assertIn('ENV{EVENT}=="FW_ERROR", RUN+="/bin/systemctl --no-block start mu300-wcn-reopen.service"', rule)
        unit = (TOP / 'rootfs/overlay/etc/systemd/system/mu300-wcn-reopen.service').read_text()
        self.assertIn('ExecStart=/opt/mu300/bin/wcn-reopen\n', unit)


class ThermalGuard(ShellTest):
    """thermal-guard's LED alarm (one round against a fake /: MU300_SYSROOT)."""
    def setUp(self):
        super().setUp()
        self.root = self.tmp / 'root'
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        led = self.bin / 'mu300-led'
        led.write_text('#!/bin/sh\necho "mu300-led $*" >> "$STUBLOG/calls"\n')
        led.chmod(0o755)
        shutil.copy(BIN / 'mu300-device', self.bin / 'mu300-device')
        self.device('u30air')
        self.stub('logger', ':')
        self.stub('poweroff', 'echo poweroff >> "$STUBLOG/calls"')

    def device(self, name):
        (self.root / 'run/mu300').mkdir(parents=True, exist_ok=True)
        (self.root / 'run/mu300/device').write_text(name + '\n')

    def round(self, shell, soc, battery=None, trips=False):
        z = self.root / 'sys/class/thermal/thermal_zone0'
        z.mkdir(parents=True, exist_ok=True)
        (z / 'temp').write_text(f'{soc}\n')
        if trips:
            (z / 'trip_point_0_temp').write_text('95000\n')
        if battery is not None:
            b = self.root / 'sys/class/power_supply/battery'
            b.mkdir(parents=True, exist_ok=True)
            (b / 'type').write_text('Battery\n')
            (b / 'temp').write_text(f'{battery}\n')
        (self.tmp / 'calls').unlink(missing_ok=True)
        r = self.script(shell, BIN / 'thermal-guard', MU300_SYSROOT=self.root, MU300_BIN=self.bin)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.tmp / 'calls').read_text().splitlines() if (self.tmp / 'calls').exists() else []

    def test_alarm_on_and_off(self):
        for shell in self.each_shell():
            shutil.rmtree(self.root, ignore_errors=True)
            self.device('u30air')
            self.assertEqual(self.round(shell, 60000, 300), [])
            self.assertEqual(self.round(shell, 86000, 300), ['mu300-led alarm on'])
            self.assertEqual(self.round(shell, 90000, 300), [])                # on already
            self.assertEqual(self.round(shell, 80000, 300), [])                # not cool enough yet
            self.assertEqual(self.round(shell, 74000, 300), ['mu300-led alarm off'])
            self.assertEqual(self.round(shell, 60000, 510), ['mu300-led alarm on'])   # the battery alone
            self.assertEqual(self.round(shell, 60000, 460), [])
            self.assertEqual(self.round(shell, 60000, 440), ['mu300-led alarm off'])

    def test_f50_battery_is_ignored(self):
        # the F50 has no battery, but mainline's fuel gauge reports one at 75.0 C from an open NTC input: the
        # alarm went on at every boot and never off (v2026.10.06)
        for shell in self.each_shell():
            shutil.rmtree(self.root, ignore_errors=True)
            self.device('f50')
            self.assertEqual(self.round(shell, 46000, 750), [])
            self.assertEqual(self.round(shell, 86000, 750), ['mu300-led alarm on'])    # the SoC still counts
            self.assertEqual(self.round(shell, 74000, 750), ['mu300-led alarm off'])

    def test_vendor_kernel_only_watches(self):
        # 5.4 has its own trip points: no throttling or power-off here, but the alarm still works
        for shell in self.each_shell():
            shutil.rmtree(self.root, ignore_errors=True)
            self.device('u30air')
            self.assertEqual(self.round(shell, 110000, trips=True), ['mu300-led alarm on'])
            shutil.rmtree(self.root, ignore_errors=True)
            self.device('u30air')
            self.assertEqual(self.round(shell, 110000), ['poweroff', 'mu300-led alarm on'])   # mainline: critical


class Nfc(ShellTest):
    """mu300-nfc against a fake FM11NT08: 1 KiB behind a stub i2ctransfer, which answers only while a stub gpioset
    holds line 190 low, as the tag does."""
    EEPROM = r'''
import os, sys
mem = os.path.join(os.environ['STUBLOG'], 'tag.bin')
data = bytearray(open(mem, 'rb').read())
args = [a for a in sys.argv[1:] if a != '-y']
bus, op = args[0], args[1]
if not os.path.exists(os.path.join(os.environ['STUBLOG'], 'held')) or bus != '2' or not op.endswith('@0x57'):
    sys.exit('Error: Sending messages failed: Remote I/O error')
n = int(op[1:op.index('@')])
addr = int(args[2], 16) << 8 | int(args[3], 16)
if op.startswith('w') and len(args) > 4 and args[4].startswith('r'):
    print(' '.join('0x%02x' % b for b in data[addr:addr + int(args[4][1:])]))
elif op.startswith('w'):
    body = [int(x, 16) for x in args[4:]]
    # NDEF pages of 16 bytes; the configuration byte on its own
    assert len(body) == n - 2 and (len(body) <= 16 and addr % 16 == 0 and addr >= 16 or (addr, len(body)) == (0x3bf, 1)), args
    data[addr:addr + len(body)] = bytes(body)
    open(mem, 'wb').write(bytes(data))
    open(os.path.join(os.environ['STUBLOG'], 'writes'), 'a').write('%x\\n' % addr)
'''
    # what ZTE's firmware leaves there: UID, capability container (NDEF, 872 bytes), a Wi-Fi record
    ZTE = bytes.fromhex('1df4bcdd99030012 88b20000e1106d00'.replace(' ', ''))

    def setUp(self):
        super().setUp()
        self.root = self.tmp / 'root'
        (self.root / 'run/mu300').mkdir(parents=True)
        chip = self.tmp / 'devices/platform/soc/64170000.gpio/gpiochip4'
        chip.mkdir(parents=True)
        (self.root / 'sys/bus/gpio/devices').mkdir(parents=True)
        (self.root / 'sys/bus/gpio/devices/gpiochip4').symlink_to(chip)
        (self.tmp / 'eeprom.py').write_text(self.EEPROM)
        self.stub('i2ctransfer', 'exec python3 "$STUBLOG/eeprom.py" "$@"')
        # libgpiod 2: holds the line until killed
        self.stub('gpioset', '[ "$1" = --help ] && { echo "  -c, --chip"; exit 0; }; '
                             '[ "$*" = "-c gpiochip4 190=0" ] || exit 1; touch "$STUBLOG/held"; '
                             'trap \'rm -f "$STUBLOG/held"; exit 0\' TERM; while :; do sleep 0.05; done')
        self.conf = self.tmp / 'hotspot.conf'
        self.conf.write_text('SSID=U30 AIR\nPSK=secret pass!\nBAND=5\n')

    def blank(self, ndef=b'\x03\x00\xfe'):
        (self.tmp / 'tag.bin').write_bytes(self.ZTE + ndef + bytes(1024 - 16 - len(ndef)))
        (self.tmp / 'writes').unlink(missing_ok=True)

    def nfc(self, shell, *args, device='u30air'):
        (self.root / 'run/mu300/device').write_text(device + '\n')
        return self.script(shell, BIN / 'mu300-nfc', *args, MU300_SYSROOT=self.root, MU300_BIN=BIN,
                           MU300_HOTSPOT_CONF=self.conf)

    def writes(self):
        w = self.tmp / 'writes'
        return w.read_text().split() if w.exists() else []

    def test_wifi_record_is_zte_s(self):
        # byte for byte what the stock firmware writes (WSC credential, WPA2-PSK, AES)
        for shell in self.each_shell():
            self.blank()
            r = self.nfc(shell, 'wifi')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'wifi: U30 AIR (with its password)'), r.stderr)
            self.assertNotIn('secret', r.stdout + r.stderr)
            ssid, key = b'U30 AIR', b'secret pass!'
            cred = (b'\x10\x45\x00' + bytes([len(ssid)]) + ssid + b'\x10\x03\x00\x02\x00\x20\x10\x0f\x00\x02\x00\x08'
                    + b'\x10\x27\x00' + bytes([len(key)]) + key + b'\x10\x20\x00\x06' + bytes(6)
                    + b'\x10\x49\x00\x06\x00\x37\x2a\x00\x01\x20')
            payload = b'\x10\x0e\x00' + bytes([len(cred)]) + cred
            rec = b'\xd2\x17' + bytes([len(payload)]) + b'application/vnd.wfa.wsc' + payload
            want = b'\x03' + bytes([len(rec)]) + rec + b'\xfe'
            data = (self.tmp / 'tag.bin').read_bytes()
            self.assertEqual(data[16:16 + len(want)], want)
            self.assertEqual(data[:16], self.ZTE)                     # UID and capability container untouched
            self.assertFalse((self.tmp / 'held').exists())            # the line is let go
            # again: nothing changed, nothing written
            (self.tmp / 'writes').unlink()
            self.assertEqual(self.nfc(shell, 'wifi').returncode, 0)
            self.assertEqual(self.writes(), [])

    def test_url_text_clear(self):
        for shell in self.each_shell():
            self.blank()
            for args, shown in ((('url', 'https://github.com/dikeckaan/mu300-linux'),
                                 'url: https://github.com/dikeckaan/mu300-linux'),
                                (('url', 'tel:+905551112233'), 'url: tel:+905551112233'),
                                (('url', 'geo:41.0,29.0'), 'url: geo:41.0,29.0'),
                                (('text', 'Merhaba, şifre kutunun altında'), 'text: Merhaba, şifre kutunun altında'),
                                (('clear',), 'empty')):
                r = self.nfc(shell, *args)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, shown), r.stderr)
                self.assertEqual(self.nfc(shell).stdout.strip(), shown)
            data = (self.tmp / 'tag.bin').read_bytes()
            self.assertEqual(data[16:19], b'\x03\x00\xfe')

    def test_long_url(self):
        # over 255 bytes: a long record and a three-byte TLV length
        for shell in self.each_shell():
            self.blank()
            url = 'https://example.com/' + 'x' * 400
            r = self.nfc(shell, 'url', url)
            self.assertEqual(r.stdout.strip(), 'url: ' + url, r.stderr)
            data = (self.tmp / 'tag.bin').read_bytes()
            self.assertEqual((data[16], data[17]), (0x03, 0xff))
            r = self.nfc(shell, 'url', 'https://example.com/' + 'x' * 900)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('too long', r.stderr)

    def test_sync_keeps_what_the_user_wrote(self):
        for shell in self.each_shell():
            self.blank()
            self.conf.write_text('SSID=U30 AIR\nPSK=secret pass!\nBAND=5\n')
            self.assertEqual(self.nfc(shell, 'sync').stdout.strip(), 'wifi: U30 AIR (with its password)')
            self.conf.write_text('SSID=Ev\nPSK=another one\n')
            self.assertEqual(self.nfc(shell, 'sync').stdout.strip(), 'wifi: Ev (with its password)')
            self.nfc(shell, 'url', 'https://example.com/')
            (self.tmp / 'writes').unlink()
            r = self.nfc(shell, 'sync')
            self.assertIn('left as it is', r.stdout)
            self.assertEqual(self.writes(), [])
            self.assertEqual(self.nfc(shell).stdout.strip(), 'url: https://example.com/')

    def test_on_off(self):
        # ZTE's NFC switch: bit 5 of the configuration byte 0x3bf (set: phones get nothing); nothing else changes
        for shell in self.each_shell():
            self.blank()
            data = bytearray((self.tmp / 'tag.bin').read_bytes())
            data[0x3b0:0x3c0] = bytes.fromhex('0578f057806002 1e0000009e44000420'.replace(' ', ''))
            (self.tmp / 'tag.bin').write_bytes(bytes(data))
            r = self.nfc(shell)
            self.assertIn('NFC is off', r.stdout)
            r = self.nfc(shell, 'on')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'NFC on'), r.stderr)
            after = (self.tmp / 'tag.bin').read_bytes()
            self.assertEqual(after[0x3b0:0x3c0], bytes.fromhex('0578f0578060021e0000009e44000400'))
            self.assertEqual(after[:0x3bf], bytes(data[:0x3bf]))
            self.assertNotIn('NFC is off', self.nfc(shell).stdout)
            self.assertEqual(self.nfc(shell, 'off').stdout.strip(), 'NFC off')
            self.assertEqual((self.tmp / 'tag.bin').read_bytes()[0x3bf], 0x20)

    def test_refusals(self):
        for shell in self.each_shell():
            self.blank()
            r = self.nfc(shell, 'wifi', device='f50')
            self.assertEqual(r.returncode, 1)
            self.assertIn('only the U30 Air', r.stderr)
            self.assertEqual(self.nfc(shell, 'blink').returncode, 2)
            self.assertEqual(self.nfc(shell, 'url').returncode, 1)
            # no capability container: not written
            (self.tmp / 'tag.bin').write_bytes(bytes(1024))
            r = self.nfc(shell, 'url', 'https://example.com/')
            self.assertEqual(r.returncode, 1)
            self.assertIn('capability container', r.stderr)
            self.assertEqual(self.writes(), [])


class Ttl(ShellTest):
    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'etc' / 'ttl.conf'
        self.stub('id', 'echo 0')
        self.stub('modprobe', 'exit 1')   # no act_pedit (the 5.4 kernel): the nft backend; test_ttl.TtlTc has tc
        # nft records its arguments, and the ruleset it is given on stdin
        self.stub('nft', 'echo "$*" >> "$STUBLOG/nft.args"; [ "$1" = -f ] && cat >> "$STUBLOG/nft.in"; '
                         '[ "$1" = list ] && exit 1; exit 0')

    def ttl(self, shell, *args):
        return self.script(shell, BIN / 'mu300-ttl', *args, MU300_TTL_CONF=self.conf)

    def reset(self):
        for f in ('nft.args', 'nft.in'):
            (self.tmp / f).unlink(missing_ok=True)
        self.conf.unlink(missing_ok=True)

    def test_set(self):
        for shell in self.each_shell():
            self.reset()
            r = self.ttl(shell, 'set', '64')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.conf.read_text(), 'TTL=64\n')
            rules = (self.tmp / 'nft.in').read_text()
            self.assertIn('table inet mu300_ttl', rules)
            self.assertIn('oifname "sipa_eth*" ip ttl set 64', rules)
            self.assertIn('oifname "sipa_eth*" ip6 hoplimit set 64', rules)
            self.assertIn('fixed at 64', r.stdout)

    def test_invalid_values_change_nothing(self):
        for shell in self.each_shell():
            for v in ('0', '256', 'abc', '-1', '6 4', ''):
                self.reset()
                r = self.ttl(shell, 'set', v)
                self.assertEqual(r.returncode, 2, v)
                self.assertFalse(self.conf.exists(), v)
                self.assertFalse((self.tmp / 'nft.in').exists(), v)

    def test_off_and_apply(self):
        for shell in self.each_shell():
            self.reset()
            self.ttl(shell, 'set', '128')
            (self.tmp / 'nft.in').unlink()
            r = self.ttl(shell, 'off')
            self.assertEqual(r.returncode, 0)
            self.assertFalse(self.conf.exists())
            self.assertIn('delete table inet mu300_ttl', (self.tmp / 'nft.args').read_text())
            self.assertFalse((self.tmp / 'nft.in').exists())  # no rule without a setting
            self.assertIn('not changed', r.stdout)
            # a hand-edited file with junk sets nothing
            self.conf.parent.mkdir(parents=True, exist_ok=True)
            self.conf.write_text('TTL=999\n')
            self.ttl(shell, 'apply')
            self.assertFalse((self.tmp / 'nft.in').exists())

    def test_not_root(self):
        self.stub('id', 'echo 1000')
        for shell in self.each_shell():
            self.reset()
            r = self.ttl(shell, 'set', '64')
            self.assertEqual(r.returncode, 1)
            self.assertFalse(self.conf.exists())
            self.assertEqual(self.ttl(shell).returncode, 0)  # status works without root



class UsbReset(ShellTest):
    """mu300-usb-reset (K67): no rebind in host role, configfs mounted when init unmounted it, --fast-run."""

    def setUp(self):
        super().setUp()
        self.gadget = self.tmp / 'gadget'
        self.gadget.mkdir()
        (self.gadget / 'UDC').write_text('5e100000.usb\n')
        self.role = self.tmp / 'role'
        self.role.write_text('device\n')
        self.hook = self.tmp / 'hook'
        self.hook.write_text('#!/bin/sh\necho "hook $ACTION $INTERFACE" >> "$STUBLOG/calls"\n')
        self.hook.chmod(0o755)
        self.run_dir = self.tmp / 'run'
        self.run_dir.mkdir()
        for n in ('sleep', 'usleep', 'ip', 'logger', 'mount'):
            self.stub(n, f'echo "{n} $*" >> "$STUBLOG/calls"')

    def reset(self, shell, *args, **env):
        e = dict(MU300_GADGET=self.gadget, MU300_USB_ROLE=self.role, MU300_USB_HOOK=self.hook,
                 MU300_RUN_DIR=self.run_dir, PATH=f'{self.stubs}:/usr/bin:/bin')
        e.update(env)
        return self.script(shell, BIN / 'mu300-usb-reset', *args, **e)

    def calls(self):
        p = self.tmp / 'calls'
        return p.read_text() if p.exists() else ''

    def test_host_role_exits_without_touching_udc(self):
        self.role.write_text('host\n')
        for shell in self.each_shell():
            for arg in ('--fast-run', '--run', '--ready', '--if-no-lease'):
                r = self.reset(shell, arg)
                self.assertEqual(0, r.returncode, r.stderr)
                self.assertEqual('5e100000.usb\n', (self.gadget / 'UDC').read_text(), arg)
                self.assertEqual('', self.calls(), arg)

    def test_fast_run_rebinds_in_100_ms_and_hands_off_the_lan(self):
        # UDC is a plain file: the unbind is seen at once, the rebind writes the name back
        for shell in self.each_shell():
            (self.tmp / 'calls').unlink(missing_ok=True)
            (self.gadget / 'UDC').write_text('5e100000.usb\n')
            r = self.reset(shell, '--fast-run')
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertEqual('5e100000.usb', (self.gadget / 'UDC').read_text().strip())
            calls = self.calls()
            self.assertIn('usleep 100000\n', calls)
            self.assertNotIn('sleep 2', calls.replace('usleep', ''))
            self.assertIn('hook ifup lan\n', calls)
            self.assertIn('mu300-usb', calls)       # logger tag
            self.assertTrue(float((self.run_dir / 'mu300-usb-rebind-done').read_text().split()[0]) >= 0)

    def test_mounts_configfs_when_init_unmounted_it(self):
        for shell in self.each_shell():
            (self.tmp / 'calls').unlink(missing_ok=True)
            r = self.reset(shell, '--fast-run', MU300_GADGET=self.tmp / 'nogadget')
            self.assertEqual(1, r.returncode)
            self.assertIn('mount -t configfs configfs /sys/kernel/config', self.calls())
            self.assertIn('no gadget', r.stderr)

    def test_ready_detaches_a_fast_run(self):
        for shell in self.each_shell():
            r = self.reset(shell, '--ready')
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertNotIn('re-enumerating', r.stdout)

    def test_lease_check_kept(self):
        # --if-no-lease still exits quietly when a lease file exists (the interim, until the K12 gate)
        lease = self.tmp / 'leases'
        lease.write_text('1 aa:bb 10.0.0.2 h *\n')
        for shell in self.each_shell():
            r = self.reset(shell, '--if-no-lease', '0', MU300_LEASES=lease)
            self.assertEqual(0, r.returncode, r.stderr)
            self.assertEqual('5e100000.usb\n', (self.gadget / 'UDC').read_text())


class Usb(ShellTest):
    """mu300-usb against a fake charger (busybox i2cget/i2cset on files) and a fake role switch."""

    def setUp(self):
        super().setUp()
        r = self.root = self.tmp / 'root'
        (r / 'run/mu300').mkdir(parents=True)
        (r / 'run/mu300/device').write_text('u30air\n')
        node = r / 'sys/firmware/devicetree/base/soc/i2c@22a0000'
        node.mkdir(parents=True)
        i2c = r / 'sys/bus/i2c/devices/i2c-6'
        i2c.mkdir(parents=True)
        (i2c / 'of_node').symlink_to(node)
        role = r / 'sys/class/usb_role/25100000.dwc3-role-switch'
        role.mkdir(parents=True)
        (role / 'role').write_text('device\n')
        self.stub('id', 'echo 0')
        self.stub('sleep', ':')
        # i2c-tools (which mu300-usb prefers to busybox's): i2cget -y BUS ADDR REG / i2cset -y BUS ADDR REG VALUE,
        # one file per register. (Not a stub called busybox: that would also replace the "busybox sh" under test.)
        # The options (-y, and -f when a kernel driver owns the address) go to $STUBLOG/flags.
        opts = 'while case $1 in -*) true ;; *) false ;; esac; do echo "$1" >> "$STUBLOG/flags"; shift; done; '
        self.stub('i2cget', opts + 'cat "$STUBLOG/reg-$3" 2>/dev/null || echo 0x00')
        self.stub('i2cset', opts + 'printf "0x%02x\\n" $(( $4 )) > "$STUBLOG/reg-$3"; '
                            'echo "$3=$(( $4 ))" >> "$STUBLOG/writes"')

    def regs(self, **values):
        for k, v in values.items():
            (self.tmp / f'reg-0x{k[1:]}').write_text(v + '\n')

    def reg(self, r):
        return int((self.tmp / f'reg-{r}').read_text(), 16)

    def usb(self, shell, *args):
        return self.script(shell, BIN / 'mu300-usb', *args, MU300_SYSROOT=self.root,
                           PATH=f'{self.stubs}:{BIN}:/usr/bin:/bin')

    def role(self):
        return (self.root / 'sys/class/usb_role/25100000.dwc3-role-switch/role').read_text().strip()

    def test_host_and_back(self):
        for shell in self.each_shell():
            self.regs(r01='0x1a', r05='0x9f', r08='0x00')   # no outside supply
            r = self.usb(shell, 'host')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.role(), 'host')
            self.assertEqual(self.reg('0x01'), 0x1a | 0x20)    # OTG_CONFIG on, the rest untouched
            self.assertEqual(self.reg('0x05'), 0x9f & ~0x30)   # watchdog off
            r = self.usb(shell, 'device')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.role(), 'device')
            self.assertEqual(self.reg('0x01'), 0x1a)
            self.assertEqual(self.reg('0x05'), (0x9f & ~0x30) | 0x10)

    def test_refuses_while_powered(self):
        for shell in self.each_shell():
            self.regs(r01='0x1a', r05='0x9f', r08='0x24')   # power good, a USB host drives VBUS
            (self.tmp / 'writes').unlink(missing_ok=True)
            r = self.usb(shell, 'host')
            self.assertEqual(r.returncode, 1)
            self.assertIn('unplug it first', r.stderr)
            self.assertFalse((self.tmp / 'writes').exists())   # not a single register written
            self.assertEqual(self.role(), 'device')

    def test_boot_switches_a_leftover_boost_off(self):
        for shell in self.each_shell():
            self.regs(r01='0x3a', r05='0x8f')
            r = self.usb(shell, 'boot')
            self.assertEqual(r.returncode, 0)
            self.assertEqual(self.reg('0x01'), 0x1a)
            self.assertIn('switched off', r.stdout)
            # nothing to do, nothing written
            (self.tmp / 'writes').unlink(missing_ok=True)
            self.assertEqual(self.usb(shell, 'boot').stdout, '')
            self.assertFalse((self.tmp / 'writes').exists())

    def test_under_the_kernel_driver(self):
        # bq256xx owns 6-006b (mainline with the charger patch): i2c-dev needs -f, and the watchdog stays off, or 40 s
        # later the chip would drop the driver's charge settings (input current, charge current, charging on)
        drv = self.root / 'sys/bus/i2c/devices/6-006b'
        drv.mkdir(parents=True)
        (drv / 'driver').symlink_to(self.root / 'run')
        for shell in self.each_shell():
            (self.tmp / 'flags').unlink(missing_ok=True)
            self.regs(r01='0x1a', r05='0x87', r08='0x00')
            r = self.usb(shell, 'host')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.reg('0x01'), 0x1a | 0x20)
            r = self.usb(shell, 'device')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.reg('0x01'), 0x1a)
            self.assertEqual(self.reg('0x05'), 0x87)          # watchdog still off
            self.regs(r01='0x3a')
            r = self.usb(shell, 'boot')
            self.assertEqual(self.reg('0x01'), 0x1a)
            self.assertEqual(self.reg('0x05'), 0x87)
            self.assertIn('-f', (self.tmp / 'flags').read_text().split())
        # without the driver, no -f
        (drv / 'driver').unlink()
        for shell in self.each_shell():
            (self.tmp / 'flags').unlink(missing_ok=True)
            self.usb(shell, 'boot')
            self.assertNotIn('-f', (self.tmp / 'flags').read_text().split())

    def test_f50(self):
        for shell in self.each_shell():
            (self.root / 'run/mu300/device').write_text('f50\n')
            r = self.usb(shell, 'host')
            self.assertEqual(r.returncode, 1)
            self.assertIn('only the U30 Air', r.stderr)
            self.assertEqual(self.usb(shell, 'boot').returncode, 0)   # boot is quiet on every device


@unittest.skipIf(os.name == 'nt' or os.geteuid() == 0, 'needs a user that cannot write the daemon directory')
class AtClient(ShellTest):
    """mu300-at as a user who cannot write /run/mu300-at: it says so at once (it used to loop for ever on a stale
    lock it could not remove, printing "rm: cannot remove .../lock/pid", and `mobile-data status` hung with it)."""

    def setUp(self):
        super().setUp()
        self.dir = self.tmp / 'at'
        self.dir.mkdir()
        os.mkfifo(self.dir / 'cmd')

    def tearDown(self):
        for p in (self.dir / 'lock', self.dir):
            if p.exists():
                p.chmod(0o755)
        super().tearDown()

    def at(self, shell):
        t = time.monotonic()
        r = self.script(shell, BIN / 'mu300-at', 'AT+CSQ', MU300_AT_DIR=self.dir, MU300_AT_LOCK_WAIT=20)
        return r, time.monotonic() - t

    def test_a_user_is_told_to_be_root(self):
        self.dir.chmod(0o555)
        for shell in self.each_shell():
            r, took = self.at(shell)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('root', r.stderr)
            self.assertLess(took, 5)

    def test_a_stale_lock_it_cannot_remove(self):
        (self.dir / 'lock').mkdir()
        (self.dir / 'lock' / 'pid').write_text('999999\n')   # an owner that is gone
        (self.dir / 'lock').chmod(0o555)
        self.dir.chmod(0o555)
        for shell in self.each_shell():
            r, took = self.at(shell)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('root', r.stderr)
            self.assertLess(took, 5)
            self.assertLess(r.stderr.count('\n'), 3, r.stderr)

    def test_a_stale_lock_it_cannot_remove_counts_as_busy(self):
        # the loop itself: a writable directory, but a lock whose dead owner's files cannot be removed. It used
        # to "continue" past the wait for ever; now it waits like for a live owner and gives up "busy".
        (self.dir / 'lock').mkdir()
        (self.dir / 'lock' / 'pid').write_text('999999\n')
        (self.dir / 'lock').chmod(0o555)
        for shell in self.each_shell():
            t = time.monotonic()
            r = self.script(shell, BIN / 'mu300-at', 'AT+CSQ', MU300_AT_DIR=self.dir, MU300_AT_LOCK_WAIT=1)
            took = time.monotonic() - t
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('busy', r.stderr)
            self.assertLess(took, 15)


class LanStart(ShellTest):
    """lan-start (bash): the bridge has udev's persistent MAC before any port joins it. Otherwise br-lan took usb0's
    MAC whenever it was up before udev got to it, its IPv6 link-local was made from that, and the address changed
    from boot to boot (seen on the U30 Air under 7.2.9)."""

    def test_udev_names_the_bridge_before_ports_join(self):
        if not shutil.which('bash'):
            self.skipTest('no bash')
        self.stub('ip', 'echo "ip $*" >> "$STUBLOG/calls"; case "$*" in "link show br-lan") exit 1;; esac; exit 0')
        self.stub('udevadm', 'echo "udevadm $*" >> "$STUBLOG/calls"')
        self.stub('dnsmasq', 'echo "dnsmasq" >> "$STUBLOG/calls"')
        r = self.script(['bash'], BIN / 'lan-start', MU300_LAN_IP='192.168.78.1')
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = (self.tmp / 'calls').read_text().splitlines()
        add = calls.index('ip link add br-lan type bridge')
        settle = next(i for i, c in enumerate(calls) if c.startswith('udevadm settle'))
        join = calls.index('ip link set usb0 master br-lan')
        up = calls.index('ip link set br-lan up')
        self.assertLess(add, settle)
        self.assertLess(settle, join)
        self.assertLess(join, up)


class KmsgForward(ShellTest):
    """kmsg-forward: the first start of a boot forwards the ring buffer from its start (the early call traces came
    before the service and were lost with --follow-new); a restart forwards only what is new, so nothing twice."""

    def test_first_start_reads_from_the_start_restart_only_new(self):
        self.stub('dmesg', 'echo "dmesg $*" >> "$STUBLOG/calls"; echo "[    1.234567] early trace"')
        self.stub('systemd-cat', 'echo "systemd-cat $*" >> "$STUBLOG/calls"; cat >> "$STUBLOG/journal"')
        # (it runs on Ubuntu only: GNU grep's --line-buffered, which busybox's grep has not, filters the ignore list)
        import subprocess
        gnu = subprocess.run(['grep', '--line-buffered', 'x'], input='x\n', capture_output=True, text=True).returncode == 0
        for shell in self.each_shell():
            for ignore in ('', 'chatter\n') if gnu else ('',):
                mark = self.tmp / 'run' / 'kmsg-forwarded'
                (self.tmp / 'ignore').write_text(ignore)
                for f in ('calls', 'journal'):
                    (self.tmp / f).unlink(missing_ok=True)
                if mark.exists():
                    mark.unlink()
                env = dict(MU300_KMSG_MARK=mark, MU300_KMSG_IGNORE=self.tmp / 'ignore')
                for _ in range(2):
                    r = self.script(shell, BIN / 'kmsg-forward', **env)
                    self.assertEqual(r.returncode, 0, r.stderr)
                d = [c for c in (self.tmp / 'calls').read_text().splitlines() if c.startswith('dmesg')]
                self.assertEqual(len(d), 2, d)
                self.assertIn('--follow ', d[0] + ' ')
                self.assertNotIn('--follow-new', d[0])
                self.assertIn('--follow-new', d[1])
                for c in d:
                    self.assertNotIn('--notime', c)                     # the kernel's timestamps stay
                    self.assertIn('--level=emerg,alert,crit,err,warn', c)
                self.assertIn('[    1.234567] early trace', (self.tmp / 'journal').read_text())


if __name__ == '__main__':
    unittest.main()


class NextBoot(ShellTest):
    """mu300-next-boot (bash) re-arms the Linux slot with tries N+1 in the slot byte of whichever slot Linux is on."""

    def setUp(self):
        super().setUp()
        import importlib.util
        spec = importlib.util.spec_from_file_location('bbi', TOP / 'boot' / 'build-boot-image.py')
        self.bbi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.bbi)
        self.run_dir = self.tmp / 'run'
        self.run_dir.mkdir()
        self.misc = self.tmp / 'misc'
        live = bytes.fromhex('5f61000042434142010200009f001e000000000000000000000000000be17146')
        self.misc.write_bytes(bytes(0x800) + live + bytes(2016))
        self.blocks = self.bbi.bootloader_control(self.misc.read_bytes())   # android_a, linux_b, android_b, linux_a
        (self.run_dir / 'misc-dev').write_text(str(self.misc))
        (self.tmp / 'default-boot').write_text('linux\n')

    def nb(self, *args):
        if not shutil.which('bash'):
            self.skipTest('no bash')
        return subprocess.run(['bash', str(BIN / 'mu300-next-boot'), *args], capture_output=True, text=True,
                              env=self.env(MU300_RUN=self.run_dir, MU300_CONF=self.tmp / 'default-boot',
                                           MU300_CMDLINE_SRC=self.tmp / 'cmdline'))

    def bc(self):
        return self.misc.read_bytes()[0x800:0x820]

    def test_slot_a(self):
        android_a, linux_b, android_b, linux_a = self.blocks
        (self.run_dir / 'linux-slot').write_text('a\n')
        (self.run_dir / 'misc-bc-android.bin').write_bytes(android_b)
        (self.run_dir / 'misc-bc-linux-trial.bin').write_bytes(linux_a)
        r = self.nb('--rearm')
        self.assertEqual(r.returncode, 0, r.stderr)
        # 5 attempts by default: tries 6 in slot a's byte (12), the rest as in the trial block, CRC fixed
        want = bytearray(linux_a)
        want[12] = 0x0f | (6 << 4)
        want[28:32] = struct.pack('<I', zlib.crc32(bytes(want[:28])))
        self.assertEqual(self.bc(), bytes(want))
        self.nb('android')
        self.assertEqual(self.bc(), android_b)

    def test_lock_unlock_and_the_trial_of_a_new_image(self):
        android_a, linux_b, _, _ = self.blocks
        (self.run_dir / 'linux-slot').write_text('b\n')
        (self.run_dir / 'misc-bc-android.bin').write_bytes(android_a)
        (self.run_dir / 'misc-bc-linux-trial.bin').write_bytes(linux_b)
        disk = self.tmp / 'disk'
        (disk / '.mu300').mkdir(parents=True)
        def nb(*a):
            if not shutil.which('bash'):
                self.skipTest('no bash')
            return subprocess.run(['bash', str(BIN / 'mu300-next-boot'), *a], capture_output=True, text=True,
                                  env=self.env(MU300_RUN=self.run_dir, MU300_CONF=self.tmp / 'default-boot',
                                               MU300_CMDLINE_SRC=self.tmp / 'cmdline', MU300_DISK=disk))
        def want(info):
            w = bytearray(linux_b); w[14] = info
            w[28:32] = struct.pack('<I', zlib.crc32(bytes(w[:28])))
            return bytes(w)
        r = nb('lock')
        self.assertEqual(r.returncode, 0, r.stderr)
        # successful=1, prio 15, tries 6: LK never counts it down, never rolls back
        self.assertEqual(self.bc(), want(0xef))
        self.assertTrue((disk / '.mu300/boot-lock').exists())
        self.assertIn('locked: yes', nb('status').stdout)
        # a good boot keeps it locked
        nb('--rearm'); self.assertEqual(self.bc(), want(0xef))
        # mu300-update before a new boot image: the usual attempts, the lock wish kept for the next good boot
        r = nb('--trial'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.bc(), want(0x6f))
        self.assertTrue((disk / '.mu300/boot-lock').exists())
        nb('--rearm'); self.assertEqual(self.bc(), want(0xef))
        # Android by hand: its block, and the wish stays for when Linux is chosen again
        nb('android'); self.assertEqual(self.bc(), android_a)
        self.assertTrue((disk / '.mu300/boot-lock').exists())
        (self.tmp / 'default-boot').write_text('linux\n')
        r = nb('unlock'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.bc(), want(0x6f))
        self.assertFalse((disk / '.mu300/boot-lock').exists())
        self.assertIn('locked: no', nb('status').stdout)

    def test_slot_b_as_before(self):
        android_a, linux_b, _, _ = self.blocks
        (self.run_dir / 'misc-bc-slot-a.bin').write_bytes(android_a)          # an older initramfs: old names only
        (self.run_dir / 'misc-bc-slot-b-trial.bin').write_bytes(linux_b)
        self.assertEqual(self.nb('--rearm').returncode, 0)
        self.assertEqual(self.bc()[14], 0x6f)
        self.nb('android')
        self.assertEqual(self.bc(), android_a)

    def test_without_the_file_the_booted_slot_decides(self):
        # no linux-slot (or a garbled one) but LK booted slot a: the old names are not slot a's, nothing is written
        android_a, linux_b, _, _ = self.blocks
        (self.run_dir / 'misc-bc-slot-a.bin').write_bytes(android_a)
        (self.run_dir / 'misc-bc-slot-b-trial.bin').write_bytes(linux_b)
        (self.tmp / 'cmdline').write_text('console=x androidboot.slot_suffix=_a\n')
        before = self.misc.read_bytes()
        for slot in (None, 'x\n'):
            if slot:
                (self.run_dir / 'linux-slot').write_text(slot)
            self.assertNotEqual(self.nb('android').returncode, 0, slot)
            (self.tmp / 'default-boot').write_text('linux\n')
            self.assertNotEqual(self.nb('--rearm').returncode, 0, slot)
            self.assertEqual(self.misc.read_bytes(), before)

    def test_slot_a_never_falls_back_to_legacy_names(self):
        android_a, linux_b, _, _ = self.blocks
        (self.run_dir / 'linux-slot').write_text('a\n')
        (self.run_dir / 'misc-bc-slot-a.bin').write_bytes(android_a)
        (self.run_dir / 'misc-bc-slot-b-trial.bin').write_bytes(linux_b)
        before = self.misc.read_bytes()
        r = self.nb('android')
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.misc.read_bytes(), before)


class EarlyRecorder(ShellTest):
    """early-recorder's choice of boot partition: the Linux slot's, never Android's."""

    def test_slot(self):
        import re
        m = re.search(r'# --- slot begin\n(.*?)# --- slot end', (BIN / 'early-recorder').read_text(), re.S)
        self.assertIsNotNone(m, 'early-recorder has no slot block')
        run, cmdline = self.tmp / 'run', self.tmp / 'cmdline'
        run.mkdir()
        cases = [(None, None, 'b'), ('a\n', None, 'a'), ('b\n', 'androidboot.slot_suffix=_a', 'b'),
                 (None, 'x androidboot.slot_suffix=_a y', 'a'), ('junk\n', 'androidboot.slot_suffix=_a', 'a'),
                 ('junk\n', 'loglevel=5', 'b')]
        for shell in self.each_shell():
            for v, cl, want in cases:
                for p, data in ((run / 'linux-slot', v), (cmdline, cl)):
                    p.unlink(missing_ok=True)
                    if data is not None:
                        p.write_text(data)
                r = self.sh(shell, m.group(1) + '\necho "$PART"', MU300_RUN=run, MU300_CMDLINE_SRC=cmdline)
                self.assertEqual((r.stdout.strip(), r.stderr), (f'boot_{want}', ''), (v, cl))
