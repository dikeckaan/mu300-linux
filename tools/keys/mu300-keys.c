/*
 * mu300-keys: the device's buttons as lines of text, for mu300-buttons (a shell script: OpenWrt has no Python and
 * a pipe from od is block-buffered, so the events came too late) and mu300-sysd.
 *
 * Watches every /dev/input/event* that has keys and prints, flushed at once:
 *   <code> short      released before the long-press time
 *   <code> long       still held when the long-press time is reached (once; nothing on its release)
 *   0 tick            every -t seconds (the LED timeout of mu300-buttons runs on these)
 *   uevent <action> <subsystem> <name>
 *                     -u: a kernel uevent of one of the subsystems given (mu300-sysd: the charger and the fuel gauge
 *                     announce a plug, an unplug and every 1 % of charge; the device's ucode cannot open a netlink
 *                     socket itself); "uevent overflow - -" when the kernel dropped some, so the reader looks again
 * Codes are Linux key codes: 116 KEY_POWER, 138 the U30 Air's Wi-Fi key, 114/115 volume.
 *
 * usage: mu300-keys [-l MS] [-t SEC] [-u SUBSYSTEM[,SUBSYSTEM...]]
 *   (long press: MS milliseconds, default 3000; tick: none by default; uevents: none by default)
 * With -u it also runs without a key (uevents only) or without uevents (keys only, a line on stderr), and it ends
 * when whoever reads its output goes away: mu300-sysd starts it again, and a reader that died leaves no helper behind.
 * SPDX-License-Identifier: MIT
 */
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/netlink.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define MAXDEV 16
#define MAXKEY KEY_MAX
#define MAXSUB 8

static long long now_ms(void)
{
	struct timespec ts;
	clock_gettime(CLOCK_MONOTONIC, &ts);
	return ts.tv_sec * 1000LL + ts.tv_nsec / 1000000;
}

static int has_keys(int fd)
{
	unsigned long ev = 0;
	if (ioctl(fd, EVIOCGBIT(0, sizeof(ev)), &ev) < 0)
		return 0;
	return (ev >> EV_KEY) & 1;
}

static const char *subsystems[MAXSUB];
static int nsub;

/* the kernel's uevent multicast group; no udev in between (OpenWrt has none) */
static int uevent_open(void)
{
	struct sockaddr_nl sa = { .nl_family = AF_NETLINK, .nl_groups = 1 };
	int fd = socket(AF_NETLINK, SOCK_DGRAM | SOCK_CLOEXEC, NETLINK_KOBJECT_UEVENT);
	int size = 256 * 1024;

	if (fd < 0)
		return -1;
	/* a boot's burst of uevents of other subsystems must not crowd out the ones asked for */
	if (setsockopt(fd, SOL_SOCKET, SO_RCVBUFFORCE, &size, sizeof(size)) < 0)
		setsockopt(fd, SOL_SOCKET, SO_RCVBUF, &size, sizeof(size));
	if (bind(fd, (struct sockaddr *)&sa, sizeof(sa)) < 0) {
		close(fd);
		return -1;
	}
	return fd;
}

/* a word of a line: no space, no control character (a reader splits the line at spaces) */
static void word(char *s)
{
	for (; *s; s++)
		if ((unsigned char)*s <= ' ' || *s == 0x7f)
			*s = '_';
}

/* one datagram: "ACTION@DEVPATH" and then KEY=VALUE strings, each ending in a NUL. Only the kernel's (the sender's
 * port id is 0): another root process could send to the group too. */
static void uevent_read(int fd)
{
	char buf[8192 + 1];
	struct sockaddr_nl sa;
	struct iovec iov = { buf, sizeof(buf) - 1 };
	struct msghdr msg = { .msg_name = &sa, .msg_namelen = sizeof(sa), .msg_iov = &iov, .msg_iovlen = 1 };
	ssize_t r = recvmsg(fd, &msg, MSG_DONTWAIT);
	char *action = NULL, *subsystem = NULL, *devpath = NULL, *name;

	if (r < 0) {
		if (errno == ENOBUFS)
			printf("uevent overflow - -\n");
		return;
	}
	if (msg.msg_namelen != sizeof(sa) || sa.nl_pid != 0 || r == 0)
		return;
	buf[r] = 0;
	for (char *p = buf; p < buf + r; p += strlen(p) + 1) {
		if (!strncmp(p, "ACTION=", 7))
			action = p + 7;
		else if (!strncmp(p, "SUBSYSTEM=", 10))
			subsystem = p + 10;
		else if (!strncmp(p, "DEVPATH=", 8))
			devpath = p + 8;
	}
	if (!action || !subsystem || !devpath)
		return;
	for (int i = 0; i < nsub; i++) {
		if (strcmp(subsystem, subsystems[i]))
			continue;
		name = strrchr(devpath, '/');
		name = name ? name + 1 : devpath;
		if (!*name)
			return;
		word(action);
		word(name);
		printf("uevent %s %s %s\n", action, subsystem, name);
		return;
	}
}

int main(int argc, char **argv)
{
	long long hold = 3000, tick = 0, next_tick = 0;
	static long long down[MAXKEY + 1];	/* press time, 0: not held */
	static char reported[MAXKEY + 1];	/* "long" already printed for this press */
	struct pollfd pfd[MAXDEV + 2];
	int n = 0, opt, ue = -1, out = -1, npfd;
	char *list = NULL;

	while ((opt = getopt(argc, argv, "l:t:u:")) != -1) {
		if (opt == 'l')
			hold = atoll(optarg);
		else if (opt == 't')
			tick = atoll(optarg) * 1000;
		else if (opt == 'u')
			list = optarg;
		else {
			fprintf(stderr, "usage: mu300-keys [-l MS] [-t SEC] [-u SUBSYSTEM[,SUBSYSTEM...]]\n");
			return 2;
		}
	}
	for (char *s = list ? strtok(list, ",") : NULL; s && nsub < MAXSUB; s = strtok(NULL, ","))
		subsystems[nsub++] = s;

	DIR *d = opendir("/dev/input");
	struct dirent *e;
	while (d && (e = readdir(d)) && n < MAXDEV) {
		char path[300];
		if (strncmp(e->d_name, "event", 5))
			continue;
		snprintf(path, sizeof(path), "/dev/input/%s", e->d_name);
		int fd = open(path, O_RDONLY | O_CLOEXEC);
		if (fd < 0)
			continue;
		if (!has_keys(fd)) {
			close(fd);
			continue;
		}
		pfd[n].fd = fd;
		pfd[n].events = POLLIN;
		n++;
	}
	if (d)
		closedir(d);
	npfd = n;
	if (nsub) {
		int fd = uevent_open();
		if (fd < 0)
			fprintf(stderr, "mu300-keys: no uevents (%s)\n", strerror(errno));
		else {
			pfd[npfd].fd = fd;
			pfd[npfd].events = POLLIN;
			ue = npfd++;
		}
		/* the reader: its going away (a hangup or an error on stdout) ends this program */
		pfd[npfd].fd = STDOUT_FILENO;
		pfd[npfd].events = 0;
		out = npfd++;
	}
	if (!n && (!nsub || ue < 0)) {
		fprintf(stderr, "mu300-keys: no input device with keys\n");
		return 1;
	}
	if (!n)
		fprintf(stderr, "mu300-keys: no input device with keys; uevents only\n");
	setvbuf(stdout, NULL, _IOLBF, 0);
	if (tick > 0)
		next_tick = now_ms() + tick;

	for (;;) {
		/* wake up in time to report a long press while the key is still held */
		int timeout = -1;
		long long t = now_ms();
		for (int k = 0; k <= MAXKEY; k++) {
			if (down[k] && !reported[k]) {
				long long left = down[k] + hold - t;
				if (left < 0)
					left = 0;
				if (timeout < 0 || left < timeout)
					timeout = (int)left;
			}
		}
		if (tick > 0) {
			long long left = next_tick - t;
			if (left < 0)
				left = 0;
			if (timeout < 0 || left < timeout)
				timeout = (int)left;
		}
		if (poll(pfd, npfd, timeout) < 0 && errno != EINTR)
			return 1;
		if (out >= 0 && (pfd[out].revents & (POLLHUP | POLLERR | POLLNVAL)))
			return 0;
		t = now_ms();
		if (tick > 0 && t >= next_tick) {
			printf("0 tick\n");
			next_tick = t + tick;
		}
		for (int k = 0; k <= MAXKEY; k++) {
			if (down[k] && !reported[k] && t - down[k] >= hold) {
				printf("%d long\n", k);
				reported[k] = 1;
			}
		}
		for (int i = 0; i < n; i++) {
			if (!(pfd[i].revents & POLLIN))
				continue;
			struct input_event ev[16];
			ssize_t r = read(pfd[i].fd, ev, sizeof(ev));
			if (r <= 0)
				continue;
			for (int j = 0; j < (int)(r / sizeof(ev[0])); j++) {
				int k = ev[j].code;
				if (ev[j].type != EV_KEY || k > MAXKEY)
					continue;
				if (ev[j].value == 1) {		/* press */
					down[k] = t;
					reported[k] = 0;
				} else if (ev[j].value == 0 && down[k]) {	/* release */
					if (!reported[k])
						printf("%d short\n", k);
					down[k] = 0;
				}
			}
		}
		if (ue >= 0 && (pfd[ue].revents & POLLIN))
			uevent_read(pfd[ue].fd);
	}
}
