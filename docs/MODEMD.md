# mu300-modemd: the modem's AT channels in one event-driven daemon

Status: design for FINDINGS 206 step 2 (the CPU work of October 2026). It replaces the shell `mu300-atd` instances
(one busybox ash per channel, ~10 forks and 11-16 ms of CPU per AT command, a `wc -c` per URC line) and the
polling around them (`mu300-smsd`'s 5 s look at the URC logs, the panel's collector started as a new process for
every round) with two processes:

* **mu300-atd-io** (C, static, `tools/atd-io/mu300-atd-io.c`): holds the SIPC ttys and the request FIFOs open and moves
  bytes between them and one client over a unix socket. No AT knowledge at all. Its name keeps `mu300-atd` in the
  command line, which the existing clients (`mu300-at`, the panel's collector) take as "a live daemon owns this
  channel".
* **mu300-modemd** (ucode + uloop, `rootfs/overlay/opt/mu300/bin/mu300-modemd`): everything `mu300-atd` did - one
  request at a time per command channel, drain before and collect after, the answer files, the URC logs, the +CMT
  spool, the +ECIND hook, the reopen rule - and on top: the ubus object `mu300.modem`, a ubus event per URC line, and
  the panel's cellular collection on demand.

Why two: the device's ucode cannot make a descriptor non-blocking (no `O_NONBLOCK` in `fs.open`, and its `ioctl` takes
no raw request number), and its reads are stdio reads, so reading a tty from the event loop would block it on the
first partial line. Unix sockets it reads without blocking (`recv(..., MSG_DONTWAIT)`), so the tty side is a small C
program and every decision stays in ucode. A second gain: the descriptors outlive modemd. Closing a SIPC channel
while the modem runs silences it until a reboot (FINDINGS 13b), so with the shell daemon any restart of it was a
gamble; modemd can be restarted (or upgraded) freely, the bridge keeps the channels.

## The bridge protocol (mu300-atd-io <-> its client)

A unix stream socket, `-s PATH` (default `/run/mu300-modem/io.sock`), mode 0600 in a 0700 directory. One client at a
time: a new connection replaces the old one (a restarted modemd is never locked out by a stale connection). Records
are lines of printable ASCII ending in `\n`, fields separated by one space; payloads are uppercase hex (`2B43...`),
so nothing a modem or a client sends can break the framing. Channel names are `[a-z0-9_-]{1,16}`.

Client to bridge:

| record | meaning |
|---|---|
| `OPEN NAME DEVICE [READY]` | own DEVICE as channel NAME: open it (O_RDWR, O_NOCTTY, O_NONBLOCK; raw termios where it is a tty) now, else try again every 200 ms until it opens or the channel is CLOSEd. READY is optional, `sbuf:SBUF`: before each attempt the line `SBUF, state: 1,` must be in `/dev/sipc_sbuf` (the second SIM group's channels have a node before the modem side is up, FINDINGS 186). Repeating an OPEN for a channel that exists with the same device changes nothing and answers its STATE. |
| `FIFO NAME PATH` | own the request FIFO of channel NAME: create PATH (mode 0600; an existing FIFO is reused, anything else is replaced), open it O_RDWR and O_NONBLOCK, and forward its complete lines. Repeats change nothing. |
| `TX NAME HEX` | write the bytes to the channel, all of them (waiting up to 2 s for it to take them). |
| `REOPEN NAME` | close the channel's descriptor and open the device again (then the OPEN retry rule). |
| `CLOSE NAME` | close and forget the channel or FIFO NAME. |
| `PING TOKEN` | answered with `PONG TOKEN`. |

Bridge to client:

| record | meaning |
|---|---|
| `HELLO VERSION PID` | the first record of every connection (VERSION is 1) |
| `STATE NAME DEVICE STATE` | after HELLO for every channel and FIFO it holds, and on every change: `open`, `pending`, `eof`, `closed` |
| `OPENFAIL NAME ERRNO` | the first failed attempt of a pending open (one per pending period) |
| `RX NAME HEX` | one line from the channel: the bytes before `\n`, one trailing `\r` removed; empty lines too. A line longer than 8192 bytes goes out in 8192-byte pieces. |
| `RXP NAME HEX` | bytes without a newline that have waited 300 ms (a prompt such as `> `) |
| `REQ NAME HEX` | one complete line from the channel's FIFO, without its `\n` |
| `TXERR NAME ERRNO` | a TX that could not be written whole |
| `EOF NAME` | a terminal read 0 bytes or failed (a pty whose other side closed): the descriptor is closed and the channel is `eof`; it is not reopened by itself. A SIPC channel is not a terminal and never sends this: nothing to read (EAGAIN, ENODATA, EBUSY) is just that, and any other error, a read of 0 bytes or a hangup keeps it open and out of the poll for 1 s, since closing it would silence it until a reboot |
| `DROPPED NAME COUNT` | records that did not fit the queue while no client was connected |
| `PONG TOKEN` | |

While no client is connected the bridge keeps reading every channel (an unread SIPC ring only fills up) and queues
RX/RXP/REQ/STATE records, 1024 per channel and 256 KiB in all, the oldest dropped first; they follow HELLO and the
STATE lines on the next connection. The bridge never exits because of its client; SIGTERM closes everything and ends
it. It does not fork into the background (procd supervises it).

## modemd

* Brokers: the channel layout `mu300-atd`'s init script chose (`start_sim1`: atd on nr1 with nr0's URCs, atd2 on nr2;
  `start_sim2`: atd/atd2/atd4/atd5 on nr1/nr2/nr4/nr5 with the URCs of nr0 and nr3, no reopen, the sbuf condition)
  is handed to modemd as one argument per broker; the init script keeps every other decision (the SIM slot, the
  dual-SIM fallbacks, the warm-up instances).
* Per broker: `$DIR/cmd` (the FIFO, via the bridge), `$DIR/owner/pid` (the bridge's pid, whose command line has
  `mu300-atd`), `$DIR/urc/*.log` (capped at MU300_AT_URC_MAX, 64 KiB), and the request rule of `mu300-at`: the line
  `T ANSWER-FILE COMMAND`, the answer file `$DIR/answer.<pid>` written whole (`.part`, then renamed), and the same
  checks (`one_request`, the timeout range, the answer file's name).
* A command: drain first (quiet for 0.1 s after a clean reply, for 1 s otherwise; at most 3 s, 25 s after an
  unanswered command), write it with `\r`, collect until a final result code (`OK`, `ERROR`, `+CME ERROR`, `+CMS ERROR`,
  `CONNECT`, `NO CARRIER`) or T + 1 s. Lines in a drain go to the channel's own URC log (never the command's echo,
  which can hold a secret). `+CMT:` frames go to `mu300-cmt-spool` on its stdin, never into a reply or a log.
* URC channels: every line to its log, `+ECIND: 3,` to `mu300-sim-state event`, and a ubus event
  `mu300.modem.urc` (`{ "channel": "nr0", "line": "..." }`; `+CMT` frames and lines that can carry a secret are not
  sent).
* The reopen rule: five unanswered commands in a row, the last reopen more than 300 s ago, and the live URC log quiet
  for 240 s; never with MU300_AT_DISABLE_REOPEN.
* ubus `mu300.modem`: `at { cmd, timeout, channel }` (answered when the reply is in), `status`, `cell { mode }`
  (start a collection round now unless one is running or the cache is fresh; answers at once), `urc` events.
* The panel's collection (`unisoc-modem/cell`'s rounds) runs inside modemd when the status plugin asks for it, with
  the same commands, files and JSON, without a process per round.
