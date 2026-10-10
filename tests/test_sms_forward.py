"""SMS forwarding of the control panel (openwrt-luci): mu300-sms-forward queues the messages mu300-sms pools and sends
them on to a webhook, a Telegram chat, an e-mail address (msmtp) and another phone; unisoc-modem/forward is the panel's
adapter for its settings. The HTTP requests go to the ucode helper on stdin: here `ucode` is a stub that records what
came on stdin and its arguments, and answers with what the test chose. mu300-sms and msmtp are stubs too.

What matters most: forwarding is off until it is turned on; the filters; the queue is bounded and on flash, the
attempts and the log in RAM; a failure is retried with a growing wait, a refusal that cannot change is not; the
secrets (token, password, webhook URL and headers) are never in a command line, the log or a reply of the adapter."""
import json
import os
import stat
import subprocess
import time
import unittest

from helpers import TOP, ShellTest
from test_mu300dash_security import JSONFILTER

FWD = TOP / 'openwrt' / 'luci-overlay' / 'opt' / 'mu300' / 'bin' / 'mu300-sms-forward'
HTTP_UC = TOP / 'openwrt' / 'luci-overlay' / 'opt' / 'mu300' / 'lib' / 'sms-forward-http.uc'
ADAPTER = TOP / 'openwrt' / 'luci-app-mu300' / 'root' / 'usr' / 'libexec' / 'unisoc-modem' / 'forward'
DASH = TOP / 'openwrt' / 'luci-app-mu300' / 'root' / 'usr' / 'libexec' / 'rpcd' / 'mu300dash'

TOKEN = '123456789:AAHsecretTokenValue_0123456789'
PASSWORD = 'hunter2-mail-pass'
HOOK_URL = 'http://192.0.2.10:8099/hook?key=urlsecret'

# the stub ucode: the request (stdin) into $STUBLOG/http.N, its arguments into $STUBLOG/argv.log; it answers with the
# first line of $STUBLOG/answers (consumed), else "status 200"
UCODE = r'''
import os, sys
log = os.environ['STUBLOG']
n = len([f for f in os.listdir(log) if f.startswith('http.')])
open(os.path.join(log, 'http.%d' % n), 'wb').write(sys.stdin.buffer.read())
open(os.path.join(log, 'argv.log'), 'a').write(' '.join(sys.argv) + '\n')
a = os.path.join(log, 'answers')
lines = open(a).read().splitlines() if os.path.exists(a) else []
print(lines[0] if lines else 'status 200')
if lines:
    open(a, 'w').write(''.join(l + '\n' for l in lines[1:]))
'''


def pool_msg(pool, mid, sender, text, direction='mt', scts='2026-10-10 12:00:00'):
    d = pool / 'msg'
    d.mkdir(parents=True, exist_ok=True)
    who = 'from' if direction == 'mt' else 'to'
    f = d / f'{mid:06d}'
    f.write_text(f'id: {mid:06d}\ndir: {direction}\nstatus: unread\n{who}: {sender}\nscts: {scts}\nreceived: 1\n'
                 f'sim_index: 1\ncoding: gsm\nfingerprint: fp{mid}\nlength: 1\n\n{text}\n', encoding='utf-8')
    return f


class Forwarder(ShellTest):
    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'sms-forward.conf'
        self.state = self.tmp / 'state'
        self.run_dir = self.tmp / 'run'
        self.pool = self.tmp / 'pool'
        (self.stubs / 'ucode.py').write_text(UCODE)
        self.stub('ucode', f'exec python3 "{self.stubs}/ucode.py" "$@"')
        # mu300-sms: the arguments and stdin of a send, and "sent (reference 7)"
        self.stub('mu300-sms', 'printf "%s\\n" "$*" >> "$STUBLOG/sms-argv.log"; cat > "$STUBLOG/sms-stdin.$$"; '
                               '[ -f "$STUBLOG/sms-fail" ] && { cat "$STUBLOG/sms-fail" >&2; exit 1; }; echo "sent (reference 7)"')
        self.stub('hostname', 'echo mu300')

    def fresh(self):
        for p in (self.state, self.run_dir):
            subprocess.run(['rm', '-rf', str(p)])
        for f in self.tmp.iterdir():
            if f.name.startswith(('http.', 'argv.log', 'answers', 'sms-')):
                f.unlink()

    def write_conf(self, **kv):
        lines = []
        for k, v in kv.items():
            for one in (v if isinstance(v, list) else [v]):
                lines.append(f'{k}={one}')
        self.conf.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        os.chmod(self.conf, 0o600)

    def fwd(self, shell, *args, **env):
        e = dict(MU300_FWD_CONF=self.conf, MU300_FWD_STATE=self.state, MU300_FWD_RUN=self.run_dir,
                 MU300_SMS_POOL=self.pool, MU300_SMS_BIN=self.stubs / 'mu300-sms', MU300_FWD_HTTP=HTTP_UC,
                 MU300_FWD_NO_WORKER=1, MU300_FWD_BACKOFF=1)
        e.update(env)
        return self.script(shell, FWD, *args, **e)

    def queue(self):
        q = self.state / 'queue'
        return [l.split('\t') for l in q.read_text().splitlines()] if q.exists() else []

    def log(self):
        p = self.run_dir / 'log'
        return [l.split('\t') for l in p.read_text().splitlines()] if p.exists() else []

    def requests(self):
        out = []
        for f in sorted(self.tmp.glob('http.*'), key=lambda p: int(p.suffix[1:])):
            head, _, body = f.read_bytes().decode('utf-8').partition('\n\n')
            lines = head.split('\n')
            out.append((lines[0], dict(l.split(': ', 1) for l in lines[1:] if l), body))
        return out

    def answers(self, *lines):
        (self.tmp / 'answers').write_text(''.join(l + '\n' for l in lines))

    # ------------------------------------------------------------------ enqueue and filters
    def test_off_unless_turned_on(self):
        pool_msg(self.pool, 1, '+905551112233', 'hello')
        for shell in self.each_shell():
            self.fresh()
            self.conf.unlink(missing_ok=True)
            r = self.fwd(shell, 'enqueue', '1')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.queue(), [])
            self.write_conf(enabled=0, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1')
            self.assertEqual(self.queue(), [])
            # on, but no target that is on and complete
            self.write_conf(enabled=1, webhook=0, webhook_url=HOOK_URL, telegram=1, telegram_token=TOKEN)
            self.fwd(shell, 'enqueue', '1')
            self.assertEqual(self.queue(), [])
            self.assertFalse(self.state.exists() and any(self.state.iterdir()))

    def test_enqueue_one_entry_per_target_and_received_only(self):
        f1 = pool_msg(self.pool, 1, '+905551112233', 'hello')
        pool_msg(self.pool, 2, '+905551112233', 'sent by me', direction='mo')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL, telegram=1, telegram_token=TOKEN,
                            telegram_chat='42', sms=1, sms_number='+905550000000')
            r = self.fwd(shell, 'enqueue', '1', '2', '000001', 'x;rm', '99')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.queue(), [['webhook', str(f1)], ['telegram', str(f1)], ['sms', str(f1)]])
            # the queue is root's only, on flash; the RAM directory too
            self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(self.run_dir.stat().st_mode), 0o700)

    def test_filters(self):
        msgs = {1: ('+90 555 111 22 33', 'Your code is 1234'), 2: ('ADANA BLD', 'Kargonuz yolda'),
                3: ('BANK', 'your CODE: 99'), 4: ('+905559999999', 'code 1'), 5: ('BANKX', 'nothing')}
        for mid, (s, t) in msgs.items():
            pool_msg(self.pool, mid, s, t)
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL, allow=['+905551112233', 'bank*', 'ADANA BLD'],
                            deny=['bankx'], keyword=['code'])
            self.fwd(shell, 'enqueue', *map(str, msgs))
            queued = sorted(int(f.rsplit('/', 1)[1]) for _, f in self.queue())
            self.assertEqual(queued, [1, 3])
            why = {int(l[1]): l[4] for l in self.log() if l[3] == 'skipped'}
            self.assertEqual(why, {2: 'no keyword', 4: 'sender not allowed', 5: 'sender denied'})
            # nothing of the sender or the text is in the log
            text = (self.run_dir / 'log').read_text()
            for s, t in msgs.values():
                self.assertNotIn(t, text)
                self.assertNotIn(s.replace(' ', ''), text.replace(' ', ''))

    def test_the_queue_is_bounded(self):
        for mid in (1, 2, 3):
            pool_msg(self.pool, mid, '+905551112233', f'm{mid}')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1', '2', MU300_FWD_QUEUE_MAX=2)
            self.fwd(shell, 'enqueue', '3', MU300_FWD_QUEUE_MAX=2)
            self.assertEqual([f.rsplit('/', 1)[1] for _, f in self.queue()], ['000002', '000003'])
            self.assertIn(['1', 'webhook', 'dropped', 'queue full'], [l[1:] for l in self.log()])

    # ------------------------------------------------------------------ delivery
    def test_webhook_json_and_form(self):
        pool_msg(self.pool, 7, '+905551112233', 'Merhaba "dünya" \\ {x}\nikinci satır')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL,
                            webhook_header=['Authorization: Bearer hdrsecret', 'X-Device: u30'],
                            template='{text}\\n-- {sender} @ {time} on {device} {nope} \\\\o/')
            self.fwd(shell, 'enqueue', '7')
            r = self.fwd(shell, 'run')
            self.assertEqual(r.returncode, 0, r.stderr)
            [(url, headers, body)] = self.requests()
            self.assertEqual(url, HOOK_URL)
            self.assertEqual(headers, {'Content-Type': 'application/json; charset=utf-8',
                                       'Authorization': 'Bearer hdrsecret', 'X-Device': 'u30'})
            doc = json.loads(body)
            dev = doc['device']
            self.assertEqual(doc, {'sender': '+905551112233', 'time': '2026-10-10 12:00:00',
                                   'text': 'Merhaba "dünya" \\ {x}\nikinci satır', 'device': dev,
                                   'message': f'Merhaba "dünya" \\ {{x}}\nikinci satır\n-- +905551112233 @ '
                                              f'2026-10-10 12:00:00 on {dev} {{nope}} \\o/'})
            self.assertTrue(dev)
            self.assertEqual(self.queue(), [])
            self.assertEqual([l[1:4] for l in self.log()], [['7', 'webhook', 'sent']])
            # form: the same fields, URL-encoded
            self.fresh()
            for f in self.tmp.glob('http.*'):
                f.unlink()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL, webhook_format='form', template='{sender}: {text}')
            self.fwd(shell, 'enqueue', '7')
            self.fwd(shell, 'run')
            [(_, headers, body)] = self.requests()
            self.assertEqual(headers['Content-Type'], 'application/x-www-form-urlencoded')
            from urllib.parse import parse_qs
            q = {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}
            self.assertEqual(q['text'], 'Merhaba "dünya" \\ {x}\nikinci satır')
            self.assertEqual(q['message'], '+905551112233: ' + q['text'])
            self.assertEqual(set(q), {'sender', 'time', 'text', 'device', 'message'})

    def test_telegram_token_never_in_argv_or_log(self):
        pool_msg(self.pool, 3, 'ADANA BLD', 'Kargonuz yolda ğüş & co')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, telegram=1, telegram_token=TOKEN, telegram_chat='-100123', template='{text}')
            self.fwd(shell, 'enqueue', '3')
            self.fwd(shell, 'run')
            [(url, headers, body)] = self.requests()
            self.assertEqual(url, f'https://api.telegram.org/bot{TOKEN}/sendMessage')
            self.assertEqual(headers['Content-Type'], 'application/x-www-form-urlencoded')
            from urllib.parse import parse_qs
            q = {k: v[0] for k, v in parse_qs(body).items()}
            self.assertEqual((q['chat_id'], q['text']), ('-100123', 'Kargonuz yolda ğüş & co'))
            argv = (self.tmp / 'argv.log').read_text()
            self.assertNotIn(TOKEN, argv)
            self.assertNotIn(TOKEN.split(':')[1], (self.run_dir / 'log').read_text())

    def test_a_failure_is_retried_with_a_growing_wait_then_given_up(self):
        pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1')
            self.answers('status 500', 'error connect', 'status 429')
            t0 = time.monotonic()
            r = self.fwd(shell, 'run', MU300_FWD_ATTEMPTS=3)
            self.assertEqual(r.returncode, 0, r.stderr)
            # 1 s, then 2 s between the three attempts; the worker's clock counts whole seconds (date +%s), so the
            # waits it really makes can be up to a second shorter each: only that it did wait is timed here
            self.assertGreaterEqual(time.monotonic() - t0, 1)
            got = [l[3:] for l in self.log()]
            self.assertEqual(got, [['retry', 'HTTP 500, attempt 1, next in 1 s'], ['retry', 'connect, attempt 2, next in 2 s'],
                                   ['failed', 'HTTP 429, gave up after 3 attempts']])
            self.assertEqual(self.queue(), [])
            self.assertEqual((self.run_dir / 'retry').read_text(), '')

    def test_a_retry_then_success(self):
        pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1')
            self.answers('error timeout')
            self.fwd(shell, 'run')
            self.assertEqual([l[3] for l in self.log()], ['retry', 'sent'])
            self.assertEqual(len(self.requests()), 2)

    def test_a_refusal_is_not_retried(self):
        pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1')
            self.answers('status 401')
            self.fwd(shell, 'run')
            self.assertEqual([l[3:] for l in self.log()], [['failed', 'HTTP 401']])
            self.assertEqual(len(self.requests()), 1)

    def test_a_message_gone_from_the_pool_is_dropped(self):
        f = pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1')
            f.rename(f.with_name('gone'))
            try:
                self.fwd(shell, 'run')
            finally:
                f.with_name('gone').rename(f)
            self.assertEqual([l[3:] for l in self.log()], [['failed', 'message no longer in the pool']])
            self.assertEqual(self.requests(), [])

    def test_a_worker_turned_off_stops_and_clear_empties_the_queue(self):
        pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'enqueue', '1')
            self.write_conf(enabled=0, webhook=1, webhook_url=HOOK_URL)
            self.fwd(shell, 'run')
            self.assertEqual(self.requests(), [])
            self.assertEqual(len(self.queue()), 1)
            self.fwd(shell, 'clear')
            self.assertEqual(self.queue(), [])
            self.assertEqual([l[3:] for l in self.log()], [['dropped', 'forwarding turned off']])

    def test_sms_target_one_part_and_never_back_to_the_sender(self):
        long_gsm = 'a' * 200
        long_ucs = 'ş' * 80
        pool_msg(self.pool, 1, '+905551112233', long_gsm)
        pool_msg(self.pool, 2, '+905551112233', long_ucs)
        pool_msg(self.pool, 3, '+905550000000', 'loop?')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, sms=1, sms_number='+905550000000', template='{text}')
            self.fwd(shell, 'enqueue', '1', '2', '3')
            self.fwd(shell, 'run')
            sent = sorted((p.read_text(encoding='utf-8') for p in self.tmp.glob('sms-stdin.*')), key=len)
            self.assertEqual(sorted(sent), sorted(['a' * 157 + '...', 'ş' * 67 + '...']))
            self.assertEqual((self.tmp / 'sms-argv.log').read_text().splitlines(),
                             ['send --stdin +905550000000'] * 2)
            res = {l[1]: l[3:] for l in self.log()}
            self.assertEqual(res['3'], ['failed', 'the sender is the forwarding number'])
            self.assertEqual((res['1'][0], res['2'][0]), ('sent', 'sent'))

    def test_sms_target_retries_a_modem_refusal(self):
        pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            (self.tmp / 'sms-fail').write_text('mu300-sms: the modem did not take the message: +CMS ERROR: 28\n')
            self.write_conf(enabled=1, sms=1, sms_number='+905550000000')
            self.fwd(shell, 'enqueue', '1')
            self.fwd(shell, 'run', MU300_FWD_ATTEMPTS=2)
            self.assertEqual([l[3] for l in self.log()], ['retry', 'failed'])
            self.assertIn('+CMS ERROR: 28', self.log()[0][4])
            (self.tmp / 'sms-fail').unlink()

    def test_email_through_msmtp_password_in_a_private_file(self):
        pool_msg(self.pool, 1, 'ADANA BLD', 'Kargonuz yolda')
        # msmtp: its arguments, the mode of its config file and that file, the message
        self.stub('msmtp', 'echo "$*" >> "$STUBLOG/msmtp-argv"; c=$2; ls -l "$c" | cut -c1-10 > "$STUBLOG/msmtp-mode"; '
                           'cp "$c" "$STUBLOG/msmtp-conf"; cat > "$STUBLOG/msmtp-msg"')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, email=1, email_host='smtp.example.com', email_port=465, email_tls='tls',
                            email_user='me@example.com', email_password=PASSWORD, email_from='me@example.com',
                            email_to='you@example.com', template='{sender}: {text}')
            self.fwd(shell, 'enqueue', '1')
            self.fwd(shell, 'run')
            self.assertEqual([l[3] for l in self.log()], ['sent'])
            self.assertNotIn(PASSWORD, (self.tmp / 'msmtp-argv').read_text())
            self.assertEqual((self.tmp / 'msmtp-mode').read_text().strip(), '-rw-------')
            conf = (self.tmp / 'msmtp-conf').read_text()
            self.assertIn(f'password {PASSWORD}\n', conf)
            self.assertIn('tls on\ntls_starttls off\n', conf)
            self.assertIn('host smtp.example.com\nport 465\n', conf)
            msg = (self.tmp / 'msmtp-msg').read_text()
            self.assertIn('To: you@example.com\nSubject: SMS from ADANA BLD\n', msg)
            self.assertTrue(msg.endswith('\n\nADANA BLD: Kargonuz yolda\n'))
            self.assertEqual(list(self.run_dir.glob('msmtp.*')), [])

    def test_send_test_to_every_target_that_is_on(self):
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=0, webhook=1, webhook_url=HOOK_URL, sms=1, sms_number='+905550000000')
            self.answers('status 503')
            r = self.fwd(shell, 'test')
            self.assertEqual(r.returncode, 1)
            self.assertEqual([l[1:4] for l in self.log()], [['test', 'webhook', 'failed'], ['test', 'sms', 'sent']])
            self.assertEqual(self.queue(), [])
            self.write_conf(enabled=1)
            r = self.fwd(shell, 'test')
            self.assertEqual(self.log()[-1][1:], ['test', '-', 'failed', 'no target is on'])

    def test_kick_with_nothing_queued_writes_nothing(self):
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            r = self.fwd(shell, 'kick', MU300_FWD_NO_WORKER=0)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse(self.state.exists())
            r = self.fwd(shell, 'status')
            self.assertEqual(r.stdout.splitlines()[:2], ['queued 0', 'running 0'])

    def test_kick_starts_one_worker_that_delivers_in_the_background(self):
        pool_msg(self.pool, 1, '+905551112233', 'x')
        for shell in self.each_shell():
            self.fresh()
            self.write_conf(enabled=1, webhook=1, webhook_url=HOOK_URL)
            r = self.fwd(shell, 'enqueue', '1', MU300_FWD_NO_WORKER=0)
            self.assertEqual(r.returncode, 0, r.stderr)
            for _ in range(100):
                if self.queue() == [] and not (self.run_dir / 'worker.lock').exists():
                    break
                time.sleep(0.1)
            self.assertEqual([l[3] for l in self.log()], ['sent'])

    def test_one_sms_cut(self):
        # 160 plain characters, or 70 UCS-2 units (an emoji takes two), "..." where it was cut
        self.lib_from_script()
        for shell in self.each_shell():
            for text, want in (('a' * 160, 'a' * 160), ('a' * 161, 'a' * 157 + '...'), ('[' * 10, '[' * 10),
                               ('x' * 70 + '{', 'x' * 67 + '...'), ('😀' * 40, '😀' * 33 + '...'),
                               ('ğ' * 70, 'ğ' * 70), ('ğ' * 71, 'ğ' * 67 + '...')):
                r = subprocess.run(shell + ['-c', f'. "{self.tmp}/lib.sh"; one_sms "$1"', 'sh', text],
                                   capture_output=True, env=self.env())
                self.assertEqual(r.stdout.decode(), want, (shell, text[:5]))

    def lib_from_script(self):
        """The functions of mu300-sms-forward, without its command dispatch, as $tmp/lib.sh."""
        src = FWD.read_text(encoding='utf-8')
        (self.tmp / 'lib.sh').write_text(src[:src.index('\ncase ${1:-} in')] + '\n', encoding='utf-8')

    def test_render_leaves_unknown_braces_and_reads_no_escapes_in_values(self):
        self.lib_from_script()
        for shell in self.each_shell():
            r = subprocess.run(shell + ['-c', f'. "{self.tmp}/lib.sh"; c_template="$1"; render "$2" "$3" "$4" "$5"', 'sh',
                                        '<{sender}|{time}|{text}|{device}|{other}|{text\\n>', '\\n&$(x)', 't', '%s\\t', 'd'],
                               capture_output=True, env=self.env())
            self.assertEqual(r.stdout.decode(), '<\\n&$(x)|t|%s\\t|d|{other}|{text\n>')

    def test_the_http_helper_takes_its_request_on_stdin_only(self):
        src = HTTP_UC.read_text()
        self.assertIn("stdin.read('all')", src)
        self.assertNotIn('ARGV', src)
        self.assertIn('verify: true', src)
        self.assertIn('if (!cl.connect())', src)
        fwd = FWD.read_text()
        self.assertIn('ucode "$HTTP"', fwd)
        self.assertNotRegex(fwd, r'ucode[^\n]*\$c_')


class Adapter(ShellTest):
    """unisoc-modem/forward: get never returns a secret, set checks and writes a root-only file."""

    def setUp(self):
        super().setUp()
        (self.stubs / 'jsonfilter.py').write_text(JSONFILTER)
        self.stub('jsonfilter', f'exec python3 "{self.stubs}/jsonfilter.py" "$@"')
        self.stub('uci', 'exit 1')
        self.conf = self.tmp / 'etc' / 'sms-forward.conf'
        # the forwarder: its status, a log, and what it was asked
        self.stub('fwd', 'echo "$*" >> "$STUBLOG/fwd.log"; case $1 in '
                         'status) printf "queued 2\\nrunning 1\\nemail ${FWD_EMAIL:-0}\\n" ;; '
                         'log) printf "1791000000\\t12\\twebhook\\tsent\\tHTTP 200\\n1791000001\\ttest\\ttelegram\\tfailed\\tHTTP 4\\"01\\n" ;; '
                         'esac')

    def adapter(self, shell, *args, stdin=None, **env):
        return self.script(shell, ADAPTER, *args, stdin=stdin, MU300_FWD_CONF=self.conf,
                           MU300_FWD_BIN=self.stubs / 'fwd', **env)

    def set(self, shell, **fields):
        r = self.adapter(shell, 'set', stdin=json.dumps(fields, ensure_ascii=False))
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def get(self, shell, **env):
        r = self.adapter(shell, 'get', **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout, json.loads(r.stdout)

    FULL = dict(enabled='1', template='{text}\n-- {sender}', allow='+905551112233\nBANK*', deny='SPAM', keywords='code, kod',
                webhook='1', webhook_url=HOOK_URL, webhook_format='json',
                webhook_headers='Authorization: Bearer hdrsecret\nX-Device: u30',
                telegram='1', telegram_token=TOKEN, telegram_chat='@mychannel',
                email='0', email_host='smtp.example.com', email_port='587', email_tls='starttls',
                email_user='me@example.com', email_password=PASSWORD, email_from='me@example.com',
                email_to='you@example.com', sms='1', sms_number='+905550000000')

    def test_set_writes_a_private_file_and_get_masks_every_secret(self):
        for shell in self.each_shell():
            self.conf.parent.mkdir(exist_ok=True)
            self.conf.unlink(missing_ok=True)
            self.assertEqual(self.set(shell, **self.FULL), {'ok': 1})
            self.assertEqual(stat.S_IMODE(self.conf.stat().st_mode), 0o600)
            lines = self.conf.read_text().splitlines()
            for want in ('enabled=1', 'template={text}\\n-- {sender}', 'allow=+905551112233', 'allow=BANK*', 'deny=SPAM',
                         'keyword=code', 'keyword=kod', f'webhook_url={HOOK_URL}',
                         'webhook_header=Authorization: Bearer hdrsecret', 'webhook_header=X-Device: u30',
                         f'telegram_token={TOKEN}', 'telegram_chat=@mychannel', f'email_password={PASSWORD}',
                         'sms_number=+905550000000'):
                self.assertIn(want, lines)
            raw, st = self.get(shell)
            for secret in (TOKEN.split(':')[1], PASSWORD, 'urlsecret', 'hdrsecret', '/hook'):
                self.assertNotIn(secret, raw)
            self.assertEqual((st['webhook_url_set'], st['webhook_url_hint']), (1, 'http://192.0.2.10:8099/...'))
            self.assertEqual((st['webhook_headers_set'], st['webhook_header_names']), (1, 'Authorization, X-Device'))
            self.assertEqual((st['telegram_token_set'], st['telegram_token_hint']), (1, '123456789:...'))
            self.assertEqual(st['email_password_set'], 1)
            self.assertEqual((st['template'], st['allow'], st['keywords']),
                             ('{text}\n-- {sender}', '+905551112233\nBANK*', 'code\nkod'))
            self.assertEqual((st['queued'], st['running'], st['email_available']), (2, 1, 0))
            self.assertEqual(st['log'][0], {'time': 1791000001, 'id': 'test', 'target': 'telegram', 'result': 'failed',
                                            'detail': 'HTTP 4"01'})

    def test_an_empty_secret_keeps_the_saved_one_and_clear_removes_it(self):
        for shell in self.each_shell():
            self.conf.parent.mkdir(exist_ok=True)
            self.conf.unlink(missing_ok=True)
            self.set(shell, **self.FULL)
            kept = dict(self.FULL, webhook_url='', webhook_headers='', telegram_token='', email_password='')
            self.assertEqual(self.set(shell, **kept), {'ok': 1})
            text = self.conf.read_text()
            for secret in (f'webhook_url={HOOK_URL}', 'webhook_header=Authorization: Bearer hdrsecret',
                           f'telegram_token={TOKEN}', f'email_password={PASSWORD}'):
                self.assertIn(secret, text)
            cleared = dict(kept, webhook='0', telegram='0', clear='webhook_url webhook_headers telegram_token email_password')
            self.assertEqual(self.set(shell, **cleared), {'ok': 1})
            text = self.conf.read_text()
            for secret in ('urlsecret', 'hdrsecret', TOKEN, PASSWORD):
                self.assertNotIn(secret, text)

    def test_turning_off_empties_the_queue(self):
        for shell in self.each_shell():
            self.conf.parent.mkdir(exist_ok=True)
            (self.tmp / 'fwd.log').unlink(missing_ok=True)
            self.set(shell, **self.FULL)
            self.set(shell, **dict(self.FULL, enabled='0'))
            self.assertIn('clear', (self.tmp / 'fwd.log').read_text().splitlines())

    def test_refusals(self):
        bad = [
            ('enabled', 'yes', 'Invalid forwarding setting'),
            ('template', 'a\x01b', 'The message template is too long or contains a control character'),
            ('template', 'x' * 1001, 'The message template is too long or contains a control character'),
            ('allow', '\n'.join(str(i) for i in range(51)), 'Invalid filter list (at most 50 lines)'),
            ('keywords', 'k' * 65, 'Invalid filter list (at most 50 lines)'),
            ('webhook_url', 'ftp://x/y', 'The webhook address must be an http:// or https:// URL'),
            ('webhook_url', 'http://x y', 'The webhook address must be an http:// or https:// URL'),
            ('webhook_url', 'http://x/\ny', 'The webhook address must be an http:// or https:// URL'),
            ('webhook_headers', 'Host: evil', 'Invalid header'),
            ('webhook_headers', 'content-length: 1', 'Invalid header'),
            ('webhook_headers', 'Bad Name: x', 'Invalid header'),
            ('webhook_format', 'xml', 'Invalid forwarding setting'),
            ('telegram_token', 'nope', 'Invalid Telegram bot token'),
            ('telegram_chat', 'chat;id', 'Invalid Telegram chat (a number, or @channel)'),
            ('email_port', '70000', 'Invalid e-mail setting'),
            ('email_to', 'not an address', 'Invalid e-mail setting'),
            ('email_password', 'pa\nss', 'Invalid e-mail setting'),
            ('sms_number', '+90abc', 'The number may only contain digits (and a leading +)'),
            ('clear', 'all;rm', 'Invalid forwarding setting'),
        ]
        for shell in self.each_shell():
            self.conf.parent.mkdir(exist_ok=True)
            self.conf.unlink(missing_ok=True)
            for key, value, err in bad:
                with self.subTest(key=key, value=value[:20]):
                    r = self.set(shell, **dict(self.FULL, **{key: value}))
                    self.assertEqual(r['ok'], 0)
                    self.assertTrue(r['error'].startswith(err), r)
                    self.assertFalse(self.conf.exists())
            for fields, err in ((dict(self.FULL, webhook_url=''), 'The webhook needs an address'),
                                (dict(self.FULL, telegram_chat=''), 'Telegram needs a bot token and a chat'),
                                (dict(self.FULL, email='1'), 'E-mail needs msmtp, which this image does not have'),
                                (dict(self.FULL, sms_number=''), 'SMS forwarding needs a phone number')):
                r = self.set(shell, **fields)
                self.assertEqual((r['ok'], r['error']), (0, err))
            # with msmtp, a mail target needs its addresses
            r = self.adapter(shell, 'set', stdin=json.dumps(dict(self.FULL, email='1', email_to='')), FWD_EMAIL=1)
            self.assertEqual(json.loads(r.stdout)['error'], 'E-mail needs a server, a sender and a recipient')

    def test_test_runs_detached(self):
        self.stub('setsid', 'echo "setsid $*" >> "$STUBLOG/fwd.log"')
        for shell in self.each_shell():
            (self.tmp / 'fwd.log').unlink(missing_ok=True)
            r = self.adapter(shell, 'test')
            self.assertEqual(json.loads(r.stdout), {'ok': 1, 'started': 1})
            for _ in range(50):
                if (self.tmp / 'fwd.log').exists():
                    break
                time.sleep(0.05)
            self.assertEqual((self.tmp / 'fwd.log').read_text().split()[-1], 'test')

    def test_unknown_operation(self):
        for shell in self.each_shell():
            r = self.adapter(shell, 'rm')
            self.assertEqual(json.loads(r.stdout), {'ok': 0, 'error': 'Unknown forwarding operation'})


class Wiring(unittest.TestCase):
    def test_page_menu_acl_and_rpc(self):
        app = TOP / 'openwrt' / 'luci-app-mu300'
        menu = json.loads((app / 'root/usr/share/luci/menu.d/luci-app-mu300.json').read_text())
        self.assertEqual(menu['admin/modem/sms-forward']['action'], {'type': 'view', 'path': 'mu300/forward'})
        cellular = [k for _, k in sorted((v['order'], k) for k, v in menu.items() if k.startswith('admin/modem/'))]
        self.assertEqual(cellular[cellular.index('admin/modem/sms') + 1], 'admin/modem/sms-forward')
        acl = json.loads((app / 'root/usr/share/rpcd/acl.d/luci-app-mu300.json').read_text())['luci-app-mu300']
        for m in ('forward_get', 'forward_set', 'forward_test'):
            self.assertIn(m, acl['write']['ubus']['mu300dash'])
            self.assertNotIn(m, acl['read']['ubus']['mu300dash'])
        common = (app / 'htdocs/luci-static/resources/mu300/common.js').read_text()
        self.assertIn('callFwdGet: callFwdGet, callFwdSet: callFwdSet, callFwdTest: callFwdTest', common)
        self.assertTrue(os.access(ADAPTER, os.X_OK))
        self.assertTrue(os.access(FWD, os.X_OK))
        build = (TOP / 'openwrt' / 'build-rootfs.sh').read_text()
        self.assertIn('$R/opt/mu300/bin/mu300-sms-forward', build)

    def test_the_view_never_shows_a_saved_secret(self):
        view = (TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/forward.js').read_text()
        # the secret fields start empty; only their *_set flags and hints are read
        for k in ('webhook_url', 'webhook_headers', 'telegram_token', 'email_password'):
            self.assertNotIn(f'st.{k})', view)
            self.assertNotIn(f'st.{k},', view)
        self.assertIn("this.secret('telegram_token', st.telegram_token_set", view)
        # the cards' ids never clash with the fields' ('mud-fwd-' + field name): a card named like its checkbox
        # made the page read the card instead of the box
        import re
        cards = re.findall(r"E\('section', \{ 'class': 'mud-card', 'id': '([^']+)'", view)
        self.assertTrue(cards and all(c.startswith('mud-fwd-card-') for c in cards), cards)
        self.assertNotIn("'id': 'mud-fwd-telegram'", view)


if __name__ == '__main__':
    unittest.main()
