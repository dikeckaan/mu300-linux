"""sprd_ddr_dfs (upstream/modules/sprd_ddr_dfs): the PM_SYS firmware's DFS protocol of ddr_dfs.h compiled on the host
(result codes, the table, the frequency picked for a request, the requests that put the firmware back as found), and
the driver's rules: loaded by name only, no polling, the channel never closed once open, built and loaded after SIPC."""
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import TOP

MOD = TOP / 'upstream/modules/sprd_ddr_dfs'
SRC = (MOD / 'sprd_ddr_dfs.c').read_text()

# commands on stdin: "e CODE" prints the errno; "t N RAW..." prints the table; "p MHZ N TABLE..." prints the pick;
# "r ENABLED AUTO FREQ VOTE" prints the restore requests as CMD:VALUE
HARNESS = r'''
#include <stdio.h>
#include "ddr_dfs.h"
int main(void)
{
	char c;
	unsigned int raw[32], table[DDR_DFS_MAX_FREQS], n, i, count;
	unsigned long mhz;
	struct ddr_dfs_state s;
	struct ddr_dfs_req req[4];

	while (scanf(" %c", &c) == 1) {
		if (c == 'e' && scanf("%x", &n) == 1) {
			printf("%d\n", ddr_dfs_errno(n));
		} else if (c == 't' && scanf("%u", &n) == 1) {
			for (i = 0; i < n; i++)
				scanf("%u", &raw[i]);
			count = ddr_dfs_table(raw, n, table);
			for (i = 0; i < count; i++)
				printf("%u ", table[i]);
			printf("#%u\n", count);
		} else if (c == 'p' && scanf("%lu %u", &mhz, &n) == 2) {
			for (i = 0; i < n; i++)
				scanf("%u", &table[i]);
			printf("%u\n", ddr_dfs_pick(table, n, mhz));
		} else if (c == 'r' && scanf("%u %u %u %u", &s.enabled, &s.autodfs, &s.freq, &s.vote) == 4) {
			n = ddr_dfs_restore(&s, req);
			for (i = 0; i < n; i++)
				printf("%04x:%u ", req[i].cmd, req[i].value);
			printf("\n");
		}
		fflush(stdout);
	}
	return 0;
}
'''

# the U30 Air's firmware: INQ_DDR_TABLE 0..8 with freq-num 8 asks for 0..7
U30AIR = [384, 533, 768, 1066, 1244, 1536, 1866, 0]


@unittest.skipUnless(shutil.which('cc'), 'needs a C compiler')
class Protocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        with open(f'{cls.dir}/h.c', 'w') as f:
            f.write(HARNESS)
        cls.exe = f'{cls.dir}/h'
        subprocess.run(['cc', '-std=c99', '-Wall', '-Werror', f'-I{MOD}', '-o', cls.exe, f'{cls.dir}/h.c'], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir, ignore_errors=True)

    def run1(self, cmd):
        r = subprocess.run([self.exe], input=cmd + '\n', capture_output=True, text=True, check=True)
        return r.stdout.strip()

    def test_result_codes(self):
        for code in ('0', '300', '500', '600', '70f'):     # vote, on/off, inquiry, set, parameter: done
            self.assertEqual(self.run1(f'e {code}'), '0', code)
        self.assertEqual(self.run1('e 2'), '-16')          # busy
        self.assertEqual(self.run1('e 5'), '-1')           # DFS off
        self.assertEqual(self.run1('e f0f'), '-95')        # unknown command (INQ_COUNT on the U30 Air)
        for code in ('1', '3', '4', '303', '503', '603'):
            self.assertEqual(self.run1(f'e {code}'), '-5', code)

    def test_table_of_the_u30_air(self):
        self.assertEqual(self.run1('t %d %s' % (len(U30AIR), ' '.join(map(str, U30AIR)))),
                         '384 533 768 1066 1244 1536 1866 #7')

    def test_table_that_does_not_rise_is_refused(self):
        self.assertEqual(self.run1('t 3 384 1866 1536'), '#0')
        self.assertEqual(self.run1('t 3 384 384 768'), '#0')
        self.assertEqual(self.run1('t 2 0 0'), '#0')

    def test_pick(self):
        table = '7 384 533 768 1066 1244 1536 1866'
        self.assertEqual(self.run1(f'p 0 {table}'), '384')       # no floor: the lowest entry
        self.assertEqual(self.run1(f'p 1066 {table}'), '1066')
        self.assertEqual(self.run1(f'p 1067 {table}'), '1244')   # a request between entries rounds up
        self.assertEqual(self.run1(f'p 2000 {table}'), '1866')   # above the table: the top

    def test_restore_what_the_u30_air_boots_with(self):
        # DFS off, auto off, 1866 MHz: the vote back, 1866 pinned (auto DFS off), then DFS off
        self.assertEqual(self.run1('r 0 0 1866 0'), '0000:0 0600:1866 0305:0')

    def test_restore_running_auto_dfs(self):
        self.assertEqual(self.run1('r 1 1 1536 1244'), '0000:1244 0310:0')

    def test_restore_a_pinned_frequency(self):
        self.assertEqual(self.run1('r 1 0 768 0'), '0000:0 0600:768')


class Driver(unittest.TestCase):
    def test_loaded_by_name_only(self):
        # an of: alias would load it for the stock tree's /scene-frequency node by itself (check-dt-modules.py)
        self.assertNotRegex(SRC, r'(?m)^MODULE_DEVICE_TABLE\(')
        self.assertIn('"sprd,ddr-dvfs"', SRC)

    def test_no_polling(self):
        self.assertRegex(SRC, r'polling_ms = 0;')
        self.assertIn('DEVFREQ_GOV_FLAG_IRQ_DRIVEN', SRC)
        for word in ('msleep', 'schedule_timeout', 'queue_delayed_work', 'timer_setup'):
            self.assertNotIn(word, SRC, word)

    def test_channel_closed_only_while_the_open_waits(self):
        # the firmware answers the OPEN handshake once per boot: an open channel is never closed
        calls = re.findall(r'^\s*smsg_ch_close\(', SRC, re.M)
        self.assertEqual(len(calls), 1, calls)
        self.assertRegex(SRC, r'if \(d->opening\)\s*\n\s*smsg_ch_close\(')
        self.assertIn('smsg_ch_open(SIPC_ID_PM_SYS, SMSG_CH_PM_CTRL, -1)', SRC)

    def test_reply_with_jiffies_left_is_success(self):
        # smsg_recv() returns the jiffies left of a timeout when a message came: only < 0 is an error
        self.assertNotRegex(SRC, r'smsg_(recv|send)\([^;]*DDR_DFS_TIMEOUT\);\s*\n\s*if \(err\)')

    def test_built_after_the_modem_stack(self):
        build = (TOP / 'upstream/build-modules.sh').read_text()
        mods = re.search(r'mods=\$\{\*:-([^}]*)\}', build).group(1).split()
        self.assertLess(mods.index('sprd_modem'), mods.index('sprd_ddr_dfs'))
        order = (TOP / 'upstream/module-order.txt').read_text().split()
        self.assertLess(order.index('sipc-core.ko'), order.index('sprd_ddr_dfs.ko'))


if __name__ == '__main__':
    unittest.main()
