"""SIM selection stays consistent for a boot; no hardware is contacted."""
import json
import re
import subprocess
from pathlib import Path

from helpers import BIN, TOP, ShellTest


class SimSelection(ShellTest):
    def setUp(self):
        super().setUp()
        self.state = self.tmp / 'run/mu300/sim-slot'
        self.choice = self.tmp / 'choice'
        self.choice.write_text('0\n')
        self.stub('uci', '''case "$*" in
  '-q get network.wan.sim_slot') cat "$STUBLOG/choice" ;;
  'set network.wan.sim_slot='*) printf '%s\\n' "${2#*=}" > "$STUBLOG/choice" ;;
  'commit network') : ;;
  *) exit 1 ;;
esac''')

    def sim(self, shell, *args):
        return self.script(shell, BIN / 'mu300-sim', *args, MU300_SIM_ROOT=self.tmp)

    def test_selection_refuses_other_devices(self):
        device = self.tmp / 'mu300-device'
        device.write_text('#!/bin/sh\necho u30air\n')
        device.chmod(0o755)
        for shell in self.each_shell():
            r = self.script(shell, BIN / 'mu300-sim', 'select', 'internal',
                            MU300_SIM_ROOT=self.tmp, MU300_DEVICE_CMD=device)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('F50 only', r.stderr)
            self.assertEqual(self.choice.read_text().strip(), '0')

    def test_common_default_and_json_status_interface(self):
        for shell in self.each_shell():
            self.state.unlink(missing_ok=True)
            self.choice.write_text('0\n')
            r = self.sim(shell, 'default', '2')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.choice.read_text().strip(), '1')
            status = self.sim(shell, 'status', '--json')
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertEqual(json.loads(status.stdout), {
                'ok': 1, 'active': 1, 'default': 2, 'hot': 0,
                'available': 0, 'result': 'reboot_required',
            })
            hot = self.sim(shell, 'hot', '1')
            self.assertNotEqual(hot.returncode, 0)
            self.assertIn('live SIM switching', hot.stderr)

    def test_selection_requires_reboot_and_is_idempotent(self):
        for shell in self.each_shell():
            self.state.unlink(missing_ok=True)
            self.choice.write_text('0\n')
            self.assertEqual(self.sim(shell, 'active').stdout.strip(), '0')
            r = self.sim(shell, 'select', 'internal')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('until reboot', r.stdout)
            self.assertEqual(self.sim(shell, 'configured').stdout.strip(), '1')
            self.assertEqual(self.sim(shell, 'active').stdout.strip(), '0')
            self.state.unlink()  # /run is cleared by a reboot
            self.assertEqual(self.sim(shell, 'active').stdout.strip(), '1')
            self.assertEqual(self.sim(shell, 'select', 'external').returncode, 0)
            self.assertEqual(self.sim(shell, 'active').stdout.strip(), '1')
            self.state.unlink()
            self.assertEqual(self.sim(shell, 'active').stdout.strip(), '0')

    def test_invalid_selection_never_writes_or_executes(self):
        for shell in self.each_shell():
            for bad in ['2', '-1', '1;touch injected', '$(touch injected)', '1\n0']:
                self.choice.write_text('0\n')
                r = self.sim(shell, 'select', bad)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(self.choice.read_text().strip(), '0')
                self.state.unlink(missing_ok=True)
                self.choice.write_text(bad)
                self.assertNotEqual(self.sim(shell, 'active').returncode, 0)
                self.assertFalse(self.state.exists())

    def test_concurrent_first_readers_publish_one_complete_slot(self):
        for shell in self.each_shell():
            self.state.unlink(missing_ok=True)
            self.choice.write_text('1\n')
            ps = [subprocess.Popen(shell + [str(BIN / 'mu300-sim'), 'active'],
                                   env=self.env(MU300_SIM_ROOT=self.tmp), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True) for _ in range(8)]
            for p in ps:
                out, err = p.communicate(timeout=15)
                self.assertEqual(p.returncode, 0, err)
                self.assertEqual(out.strip(), '1')

    def test_procd_channels_and_dashboard_follow_active_slot(self):
        helper = self.tmp / 'mu300-sim'
        helper.write_text('#!/bin/sh\ncat "$STUBLOG/choice"\n')
        helper.chmod(0o755)
        for shell in self.each_shell():
            for slot in (0, 1):
                self.choice.write_text(str(slot))
                for source, dashboard in [
                    (TOP / 'openwrt/overlay/etc/init.d/mu300-atd', False),
                    (TOP / 'openwrt/luci-overlay/etc/init.d/mu300-atd-dash', True),
                ]:
                    s = source.read_text().replace('/opt/mu300/bin/mu300-sim', str(helper))
                    code = 'procd_open_instance() { echo instance "$@"; }; procd_set_param() { echo param "$@"; }; procd_close_instance() { :; };\n' + s + '\nstart_service\n'
                    r = self.sh(shell, code)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    if dashboard:
                        if slot == 1: self.assertNotIn('instance ', r.stdout)
                        else:
                            self.assertIn('/dev/stty_nr6', r.stdout)
                            self.assertIn('/dev/stty_nr7', r.stdout)
                    else:
                        self.assertIn('/dev/stty_nr' + str(slot * 3 + 1), r.stdout)
                        self.assertIn('MU300_AT_DEV=/dev/stty_nr' + str(slot * 3 + 2), r.stdout)

    def test_data_route_command_failure_stops_slot1_only(self):
        s = (BIN / 'mobile-data').read_text()
        start = s.index('    if [ "$SIM_SLOT" = 1 ]; then', s.index('mark dial-addr-ok'))
        block = s[start:s.index('    prefix=$(mask2prefix', start)]
        for shell in self.each_shell():
            for slot, reply, rc in [(0, 'ERROR', 0), (1, 'OK', 0), (1, 'ERROR', 1)]:
                calls = self.tmp / 'calls'; calls.write_text('')
                code = 'at() { echo "$1" >> "$STUBLOG/calls"; echo "$REPLY"; }; dial() {\n' + block + '\necho connected; }; dial'
                r = self.sh(shell, code, SIM_SLOT=slot, REPLY=reply)
                self.assertEqual(r.returncode, rc, r.stderr)
                self.assertEqual(calls.read_text().splitlines(), [] if slot == 0 else ['AT+SPSWDATA'])
                if rc: self.assertNotIn('connected', r.stdout)

    def test_missing_neighbours_do_not_abort_dashboard(self):
        import shutil
        node = shutil.which('node')
        if not node: self.skipTest('node unavailable')
        js = (TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js').read_text()
        start = js.index('function neighborRows(')
        body = js[start:js.index('\n}', start) + 2]
        code = '''const _=s=>s, esc=s=>s, qLevel=()=>'', qCol=()=>'';
''' + body + '''
for (const neigh of [null, [null], {}, [null, {rat:'nr', band:41, pci:315, arfcn:504990, rsrp:-85}]]) {
  if (!neighborRows({neigh}, []).includes('<tr>')) throw Error('missing row');
}
'''
        r = subprocess.run([node, '-e', code], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_empty_lte_neighbours_are_not_null_entries(self):
        s = (TOP / 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/cell').read_text()
        start = s.index('LN=$(sp_fragment ltenb')
        block = s[start:s.index('\nCOPSJ=', start)]
        for shell in self.each_shell():
            r = self.sh(shell, 'sp_fragment() { echo null; }; nr_neighbours() { :; };\n' + block + '\necho "$NEIGH"')
            value = json.loads(r.stdout)
            self.assertIn(value, [None, []])

    def test_profile_fields_survive_changing_selector(self):
        # LuCI removes hidden options unless retain is set: changing slots must not erase an APN.
        s = (TOP / 'openwrt/overlay/www/luci-static/resources/protocol/mu300cell.js').read_text()
        for field in ['apn', 'apn_internal', 'pdptype', 'pdptype_internal']:
            block = re.search(r"o = s.taboption\([^;]*'" + field + r"'[^;]*;([\s\S]*?)(?=\n\s*o =|\n\s*}\n)", s)
            self.assertIsNotNone(block, field)
            self.assertIn('o.retain = true', block[1], field)

    def test_ipv6_prefix_comes_from_the_selected_card_only(self):
        source = TOP / 'openwrt/luci-overlay/opt/mu300/bin/ndp-learn'
        helper = self.tmp / 'mu300-sim'
        helper.write_text('#!/bin/sh\necho 1\n')
        helper.chmod(0o755)
        script = self.tmp / 'ndp-learn'
        script.write_text(source.read_text().replace('/opt/mu300/bin/mu300-sim', str(helper)))
        addresses = self.tmp / 'if_inet6'
        addresses.write_text('24090001000200030000000000000001 05 40 00 00 sipa_eth0\n'
                             '24090004000500060000000000000001 0d 40 00 00 sipa_eth8\n')
        for shell in self.each_shell():
            r = self.script(shell, script, '--prefix', MU300_IF_INET6=addresses)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.strip(), '2409:4:5:6::/64')
