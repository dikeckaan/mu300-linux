/*
 * mu300-atd-io: holds the modem's AT channels (the SIPC ttys /dev/stty_nr*) and mu300-at's request FIFOs open and moves
 * their bytes to and from one client over a unix socket: mu300-modemd, which makes every decision. No AT knowledge at
 * all. The protocol is docs/MODEMD.md, "The bridge protocol".
 *
 * Why a C program: modemd is ucode, which cannot make a descriptor non-blocking, so a tty read from its event loop
 * would stop the loop at the first partial line. And the descriptors outlive modemd: closing a SIPC channel while the
 * modem runs silences it until a reboot (FINDINGS 13b). Everything here follows from that: a channel is closed on
 * CLOSE, REOPEN, SIGTERM and the end of file of a terminal (a test's pty) and on nothing else. A client that goes away, stops reading or sends garbage
 * loses its connection at most, never a channel.
 *
 * usage: mu300-atd-io [-s SOCKET]     (default /run/mu300-modem/io.sock)
 *   MU300_SIPC_SBUF   the file the READY condition reads (default /dev/sipc_sbuf; for the tests)
 * Runs in the foreground (procd supervises it). Short lines on stderr, and never a payload byte: AT traffic holds
 * PINs, passwords and messages. Its name keeps "mu300-atd" in the command line, which mu300-at and the panel's
 * collector take for a live owner of the channel.
 *
 * What the protocol leaves open, decided here:
 *   - An ERRNO field is the decimal errno value (Linux numbers, the same on arm64 and x86_64).
 *   - An empty payload is an empty last field: "RX nr0 " is an empty line. "TX NAME " writes nothing.
 *   - RXP goes out once no byte has come for 300 ms, so a line that arrives in pieces is not cut.
 *   - A channel and a FIFO may share a NAME (the FIFO of channel nr1 is FIFO nr1); their STATE lines differ in the
 *     path, and they share the queue limit of that name. CLOSE NAME closes both. A CLOSE of an unknown name does
 *     nothing; a TX to a channel that is unknown or not open is answered with TXERR (ENOENT, EBADF).
 *   - An OPEN of a known NAME with another device changes nothing and answers the channel's STATE (which names the
 *     device it holds); an OPEN of a device another channel holds is refused (OPENFAIL EBUSY, STATE closed): two
 *     readers of a SIPC channel each get half of every reply. The same for FIFO with a path in use.
 *   - A FIFO that cannot be made: OPENFAIL NAME ERRNO and STATE NAME PATH closed. A repeated FIFO whose path no longer
 *     is our FIFO (removed, replaced) makes it again. CLOSE and SIGTERM remove a FIFO that still is ours, as
 *     mu300-atd did: no client may write into a FIFO that nobody reads.
 *   - Nothing to read is EAGAIN, and also ENODATA and EBUSY: a SIPC pipe opened O_NONBLOCK reads ENODATA once it is
 *     drained (sbuf_read without waiting) and EBUSY while its reader lock is taken.
 *   - On a terminal (a pty in the tests) any other read error is an end of file (one whose other side closed reads
 *     EIO). A SIPC channel is not a terminal and is never closed by what a read says, since closing it is what silences
 *     it: after an error, a read of 0 bytes or a hangup it stays open and is left out of the poll for PAUSE_MS, one
 *     line on stderr per new error. A channel that wakes the loop EMPTY_MAX times in a row with nothing to read is
 *     left out for EMPTY_PAUSE_MS, so a poll that keeps saying POLLIN cannot spin the loop either.
 *   - A partial line still waiting is sent as RXP before EOF, REOPEN and CLOSE.
 *   - A record that never reached a client that went away goes back into the queue for the next one (whole records
 *     only, no replies), so a client restart loses only what was already in the socket.
 *   - A peer of another uid is refused. A second instance on the same socket waits for the first (a lock file next
 *     to the socket), as a second mu300-atd did: two of them would split every channel.
 *
 * SPDX-License-Identifier: MIT
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <poll.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <termios.h>
#include <time.h>
#include <unistd.h>

#define PROTO_VERSION 1
#define MAXCH 32		/* channels held at once */
#define MAXFIFO 32		/* request FIFOs held at once */
#define NAMEMAX 16		/* [a-z0-9_-]{1,16} */
#define PATHMAX 255		/* a device or FIFO path */
#define SBUFMAX 64		/* the sbuf name of a READY condition */
#define TOKENMAX 64		/* a PING token */
#define LINEMAX 8192		/* an RX piece; the longest request line */
#define TXMAX 65536		/* the bytes of one TX */
#define RECMAX (2 * TXMAX + 64)	/* the longest client record */
#define OUTMAX (1 << 20)	/* a client that lets more than this wait is dropped */
#define QPER 1024		/* records queued per name while no client is connected */
#define QBYTES (256 * 1024)	/* ... and in all */
#define QNAMES 128
#define RETRY_MS 200		/* a pending open is tried again after this */
#define RXP_MS 300		/* a partial line goes out once quiet this long */
#define TX_MS 2000		/* a TX the channel has not taken whole by then fails */
#define PAUSE_MS 1000		/* a SIPC channel whose read failed is read again after this */
#define EMPTY_MAX 8		/* wakeups in a row with nothing to read ... */
#define EMPTY_PAUSE_MS 200	/* ... leave the channel out of the poll this long */
#define BADLOG 20		/* malformed records logged per connection */

enum { ST_NEW = -1, ST_OPEN, ST_PENDING, ST_EOF };
static const char *const st_word[] = { "open", "pending", "eof" };

struct chan {
	int used;
	char name[NAMEMAX + 1], dev[PATHMAX + 1], sbuf[SBUFMAX + 1];	/* sbuf: the READY condition, "" for none */
	int fd, state;
	int failed;		/* this pending period has had its OPENFAIL */
	long long next_try;	/* pending: the next attempt */
	long long since;	/* pending: since when */
	long long last_rx;	/* when the last byte of the partial line came */
	int tty;		/* open: the device is a terminal, whose read errors are an end of file */
	int rderr;		/* open: the read error being paused on (-1: a read of 0 bytes), 0 while reads work */
	int empty;		/* open: wakeups in a row with nothing to read */
	int quiet_said;		/* open: the EMPTY_MAX line went out */
	long long resume;	/* open: left out of the poll until then, 0 when polled */
	size_t len;		/* the partial line */
	unsigned char line[LINEMAX];
};

struct fifo {
	int used;
	char name[NAMEMAX + 1], path[PATHMAX + 1];
	int fd, skipping;	/* skipping: the rest of an overlong line */
	dev_t dev;
	ino_t ino;
	size_t len;
	unsigned char line[LINEMAX];
};

/* the queue while no client is connected: every record oldest first, and each name's records oldest first */
struct qname;
struct rec {
	struct rec *prev, *next, *nnext;
	struct qname *q;
	size_t len;
	char text[];
};
struct qname {
	char name[NAMEMAX + 1];
	struct rec *head, *tail;
	unsigned count;
	unsigned long dropped;
};

static struct chan ch[MAXCH];
static struct fifo ff[MAXFIFO];
static struct qname qn[QNAMES];
static struct rec *qhead, *qtail;
static size_t qbytes;

static int lfd = -1, cfd = -1;		/* the listening socket, the client */
static char *obuf;			/* to the client: obuf[ooff..olen) */
static size_t ooff, olen, ocap;
static char ibuf[RECMAX + 1];		/* from the client: the record so far */
static size_t ilen;
static int iskip, nbad;
static char rbuf[2 * LINEMAX + 2 * PATHMAX + 64];	/* the record being made */
static volatile sig_atomic_t stop;

static long long now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
}

/* one line on stderr, written whole */
static void say(const char *fmt, ...)
{
	char b[640] = "mu300-atd-io: ";
	size_t n = strlen(b);
	va_list ap;
	va_start(ap, fmt);
	vsnprintf(b + n, sizeof(b) - n - 1, fmt, ap);
	va_end(ap);
	n = strlen(b);
	b[n++] = '\n';
	if (write(2, b, n) < 0) {
	}
}

static void on_stop(int sig)
{
	(void)sig;
	stop = 1;
}

/* ---------------------------------------------------------------- the queue */

static struct qname *qslot(const char *name)
{
	struct qname *empty = NULL;
	for (int i = 0; i < QNAMES; i++) {
		if (qn[i].name[0] && !strcmp(qn[i].name, name))
			return &qn[i];
		if (!qn[i].name[0] && !empty)
			empty = &qn[i];
	}
	if (empty)
		snprintf(empty->name, sizeof(empty->name), "%s", name);
	return empty;
}

/* drop the oldest record of Q (the oldest of its name; the oldest of all is the oldest of its own name too) */
static void qdrop(struct qname *q)
{
	struct rec *r = q->head;
	if (!r)
		return;
	q->head = r->nnext;
	if (!q->head)
		q->tail = NULL;
	if (r->prev)
		r->prev->next = r->next;
	else
		qhead = r->next;
	if (r->next)
		r->next->prev = r->prev;
	else
		qtail = r->prev;
	q->count--;
	qbytes -= r->len;
	if (!q->dropped++)
		say("no client: the queue is full, dropping the oldest records of %s", q->name);
	free(r);
}

static void queue(const char *name, const char *s, size_t n)
{
	struct qname *q = qslot(name);
	if (!q || n > QBYTES)
		return;
	if (q->count >= QPER)
		qdrop(q);
	while (qhead && qbytes + n > QBYTES)
		qdrop(qhead->q);
	struct rec *r = malloc(sizeof(*r) + n);
	if (!r) {
		q->dropped++;
		return;
	}
	memcpy(r->text, s, n);
	r->len = n;
	r->q = q;
	r->next = r->nnext = NULL;
	r->prev = qtail;
	if (qtail)
		qtail->next = r;
	else
		qhead = r;
	qtail = r;
	if (q->tail)
		q->tail->nnext = r;
	else
		q->head = r;
	q->tail = r;
	q->count++;
	qbytes += n;
}

/* a record that never reached the client goes back into the queue: the kinds that are queued, not the replies */
static void requeue(const char *s, size_t n)
{
	static const char *const kinds[] = { "RX ", "RXP ", "REQ ", "STATE ", "EOF ", "OPENFAIL " };
	for (size_t k = 0; k < sizeof(kinds) / sizeof(kinds[0]); k++) {
		size_t kl = strlen(kinds[k]), l = 0;
		if (n <= kl || memcmp(s, kinds[k], kl))
			continue;
		const char *name = s + kl;
		while (kl + l < n && name[l] != ' ' && name[l] != '\n')
			l++;
		if (l && l <= NAMEMAX) {
			char nm[NAMEMAX + 1];
			memcpy(nm, name, l);
			nm[l] = 0;
			queue(nm, s, n);
		}
		return;
	}
}

/* ---------------------------------------------------------------- the client */

static void client_close(const char *why)
{
	if (cfd < 0)
		return;
	say("client %s", why);
	close(cfd);
	cfd = -1;
	/* whole records only: the first one may have gone out in part */
	size_t p = ooff;
	if (p > 0 && obuf[p - 1] != '\n') {
		while (p < olen && obuf[p] != '\n')
			p++;
		if (p < olen)
			p++;
	}
	while (p < olen) {
		char *e = memchr(obuf + p, '\n', olen - p);
		if (!e)
			break;
		size_t n = (size_t)(e + 1 - (obuf + p));
		requeue(obuf + p, n);
		p += n;
	}
	ooff = olen = 0;
	ilen = 0;
	iskip = nbad = 0;
	if (ocap > 256 * 1024) {
		free(obuf);
		obuf = NULL;
		ocap = 0;
	}
}

static void flush(void)
{
	while (cfd >= 0 && ooff < olen) {
		ssize_t w = send(cfd, obuf + ooff, olen - ooff, MSG_NOSIGNAL | MSG_DONTWAIT);
		if (w > 0) {
			ooff += (size_t)w;
			continue;
		}
		if (w == 0 || errno == EAGAIN || errno == EWOULDBLOCK)
			break;
		if (errno == EINTR)
			continue;
		client_close("gone");
		return;
	}
	if (ooff == olen)
		ooff = olen = 0;
}

static void out_add(const char *s, size_t n)
{
	if (olen + n > ocap) {
		if (ooff) {
			memmove(obuf, obuf + ooff, olen - ooff);
			olen -= ooff;
			ooff = 0;
		}
		if (olen + n > ocap) {
			size_t cap = ocap ? ocap : 65536;
			while (cap < olen + n)
				cap *= 2;
			char *b = realloc(obuf, cap);
			if (!b) {
				client_close("dropped: out of memory");
				return;
			}
			obuf = b;
			ocap = cap;
		}
	}
	memcpy(obuf + olen, s, n);
	olen += n;
	if (olen - ooff > OUTMAX) {
		flush();
		if (cfd >= 0 && olen - ooff > OUTMAX)
			client_close("stopped reading (1 MiB waiting): dropped");
	}
}

/* a record to the client, or into the queue under NAME while there is none (NAME NULL: a reply, never queued) */
static void put(const char *name, const char *s, size_t n)
{
	if (cfd >= 0)
		out_add(s, n);
	else if (name)
		queue(name, s, n);
}

static void rec(const char *name, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int n = vsnprintf(rbuf, sizeof(rbuf), fmt, ap);
	va_end(ap);
	if (n > 0 && (size_t)n < sizeof(rbuf))
		put(name, rbuf, (size_t)n);
}

static void rec_hex(const char *kind, const char *name, const unsigned char *p, size_t n)
{
	static const char hx[] = "0123456789ABCDEF";
	size_t o = (size_t)snprintf(rbuf, sizeof(rbuf), "%s %s ", kind, name);
	for (size_t i = 0; i < n; i++) {
		rbuf[o++] = hx[p[i] >> 4];
		rbuf[o++] = hx[p[i] & 15];
	}
	rbuf[o++] = '\n';
	put(name, rbuf, o);
}

static void bad(const char *kind)
{
	if (nbad < BADLOG)
		say("malformed %s record from the client, ignored", kind);
	else if (nbad == BADLOG)
		say("more malformed records from this client: not logged");
	if (nbad <= BADLOG)
		nbad++;
}

/* ---------------------------------------------------------------- channels */

static struct chan *chan_find(const char *name)
{
	for (int i = 0; i < MAXCH; i++)
		if (ch[i].used && !strcmp(ch[i].name, name))
			return &ch[i];
	return NULL;
}

static void chan_state(const struct chan *c)
{
	if (c->state >= 0)
		rec(c->name, "STATE %s %s %s\n", c->name, c->dev, st_word[c->state]);
}

/* the READY condition: a line "SBUF, state: 1," in the driver's state file. 0, or why not (ENODEV: not there) */
static int sbuf_ready(const char *sbuf)
{
	static char b[65536];
	const char *path = getenv("MU300_SIPC_SBUF");
	if (!path || !*path)
		path = "/dev/sipc_sbuf";
	int fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC);
	if (fd < 0)
		return errno;
	size_t n = 0;
	while (n < sizeof(b)) {
		ssize_t r = read(fd, b + n, sizeof(b) - n);
		if (r < 0 && errno == EINTR)
			continue;
		if (r <= 0)
			break;
		n += (size_t)r;
	}
	close(fd);
	char want[SBUFMAX + 16];
	size_t wl = (size_t)snprintf(want, sizeof(want), "%s, state: 1,", sbuf);
	for (size_t at = 0; at < n;) {
		if (n - at >= wl && !memcmp(b + at, want, wl))
			return 0;
		char *nl = memchr(b + at, '\n', n - at);
		if (!nl)
			break;
		at = (size_t)(nl + 1 - b);
	}
	return ENODEV;
}

/* one attempt: open (raw where it is a tty), or pending with one OPENFAIL per pending period */
static void try_open(struct chan *c, long long t)
{
	int err = c->sbuf[0] ? sbuf_ready(c->sbuf) : 0, notready = err != 0, fd = -1;
	if (!err) {
		fd = open(c->dev, O_RDWR | O_NOCTTY | O_NONBLOCK | O_CLOEXEC);
		if (fd < 0)
			err = errno;
	}
	if (fd >= 0) {
		/* what mu300-atd did with stty raw -echo: no echo, no line editing, no CR/NL translation either way */
		struct termios tio;
		if (isatty(fd) && tcgetattr(fd, &tio) == 0) {
			cfmakeraw(&tio);
			tcsetattr(fd, TCSANOW, &tio);
		}
		if (c->state == ST_PENDING && c->failed)
			say("%s: %s opened after %.1f s", c->name, c->dev, (double)(t - c->since) / 1000);
		c->fd = fd;
		c->state = ST_OPEN;
		c->failed = 0;
		c->tty = isatty(fd);
		c->rderr = c->empty = c->quiet_said = 0;
		c->resume = 0;
		c->len = 0;
		chan_state(c);
		return;
	}
	if (c->state != ST_PENDING) {
		c->state = ST_PENDING;
		c->since = t;
		c->failed = 0;
		chan_state(c);
	}
	if (!c->failed) {
		c->failed = 1;
		if (notready)
			say("%s: %s: waiting for \"%s, state: 1,\" (%s); trying again every %d ms", c->name, c->dev, c->sbuf,
			    err == ENODEV ? "not there yet" : strerror(err), RETRY_MS);
		else
			say("%s: %s: %s; trying again every %d ms", c->name, c->dev, strerror(err), RETRY_MS);
		rec(c->name, "OPENFAIL %s %d\n", c->name, err);
	}
	c->next_try = t + RETRY_MS;
}

static void chan_partial(struct chan *c)
{
	if (c->len) {
		rec_hex("RXP", c->name, c->line, c->len);
		c->len = 0;
	}
}

static void chan_eof(struct chan *c, int err)
{
	chan_partial(c);
	close(c->fd);
	c->fd = -1;
	c->state = ST_EOF;
	if (err)
		say("%s: %s: read failed (%s): end of file, closed", c->name, c->dev, strerror(err));
	else
		say("%s: %s: end of file, closed", c->name, c->dev);
	rec(c->name, "EOF %s\n", c->name);
	chan_state(c);
}

/* lines: the bytes before \n without one trailing \r, in pieces of LINEMAX when longer */
static void chan_bytes(struct chan *c, const unsigned char *p, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		if (p[i] == '\n') {
			size_t len = c->len;
			if (len && c->line[len - 1] == '\r')
				len--;
			rec_hex("RX", c->name, c->line, len);
			c->len = 0;
			continue;
		}
		if (c->len == LINEMAX) {
			rec_hex("RX", c->name, c->line, c->len);
			c->len = 0;
		}
		c->line[c->len++] = p[i];
	}
	c->last_rx = now_ms();
}

static int nothing_now(int err)
{
	return err == EAGAIN || err == EWOULDBLOCK || err == ENODATA || err == EBUSY;
}

/* a SIPC channel that read ERR (-1: 0 bytes): kept open, out of the poll for PAUSE_MS */
static void chan_pause(struct chan *c, int err)
{
	if (c->rderr != err) {
		if (err < 0)
			say("%s: %s: read 0 bytes; kept open, read again in %d ms", c->name, c->dev, PAUSE_MS);
		else
			say("%s: %s: read failed (%s); kept open, read again in %d ms", c->name, c->dev, strerror(err),
			    PAUSE_MS);
	}
	c->rderr = err;
	c->resume = now_ms() + PAUSE_MS;
}

static void chan_read(struct chan *c, short revents)
{
	unsigned char b[4096];
	for (int round = 0; round < 16; round++) {
		ssize_t r = read(c->fd, b, sizeof(b));
		if (r > 0) {
			if (c->rderr) {
				say("%s: %s reads again", c->name, c->dev);
				c->rderr = 0;
			}
			c->empty = 0;
			chan_bytes(c, b, (size_t)r);
			continue;
		}
		int err = r < 0 ? errno : 0;
		if (err == EINTR)
			continue;
		if (nothing_now(err)) {
			if (round > 0)
				return;	/* drained */
			/* a hangup or an error with nothing to read stays so, and polling it again would spin */
			if (revents & (POLLHUP | POLLERR | POLLNVAL)) {
				if (c->tty)
					chan_eof(c, EIO);
				else
					chan_pause(c, EIO);
				return;
			}
			if (++c->empty >= EMPTY_MAX) {
				if (!c->quiet_said) {
					say("%s: %s: woken %d times in a row with nothing to read; such wakeups now wait %d ms",
					    c->name, c->dev, EMPTY_MAX, EMPTY_PAUSE_MS);
					c->quiet_said = 1;
				}
				c->empty = 0;
				c->resume = now_ms() + EMPTY_PAUSE_MS;
			}
			return;
		}
		if (c->tty)
			chan_eof(c, err);
		else
			chan_pause(c, err ? err : -1);
		return;
	}
}

/* all N bytes, waiting up to TX_MS for the channel to take them: the one wait outside the main loop, and bounded */
static int write_all(int fd, const unsigned char *p, size_t n)
{
	long long end = now_ms() + TX_MS;
	while (n) {
		ssize_t w = write(fd, p, n);
		if (w > 0) {
			p += w;
			n -= (size_t)w;
			continue;
		}
		if (w < 0 && errno == EINTR)
			continue;
		if (w < 0 && errno != EAGAIN && errno != EWOULDBLOCK)
			return errno;
		long long left = end - now_ms();
		if (left <= 0)
			return ETIMEDOUT;
		struct pollfd p1 = { .fd = fd, .events = POLLOUT };
		int r = poll(&p1, 1, (int)left);
		if (r < 0 && errno != EINTR)
			return errno;
		if (r > 0 && !(p1.revents & POLLOUT) && (p1.revents & (POLLERR | POLLHUP | POLLNVAL)))
			return EIO;
	}
	return 0;
}

/* ---------------------------------------------------------------- FIFOs */

static struct fifo *fifo_find(const char *name)
{
	for (int i = 0; i < MAXFIFO; i++)
		if (ff[i].used && !strcmp(ff[i].name, name))
			return &ff[i];
	return NULL;
}

static void fifo_state(const struct fifo *f, const char *word)
{
	rec(f->name, "STATE %s %s %s\n", f->name, f->path, word);
}

/* is PATH still the FIFO we hold? */
static int fifo_ours(const struct fifo *f)
{
	struct stat st;
	return lstat(f->path, &st) == 0 && S_ISFIFO(st.st_mode) && st.st_dev == f->dev && st.st_ino == f->ino;
}

/* PATH as a FIFO of mode 0600 (an existing FIFO kept, anything else replaced), open: 0 or an errno */
static int fifo_make(struct fifo *f)
{
	struct stat st;
	if (lstat(f->path, &st) == 0) {
		if (!S_ISFIFO(st.st_mode)) {
			if (unlink(f->path) < 0)
				return errno;
			say("%s: %s was not a FIFO: replaced", f->name, f->path);
		}
	} else if (errno != ENOENT)
		return errno;
	if (mkfifo(f->path, 0600) < 0 && errno != EEXIST)
		return errno;
	/* O_RDWR: never blocks, and never reads an end of file when the last writer goes */
	int fd = open(f->path, O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return errno;
	if (fstat(fd, &st) < 0 || !S_ISFIFO(st.st_mode)) {
		close(fd);
		return EINVAL;
	}
	if (fchmod(fd, 0600) < 0) {
	}
	f->fd = fd;
	f->dev = st.st_dev;
	f->ino = st.st_ino;
	f->len = 0;
	f->skipping = 0;
	return 0;
}

/* close and forget: STATE closed, and the path removed while it is still ours */
static void fifo_drop(struct fifo *f, const char *why)
{
	if (f->fd >= 0 && fifo_ours(f))
		unlink(f->path);
	if (f->fd >= 0)
		close(f->fd);
	if (why)
		say("%s: FIFO %s %s", f->name, f->path, why);
	fifo_state(f, "closed");
	memset(f, 0, sizeof(*f));
	f->fd = -1;
}

static void fifo_read(struct fifo *f)
{
	unsigned char b[4096];
	for (int round = 0; round < 16; round++) {
		ssize_t r = read(f->fd, b, sizeof(b));
		if (r < 0 && errno == EINTR)
			continue;
		if (r < 0 && (errno == EAGAIN || errno == EWOULDBLOCK))
			return;
		if (r <= 0) {
			say("%s: reading the FIFO %s failed (%s)", f->name, f->path, r < 0 ? strerror(errno) : "end of file");
			fifo_drop(f, "closed");
			return;
		}
		for (ssize_t i = 0; i < r; i++) {
			if (b[i] == '\n') {
				if (!f->skipping)
					rec_hex("REQ", f->name, f->line, f->len);
				f->len = 0;
				f->skipping = 0;
			} else if (!f->skipping) {
				if (f->len == LINEMAX) {
					say("%s: a request longer than %d bytes, dropped", f->name, LINEMAX);
					f->len = 0;
					f->skipping = 1;
				} else
					f->line[f->len++] = b[i];
			}
		}
	}
}

/* ---------------------------------------------------------------- client records */

static int valid_name(const char *s)
{
	size_t n = strlen(s);
	if (!n || n > NAMEMAX)
		return 0;
	for (; *s; s++)
		if (!((*s >= 'a' && *s <= 'z') || (*s >= '0' && *s <= '9') || *s == '_' || *s == '-'))
			return 0;
	return 1;
}

/* printable and without a space already (the record was split at spaces) */
static int valid_path(const char *s)
{
	return s[0] == '/' && strlen(s) <= PATHMAX;
}

static int valid_sbuf(const char *s)
{
	size_t n = strlen(s);
	if (!n || n > SBUFMAX)
		return 0;
	for (; *s; s++)
		if (!((*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') || (*s >= '0' && *s <= '9') || *s == '_' ||
		      *s == '-' || *s == '.'))
			return 0;
	return 1;
}

static int unhex(int c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	return -1;
}

static void do_open(const char *name, const char *dev, const char *sbuf)
{
	struct chan *c = chan_find(name);
	if (c) {
		if (strcmp(c->dev, dev))
			say("OPEN %s %s: the channel holds %s; nothing changed", name, dev, c->dev);
		chan_state(c);
		return;
	}
	for (int i = 0; i < MAXCH; i++) {
		if (ch[i].used && !strcmp(ch[i].dev, dev)) {
			say("OPEN %s %s: channel %s holds that device; refused", name, dev, ch[i].name);
			rec(name, "OPENFAIL %s %d\n", name, EBUSY);
			rec(name, "STATE %s %s closed\n", name, dev);
			return;
		}
	}
	for (int i = 0; i < MAXCH; i++) {
		if (ch[i].used)
			continue;
		c = &ch[i];
		memset(c, 0, sizeof(*c));
		c->used = 1;
		snprintf(c->name, sizeof(c->name), "%s", name);
		snprintf(c->dev, sizeof(c->dev), "%s", dev);
		snprintf(c->sbuf, sizeof(c->sbuf), "%s", sbuf);
		c->fd = -1;
		c->state = ST_NEW;
		try_open(c, now_ms());
		return;
	}
	say("OPEN %s %s: no room for more than %d channels", name, dev, MAXCH);
	rec(name, "OPENFAIL %s %d\n", name, EMFILE);
	rec(name, "STATE %s %s closed\n", name, dev);
}

static void do_fifo(const char *name, const char *path)
{
	struct fifo *f = fifo_find(name);
	int err;
	if (f) {
		if (strcmp(f->path, path)) {
			say("FIFO %s %s: it has %s; nothing changed", name, path, f->path);
		} else if (!fifo_ours(f)) {
			say("%s: the FIFO %s was removed or replaced: made again", name, path);
			close(f->fd);
			f->fd = -1;
			if ((err = fifo_make(f))) {
				say("%s: cannot make the FIFO %s (%s)", name, path, strerror(err));
				rec(name, "OPENFAIL %s %d\n", name, err);
				fifo_drop(f, NULL);
				return;
			}
		}
		fifo_state(f, "open");
		return;
	}
	for (int i = 0; i < MAXFIFO; i++) {
		if (ff[i].used && !strcmp(ff[i].path, path)) {
			say("FIFO %s %s: FIFO %s has that path; refused", name, path, ff[i].name);
			rec(name, "OPENFAIL %s %d\n", name, EBUSY);
			rec(name, "STATE %s %s closed\n", name, path);
			return;
		}
	}
	for (int i = 0; i < MAXFIFO; i++) {
		if (ff[i].used)
			continue;
		f = &ff[i];
		memset(f, 0, sizeof(*f));
		snprintf(f->name, sizeof(f->name), "%s", name);
		snprintf(f->path, sizeof(f->path), "%s", path);
		f->fd = -1;
		if ((err = fifo_make(f))) {
			say("%s: cannot make the FIFO %s (%s)", name, path, strerror(err));
			rec(name, "OPENFAIL %s %d\n", name, err);
			rec(name, "STATE %s %s closed\n", name, path);
			memset(f, 0, sizeof(*f));
			f->fd = -1;
			return;
		}
		f->used = 1;
		fifo_state(f, "open");
		return;
	}
	say("FIFO %s %s: no room for more than %d FIFOs", name, path, MAXFIFO);
	rec(name, "OPENFAIL %s %d\n", name, EMFILE);
	rec(name, "STATE %s %s closed\n", name, path);
}

static void do_tx(const char *name, const char *hex)
{
	static unsigned char b[TXMAX];
	size_t hl = strlen(hex), n = hl / 2;
	if (hl % 2 || n > TXMAX) {
		bad("TX");
		return;
	}
	for (size_t i = 0; i < n; i++) {
		int hi = unhex(hex[2 * i]), lo = unhex(hex[2 * i + 1]);
		if (hi < 0 || lo < 0) {
			bad("TX");
			return;
		}
		b[i] = (unsigned char)(hi << 4 | lo);
	}
	struct chan *c = chan_find(name);
	int err = !c ? ENOENT : c->fd < 0 ? EBADF : write_all(c->fd, b, n);
	if (err) {
		if (c && c->fd >= 0)
			say("%s: %s: a write failed (%s)", c->name, c->dev, strerror(err));
		rec(NULL, "TXERR %s %d\n", name, err);
	}
}

static void do_reopen(const char *name)
{
	struct chan *c = chan_find(name);
	if (!c) {
		say("REOPEN %s: no such channel", name);
		return;
	}
	say("%s: %s reopened on request", c->name, c->dev);
	chan_partial(c);
	if (c->fd >= 0)
		close(c->fd);
	c->fd = -1;
	c->state = ST_NEW;
	c->failed = 0;
	try_open(c, now_ms());
}

static void do_close(const char *name)
{
	struct chan *c = chan_find(name);
	struct fifo *f = fifo_find(name);
	if (c) {
		say("%s: %s closed on request", c->name, c->dev);
		chan_partial(c);
		if (c->fd >= 0)
			close(c->fd);
		rec(c->name, "STATE %s %s closed\n", c->name, c->dev);
		memset(c, 0, sizeof(*c));
		c->fd = -1;
	}
	if (f)
		fifo_drop(f, "closed on request");
}

static void client_record(char *s, size_t n)
{
	char *f[4];
	int nf = 0;
	for (size_t i = 0; i < n; i++) {
		if ((unsigned char)s[i] < 0x20 || (unsigned char)s[i] > 0x7e) {
			bad("(not printable)");
			return;
		}
	}
	for (char *p = s;;) {
		if (nf == 4) {		/* more fields than any record has */
			nf = 5;
			break;
		}
		f[nf++] = p;
		char *sp = strchr(p, ' ');
		if (!sp)
			break;
		*sp = 0;
		p = sp + 1;
	}
	const char *cmd = f[0];
	if (!strcmp(cmd, "OPEN")) {
		if ((nf != 3 && nf != 4) || !valid_name(f[1]) || !valid_path(f[2]) ||
		    (nf == 4 && (strncmp(f[3], "sbuf:", 5) || !valid_sbuf(f[3] + 5))))
			bad("OPEN");
		else
			do_open(f[1], f[2], nf == 4 ? f[3] + 5 : "");
	} else if (!strcmp(cmd, "FIFO")) {
		if (nf != 3 || !valid_name(f[1]) || !valid_path(f[2]))
			bad("FIFO");
		else
			do_fifo(f[1], f[2]);
	} else if (!strcmp(cmd, "TX")) {
		if (nf != 3 || !valid_name(f[1]))
			bad("TX");
		else
			do_tx(f[1], f[2]);
	} else if (!strcmp(cmd, "REOPEN")) {
		if (nf != 2 || !valid_name(f[1]))
			bad("REOPEN");
		else
			do_reopen(f[1]);
	} else if (!strcmp(cmd, "CLOSE")) {
		if (nf != 2 || !valid_name(f[1]))
			bad("CLOSE");
		else
			do_close(f[1]);
	} else if (!strcmp(cmd, "PING")) {
		if (nf != 2 || !f[1][0] || strlen(f[1]) > TOKENMAX)
			bad("PING");
		else
			rec(NULL, "PONG %s\n", f[1]);
	} else
		bad("(unknown)");
}

static void client_read(void)
{
	char b[16384];
	int fd = cfd;
	for (int round = 0; round < 64; round++) {
		ssize_t r = read(fd, b, sizeof(b));
		if (r == 0) {
			client_close("disconnected");
			return;
		}
		if (r < 0) {
			if (errno == EINTR)
				continue;
			if (errno != EAGAIN && errno != EWOULDBLOCK)
				client_close("gone");
			return;
		}
		for (ssize_t i = 0; i < r; i++) {
			if (b[i] == '\n') {
				if (!iskip) {
					ibuf[ilen] = 0;
					client_record(ibuf, ilen);
					if (cfd != fd)	/* dropped on the way (it stopped reading) */
						return;
				}
				ilen = 0;
				iskip = 0;
			} else if (!iskip) {
				if (ilen == RECMAX) {
					bad("(overlong)");
					iskip = 1;
				} else
					ibuf[ilen++] = b[i];
			}
		}
	}
}

/* the first records of a connection: HELLO, every channel's and FIFO's STATE, DROPPED, then the queue */
static void hello(void)
{
	rec(NULL, "HELLO %d %d\n", PROTO_VERSION, (int)getpid());
	for (int i = 0; i < MAXCH; i++)
		if (ch[i].used)
			chan_state(&ch[i]);
	for (int i = 0; i < MAXFIFO; i++)
		if (ff[i].used)
			fifo_state(&ff[i], "open");
	for (int i = 0; i < QNAMES; i++) {
		if (qn[i].dropped) {
			rec(NULL, "DROPPED %s %lu\n", qn[i].name, qn[i].dropped);
			say("%lu records of %s were dropped while no client was connected", qn[i].dropped, qn[i].name);
		}
	}
	struct rec *r = qhead;
	qhead = qtail = NULL;
	qbytes = 0;
	memset(qn, 0, sizeof(qn));
	while (r) {
		struct rec *next = r->next;
		if (cfd >= 0)
			out_add(r->text, r->len);
		free(r);
		r = next;
	}
}

static void client_accept(void)
{
	for (;;) {
		int fd = accept4(lfd, NULL, NULL, SOCK_NONBLOCK | SOCK_CLOEXEC);
		if (fd < 0) {
			if (errno == EINTR)
				continue;
			if (errno != EAGAIN && errno != EWOULDBLOCK)
				say("accept: %s", strerror(errno));
			return;
		}
		struct ucred cr;
		socklen_t len = sizeof(cr);
		if (getsockopt(fd, SOL_SOCKET, SO_PEERCRED, &cr, &len) < 0 || cr.uid != geteuid()) {
			say("a connection from another user refused");
			close(fd);
			continue;
		}
		/* a restarted client is never locked out by its own stale connection */
		if (cfd >= 0)
			client_close("replaced by a new connection");
		say("client connected (pid %d)", (int)cr.pid);
		cfd = fd;
		hello();
	}
}

/* ---------------------------------------------------------------- setup */

/* the socket's directory: made mode 0700 when missing; one that is there is used as it is */
static int socket_dir(const char *sock)
{
	char dir[PATHMAX + 1];
	struct stat st;
	snprintf(dir, sizeof(dir), "%s", sock);
	char *sl = strrchr(dir, '/');
	if (!sl || sl == dir)
		return 0;
	*sl = 0;
	if (mkdir(dir, 0700) < 0 && errno != EEXIST) {
		say("%s: %s", dir, strerror(errno));
		return -1;
	}
	if (stat(dir, &st) < 0 || !S_ISDIR(st.st_mode)) {
		say("%s: not a directory", dir);
		return -1;
	}
	return 0;
}

/* one instance per socket: a second one waits here for the first to end */
static int take_lock(const char *sock)
{
	char path[PATHMAX + 8];
	snprintf(path, sizeof(path), "%s.lock", sock);
	int fd = open(path, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
	if (fd < 0) {
		say("%s: %s", path, strerror(errno));
		return -1;
	}
	if (flock(fd, LOCK_EX | LOCK_NB) == 0)
		return fd;
	say("another mu300-atd-io holds %s: waiting for it to end", sock);
	while (flock(fd, LOCK_EX) < 0) {
		if (errno != EINTR || stop) {
			close(fd);
			return -1;
		}
	}
	return fd;
}

static int listen_on(const char *path, struct stat *st)
{
	struct sockaddr_un a;
	memset(&a, 0, sizeof(a));
	a.sun_family = AF_UNIX;
	if (strlen(path) >= sizeof(a.sun_path)) {
		say("%s: too long for a socket path", path);
		return -1;
	}
	memcpy(a.sun_path, path, strlen(path) + 1);
	int fd = socket(AF_UNIX, SOCK_STREAM | SOCK_NONBLOCK | SOCK_CLOEXEC, 0);
	if (fd < 0) {
		say("socket: %s", strerror(errno));
		return -1;
	}
	/* a stale socket of an earlier run is removed; the lock says no live one is behind it */
	if ((unlink(path) < 0 && errno != ENOENT) || bind(fd, (struct sockaddr *)&a, sizeof(a)) < 0 ||
	    chmod(path, 0600) < 0 || listen(fd, 8) < 0 || stat(path, st) < 0) {
		say("%s: %s", path, strerror(errno));
		close(fd);
		return -1;
	}
	return fd;
}

int main(int argc, char **argv)
{
	const char *sock = "/run/mu300-modem/io.sock";
	int opt;
	while ((opt = getopt(argc, argv, "s:")) != -1) {
		if (opt == 's' && optarg[0] && strlen(optarg) <= PATHMAX)
			sock = optarg;
		else {
			fprintf(stderr, "usage: mu300-atd-io [-s SOCKET]\n");
			return 2;
		}
	}
	if (optind != argc) {
		fprintf(stderr, "usage: mu300-atd-io [-s SOCKET]\n");
		return 2;
	}
	umask(077);
	signal(SIGPIPE, SIG_IGN);
	struct sigaction sa;
	memset(&sa, 0, sizeof(sa));
	sa.sa_handler = on_stop;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGTERM, &sa, NULL);
	sigaction(SIGINT, &sa, NULL);
	for (int i = 0; i < MAXCH; i++)
		ch[i].fd = -1;
	for (int i = 0; i < MAXFIFO; i++)
		ff[i].fd = -1;

	if (socket_dir(sock) < 0 || take_lock(sock) < 0)
		return stop ? 0 : 1;
	/* SIGTERM and SIGINT are let in only while waiting in ppoll: a signal between a check and the wait is not lost */
	sigset_t block, waitmask;
	sigemptyset(&block);
	sigaddset(&block, SIGTERM);
	sigaddset(&block, SIGINT);
	sigprocmask(SIG_BLOCK, &block, &waitmask);
	sigdelset(&waitmask, SIGTERM);
	sigdelset(&waitmask, SIGINT);
	if (stop)
		return 0;
	struct stat sst;
	lfd = listen_on(sock, &sst);
	if (lfd < 0)
		return 1;
	say("listening on %s (pid %d, protocol %d)", sock, (int)getpid(), PROTO_VERSION);

	enum { K_LISTEN, K_CLIENT, K_CHAN, K_FIFO };
	struct pollfd pfd[2 + MAXCH + MAXFIFO];
	int kind[2 + MAXCH + MAXFIFO], idx[2 + MAXCH + MAXFIFO];
	while (!stop) {
		int n = 0;
		pfd[n] = (struct pollfd){ .fd = lfd, .events = POLLIN };
		kind[n++] = K_LISTEN;
		if (cfd >= 0) {
			pfd[n] = (struct pollfd){ .fd = cfd, .events = (short)(POLLIN | (olen > ooff ? POLLOUT : 0)) };
			kind[n++] = K_CLIENT;
		}
		for (int i = 0; i < MAXCH; i++) {
			if (ch[i].used && ch[i].fd >= 0 && !ch[i].resume) {
				pfd[n] = (struct pollfd){ .fd = ch[i].fd, .events = POLLIN };
				kind[n] = K_CHAN;
				idx[n++] = i;
			}
		}
		for (int i = 0; i < MAXFIFO; i++) {
			if (ff[i].used && ff[i].fd >= 0) {
				pfd[n] = (struct pollfd){ .fd = ff[i].fd, .events = POLLIN };
				kind[n] = K_FIFO;
				idx[n++] = i;
			}
		}
		/* a timeout only while an open is pending, a partial line waits or a channel is paused */
		long long t = now_ms(), due = -1;
		for (int i = 0; i < MAXCH; i++) {
			const struct chan *c = &ch[i];
			long long d = -1;
			if (!c->used)
				continue;
			if (c->state == ST_PENDING)
				d = c->next_try;
			else if (c->state == ST_OPEN && c->len)
				d = c->last_rx + RXP_MS;
			if (c->state == ST_OPEN && c->resume && (d < 0 || c->resume < d))
				d = c->resume;
			if (d >= 0 && (due < 0 || d < due))
				due = d;
		}
		struct timespec ts, *tp = NULL;
		if (due >= 0) {
			long long w = due > t ? due - t : 0;
			ts.tv_sec = w / 1000;
			ts.tv_nsec = (w % 1000) * 1000000;
			tp = &ts;
		}
		if (ppoll(pfd, (nfds_t)n, tp, &waitmask) < 0) {
			if (errno != EINTR) {
				say("poll: %s", strerror(errno));
				struct timespec pause = { 0, 100 * 1000000 };
				nanosleep(&pause, NULL);
			}
			continue;
		}
		/* channels and FIFOs first, while the descriptors are still the ones polled; then the client's records,
		   which may open and close some; then a new connection, which may replace the client */
		for (int i = 0; i < n; i++) {
			if (!pfd[i].revents)
				continue;
			if (kind[i] == K_CHAN && ch[idx[i]].used && ch[idx[i]].fd == pfd[i].fd)
				chan_read(&ch[idx[i]], pfd[i].revents);
			else if (kind[i] == K_FIFO && ff[idx[i]].used && ff[idx[i]].fd == pfd[i].fd)
				fifo_read(&ff[idx[i]]);
		}
		for (int i = 0; i < n; i++)
			if (kind[i] == K_CLIENT && cfd >= 0 && pfd[i].fd == cfd && (pfd[i].revents & (POLLIN | POLLHUP | POLLERR)))
				client_read();
		if (pfd[0].revents & POLLIN)
			client_accept();
		t = now_ms();
		for (int i = 0; i < MAXCH; i++) {
			struct chan *c = &ch[i];
			if (!c->used)
				continue;
			if (c->state == ST_PENDING && c->next_try <= t)
				try_open(c, t);
			else if (c->state == ST_OPEN && c->len && c->last_rx + RXP_MS <= t)
				chan_partial(c);
			if (c->state == ST_OPEN && c->resume && c->resume <= t)
				c->resume = 0;
		}
		flush();
	}

	say("stopping: closing every channel");
	flush();
	if (cfd >= 0)
		close(cfd);
	for (int i = 0; i < MAXCH; i++)
		if (ch[i].used && ch[i].fd >= 0)
			close(ch[i].fd);
	for (int i = 0; i < MAXFIFO; i++) {
		if (!ff[i].used || ff[i].fd < 0)
			continue;
		if (fifo_ours(&ff[i]))
			unlink(ff[i].path);
		close(ff[i].fd);
	}
	struct stat now;
	if (stat(sock, &now) == 0 && now.st_dev == sst.st_dev && now.st_ino == sst.st_ino)
		unlink(sock);
	close(lfd);
	return 0;
}
