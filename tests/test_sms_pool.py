"""The SMS pool of openwrt-luci (K69, D11): mu300-sms keeps every message the SIM holds, and every message the panel
sends, in /etc/mu300/sms-pool, one file per message; mu300-smsd keeps it in step with the SIM. It is the panel's SMS
store only - the `sms` command stays the SMS tool of every system, with its own state in /etc/mu300/sms.

mu300-sms talks to the modem only through mu300-at, in PDU mode as `sms` does, and decodes with the same
/opt/mu300/lib/sms-pdu.awk. Here mu300-at is a stub that answers from a table and records every command, and the AT
daemon's command fifo is a fifo in the scratch directory. The panel side is mu300dash (luci-app-mu300's rpcd backend)
run on the real mu300-sms, with the jsonfilter stand-in of test_mu300dash_security."""
import json
import os
import re
import shutil
import signal
import subprocess
import time
import unittest

from helpers import TOP, ShellTest
from test_mu300dash_security import DASH, JSONFILTER

LUCI = TOP / 'openwrt' / 'luci-overlay'
SMS = LUCI / 'opt' / 'mu300' / 'bin' / 'mu300-sms'
SMSD = LUCI / 'opt' / 'mu300' / 'bin' / 'mu300-smsd'
INITD = LUCI / 'etc' / 'init.d' / 'mu300-smsd'
AWK = TOP / 'rootfs' / 'overlay' / 'opt' / 'mu300' / 'lib' / 'sms-pdu.awk'
BUILD = TOP / 'openwrt' / 'build-rootfs.sh'
APP = TOP / 'openwrt' / 'luci-app-mu300'

# Two SMS-DELIVER PDUs, checked against sms-pdu.awk: the GSM 7-bit textbook example (from +31641600986, unread on the
# SIM) and a UCS-2 one from an alphanumeric sender (ADANA BLD, the case text mode mangles - FINDINGS 26c), already read
PDU_GSM = '07911326040000F0040B911346610089F60000208062917314480CC8F71D14969741F977FD07'
PDU_UCS2 = ('000410D04162D0190409994400086290517181004024004B006100720067006F006E0075007A00200079006F006C006400610020011F'
            '00FC015F')
CMGL = f'+CMGL: 3,0,,40\n{PDU_GSM}\n+CMGL: 7,1,,56\n{PDU_UCS2}\nOK\n'

# The stub mu300-at: `mu300-at -t SECONDS COMMAND`. Appends the command to $STUBLOG/at.log (one per line, the CR and
# Ctrl-Z of a submit shown as ^ and ~), then answers from $STUBLOG/at/<name>: the first file whose name is a prefix
# of the command with the characters outside [A-Za-z0-9] dropped (CMGL4, CPMS, CMGS ...); OK when there is none.
# $STUBLOG/at/BUSY makes it the client that gave up on the lock.
AT_STUB = r'''
log=$STUBLOG/at.log
[ "${1:-}" = -t ] && shift 2
printf '%s\n' "$1" | tr '\r\032' '^~' >> "$log"
[ -f "$STUBLOG/at/BUSY" ] && { echo "mu300-at: busy" >&2; exit 1; }
key=$(printf '%s' "$1" | tr -cd 'A-Za-z0-9')
for f in $(ls "$STUBLOG/at" 2>/dev/null | sort -r); do
    case $key in AT"$f"*) cat "$STUBLOG/at/$f"; exit 0 ;; esac
done
echo OK
'''


class Pool(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('mu300-at', AT_STUB)
        (self.tmp / 'at').mkdir()
        self.answer('CPMS', '+CPMS: 2,50,2,50,2,50\nOK\n')
        self.answer('CMGL4', CMGL)
        self.atdir = self.tmp / 'run-at'
        self.atdir.mkdir()
        os.mkfifo(self.atdir / 'cmd')
        self.pool = self.tmp / 'pool'
        self.run = self.tmp / 'run'   # where the pool lock goes (/run on the device)
        self.run.mkdir()

    def test_no_cksum_on_the_device(self):
        # OpenWrt's busybox has md5sum but no cksum: the pool lock is named without it, and nothing is printed
        self.stub('cksum', 'echo "cksum: not found" >&2; exit 127')
        for shell in self.each_shell():
            self.fresh()
            r = self.run_sms(shell, 'list')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn('cksum', r.stderr, shell)
            self.assertNotIn('not found', r.stderr + r.stdout, shell)

    def fresh(self):
        """An empty pool, an empty AT log and the default answers (for the next shell)."""
        shutil.rmtree(self.pool, ignore_errors=True)
        (self.tmp / 'at.log').unlink(missing_ok=True)
        for f in (self.tmp / 'at').iterdir():
            f.unlink()
        self.answer('CPMS', '+CPMS: 2,50,2,50,2,50\nOK\n')
        self.answer('CMGL4', CMGL)

    def answer(self, name, text):
        (self.tmp / 'at' / name).write_text(text)

    def at_log(self):
        p = self.tmp / 'at.log'
        return p.read_text().splitlines() if p.exists() else []

    def run_sms(self, shell, *args, stdin=None, **env):
        e = dict(MU300_SMS_POOL=self.pool, MU300_AT_DIR=self.atdir, MU300_SMS_AWK=AWK, MU300_SMS_RUN=self.run)
        e.update(env)
        return self.script(shell, SMS, *args, stdin=stdin, **e)

    def msgs(self):
        """{id: (headers dict, body)} of the pool."""
        out = {}
        for f in sorted((self.pool / 'msg').glob('[0-9]*')):
            head, _, body = f.read_text().partition('\n\n')
            out[f.name] = (dict(line.split(': ', 1) for line in head.splitlines()), body)
        return out

    def put(self, mid, status, direction, peer, scts, body, sim_index=''):
        """A message written into the pool directly, as mu300-sms writes it."""
        d = self.pool / 'msg'
        d.mkdir(parents=True, exist_ok=True)
        who = 'from' if direction == 'mt' else 'to'
        (d / f'{mid:06d}').write_text(
            f'id: {mid:06d}\ndir: {direction}\nstatus: {status}\n{who}: {peer}\nscts: {scts}\nreceived: 1790000000\n'
            f'sim_index: {sim_index}\ncoding: gsm\nfingerprint: fp{mid}\nlength: {len(body.encode())}\n\n{body}\n')
        nid = self.pool / 'next_id'
        if not nid.exists() or int(nid.read_text()) < mid:
            nid.write_text(f'{mid}\n')

    # ------------------------------------------------------------------ the pool path
    def test_the_pool_is_etc_mu300_sms_pool_everywhere(self):
        # D11: /etc/mu300/sms is the sms command's state directory, so the pool is never there
        for p in (SMS, SMSD):
            with self.subTest(p=p.name):
                self.assertIn('POOL=${MU300_SMS_POOL:-/etc/mu300/sms-pool}\n', p.read_text())
        src = INITD.read_text()
        self.assertIn('local pool=/etc/mu300/sms-pool\n', src)
        self.assertIn('case $pool in /etc/mu300/sms|/etc/mu300/sms/*) pool=/etc/mu300/sms-pool ;; esac', src)
        self.assertIn('procd_set_param env MU300_SMS_POOL="$pool"', src)
        self.assertIn("option sms_pool '/etc/mu300/sms-pool'",
                      (APP / 'root' / 'etc' / 'config' / 'unisoc_modem').read_text())
        self.assertIn("o.placeholder = '/etc/mu300/sms-pool'",
                      (APP / 'htdocs/luci-static/resources/view/mu300/settings.js').read_text())

    def test_programs_are_executable_and_english(self):
        for p in (SMS, SMSD, INITD):
            with self.subTest(p=p.name):
                self.assertTrue(p.stat().st_mode & 0o111, 'not executable')
                self.assertIsNone(re.search('[⺀-鿿豈-﫿＀-￯]', p.read_text()))
                if not shutil.which('git'):
                    continue
                mode = subprocess.run(['git', 'ls-files', '-s', str(p)], cwd=TOP, capture_output=True,
                                      text=True).stdout.split(' ')[0]
                if mode:   # tracked: the image gets the git mode
                    self.assertEqual(mode, '100755')

    # ------------------------------------------------------------------ list / show
    def test_list_on_a_pool(self):
        self.put(1, 'read', 'mt', '+905551112233', '2026-10-01 09:00:00', 'first')
        self.put(2, 'unread', 'mt', 'ADANA BLD', '2026-10-02 10:00:00', 'second line one\nline two')
        self.put(3, 'sent', 'mo', '10086', '2026-10-03 11:00:00', 'x' * 60)
        for shell in self.each_shell():
            r = self.run_sms(shell, 'list')
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            self.assertEqual(lines[0], 'pool: 3 message(s), 1 unread - page 1/1 (10 per page)')
            # newest first, the columns mu300dash cuts at (1-7, 9-15, 17-19, 21-38, 40-60, 62-)
            self.assertEqual([(ln[0:7].strip(), ln[8:15].strip(), ln[16:19].strip(), ln[20:38].strip(),
                               ln[39:60].strip(), ln[61:]) for ln in lines[1:]],
                             [('000003', 'sent', 'mo', '10086', '2026-10-03 11:00:00', 'x' * 44),
                              ('000002', 'unread', 'mt', 'ADANA BLD', '2026-10-02 10:00:00', 'second line one'),
                              ('000001', 'read', 'mt', '+905551112233', '2026-10-01 09:00:00', 'first')])
            r = self.run_sms(shell, 'list', '2', MU300_SMS_PAGE=2)
            self.assertEqual(r.stdout.splitlines(), [
                'pool: 3 message(s), 1 unread - page 2/2 (2 per page)',
                '000001  read    mt  +905551112233      2026-10-01 09:00:00   first'])

    def test_list_on_an_empty_pool_creates_it(self):
        for shell in self.each_shell():
            r = self.run_sms(shell, 'list')
            self.assertEqual((r.returncode, r.stdout), (0, 'pool: 0 message(s), 0 unread - page 1/1 (10 per page)\n'))
            self.assertTrue((self.pool / 'msg').is_dir())

    def test_show_prints_the_whole_message_and_marks_it_read(self):
        for shell in self.each_shell():
            self.put(2, 'unread', 'mt', 'ADANA BLD', '2026-10-02 10:00:00', 'line one\nline two')
            r = self.run_sms(shell, 'show', '2')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('from:        ADANA BLD\n', r.stdout)
            self.assertTrue(r.stdout.endswith('\n---\nline one\nline two\n'), r.stdout)
            self.assertEqual(self.msgs()['000002'][0]['status'], 'read')
            # already read: still exit 0 (mu300dash reads a non-zero exit as a failed read)
            self.assertEqual(self.run_sms(shell, 'show', '000002').returncode, 0)
            r = self.run_sms(shell, 'show', '9')
            self.assertEqual((r.returncode, r.stdout, r.stderr), (1, '', 'mu300-sms: no message 9\n'))
            for bad in ('', '-1', '1x', '../1'):
                self.assertEqual(self.run_sms(shell, 'show', bad).returncode, 1, bad)

    # ------------------------------------------------------------------ sync
    def test_sync_pulls_the_sim_into_the_pool_in_pdu_mode(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('sync: 2 new, 2 on the SIM, 2 in the pool', r.stdout)
            log = self.at_log()
            self.assertIn('AT+CMGF=0', log)
            self.assertIn('AT+CMGL=4', log)
            self.assertLess(log.index('AT+CMGF=0'), log.index('AT+CMGL=4'))
            self.assertNotIn('AT+CMGF=1', log)          # PDU mode stays, as the sms command leaves it
            m = self.msgs()
            got = {h['from']: (h['dir'], h['status'], h['scts'], h['sim_index'], body) for h, body in m.values()}
            self.assertEqual(got, {
                '+31641600986': ('mt', 'unread', '2002-08-26 19:37:41', '3', 'How are you?\n'),
                'ADANA BLD': ('mt', 'read', '2026-09-15 17:18:00', '7', 'Kargonuz yolda ğüş\n')})
            # again: nothing new, and the SIM index of a message that moved is brought up to date
            self.answer('CMGL4', CMGL.replace('+CMGL: 7,', '+CMGL: 5,'))
            r = self.run_sms(shell, 'sync')
            self.assertIn('sync: 0 new, 2 on the SIM, 2 in the pool', r.stdout)
            self.assertEqual(sorted(h['sim_index'] for h, _ in self.msgs().values()), ['3', '5'])
            # list on what sync wrote
            lines = self.run_sms(shell, 'list').stdout.splitlines()
            self.assertEqual(lines[0], 'pool: 2 message(s), 1 unread - page 1/1 (10 per page)')

    def test_sync_joins_a_long_message_and_waits_for_its_missing_parts(self):
        # two parts of one message (concatenation header, reference 0x42), and a third message with a missing part
        def part(ref, total, n, text):
            ud = bytes([5, 0, 3, ref, total, n]).hex().upper() + text.encode('utf-16-be').hex().upper()
            return f'00440B911346610089F6000820806291731448{len(ud) // 2:02X}{ud}'
        cmgl = (f'+CMGL: 1,1,,30\n{part(0x42, 2, 2, " world")}\n+CMGL: 2,1,,30\n{part(0x42, 2, 1, "hello")}\n'
                f'+CMGL: 4,1,,30\n{part(0x43, 2, 1, "half")}\nOK\n')
        for shell in self.each_shell():
            self.fresh()
            self.answer('CMGL4', cmgl)
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('sync: 1 new, 1 on the SIM, 1 in the pool, 1 waiting for its other parts', r.stdout)
            [(h, body)] = self.msgs().values()
            self.assertEqual((h['sim_index'], body), ('1,2', 'hello world\n'))

    # ------------------------------------------------------------------ off the SIM
    def cmgr(self, slot, pdu):
        """What AT+CMGR=slot answers: the slot still holding PDU."""
        self.answer(f'CMGR{slot}', f'+CMGR: 1,,{len(pdu) // 2}\n{pdu}\nOK\n')

    def cmgd(self):
        return [c for c in self.at_log() if c.startswith('AT+CMGD')]

    def test_sync_moves_what_it_pooled_off_the_sim(self):
        # a full SIM takes no more messages: what the pool holds leaves the SIM, after the pool has it on the disk
        for shell in self.each_shell():
            self.fresh()
            self.cmgr(3, PDU_GSM)
            self.cmgr(7, PDU_UCS2)
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('sync: 2 new, 2 on the SIM, 2 in the pool, 2 moved off the SIM\n', r.stdout)
            log = self.at_log()
            self.assertEqual(self.cmgd(), ['AT+CMGD=3', 'AT+CMGD=7'])
            # each slot read back right before it goes, after the listing
            self.assertLess(log.index('AT+CMGL=4'), log.index('AT+CMGR=3'))
            self.assertLess(log.index('AT+CMGR=3'), log.index('AT+CMGD=3'))
            self.assertEqual(sorted(h['from'] for h, _ in self.msgs().values()), ['+31641600986', 'ADANA BLD'])
            # the SIM is empty now: the pool keeps both, unread stays unread
            self.answer('CMGL4', 'OK\n')
            r = self.run_sms(shell, 'sync')
            self.assertIn('sync: 0 new, 0 on the SIM, 2 in the pool, 0 moved off the SIM\n', r.stdout)
            self.assertEqual(sorted(h['status'] for h, _ in self.msgs().values()), ['read', 'unread'])

    def test_a_slot_that_changed_since_the_listing_stays(self):
        # slot 7 holds another message by the time it would go (deleted by `sms`, a new one landed): not touched
        for shell in self.each_shell():
            self.fresh()
            self.cmgr(3, PDU_GSM)
            self.cmgr(7, PDU_GSM)
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.cmgd(), ['AT+CMGD=3'])
            self.assertIn('1 moved off the SIM, 1 left there', r.stdout)
            # a slot that does not answer (busy channel, CMS error) stays too
            self.fresh()
            self.cmgr(3, PDU_GSM)
            self.answer('CMGR7', '+CMS ERROR: 321\n')
            self.run_sms(shell, 'sync')
            self.assertEqual(self.cmgd(), ['AT+CMGD=3'])

    def test_a_message_the_pool_could_not_take_stays_on_the_sim(self):
        if os.geteuid() == 0:
            self.skipTest('root writes into a read-only directory')
        for shell in self.each_shell():
            self.fresh()
            self.cmgr(3, PDU_GSM)
            self.cmgr(7, PDU_UCS2)
            self.run_sms(shell, 'list')                 # the pool directory, then made read-only
            os.chmod(self.pool / 'msg', 0o500)
            try:
                r = self.run_sms(shell, 'sync')
            finally:
                os.chmod(self.pool / 'msg', 0o700)
            self.assertIn('it stays on the SIM', r.stderr)
            self.assertEqual(self.cmgd(), [])
            self.assertEqual(self.msgs(), {})

    def test_the_parts_of_an_incomplete_message_stay_until_it_is_whole(self):
        def part(ref, total, n, text):
            ud = bytes([5, 0, 3, ref, total, n]).hex().upper() + text.encode('utf-16-be').hex().upper()
            return f'00440B911346610089F6000820806291731448{len(ud) // 2:02X}{ud}'
        p1, p2, half = part(0x42, 2, 1, 'hello'), part(0x42, 2, 2, ' world'), part(0x43, 2, 1, 'half')
        for shell in self.each_shell():
            self.fresh()
            self.answer('CMGL4', f'+CMGL: 1,1,,30\n{p2}\n+CMGL: 2,1,,30\n{p1}\n+CMGL: 4,1,,30\n{half}\nOK\n')
            for slot, pdu in ((1, p2), (2, p1), (4, half)):
                self.cmgr(slot, pdu)
            r = self.run_sms(shell, 'sync')
            self.assertIn('1 waiting for its other parts, 2 moved off the SIM', r.stdout)
            self.assertEqual(self.cmgd(), ['AT+CMGD=1', 'AT+CMGD=2'])

    def test_a_message_deleted_from_the_pool_goes_from_the_sim_too(self):
        for shell in self.each_shell():
            self.fresh()
            self.run_sms(shell, 'sync')                 # no CMGR answers: both stay on the SIM this time
            self.assertEqual(self.cmgd(), [])
            ids = {h['from']: i for i, (h, _) in self.msgs().items()}
            self.run_sms(shell, 'delete', ids['ADANA BLD'])
            self.cmgr(7, PDU_UCS2)
            self.run_sms(shell, 'sync')
            self.assertEqual(self.cmgd(), ['AT+CMGD=7'])
            self.assertEqual([h['from'] for h, _ in self.msgs().values()], ['+31641600986'])

    def test_a_new_message_runs_the_hook_once(self):
        hook = self.tmp / 'hook'
        out = self.tmp / 'hook.out'
        hook.write_text(f'#!/bin/sh\nprintf "%s|%s|%s|%s\\n" "$SMS_ID" "$SMS_FROM" "$SMS_DATE" "$SMS_TEXT" >> "{out}"\n')
        hook.chmod(0o755)
        for shell in self.each_shell():
            self.fresh()
            out.unlink(missing_ok=True)
            r = self.run_sms(shell, 'sync', MU300_SMS_HOOK=hook)
            self.assertEqual(r.returncode, 0, r.stderr)
            for _ in range(50):
                if out.exists() and len(out.read_text().splitlines()) == 2:
                    break
                time.sleep(0.1)
            got = sorted(out.read_text().splitlines())
            self.assertEqual([g.split('|', 1)[1] for g in got],
                             ['+31641600986|2002-08-26 19:37:41|How are you?', 'ADANA BLD|2026-09-15 17:18:00|Kargonuz yolda ğüş'])
            # a sync that finds nothing new runs it no more; a hook that is not executable is not run
            self.run_sms(shell, 'sync', MU300_SMS_HOOK=hook)
            time.sleep(0.3)
            self.assertEqual(len(out.read_text().splitlines()), 2)

    def test_a_deleted_message_stays_deleted(self):
        for shell in self.each_shell():
            self.fresh()
            self.run_sms(shell, 'sync')
            ids = {h['from']: i for i, (h, _) in self.msgs().items()}
            r = self.run_sms(shell, 'delete', ids['ADANA BLD'])
            self.assertEqual((r.returncode, r.stdout), (0, f'deleted {ids["ADANA BLD"]}\n'), r.stderr)
            self.run_sms(shell, 'sync')
            self.assertEqual([h['from'] for h, _ in self.msgs().values()], ['+31641600986'])
            # delete itself touches the pool only; a slot that does not read back (no CMGR answer here) stays
            self.assertFalse([c for c in self.at_log() if c.startswith('AT+CMGD')])
            # gone from the SIM too: its tombstone goes with it
            self.answer('CMGL4', f'+CMGL: 3,0,,40\n{PDU_GSM}\nOK\n')
            self.run_sms(shell, 'sync')
            self.assertEqual((self.pool / 'deleted').read_text().count('\n'), 0)

    def test_a_busy_sim_does_not_drop_the_tombstones(self):
        # AT+CPMS="SM" refused (SIM busy) and an empty ME listed instead: that says nothing about the SIM, so the
        # tombstones stay, and the deleted message does not come back on the next good listing
        for shell in self.each_shell():
            self.fresh()
            self.run_sms(shell, 'sync')
            ids = {h['from']: i for i, (h, _) in self.msgs().items()}
            self.run_sms(shell, 'delete', ids['ADANA BLD'])
            self.answer('CPMSSM', '+CME ERROR: 14\n')            # both forms of AT+CPMS="SM"...
            self.answer('CPMSME', '+CPMS: 0,100,0,100,0,100\nOK\n')
            self.answer('CMGL4', 'OK\n')                         # ...and an empty ME
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('AT+CPMS="ME","ME","ME"', self.at_log())
            self.assertEqual((self.pool / 'deleted').read_text().count('\n'), 1)
            # the SIM answers again
            (self.tmp / 'at' / 'CPMSSM').unlink()
            (self.tmp / 'at' / 'CPMSME').unlink()
            self.answer('CMGL4', CMGL)
            self.run_sms(shell, 'sync')
            self.assertEqual([h['from'] for h, _ in self.msgs().values()], ['+31641600986'])
            # an SM that answers but holds nothing, and an ME that does not answer: not sure either
            self.answer('CPMS', '+CPMS: 0,50,0,50,0,50\nOK\n')
            self.answer('CPMSME', 'ERROR\n')
            self.answer('CMGL4', 'OK\n')
            self.run_sms(shell, 'sync')
            self.assertEqual((self.pool / 'deleted').read_text().count('\n'), 1)
            # both answer and neither holds it: now it is really gone, and so is the tombstone
            self.answer('CPMSME', '+CPMS: 0,100,0,100,0,100\nOK\n')
            self.run_sms(shell, 'sync')
            self.assertEqual((self.pool / 'deleted').read_text().count('\n'), 0)

    def test_delete_sim_removes_the_matching_slot(self):
        for shell in self.each_shell():
            self.fresh()
            self.run_sms(shell, 'sync')
            ids = {h['from']: i for i, (h, _) in self.msgs().items()}
            # the SIM was re-ordered since the sync: the slot is found by content, not by the index the pool knew
            self.answer('CMGL4', CMGL.replace('+CMGL: 7,', '+CMGL: 9,'))
            r = self.run_sms(shell, 'delete', ids['ADANA BLD'], '--sim')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual([c for c in self.at_log() if c.startswith('AT+CMGD')], ['AT+CMGD=9'])
            self.assertEqual(len(self.msgs()), 1)
            r = self.run_sms(shell, 'delete', 'all')
            self.assertEqual((r.returncode, self.msgs()), (0, {}))
            self.assertEqual([c for c in self.at_log() if c.startswith('AT+CMGD')], ['AT+CMGD=9'])

    def test_no_at_daemon_no_modem_traffic(self):
        # without mu300-atd, mu300-at would open the tty itself, which can wedge the channel: refused instead
        for shell in self.each_shell():
            os.unlink(self.atdir / 'cmd')
            for args, stdin in ((('sync',), None), (('send', '--stdin', '123'), 'hi')):
                r = self.run_sms(shell, *args, stdin=stdin)
                self.assertEqual(r.returncode, 1, args)
                self.assertIn('mu300-atd is not running', r.stderr)
            self.assertEqual(self.at_log(), [])
            os.mkfifo(self.atdir / 'cmd')

    # ------------------------------------------------------------------ send
    def test_send_reads_the_text_on_stdin(self):
        self.answer('CMGS', '+CMGS: 12\nOK\n')
        for shell in self.each_shell():
            for text in ('Merhaba ğüş', '--help', '-x; $(reboot) `id`', 'two\nlines', 'back\\slash \\n'):
                with self.subTest(text=text):
                    (self.tmp / 'at.log').unlink(missing_ok=True)
                    r = self.run_sms(shell, 'send', '--stdin', '+905551112233', stdin=text)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertTrue(r.stdout.endswith('sent (reference 12)\n'), r.stdout)
                    enc = subprocess.run(['awk', '-v', 'mode=encode', '-v', 'number=+905551112233', '-v',
                                          'text=' + text.replace('\\', '\\\\').replace('\n', '\\n'), '-f', str(AWK)],
                                         capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                         env=dict(os.environ, LC_ALL='C')).stdout.split()
                    self.assertEqual(self.at_log(), ['AT+CMGF=0', f'AT+CMGS={enc[0]}^{enc[1]}~'])
                    if 'ğüş' in text:   # UCS-2 of the letters, also under gawk in a UTF-8 locale
                        self.assertIn('011F00FC015F', enc[1])
                    sent = [(h, b) for h, b in self.msgs().values() if h['dir'] == 'mo']
                    self.assertEqual((sent[-1][0]['to'], sent[-1][0]['status'], sent[-1][1]),
                                     ('+905551112233', 'sent', text + '\n'))

    def test_send_takes_the_text_from_arguments_too(self):
        self.answer('CMGS', '+CMGS: 3\nOK\n')
        for shell in self.each_shell():
            r = self.run_sms(shell, 'send', '10086', '-n', 'hello')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(list(self.msgs().values())[-1][1], '-n hello\n')

    def test_send_refusals_never_read_as_success(self):
        # mu300dash takes any output with "sent" or "OK" in it for success and one with "busy" for a busy channel
        self.answer('CMGS', '+CMS ERROR: 500\n')
        for shell in self.each_shell():
            for args, stdin in ((('--stdin', '-1'), 'hi'), (('--stdin', '+'), 'hi'), (('--stdin', '12+3'), 'hi'),
                                (('--stdin', '1' * 21), 'hi'), (('--stdin', '--stdin'), 'hi'),
                                (('--stdin', '123'), ''), (('--stdin',), 'hi'), (('--stdin', '123'), 'a' * 161),
                                (('--stdin', '123'), 'ğ' * 71), (('--stdin', '123'), 'hi'), ('bare OK', 'hi')):
                with self.subTest(args=args, text=stdin[:8]):
                    if args == 'bare OK':   # the modem says OK without a +CMGS: not taken, and no OK in the refusal
                        self.answer('CMGS', 'OK\n')
                        args = ('--stdin', '123')
                    r = self.run_sms(shell, 'send', *args, stdin=stdin)
                    self.assertEqual(r.returncode, 1, r.stdout)
                    out = r.stdout + r.stderr
                    self.assertNotRegex(out, 'sent|OK|busy')
                    self.assertTrue(r.stderr.startswith('mu300-sms: '), r.stderr)
            self.assertFalse([h for h, _ in self.msgs().values() if h['dir'] == 'mo'])
            # the panel's backend on the same refusal: Sending failed, not Sent
            r = self.dash(shell, 'sms_send', {'num': '123', 'text': 'hi'})
            self.assertEqual((r['ok'], r['error']), (0, 'Sending failed'))
            self.assertEqual(r['detail'], 'mu300-sms: the modem did not take the message: no +CMGS confirmation')
            # one part's worth goes out: 160 GSM characters, 70 UCS-2 ones
            self.answer('CMGS', '+CMGS: 1\nOK\n')
            for text in ('a' * 160, 'ğ' * 70):
                self.assertEqual(self.run_sms(shell, 'send', '--stdin', '123', stdin=text).returncode, 0)
            (self.tmp / 'at' / 'CMGS').write_text('+CMS ERROR: 500\n')
            shutil.rmtree(self.pool)

    def stat_tree(self, *dirs):
        """{path: (mtime_ns, ctime_ns, size, mode)} of every file and directory under DIRS, the DIRS included."""
        out = {}
        for d in dirs:
            for p in [d] + sorted(d.rglob('*')):
                st = p.stat()
                out[str(p)] = (st.st_mtime_ns, st.st_ctime_ns, st.st_size, st.st_mode)
        return out

    def test_an_unchanged_sim_writes_nothing_to_the_pool(self):
        # the pool is on flash and smsd syncs every 30 s: a sync of an unchanged SIM, a list, and a show of a read
        # message leave every file and directory of the pool as it was (no lock, no chmod, no tombstone rewrite)
        for shell in self.each_shell():
            self.fresh()
            self.run_sms(shell, 'sync')
            ids = {h['from']: i for i, (h, _) in self.msgs().items()}
            self.run_sms(shell, 'delete', ids['ADANA BLD'])          # a tombstone that stays (still on the SIM)
            self.run_sms(shell, 'show', ids['+31641600986'])        # read now
            time.sleep(0.05)
            before = self.stat_tree(self.pool)
            time.sleep(0.05)
            for args in (('sync',), ('sync',), ('list',), ('show', ids['+31641600986'])):
                r = self.run_sms(shell, *args)
                self.assertEqual(r.returncode, 0, (args, r.stderr))
            self.assertEqual(self.stat_tree(self.pool), before)
            self.assertEqual(list(self.run.iterdir()), [])          # the lock is in RAM, and released
            # a tombstone that is no longer needed is the one change a sync of a changed SIM makes to the list
            self.answer('CMGL4', f'+CMGL: 3,0,,40\n{PDU_GSM}\nOK\n')
            self.run_sms(shell, 'sync')
            self.assertEqual((self.pool / 'deleted').read_text(), '')

    @unittest.skipUnless(os.path.isdir('/proc/self'), 'a live lock holder is told by /proc/PID/cmdline')
    def test_delete_waits_for_the_pool_lock(self):
        # tombstone and removal under the pool lock: a tombstone written while a sync rewrote the list was lost
        # named the way mu300-sms names it: md5sum where there is one (OpenWrt, Linux), else cksum
        key = subprocess.run(['md5sum' if shutil.which('md5sum') else 'cksum'], input=str(self.pool), capture_output=True,
                             text=True).stdout.split()[0]
        for shell in self.each_shell():
            self.fresh()
            self.run_sms(shell, 'sync')
            mid = sorted(self.msgs())[0]
            lock = self.run / f'mu300-sms-pool.{key}.lock'
            lock.mkdir()
            # a live holder named mu300-sms ("; true": the shell must not exec sleep and lose its command line)
            holder = subprocess.Popen(['sh', '-c', 'sleep 2; true', 'mu300-sms'])
            (lock / 'pid').write_text(f'{holder.pid}\n')
            try:
                d = subprocess.Popen(shell + [str(SMS), 'delete', mid], env=self.env(
                    MU300_SMS_POOL=self.pool, MU300_SMS_RUN=self.run), stdout=subprocess.PIPE, text=True)
                time.sleep(1)
                self.assertIsNone(d.poll(), 'delete did not wait for the lock')
                self.assertIn(mid, self.msgs())
                holder.wait()
                shutil.rmtree(lock)
                self.assertEqual(d.communicate(timeout=10)[0], f'deleted {mid}\n')
                self.assertNotIn(mid, self.msgs())
                self.assertEqual((self.pool / 'deleted').read_text().count('\n'), 1)
            finally:
                holder.kill()

    def test_a_busy_channel_says_busy(self):
        (self.tmp / 'at' / 'BUSY').write_text('')
        for shell in self.each_shell():
            r = self.run_sms(shell, 'send', '--stdin', '123', stdin='hi')
            self.assertEqual(r.returncode, 1)
            self.assertIn('busy', r.stdout + r.stderr)

    # ------------------------------------------------------------------ the panel on the pool
    def dash(self, shell, method, params, **env):
        (self.stubs / 'jsonfilter.py').write_text(JSONFILTER)
        self.stub('jsonfilter', f'exec python3 "{self.stubs}/jsonfilter.py" "$@"')
        self.stub('uci', '[ "$3" = unisoc_modem.main.sms_pool ] && [ -n "${UCI_POOL:-}" ] && '
                         'printf "%s\\n" "$UCI_POOL" && exit 0; exit 1')
        self.stub('logger', 'exit 0')
        e = self.env(MU300_SMS_BIN=SMS, MU300_SMS_POOL=self.pool, MU300_AT_DIR=self.atdir, MU300_SMS_AWK=AWK,
                     MU300_SMS_RUN=self.run, MU300_DASH_DIR=self.tmp / 'dash', MU300_DASH_BIN=self.tmp / 'none')
        e.update({k: str(v) for k, v in env.items()})
        e = {k: v for k, v in e.items() if v != ''}
        r = subprocess.run(shell + [str(DASH), 'call', method], input=json.dumps(params).encode(),
                           capture_output=True, env=e, timeout=60)
        return json.loads(r.stdout.decode())

    def test_the_panel_reads_the_pool(self):
        for shell in self.each_shell():
            shutil.rmtree(self.pool, ignore_errors=True)
            self.put(1, 'read', 'mt', '+905551112233', '2026-10-01 09:00:00', 'first "quoted" \\ text')
            self.put(2, 'unread', 'mt', 'ADANA BLD', '2026-10-02 10:00:00', 'Kargonuz yolda ğüş\nline two')
            self.assertEqual(self.dash(shell, 'sms_list', {}), {
                'total': 2, 'unread': 1, 'page': 1, 'pages': 1, 'msgs': [
                    {'id': '000002', 'status': 'unread', 'dir': 'mt', 'peer': 'ADANA BLD',
                     'time': '2026-10-02 10:00:00', 'preview': 'Kargonuz yolda ğüş'},
                    {'id': '000001', 'status': 'read', 'dir': 'mt', 'peer': '+905551112233',
                     'time': '2026-10-01 09:00:00', 'preview': 'first "quoted" \\ text'}]})
            r = self.dash(shell, 'sms_show', {'id': '2'})
            self.assertEqual(r['ok'], 1)
            self.assertEqual(r['text'].split('\n---\n', 1)[1], 'Kargonuz yolda ğüş\nline two')
            self.assertEqual(self.dash(shell, 'sms_show', {'id': '9'})['error'], 'Read failed')
            self.answer('CMGS', '+CMGS: 4\nOK\n')
            r = self.dash(shell, 'sms_send', {'num': '10086', 'text': '-hi'})
            self.assertEqual((r['ok'], r['reply'].splitlines()[-1]), (1, 'sent (reference 4)'))
            (self.tmp / 'at' / 'CMGS').write_text('+CMS ERROR: 500\n')
            r = self.dash(shell, 'sms_send', {'num': '10086', 'text': 'hi'})
            self.assertEqual((r['ok'], r['error']), (0, 'Sending failed'))
            self.assertIn('+CMS ERROR: 500', r['detail'])
            self.assertEqual(self.dash(shell, 'sms_delete', {'id': '1'}), {'ok': 1})
            r = self.dash(shell, 'sms_delete', {'id': '1'})
            self.assertEqual((r['error'], r['detail']), ('Delete failed', 'mu300-sms: no message 1'))

    def test_the_panel_never_puts_the_pool_in_the_sms_state_directory(self):
        # the pool the backend hands mu300-sms: the default, or a uci sms_pool under /etc/mu300 - but never
        # /etc/mu300/sms, which is the sms command's own state (D11)
        self.stub('mu300-sms-env', 'printf "%s\\n" "$MU300_SMS_POOL" > "$STUBLOG/pool"; '
                                   'echo "pool: 0 message(s), 0 unread - page 1/1 (10 per page)"')
        for shell in self.each_shell():
            for uci, want in (('', '/etc/mu300/sms-pool'), ('/etc/mu300/sms', '/etc/mu300/sms-pool'),
                              ('/etc/mu300/sms/x', '/etc/mu300/sms-pool'), ('/tmp/x', '/etc/mu300/sms-pool'),
                              ('/etc/mu300/other', '/etc/mu300/other')):
                with self.subTest(uci=uci):
                    (self.tmp / 'pool').unlink(missing_ok=True)
                    r = self.dash(shell, 'sms_list', {}, MU300_SMS_POOL='', MU300_SMS_BIN=self.stubs / 'mu300-sms-env',
                                  UCI_POOL=uci)
                    self.assertEqual(r['total'], 0)
                    self.assertEqual((self.tmp / 'pool').read_text(), want + '\n')

    # ------------------------------------------------------------------ durable before the SIM lets go
    def test_the_pool_is_fsynced_before_any_slot_leaves_the_sim_and_never_globally(self):
        # fsync (busybox's applet on OpenWrt) and a global sync both write into the AT log, so the order is one list
        self.stub('fsync', 'echo "FSYNC $*" >> "$STUBLOG/at.log"')
        self.stub('sync', 'echo "GLOBAL SYNC $*" >> "$STUBLOG/at.log"')
        for shell in self.each_shell():
            self.fresh()
            self.cmgr(3, PDU_GSM)
            self.cmgr(7, PDU_UCS2)
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            log = self.at_log()
            self.assertFalse([l for l in log if l.startswith('GLOBAL SYNC')], log)
            fs = [l for l in log if l.startswith('FSYNC')]
            msg = self.pool / 'msg'
            # each message file before its rename, then the directory entries and next_id
            self.assertEqual(sorted(fs[:2]), [f'FSYNC {msg}/000001.part', f'FSYNC {msg}/000002.part'])
            self.assertEqual(fs[2], f'FSYNC {msg} {self.pool}/next_id {self.pool}')
            self.assertLess(log.index(fs[2]), log.index('AT+CMGD=3'))
            # a sync that takes nothing new syncs nothing
            (self.tmp / 'at.log').unlink()
            self.run_sms(shell, 'sync')
            self.assertFalse([l for l in self.at_log() if 'SYNC' in l])

    def test_without_fsync_coreutils_sync_takes_the_files(self):
        # Ubuntu: no fsync applet, but coreutils' sync FILE...; busybox's sync (no FILE in its help) is never given files
        for shell in self.each_shell():
            for helptext, want in (('Usage: sync [OPTION] [FILE]...', 'SYNC -- '), ('Usage: sync', 'SYNC ')):
                self.fresh()
                self.stub('fsync', 'exit 127')
                self.stub('sync', f'[ "$1" = --help ] && {{ echo "{helptext}"; exit 0; }}; echo "SYNC $*" >> "$STUBLOG/at.log"')
                os.unlink(self.stubs / 'fsync')
                self.cmgr(3, PDU_GSM)
                self.run_sms(shell, 'sync')
                syncs = [l for l in self.at_log() if l.startswith('SYNC')]
                if want == 'SYNC ':
                    self.assertTrue(syncs and all(l == 'SYNC ' for l in syncs), syncs)
                else:
                    self.assertTrue(syncs and all(l.startswith('SYNC -- ') for l in syncs), syncs)

    def test_next_id_survives_an_empty_id_file(self):
        # a power cut that left next_id empty must not start the ids over and overwrite message 1
        for shell in self.each_shell():
            self.fresh()
            self.put(5, 'read', 'mt', '+905551112233', '26/10/01,10:00:00+12', 'old')
            (self.pool / 'next_id').write_text('')
            r = self.run_sms(shell, 'sync')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(self.msgs()), ['000005', '000006', '000007'])
            self.assertEqual(self.msgs()['000005'][1], 'old\n')
            self.assertEqual((self.pool / 'next_id').read_text(), '7\n')
            self.assertFalse((self.pool / 'next_id.part').exists())

    @staticmethod
    def part(ref, total, n, text):
        ud = bytes([5, 0, 3, ref, total, n]).hex().upper() + text.encode('utf-16-be').hex().upper()
        return f'00440B911346610089F6000820806291731448{len(ud) // 2:02X}{ud}'

    def test_parts_that_never_complete_are_pooled_after_the_wait(self):
        p1, p3 = self.part(0x43, 3, 1, 'first '), self.part(0x43, 3, 3, ' third')
        cmgl = f'+CMGL: 4,0,,30\n{p1}\n+CMGL: 5,1,,30\n{p3}\nOK\n'
        for shell in self.each_shell():
            self.fresh()
            self.answer('CMGL4', cmgl)
            self.cmgr(4, p1)
            self.cmgr(5, p3)
            r = self.run_sms(shell, 'sync')
            self.assertIn('sync: 0 new, 0 on the SIM, 0 in the pool, 1 waiting for its other parts, 0 moved', r.stdout)
            key, first, unread = (self.pool / 'partial').read_text().rstrip('\n').split('\t')
            self.assertEqual((key, unread), ('multi:+31641600986:67:3', '1'))
            # unchanged while it waits: the state file is not written again, though the modem now lists the parts
            # as read (AT+CMGL marks what it lists read)
            self.answer('CMGL4', cmgl.replace('+CMGL: 4,0,', '+CMGL: 4,1,'))
            before = self.stat_tree(self.pool)
            time.sleep(0.05)
            self.run_sms(shell, 'sync')
            self.assertEqual(self.stat_tree(self.pool), before)
            # an hour later (the state says so): pooled as it is, unread as first seen, its slots off the SIM, the
            # state gone
            (self.pool / 'partial').write_text(f'{key}\t{int(first) - 3600}\t1\n')
            r = self.run_sms(shell, 'sync')
            self.assertIn('sync: 1 new, 0 on the SIM, 1 in the pool, 2 moved off the SIM', r.stdout)
            [(h, body)] = self.msgs().values()
            self.assertEqual((h['incomplete'], h['sim_index'], h['status'], body),
                             ('2/3', '4,5', 'unread', 'first [...] third\n'))
            self.assertRegex(h['partial'], r'^[0-9a-f]{32}$|^[0-9]+$')
            self.assertFalse((self.pool / 'partial').exists())
            show = self.run_sms(shell, 'show', '1').stdout
            self.assertIn('\nincomplete:  2 of 3 parts arrived\n', show.split('\n---\n')[0] + '\n')
            self.assertEqual(show.split('\n---\n')[1], 'first [...] third\n')
            # the missing part, late: pooled at once, as a message of its own
            p2 = self.part(0x43, 3, 2, 'second')
            self.answer('CMGL4', f'+CMGL: 1,0,,30\n{p2}\nOK\n')
            self.cmgr(1, p2)
            r = self.run_sms(shell, 'sync')
            self.assertIn('sync: 1 new, 0 on the SIM, 2 in the pool, 1 moved off the SIM', r.stdout)
            late = [m for m in self.msgs().values() if m[0]['sim_index'] == '1']
            self.assertEqual((late[0][0]['incomplete'], late[0][1]), ('1/3', '[...]second[...]\n'))

    def test_partial_wait_zero_pools_at_once(self):
        half = self.part(0x44, 2, 2, 'only the end')
        for shell in self.each_shell():
            self.fresh()
            self.answer('CMGL4', f'+CMGL: 9,1,,30\n{half}\nOK\n')
            r = self.run_sms(shell, 'sync', MU300_SMS_PARTIAL_WAIT=0)
            self.assertIn('1 new', r.stdout)
            [(h, body)] = self.msgs().values()
            self.assertEqual((h['incomplete'], h['status'], body), ('1/2', 'read', '[...]only the end\n'))

    def test_new_messages_go_to_the_forwarding(self):
        fwd = self.tmp / 'fwd'
        fwd.write_text('#!/bin/sh\necho "$*" >> "$STUBLOG/fwd.log"\n')
        fwd.chmod(0o755)
        for shell in self.each_shell():
            self.fresh()
            (self.tmp / 'fwd.log').unlink(missing_ok=True)
            self.run_sms(shell, 'sync', MU300_SMS_FORWARD=fwd)
            self.run_sms(shell, 'sync', MU300_SMS_FORWARD=fwd)
            self.assertEqual((self.tmp / 'fwd.log').read_text().splitlines(), ['enqueue 000001 000002', 'kick'])


class Watch(ShellTest):
    """`sms watch` (every system): a long message waits for its other parts, MU300_SMS_PARTIAL_WAIT at most."""

    def setUp(self):
        super().setUp()
        self.stub('mu300-at', AT_STUB)
        (self.tmp / 'at').mkdir()
        (self.tmp / 'at' / 'CPMS').write_text('+CPMS: 2,50,2,50,2,50\nOK\n')
        # one round of the loop: the second sleep ends the script
        self.stub('sleep', 'n=$(cat "$STUBLOG/rounds" 2>/dev/null || echo 0); n=$((n + 1)); echo $n > "$STUBLOG/rounds"; '
                           '[ "$n" -ge "${ROUNDS:-1}" ] && kill $PPID; exit 0')

    def watch(self, shell, cmgl, **env):
        (self.tmp / 'at' / 'CMGL4').write_text(cmgl)
        (self.tmp / 'rounds').unlink(missing_ok=True)
        hook = f'printf "%s|%s\\n" "$SMS_FROM" "$SMS_TEXT" >> "{self.tmp}/hook.out"'
        # A busybox that runs sleep as its own applet never calls the stub, so the loop sleeps for real: one round
        # takes well under the timeout, which then ends it.
        try:
            return subprocess.run(shell + [str(TOP / 'rootfs/overlay/opt/mu300/bin/sms'), 'watch', hook],
                                  capture_output=True, text=True, timeout=8,
                                  env=self.env(MU300_SMS_AWK=AWK, MU300_SMS_STATE=self.tmp / 'state', **env))
        except subprocess.TimeoutExpired as e:
            return e

    def test_an_incomplete_message_waits_then_is_reported(self):
        part = Pool.part
        p1 = part(0x45, 2, 1, 'hello')
        for shell in self.each_shell():
            for f in ('hook.out', 'state'):
                subprocess.run(['rm', '-rf', str(self.tmp / f)])
            self.watch(shell, f'+CMGL: 1,0,,30\n{p1}\nOK\n')
            time.sleep(0.3)
            self.assertFalse((self.tmp / 'hook.out').exists())
            key, first = (self.tmp / 'state' / 'partial').read_text().rstrip('\n').split('\t')
            (self.tmp / 'state' / 'partial').write_text(f'{key}\t{int(first) - 3600}\n')
            self.watch(shell, f'+CMGL: 1,0,,30\n{p1}\nOK\n')
            for _ in range(30):
                if (self.tmp / 'hook.out').exists():
                    break
                time.sleep(0.1)
            self.assertEqual((self.tmp / 'hook.out').read_text(), '+31641600986|hello[missing part 2]\n')
            # the whole message, once the rest comes: reported again, and the waiting state is gone
            p2 = part(0x45, 2, 2, ' world')
            self.watch(shell, f'+CMGL: 1,0,,30\n{p1}\n+CMGL: 2,0,,30\n{p2}\nOK\n')
            for _ in range(30):
                if len((self.tmp / 'hook.out').read_text().splitlines()) == 2:
                    break
                time.sleep(0.1)
            self.assertEqual((self.tmp / 'hook.out').read_text().splitlines()[1], '+31641600986|hello world')
            self.assertFalse((self.tmp / 'state' / 'partial').exists() and
                             (self.tmp / 'state' / 'partial').read_text())


@unittest.skipUnless(os.path.isdir('/proc/self'), 'mu300-smsd tells a live holder by /proc/PID/cmdline')
class Daemon(ShellTest):
    def setUp(self):
        super().setUp()
        self.atdir = self.tmp / 'run-at'
        (self.atdir / 'urc').mkdir(parents=True)
        os.mkfifo(self.atdir / 'cmd')
        self.stub('mu300-at', 'printf "%s\\n" "$*" >> "$STUBLOG/at.log"; '
                              'case $* in *CPIN*) printf "+CPIN: READY\\nOK\\n" ;; *) echo OK ;; esac')
        self.stub('fake-sms', 'echo "$*" >> "$STUBLOG/sms.log"')
        self.lock = self.tmp / 'smsd.lock'

    def start(self, shell):
        e = self.env(MU300_AT_DIR=self.atdir, MU300_SMS_BIN=self.stubs / 'fake-sms', MU300_SMS_LOCK=self.lock,
                     MU300_SMS_POLL=1, MU300_SMS_SYNC_INTERVAL=600, MU300_SMS_POOL=self.tmp / 'pool')
        return subprocess.Popen(shell + [str(SMSD)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                env=e)

    def syncs(self):
        p = self.tmp / 'sms.log'
        return p.read_text().splitlines() if p.exists() else []

    def wait_for(self, cond, what, timeout=10):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if cond():
                return
            time.sleep(0.1)
        self.fail(what)

    def test_one_daemon_and_a_sync_on_each_new_message(self):
        for shell in self.each_shell():
            (self.tmp / 'sms.log').unlink(missing_ok=True)
            first = self.start(shell)
            try:
                self.wait_for(lambda: self.syncs() == ['sync'], 'no first sync')
                self.assertIn('AT+CNMI=2,1,0,0,0', (self.tmp / 'at.log').read_text())
                # a second one leaves the pool to the first
                second = self.start(shell)
                out, err = second.communicate(timeout=10)
                self.assertEqual(second.returncode, 0)
                self.assertIn(f'pid {first.pid} is already pooling', err)
                # a +CMTI in the AT daemon's URC log: one more sync
                with open(self.atdir / 'urc' / 'stty_nr0.log', 'a') as f:
                    f.write('+CMTI: "SM",4\n')
                self.wait_for(lambda: self.syncs() == ['sync', 'sync'], 'no sync after +CMTI', timeout=15)
            finally:
                first.send_signal(signal.SIGTERM)
                first.communicate(timeout=10)
            self.assertFalse(self.lock.exists(), 'the lock outlived its daemon')

    def test_a_new_message_syncs_without_cksum(self):
        # OpenWrt's busybox has md5sum but no cksum: a +CMTI still starts a sync, and nothing says "not found"
        self.stub('cksum', 'echo "cksum: not found" >&2; exit 127')
        for shell in self.each_shell():
            (self.tmp / 'sms.log').unlink(missing_ok=True)
            (self.atdir / 'urc' / 'stty_nr0.log').unlink(missing_ok=True)
            d = self.start(shell)
            try:
                self.wait_for(lambda: self.syncs() == ['sync'], 'no first sync')
                time.sleep(1.5)   # a look or two at the URC logs before the message
                with open(self.atdir / 'urc' / 'stty_nr0.log', 'a') as f:
                    f.write('+CMTI: "SM",4\n')
                self.wait_for(lambda: self.syncs() == ['sync', 'sync'], 'no sync after +CMTI', timeout=15)
            finally:
                d.send_signal(signal.SIGTERM)
                out, err = d.communicate(timeout=10)
            self.assertNotIn('not found', err + out)

    def test_a_dead_holder_is_taken_over(self):
        for shell in self.each_shell():
            self.lock.mkdir()
            dead = subprocess.Popen(['true'])
            dead.wait()
            (self.lock / 'pid').write_text(f'{dead.pid}\n')
            d = self.start(shell)
            try:
                self.wait_for(lambda: (self.lock / 'pid').exists() and
                              (self.lock / 'pid').read_text().strip() == str(d.pid), 'lock not taken over')
            finally:
                d.send_signal(signal.SIGTERM)
                d.communicate(timeout=10)


class Wiring(unittest.TestCase):
    def test_init_script(self):
        src = INITD.read_text()
        self.assertTrue(src.startswith('#!/bin/sh /etc/rc.common\n'))
        self.assertIn('USE_PROCD=1', src)
        self.assertIn('procd_set_param command /opt/mu300/bin/mu300-smsd', src)
        self.assertIn('procd_set_param respawn', src)
        self.assertRegex(src, r'(?m)^START=\d+$')

    def test_build_enables_the_pool_on_openwrt_luci_only(self):
        src = BUILD.read_text()
        # inside the same luci-plugin branch that enables the panel's own service, never in the common lists
        block = src[src.index('    ln -sf ../init.d/unisoc-modem-ui'):]
        block = block[:block.index('\nfi\n')]
        self.assertIn('ln -sf ../init.d/mu300-smsd $R/etc/rc.d/S${n}mu300-smsd', block)
        self.assertIn('ln -sf /opt/mu300/bin/mu300-sms $R/usr/bin/mu300-sms', block)
        common = re.search(r'for s in (mu300-accounts[^;]*);', src).group(1)
        self.assertNotIn('smsd', common)
        # the commands every system links come from the shared list
        self.assertIn('for c in $(cat /in/opt-mu300/lib/path-commands)', src)
        common = (TOP / 'rootfs' / 'overlay' / 'opt' / 'mu300' / 'lib' / 'path-commands').read_text().split()
        self.assertNotIn('mu300-sms', common)
        # the pool programs come from the luci overlay; the shared tree (every system) has none of them
        for name in ('mu300-sms', 'mu300-smsd'):
            self.assertFalse((TOP / 'rootfs' / 'overlay' / 'opt' / 'mu300' / 'bin' / name).exists())
        self.assertFalse((TOP / 'openwrt' / 'overlay' / 'etc' / 'init.d' / 'mu300-smsd').exists())


if __name__ == '__main__':
    unittest.main()
