"""History imports are not live SMS events, including on legacy adapters."""
from datetime import datetime

from helpers import ShellTest, TOP


FORWARD = TOP / 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/sms-forward'


def epoch(iso):
    return int(datetime.fromisoformat(iso).timestamp())


class ForwardHistory(ShellTest):
    def setUp(self):
        super().setUp()
        text = FORWARD.read_text()
        self.code = '\n'.join([
            text[text.index('number() {'):text.index('bool() {')],
            text[text.index('load_state() {'):text.index('save_config() {')],
            text[text.index('write_result() {'):text.index('read_result() {')],
            text[text.index('message_file() {'):text.index('template_strings() {')],
            text[text.index('scts_epoch() {'):text.index('process_power() {')],
            'deliver() { printf "%s\\n" "$3" >> "$DELIVERIES"; DELIVER_RESULT=sent; }',
        ])
        self.barrier = epoch('2026-10-07T12:00:00+08:00')

    def test_timestamp_offsets_and_calendar_independent_of_host_timezone(self):
        cases = [
            ('26/10/07,12:34:56+32', '2026-10-07T12:34:56+08:00'),
            ('26/10/07,12:34:56-14', '2026-10-07T12:34:56-03:30'),
            ('26/10/07,00:00:00+23', '2026-10-07T00:00:00+05:45'),
            ('00/02/29,00:00:00+00', '2000-02-29T00:00:00+00:00'),
            ('28/02/29,23:59:59+56', '2028-02-29T23:59:59+14:00'),
            ('2026-10-07 12:34:56+08:00', '2026-10-07T12:34:56+08:00'),
            ('2026-10-07T12:34:56-03:30', '2026-10-07T12:34:56-03:30'),
        ]
        for shell in self.each_shell():
            for value, iso in cases:
                for tz in ('UTC0', 'EST5', 'JST-9'):
                    result = self.sh(shell, self.code + '\nscts_epoch "$STAMP"', STAMP=value, TZ=tz)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(int(result.stdout), epoch(iso), (value, tz))

    def test_unknown_or_invalid_sim_timestamps_are_not_guessed(self):
        cases = ['', 'garbage', '26/10/07,12:00:00', '2026-10-07 12:00:00',
                 '26/02/29,12:00:00+32', '26/04/31,12:00:00+32',
                 '26/13/01,12:00:00+32', '26/10/00,12:00:00+32',
                 '26/10/07,24:00:00+32', '26/10/07,12:60:00+32',
                 '26/10/07,12:00:60+32', '26/10/07,12:00:00+99',
                 '2026-10-07 12:00:00+08:60', '26/10/07,12:00:00+32\n123']
        for shell in self.each_shell():
            for value in cases:
                result = self.sh(shell, self.code + '\nscts_epoch "$STAMP"', STAMP=value)
                self.assertNotEqual(result.returncode, 0, value)

    def test_live_delayed_delivery_and_sim_boundary(self):
        for shell in self.each_shell():
            for source in ('sim', ''):
                for stamp, expected in [('26/09/29,12:00:00+32', False),
                                        ('26/10/07,11:59:59+32', False),
                                        ('26/10/07,12:00:00+32', True),
                                        ('26/10/07,12:00:01+32', True)]:
                    result = self.sh(shell, self.code + '\nsms_is_new "$SOURCE" "$STAMP" "$RECEIVED"',
                                     SOURCE=source, STAMP=stamp, RECEIVED=self.barrier + 500,
                                     since=self.barrier)
                    self.assertEqual(result.returncode == 0, expected)
            # A direct SMS received now can have an old SMSC timestamp; do not
            # suppress genuine delayed network delivery just because it is old.
            result = self.sh(shell, self.code + '\nsms_is_new direct old "$RECEIVED"',
                             RECEIVED=self.barrier + 500, since=self.barrier)
            self.assertEqual(result.returncode, 0)
            result = self.sh(shell, self.code + '\nsms_is_new direct old "$RECEIVED"',
                             RECEIVED=self.barrier - 1, since=self.barrier)
            self.assertNotEqual(result.returncode, 0)

    def test_mixed_batch_downtime_restart_blacklist_and_no_replay(self):
        for index, shell in enumerate(self.each_shell()):
            base = self.tmp / str(index)
            pool = base / 'pool'
            (pool / 'msg').mkdir(parents=True)
            # Import all of these AFTER enabling. Old SIM history must not
            # masquerade as new mail; new arrivals while worker is down must.
            records = [
                ('', '26/09/29,12:00:00+32', 'ucs2', 'mt', 'old legacy'),
                ('sim', '2026-09-29 12:00:00+08:00', 'pdu', 'mt', 'old PDU'),
                ('sim', '26/10/07,12:00:01+32', 'ucs2', 'mt', 'new SIM'),
                ('', '26/10/07,12:00:02+32', 'ucs2', 'mt', 'new legacy'),
                ('direct', '26/09/29,12:00:00+32', 'pdu', 'mt', 'live delayed'),
                ('sim', '26/10/07,12:00:01+32', 'ucs2', 'mt', 'BLOCKME'),
                ('direct', '26/10/07,12:00:01+32', 'pdu', 'mo', 'outgoing'),
                ('sim', 'unknown', 'pdu', 'mt', 'unknown SIM'),
                ('sim', '26/10/07,12:00:01+32', 'raw-pdu', 'mt', 'undecoded SIM'),
            ]
            for num, (source, stamp, coding, direction, body) in enumerate(records, 1):
                (pool / 'msg' / f'{num:06d}').write_text(
                    f'dir: {direction}\nfrom: 10010\nsource: {source}\nscts: {stamp}\n'
                    f'received: {self.barrier + 500}\ncoding: {coding}\n\n{body}\n')
            (pool / 'next_id').write_text(f'{len(records)}\n')
            state = base / 'state'
            state.write_text(f'0|{self.barrier}|-1|none\n')
            env = dict(BASE=base, POOL=pool, STATE=state, RESULT=base / 'result',
                       DELIVERIES=base / 'sent', enabled=1, power_last_result='idle',
                       blacklist_phone='', blacklist_keywords='BLOCKME')
            run = self.code + '\nload_state\nfor pass in 1 2 3 4 5 6 7 8 9 10; do process_sms; done'
            for _ in range(2):  # restart: use saved cursor, not an in-memory flag
                result = self.sh(shell, run, **env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((base / 'sent').read_text().splitlines(),
                                 ['new SIM', 'new legacy', 'live delayed'])
                self.assertEqual(state.read_text().split('|')[0], '9')


if __name__ == '__main__':
    import unittest
    unittest.main()
