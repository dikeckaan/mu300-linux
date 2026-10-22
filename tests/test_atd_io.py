"""mu300-atd-io (tools/atd-io/mu300-atd-io.c; docs/MODEMD.md, "The bridge protocol"): the C bridge that holds the
modem's AT channels and mu300-at's request FIFOs open for mu300-modemd. Built here with the machine's C compiler (Linux
only, else skipped) and driven through its socket: pseudo-terminals stand in for the SIPC channels (the bridge opens
the slave, the test is the modem on the master), real FIFOs for the request FIFOs, a file for /dev/sipc_sbuf. The rule
above all: a channel is never closed because of its client."""
import errno
import fcntl
import os
import select
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest
from pathlib import Path

from helpers import TOP

SRC = TOP / 'tools' / 'atd-io' / 'mu300-atd-io.c'
CC = shutil.which('gcc') or shutil.which('cc')
LINUX = sys.platform.startswith('linux')
BRIDGE = None
SIPC = None
_build = None

# Makes the bridge's ptys read like the SIPC pipes of the U30 Air (sprd spipe opened O_NONBLOCK): ENODATA where a pty
# says EAGAIN, and with MU300_TEST_NOTTY=1 not a terminal either (the stty_nr channels are misc devices, not ttys).
SIPC_SHIM = r'''
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <stdlib.h>
#include <unistd.h>
static ssize_t (*real_read)(int, void *, size_t);
static int (*real_isatty)(int);
static int tty(int fd)
{
	if (!real_isatty)
		real_isatty = (int (*)(int))dlsym(RTLD_NEXT, "isatty");
	return real_isatty(fd);
}
ssize_t read(int fd, void *b, size_t n)
{
	if (!real_read)
		real_read = (ssize_t (*)(int, void *, size_t))dlsym(RTLD_NEXT, "read");
	ssize_t r = real_read(fd, b, n);
	int e = errno;
	if (r < 0 && e == EAGAIN && tty(fd))
		e = ENODATA;
	errno = e;		/* isatty sets ENOTTY on anything else */
	return r;
}
int isatty(int fd)
{
	const char *e = getenv("MU300_TEST_NOTTY");
	if (e && *e == '1')
		return 0;
	return tty(fd);
}
'''


def setUpModule():
    global BRIDGE, SIPC, _build
    if not (CC and LINUX):
        return
    _build = tempfile.mkdtemp(prefix='mu300-atd-io-build-')
    out = Path(_build) / 'mu300-atd-io'
    r = subprocess.run([CC, '-O2', '-Wall', '-Wextra', '-Werror', '-o', str(out), str(SRC)], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('mu300-atd-io.c does not build without warnings:\n' + r.stderr)
    BRIDGE = out
    shim = Path(_build) / 'sipc-shim.c'
    shim.write_text(SIPC_SHIM)
    r = subprocess.run([CC, '-O2', '-shared', '-fPIC', '-o', str(shim.with_suffix('.so')), str(shim), '-ldl'],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError('the SIPC shim does not build:\n' + r.stderr)
    SIPC = shim.with_suffix('.so')


def tearDownModule():
    if _build:
        shutil.rmtree(_build, ignore_errors=True)


def h(b):
    return b.hex().upper()


def fionread(fd):
    return struct.unpack('i', fcntl.ioctl(fd, termios.FIONREAD, b'\0\0\0\0'))[0]


class Peer:
    """one client connection; records are str without their newline"""

    def __init__(self, path):
        end = time.monotonic() + 3
        while True:
            self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                self.s.connect(str(path))
                break
            except (ConnectionRefusedError, FileNotFoundError):  # between bind and listen, or not there yet
                self.s.close()
                if time.monotonic() > end:
                    raise
                time.sleep(0.01)
        self.buf = b''
        self.eof = False
        self.n = 0

    def send(self, *records):
        self.s.sendall(b''.join((r if isinstance(r, bytes) else r.encode()) + b'\n' for r in records))

    def _fill(self, timeout):
        if self.eof or not select.select([self.s], [], [], max(0.0, timeout))[0]:
            return False
        d = self.s.recv(1 << 20)
        if not d:
            self.eof = True
            return False
        self.buf += d
        return True

    def get(self, timeout=3.0):
        """the next record, or None when none comes within TIMEOUT"""
        end = time.monotonic() + timeout
        while b'\n' not in self.buf:
            if not self._fill(end - time.monotonic()):
                return None
        line, self.buf = self.buf.split(b'\n', 1)
        return line.decode('ascii')

    def until(self, want, timeout=3.0):
        """the records up to and including WANT"""
        seen = []
        end = time.monotonic() + timeout
        while True:
            r = self.get(end - time.monotonic())
            if r is None:
                raise AssertionError(f'never came: {want!r}; came: {[s[:80] for s in seen]!r}')
            seen.append(r)
            if r == want:
                return seen

    def ping(self, timeout=3.0):
        """everything the bridge sent before it answered a PING"""
        self.n += 1
        self.send(f'PING t{self.n}')
        return self.until(f'PONG t{self.n}', timeout)[:-1]

    def closed_by_peer(self, timeout=3.0):
        end = time.monotonic() + timeout
        while not self.eof and time.monotonic() < end:
            self._fill(end - time.monotonic())
        return self.eof

    def close(self):
        self.s.close()


class Pty:
    """a fake channel: the bridge opens PATH (the slave), the test plays the modem on the master. The test keeps a
    slave descriptor of its own, so that the pty lives on whatever the bridge does with its one."""

    def __init__(self):
        self.master, self.slave = os.openpty()
        self.path = os.ttyname(self.slave)
        os.set_blocking(self.master, False)

    def write(self, data):
        while data:
            try:
                data = data[os.write(self.master, data):]
            except BlockingIOError:
                select.select([], [self.master], [], 1)

    def read(self, n, timeout=3.0):
        out = b''
        end = time.monotonic() + timeout
        while len(out) < n and select.select([self.master], [], [], max(0.0, end - time.monotonic()))[0]:
            try:
                out += os.read(self.master, n - len(out))
            except BlockingIOError:
                pass
        return out

    def pending(self, quiet=0.2):
        """whatever the bridge writes until it has been quiet for QUIET seconds"""
        out = b''
        while select.select([self.master], [], [], quiet)[0]:
            try:
                out += os.read(self.master, 1 << 16)
            except BlockingIOError:
                pass
        return out

    def close_master(self):
        if self.master >= 0:
            os.close(self.master)
            self.master = -1

    def close(self):
        self.close_master()
        os.close(self.slave)


@unittest.skipUnless(CC and LINUX, 'needs a C compiler on Linux')
class Bridge(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mu300-atd-io-'))
        self.sock = self.tmp / 'run' / 'io.sock'
        self.sbuf = self.tmp / 'sipc_sbuf'
        self.peers, self.ptys, self.procs = [], [], []
        self.proc = self.start()

    def start(self, log='stderr', **env):
        err = open(self.tmp / log, 'wb')
        p = subprocess.Popen([str(BRIDGE), '-s', str(self.sock)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=err, env=dict(os.environ, MU300_SIPC_SBUF=str(self.sbuf), **env))
        err.close()
        self.procs.append(p)
        return p

    def restart_as_sipc(self, notty):
        """the bridge again, reading its ptys as it reads the SIPC pipes"""
        self.proc.kill()
        self.proc.wait()
        self.proc = self.start('stderr', LD_PRELOAD=str(SIPC), MU300_TEST_NOTTY='1' if notty else '0')

    def tearDown(self):
        for c in self.peers:
            c.close()
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()
        for t in self.ptys:
            t.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stderr(self, log='stderr'):
        return (self.tmp / log).read_text(errors='replace')

    def connect(self, pid=None):
        c = Peer(self.sock)
        self.peers.append(c)
        self.assertEqual(c.get(), f'HELLO 1 {pid or self.proc.pid}')
        return c

    def pty(self):
        t = Pty()
        self.ptys.append(t)
        return t

    def channel(self, c, name='nr1'):
        t = self.pty()
        c.send(f'OPEN {name} {t.path}')
        c.until(f'STATE {name} {t.path} open')
        return t

    def fds_on(self, path):
        """the bridge's descriptors on PATH"""
        d = f'/proc/{self.proc.pid}/fd'
        out = []
        for fd in os.listdir(d):
            try:
                if os.readlink(f'{d}/{fd}').removesuffix(' (deleted)') == str(path):  # a pty without its master
                    out.append(int(fd))
            except OSError:
                pass
        return out

    def switches(self):
        with open(f'/proc/{self.proc.pid}/status') as f:
            return sum(int(line.split()[1]) for line in f if 'ctxt_switches:' in line)

    def drained(self, fifo):
        """wait until the bridge has read everything written to FIFO"""
        fd = os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            end = time.monotonic() + 5
            while fionread(fd):
                self.assertLess(time.monotonic(), end, 'the bridge does not read its FIFO')
                time.sleep(0.005)
        finally:
            os.close(fd)

    def write_sbuf(self, text):
        tmp = self.sbuf.with_suffix('.new')
        tmp.write_text(text)
        os.replace(tmp, self.sbuf)


class Connection(Bridge):
    def test_hello_and_the_state_of_everything_held_on_every_connection(self):
        c = self.connect()
        self.assertEqual(stat.S_IMODE(self.sock.parent.stat().st_mode), 0o700)
        st = os.lstat(self.sock)
        self.assertTrue(stat.S_ISSOCK(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        t = self.channel(c)
        cmd = self.tmp / 'cmd'
        c.send(f'FIFO nr1 {cmd}')
        self.assertEqual(c.ping(), [f'STATE nr1 {cmd} open'])
        # repeats change nothing and answer the state; another device under a known name changes nothing either
        c.send(f'OPEN nr1 {t.path}', f'FIFO nr1 {cmd}', 'OPEN nr1 /dev/null')
        self.assertEqual(c.ping(), [f'STATE nr1 {t.path} open', f'STATE nr1 {cmd} open', f'STATE nr1 {t.path} open'])
        # a device another channel holds is refused: two readers of a SIPC channel would each get half of every reply
        c.send(f'OPEN nr2 {t.path}', f'FIFO nr2 {cmd}')
        self.assertEqual(c.ping(), [f'OPENFAIL nr2 {errno.EBUSY}', f'STATE nr2 {t.path} closed',
                                    f'OPENFAIL nr2 {errno.EBUSY}', f'STATE nr2 {cmd} closed'])
        self.assertEqual(len(self.fds_on(t.path)), 1)
        c2 = self.connect()
        self.assertEqual(c2.ping(), [f'STATE nr1 {t.path} open', f'STATE nr1 {cmd} open'])
        self.assertIn(f'listening on {self.sock}', self.stderr())

    def test_a_new_client_replaces_the_old_one_and_the_channel_stays_open(self):
        c1 = self.connect()
        t = self.channel(c1)
        fds = self.fds_on(t.path)
        self.assertEqual(len(fds), 1)
        c2 = self.connect()                     # c1 still connected: it is the one that goes
        self.assertEqual(c2.ping(), [f'STATE nr1 {t.path} open'])
        self.assertTrue(c1.closed_by_peer())
        t.write(b'one\r\n')
        self.assertEqual(c2.get(), 'RX nr1 ' + h(b'one'))
        # the client goes away, the modem keeps talking: the next client gets what was said meanwhile
        c2.close()
        t.write(b'two\r\n+CREG: 1\r\n')
        c3 = self.connect()
        self.assertEqual(c3.get(), f'STATE nr1 {t.path} open')
        self.assertEqual(c3.get(), 'RX nr1 ' + h(b'two'))
        self.assertEqual(c3.get(), 'RX nr1 ' + h(b'+CREG: 1'))
        c3.send('TX nr1 ' + h(b'AT\r'))
        self.assertEqual(t.read(3), b'AT\r')
        self.assertEqual(self.fds_on(t.path), fds)     # the same descriptor all along
        self.assertNotIn('end of file', self.stderr())
        self.assertIn('client replaced', self.stderr())

    def test_a_client_that_stops_reading_is_dropped_and_the_channel_kept(self):
        c = self.connect()
        t = self.channel(c)
        fds = self.fds_on(t.path)
        t.write(b'X' * 100 + b'\r\n' + (b'Y' * 100 + b'\r\n') * 10000 + b'END\r\n')   # 2 MB of records, unread
        end = time.monotonic() + 10
        while 'stopped reading' not in self.stderr():
            self.assertLess(time.monotonic(), end, self.stderr())
            time.sleep(0.01)
        self.assertTrue(c.closed_by_peer())
        c2 = self.connect()
        seen = c2.until('RX nr1 ' + h(b'END'), timeout=10)
        self.assertEqual(seen[0], f'STATE nr1 {t.path} open')
        self.assertTrue(seen[1].startswith('DROPPED nr1 '), seen[1])
        self.assertTrue(all(r == 'RX nr1 ' + h(b'Y' * 100) for r in seen[2:-1]))
        self.assertEqual(self.fds_on(t.path), fds)
        self.assertNotIn('end of file', self.stderr())

    def test_malformed_records_are_ignored_with_one_line_each(self):
        c = self.connect()
        t = self.channel(c)
        secret = h(b'1234 SECRET PIN').encode()
        bad = [b'BOGUS nr1', b'TX nr1 ' + secret + b'5', b'TX nr1 ' + secret[:-2] + b'ZZ', b'TX NR1 41', b'TX nr1  41',
               b'TX nr1 41 ', b'TX nr1', b'OPEN nr1', b'OPEN seventeen-chars-x /dev/null', b'OPEN nr2 dev/null',
               b'OPEN nr2 /dev/null ready', b'OPEN nr2 /dev/null sbuf:a,b', b'FIFO nr2', b'CLOSE', b'PING', b'',
               b'TX nr1 41\x01', b'TX nr1 \xc3\xa9', b'TX nr1 ' + b'41' * 70000]
        c.send(*bad)
        self.assertEqual(c.ping(), [])
        self.assertEqual(t.pending(), b'')                     # nothing reached the channel
        c.send(f'OPEN nr1 {t.path}')
        self.assertEqual(c.ping(), [f'STATE nr1 {t.path} open'])
        err = self.stderr()
        self.assertEqual(err.count('record from the client, ignored'), len(bad), err)
        self.assertNotIn(secret[:20].decode(), err)
        self.assertNotIn('SECRET', err)
        # past 20 lines per connection: one line that says so, then silence
        c.send(*bad[:5])
        self.assertEqual(c.ping(), [])
        err = self.stderr()
        self.assertEqual(err.count('record from the client, ignored'), 20)
        self.assertEqual(err.count('not logged'), 1)
        # none of them made a channel
        c2 = self.connect()
        self.assertEqual(c2.ping(), [f'STATE nr1 {t.path} open'])


class Channels(Bridge):
    def test_rx_lines(self):
        c = self.connect()
        t = self.channel(c)
        t.write(b'+CSQ: 23,99\r\nOK\r\n\r\nplain\n\x00\xff\x1a\r\r\n')
        for line in (b'+CSQ: 23,99', b'OK', b'', b'plain', b'\x00\xff\x1a\r'):
            self.assertEqual(c.get(), 'RX nr1 ' + h(line))
        # a line in two writes is one line, without an RXP between them
        t.write(b'+CRE')
        time.sleep(0.05)
        t.write(b'G: 1,5\r\n')
        self.assertEqual(c.until('RX nr1 ' + h(b'+CREG: 1,5')), ['RX nr1 ' + h(b'+CREG: 1,5')])
        # longer than 8192 bytes: in pieces
        long = bytes(range(32, 127)) * 100
        t.write(long + b'\r\n')
        self.assertEqual(c.get(), 'RX nr1 ' + h(long[:8192]))
        self.assertEqual(c.get(), 'RX nr1 ' + h(long[8192:]))
        self.assertEqual(c.ping(), [])

    def test_a_prompt_without_a_newline_goes_out_after_300_ms_of_quiet(self):
        c = self.connect()
        t = self.channel(c)
        start = time.monotonic()
        t.write(b'\r\n> ')
        self.assertEqual(c.get(), 'RX nr1 ')
        self.assertEqual(c.get(), 'RXP nr1 ' + h(b'> '))
        took = time.monotonic() - start
        self.assertGreaterEqual(took, 0.28)
        self.assertLess(took, 1.5)
        t.write(b'+CMGS: 5\r\n')
        self.assertEqual(c.get(), 'RX nr1 ' + h(b'+CMGS: 5'))
        # the wait starts again with every byte: a line that comes in pieces is not cut
        start = time.monotonic()
        t.write(b'abc')
        time.sleep(0.2)
        t.write(b'def')
        self.assertEqual(c.get(), 'RXP nr1 ' + h(b'abcdef'))
        self.assertGreaterEqual(time.monotonic() - start, 0.48)

    def test_tx_bytes_reach_the_channel_exactly(self):
        c = self.connect()
        t = self.channel(c)
        data = bytes(range(256)) + b'AT+CMGS=23\r0891\x1a'
        c.send('TX nr1 ' + h(data))
        self.assertEqual(t.read(len(data)), data)
        c.send('TX nr1 ' + data.hex())                       # lower case is hex too
        self.assertEqual(t.read(len(data)), data)
        c.send('TX nr1 ', 'TX nr9 41')                        # nothing to write; no such channel
        self.assertEqual(c.ping(), [f'TXERR nr9 {errno.ENOENT}'])
        self.assertEqual(t.pending(), b'')

    def test_a_channel_that_does_not_take_a_tx_fails_it_after_2_s_and_stays_open(self):
        c = self.connect()
        t = self.channel(c)
        chunk = 'TX nr1 ' + h(b'A' * 65536)
        for _ in range(100):                                  # until the pty's buffers are full
            start = time.monotonic()
            c.send(chunk)
            got = c.ping(timeout=5)
            if got:
                break
        took = time.monotonic() - start
        self.assertEqual(got, [f'TXERR nr1 {errno.ETIMEDOUT}'])
        self.assertGreaterEqual(took, 1.9)
        self.assertLess(took, 3.5)
        t.pending(quiet=0.3)
        c.send('TX nr1 ' + h(b'Z\r'))
        self.assertTrue(t.pending().endswith(b'Z\r'))
        c.send(f'OPEN nr1 {t.path}')
        self.assertEqual(c.ping(), [f'STATE nr1 {t.path} open'])
        self.assertIn('a write failed', self.stderr())
        self.assertNotIn('4141', self.stderr())

    def test_end_of_file_closes_the_channel_for_good(self):
        c = self.connect()
        t = self.channel(c)
        t.write(b'last\r\n')
        c.until('RX nr1 ' + h(b'last'))
        t.close_master()
        seen = c.until(f'STATE nr1 {t.path} eof')
        self.assertEqual(seen[-2:], ['EOF nr1', f'STATE nr1 {t.path} eof'])
        self.assertEqual(self.fds_on(t.path), [])
        time.sleep(0.25)                                     # longer than an open retry: none comes
        c.send('TX nr1 41', f'OPEN nr1 {t.path}')
        self.assertEqual(c.ping(), [f'TXERR nr1 {errno.EBADF}', f'STATE nr1 {t.path} eof'])
        self.assertIn('end of file', self.stderr())
        # REOPEN opens it again (gone with its master: pending), CLOSE forgets it
        c.send('REOPEN nr1')
        got = c.ping()
        self.assertEqual(got[0], f'STATE nr1 {t.path} pending')
        self.assertTrue(got[1].startswith('OPENFAIL nr1 '), got)
        c.send('CLOSE nr1')
        self.assertEqual(c.ping(), [f'STATE nr1 {t.path} closed'])
        c.send('CLOSE nr1')                                  # again: nothing
        self.assertEqual(c.ping(), [])
        self.assertEqual(self.connect().ping(), [])

    def test_a_drained_sipc_channel_reads_enodata_and_stays_open(self):
        # the U30 Air, 2026-10-23: every channel read a line and then ENODATA, which closed all three for good
        self.restart_as_sipc(notty=False)
        c = self.connect()
        t = self.channel(c)
        for n in range(3):
            t.write(b'+CEREG: %d\r\n' % n)
            c.until('RX nr1 ' + h(b'+CEREG: %d' % n))
            time.sleep(0.05)
        t.write(b'> ')
        c.until('RXP nr1 ' + h(b'> '))
        c.send('TX nr1 ' + h(b'AT\r'))
        self.assertTrue(t.pending().endswith(b'AT\r'))
        self.assertEqual(c.ping(), [])
        self.assertEqual(len(self.fds_on(t.path)), 1)
        self.assertNotIn('end of file', self.stderr())
        self.assertNotIn('read failed', self.stderr())

    def test_a_sipc_channel_is_never_closed_by_a_read_and_does_not_spin(self):
        self.restart_as_sipc(notty=True)
        c = self.connect()
        t = self.channel(c)
        t.write(b'OK\n')                                     # not a terminal: left cooked, where \r would be \n
        c.until('RX nr1 ' + h(b'OK'))
        t.close_master()                                     # the slave now reads EIO and polls POLLHUP for ever
        time.sleep(0.3)
        before = self.switches()
        time.sleep(1.2)
        self.assertLess(self.switches() - before, 12)        # one read a second, not a loop
        self.assertEqual(c.ping(), [])                       # no EOF, no STATE
        self.assertEqual(len(self.fds_on(t.path)), 1)
        err = self.stderr()
        self.assertEqual(err.count('kept open'), 1, err)     # one line per new error
        self.assertNotIn('end of file', err)
        c.send('TX nr1 41')                                  # the channel is still there to write to (the pty fails it)
        got = c.ping()
        self.assertTrue(all(r.startswith('TXERR nr1 ') for r in got), got)
        self.assertNotIn(f'STATE nr1 {t.path} eof', got)

    def test_a_device_that_appears_later_is_opened_by_the_retry(self):
        c = self.connect()
        dev = self.tmp / 'stty_nr4'
        c.send(f'OPEN nr4 {dev}')
        self.assertEqual(c.ping(), [f'STATE nr4 {dev} pending', f'OPENFAIL nr4 {errno.ENOENT}'])
        time.sleep(0.45)                                     # two retries: one OPENFAIL per pending period
        self.assertEqual(c.ping(), [])
        t = self.pty()
        os.symlink(t.path, dev)
        start = time.monotonic()
        c.until(f'STATE nr4 {dev} open')
        self.assertLess(time.monotonic() - start, 1.0)
        t.write(b'OK\r\n')
        self.assertEqual(c.get(), 'RX nr4 ' + h(b'OK'))
        self.assertIn('opened after', self.stderr())

    def test_ready_waits_for_the_sbuf_line(self):
        c = self.connect()
        t = self.pty()
        self.write_sbuf('sbuf_5_006, state: 0, rxbuf 0\n xsbuf_5_006, state: 1,\nsbuf_5_0060, state: 1,\n'
                        'sbuf_5_006 state: 1,\n')
        c.send(f'OPEN nr4 {t.path} sbuf:sbuf_5_006')
        self.assertEqual(c.ping(), [f'STATE nr4 {t.path} pending', f'OPENFAIL nr4 {errno.ENODEV}'])
        time.sleep(0.45)
        self.assertEqual(c.ping(), [])
        self.assertEqual(self.fds_on(t.path), [])               # never opened before it is ready
        self.write_sbuf('sbuf_5_005, state: 1, a\nsbuf_5_006, state: 1, rxbuf 0\n')
        c.until(f'STATE nr4 {t.path} open')
        self.assertEqual(len(self.fds_on(t.path)), 1)
        # without the file at all it is never ready
        os.unlink(self.sbuf)
        t2 = self.pty()
        c.send(f'OPEN nr5 {t2.path} sbuf:sbuf_5_007')
        self.assertEqual(c.ping(), [f'STATE nr5 {t2.path} pending', f'OPENFAIL nr5 {errno.ENOENT}'])

    def test_no_wakeups_while_nothing_is_pending(self):
        c = self.connect()
        t = self.channel(c)
        c.send(f'FIFO nr1 {self.tmp}/cmd')
        c.until(f'STATE nr1 {self.tmp}/cmd open')
        t.write(b'> ')
        c.until('RXP nr1 ' + h(b'> '))
        before = self.switches()
        time.sleep(0.5)
        self.assertEqual(self.switches(), before)
        # a pending open is tried every 200 ms
        c.send(f'OPEN nr5 {self.tmp}/missing')
        c.ping()
        before = self.switches()
        time.sleep(0.5)
        self.assertGreaterEqual(self.switches() - before, 2)


class Fifos(Bridge):
    def test_requests_from_the_fifo(self):
        c = self.connect()
        d = self.tmp / 'at'
        d.mkdir()
        cmd = d / 'cmd'
        c.send(f'FIFO nr1 {cmd}')
        self.assertEqual(c.ping(), [f'STATE nr1 {cmd} open'])
        st = os.lstat(cmd)
        self.assertTrue(stat.S_ISFIFO(st.st_mode))
        self.assertEqual(stat.S_IMODE(st.st_mode), 0o600)
        # another process writes a request, the way mu300-at does
        subprocess.run(['sh', '-c', 'printf "6 %s AT+CSQ\\n" "$2" > "$1"', 'sh', str(cmd), f'{d}/answer.1'],
                       check=True, timeout=5)
        self.assertEqual(c.get(), 'REQ nr1 ' + h(f'6 {d}/answer.1 AT+CSQ'.encode()))
        # a CR inside (the PDU send) and an empty line pass as they are; a line over 8192 bytes is dropped
        with open(cmd, 'wb', buffering=0) as w:
            w.write(b'9 /x AT+CMGS=23\r0891\x1a\n\n' + b'A' * 9000 + b'\nafter\n')
        self.assertEqual(c.get(), 'REQ nr1 ' + h(b'9 /x AT+CMGS=23\r0891\x1a'))
        self.assertEqual(c.get(), 'REQ nr1 ')
        self.assertEqual(c.get(), 'REQ nr1 ' + h(b'after'))
        self.assertIn('longer than 8192 bytes, dropped', self.stderr())
        self.assertNotIn('AAAA', self.stderr())
        # a request while no client is connected waits for the next one
        c.close()
        subprocess.run(['sh', '-c', 'printf "7 /x AT+COPS?\\n" > "$1"', 'sh', str(cmd)], check=True, timeout=5)
        self.drained(cmd)
        c2 = self.connect()
        self.assertEqual(c2.get(), f'STATE nr1 {cmd} open')
        self.assertEqual(c2.get(), 'REQ nr1 ' + h(b'7 /x AT+COPS?'))

    def test_an_existing_fifo_is_kept_and_anything_else_replaced(self):
        c = self.connect()
        keep = self.tmp / 'keep'
        os.mkfifo(keep, 0o644)
        ino = os.lstat(keep).st_ino
        c.send(f'FIFO a {keep}')
        c.until(f'STATE a {keep} open')
        self.assertEqual(os.lstat(keep).st_ino, ino)
        self.assertEqual(stat.S_IMODE(os.lstat(keep).st_mode), 0o600)
        regular, link = self.tmp / 'regular', self.tmp / 'link'
        regular.write_text('x')
        os.symlink(self.tmp / 'target', link)
        for name, p in (('b', regular), ('c', link)):
            c.send(f'FIFO {name} {p}')
            c.until(f'STATE {name} {p} open')
            self.assertTrue(stat.S_ISFIFO(os.lstat(p).st_mode))
        self.assertFalse(os.path.lexists(self.tmp / 'target'))
        # one that cannot be made
        c.send(f'FIFO d {self.tmp}/no/such/cmd')
        self.assertEqual(c.ping(), [f'OPENFAIL d {errno.ENOENT}', f'STATE d {self.tmp}/no/such/cmd closed'])
        # removed under the bridge: a repeat makes it again, and requests come through the new one
        os.unlink(keep)
        c.send(f'FIFO a {keep}')
        c.until(f'STATE a {keep} open')
        with open(keep, 'wb', buffering=0) as w:
            w.write(b'again\n')
        self.assertEqual(c.get(), 'REQ a ' + h(b'again'))
        # CLOSE removes it
        c.send('CLOSE a')
        self.assertEqual(c.ping(), [f'STATE a {keep} closed'])
        self.assertFalse(os.path.lexists(keep))


class Queue(Bridge):
    def test_1024_records_per_name_and_256_kib_in_all_while_no_client_is_connected(self):
        c = self.connect()
        q = self.tmp / 'q'
        c.send(f'FIFO q {q}')
        c.until(f'STATE q {q} open')
        c.close()
        with open(q, 'wb', buffering=0) as w:
            w.write(b''.join(b'R%d\n' % i for i in range(1100)))
        self.drained(q)
        c2 = self.connect()
        self.assertEqual(c2.get(), f'STATE q {q} open')
        self.assertEqual(c2.get(), 'DROPPED q 76')
        for i in range(76, 1100):
            self.assertEqual(c2.get(), 'REQ q ' + h(b'R%d' % i))
        self.assertEqual(c2.ping(), [])
        self.assertIn('76 records of q were dropped', self.stderr())
        # 16 records of 16007 bytes fit in 256 KiB, the 24 before them do not
        c2.close()
        with open(q, 'wb', buffering=0) as w:
            for i in range(40):
                w.write(b'%02d' % i + b'B' * 7998 + b'\n')
        self.drained(q)
        c3 = self.connect()
        self.assertEqual(c3.get(), f'STATE q {q} open')
        self.assertEqual(c3.get(), 'DROPPED q 24')
        for i in range(24, 40):
            self.assertEqual(c3.get(), 'REQ q ' + h(b'%02d' % i + b'B' * 7998))
        self.assertEqual(c3.ping(), [])


class Stop(Bridge):
    def test_sigterm_closes_everything_and_exits_0(self):
        c = self.connect()
        self.channel(c)
        cmd = self.tmp / 'cmd'
        c.send(f'FIFO nr1 {cmd}')
        c.until(f'STATE nr1 {cmd} open')
        self.proc.send_signal(signal.SIGTERM)
        self.assertEqual(self.proc.wait(timeout=5), 0)
        self.assertTrue(c.closed_by_peer())
        self.assertFalse(os.path.lexists(self.sock))
        self.assertFalse(os.path.lexists(cmd))
        self.assertIn('stopping', self.stderr())

    def test_a_second_instance_waits_for_the_first(self):
        c = self.connect()
        second = self.start('stderr2')
        end = time.monotonic() + 5
        while 'waiting for it to end' not in self.stderr('stderr2'):
            self.assertLess(time.monotonic(), end, self.stderr('stderr2'))
            time.sleep(0.01)
        self.assertEqual(c.ping(), [])                       # the first one still serves
        self.proc.send_signal(signal.SIGINT)
        self.assertEqual(self.proc.wait(timeout=5), 0)
        end = time.monotonic() + 5
        while True:                                          # the socket of the first may still be there for a moment
            try:
                c2 = Peer(self.sock)
                first = c2.get()
                if first == f'HELLO 1 {second.pid}':
                    break
                c2.close()
            except OSError:
                pass
            self.assertLess(time.monotonic(), end)
            time.sleep(0.01)
        self.peers.append(c2)
        second.send_signal(signal.SIGTERM)
        self.assertEqual(second.wait(timeout=5), 0)


class Wiring(unittest.TestCase):
    """the images get the bridge the way they get mu300-keys: built static in the release and the installer, put into
    /opt/mu300/bin by both root filesystem builds"""

    def test_built_and_installed(self):
        for script, d in (('tools/make-release.sh', '$IN'), ('install.sh', '$WORK')):
            text = (TOP / script).read_text()
            self.assertIn('mkdir -p /o/atd-io && gcc -O2 -static -o /o/atd-io/mu300-atd-io /src/atd-io/mu300-atd-io.c &&',
                          text)
            self.assertIn(f'-v "{d}/tools/atd-io/mu300-atd-io":/atd-io:ro', text)
        assemble = (TOP / 'rootfs/assemble.sh').read_text()
        self.assertIn('if [ -e /atd-io ]; then install -m755 /atd-io $R/opt/mu300/bin/mu300-atd-io; fi', assemble)
        owrt = (TOP / 'openwrt/build-rootfs.sh').read_text()
        self.assertIn('$(opt tools/atd-io/mu300-atd-io atd-io)', owrt)
        self.assertIn('[ -e /in/atd-io ] && { cp /in/atd-io $R/opt/mu300/bin/mu300-atd-io; '
                      'chmod 755 $R/opt/mu300/bin/mu300-atd-io; }', owrt)


if __name__ == '__main__':
    unittest.main()
