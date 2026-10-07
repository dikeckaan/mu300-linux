"""openwrt/overlay/lib/netifd/proto/mu300cell.sh: the netifd protocol handler, sourced with the netifd functions stubbed.

The script is sourced with INCLUDE_ONLY=1 (it then defines only the proto_mu300cell_* functions). The netifd
functions, `ip`, `mobile-data`, `mu300-led`, `sleep`, `logger` and `fw4` record their arguments in $STUBLOG/calls.
The script's absolute paths (/opt/mu300/bin, /tmp, /proc/sys) are pointed into the scratch directory in a copy;
sipa_eth0's disable_ipv6 and accept_ra are files there, so what the script writes into them is checked.

Relay mode (K35-K37, K30, D9; openwrt-luci only) has its files in openwrt/luci-overlay: the event monitor
mu300cell-v6.sh, ndp-learn, init.d/mu300-ndp and the first-boot settings in 91-mu300-luci (class Relay).
"""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import BIN, TOP, ShellTest

PROTO = TOP / 'openwrt' / 'overlay' / 'lib' / 'netifd' / 'proto' / 'mu300cell.sh'
LUCI = TOP / 'openwrt' / 'luci-overlay'
MONITOR = LUCI / 'lib' / 'netifd' / 'proto' / 'mu300cell-v6.sh'
NDP_LEARN = LUCI / 'opt' / 'mu300' / 'bin' / 'ndp-learn'
NDP_INIT = LUCI / 'etc' / 'init.d' / 'mu300-ndp'
LUCI_DEFAULTS = LUCI / 'etc' / 'uci-defaults' / '91-mu300-luci'

HARNESS = r'''
rec() { printf '%s\n' "$*" >> "$STUBLOG/calls"; }
proto_init_update() { rec proto_init_update "$@"; }
proto_add_ipv4_address() { rec proto_add_ipv4_address "$@"; }
proto_add_ipv4_route() { rec proto_add_ipv4_route "$@"; }
proto_add_dns_server() { rec proto_add_dns_server "$@"; }
proto_send_update() { rec proto_send_update "$@"; }
proto_kill_command() { rec proto_kill_command "$@"; }
proto_run_command() { rec proto_run_command "$@"; }
proto_config_add_string() { rec proto_config_add_string "$@"; }
proto_config_add_boolean() { rec proto_config_add_boolean "$@"; }
proto_config_add_array() { rec proto_config_add_array "$@"; }
proto_notify_error() { rec proto_notify_error "$@"; }
proto_block_restart() { rec proto_block_restart "$@"; }
proto_setup_failed() { rec proto_setup_failed "$@"; }
proto_add_dynamic_defaults() { rec proto_add_dynamic_defaults; }
json_get_vars() { apn=$T_APN; pdptype=$T_PDPTYPE; peerdns=$T_PEERDNS; ipv6=$T_IPV6; }
json_init() { rec json_init; }
json_add_string() { rec json_add_string "$@"; }
json_add_boolean() { rec json_add_boolean "$@"; }
json_close_object() { rec json_close_object; }
json_dump() { echo '{}'; }
ubus() { rec ubus "$@"; }
INCLUDE_ONLY=1
. "$SCRIPT"
'''

# What mobile-data's netifd path prints (MU300_NETIFD=1 mobile-data up): six KEY=VALUE lines, in this order.
UP_V4 = 'IFACE=sipa_eth0\\nIP=10.20.30.40\\nPREFIX=30\\nDNS1=1.1.1.1\\nDNS2=8.8.8.8\\nIID6=\\n'
UP_V6 = 'IFACE=sipa_eth0\\nIP=10.20.30.40\\nPREFIX=30\\nDNS1=1.1.1.1\\nDNS2=\\nIID6=0000:0000:1234:5678\\n'


class Mu300cell(ShellTest):
    def setUp(self):
        super().setUp()
        bindir = self.tmp / 'bin'
        bindir.mkdir()
        self.conf = self.tmp / 'proc' / 'net' / 'ipv6' / 'conf' / 'sipa_eth0'
        self.conf.mkdir(parents=True)
        text = PROTO.read_text()
        text = text.replace('/opt/mu300/bin', str(bindir)).replace('/tmp/mu300cell.err', str(self.tmp / 'err')) \
                   .replace('/proc/sys', str(self.tmp / 'proc'))
        self.script_copy = self.tmp / 'mu300cell.sh'
        self.script_copy.write_text(text)
        self.stub('sleep', 'echo "sleep $*" >> "$STUBLOG/calls"')
        self.stub('logger', 'echo "logger $*" >> "$STUBLOG/calls"')
        self.stub('fw4', 'exit 1')
        # ip: records; `-4 -o addr show` lists the global v4 addresses the carrier "left behind" ($T_LEFT);
        # `-4 addr replace` fails when $T_NO_REPLACE is set (an ip without it).
        self.stub('ip', '''echo "ip $*" >> "$STUBLOG/calls"
case "$*" in
  "-4 -o addr show dev "*) for a in $T_LEFT; do echo "2: sipa_eth0    inet $a scope global sipa_eth0"; done ;;
  "-4 addr replace "*) [ -z "$T_NO_REPLACE" ] || exit 2 ;;
esac
exit 0''')
        self.mobile = bindir / 'mobile-data'
        self.set_mobile('up', 0)
        for n, body in (('mu300-led', 'echo "mu300-led $*" >> "$STUBLOG/calls"'),):
            p = bindir / n
            p.write_text('#!/bin/sh\n' + body + '\n')
            p.chmod(0o755)

    def set_mobile(self, out, rc, err=''):
        self.mobile.write_text('#!/bin/sh\necho "mobile-data $* env:$MU300_NETIFD:$MU300_PDP_TYPE:$MU300_IPV6" >> "$STUBLOG/calls"\n'
                               f'[ "$1" = up ] || exit 0\nprintf \'{out}\'\necho \'{err}\' >&2\nexit {rc}\n')
        self.mobile.chmod(0o755)

    def run_proto(self, shell, func, out=UP_V4, rc=0, err='', ok=0, **env):
        self.set_mobile(out, rc, err)
        (self.tmp / 'calls').write_text('')
        for k in ('disable_ipv6', 'accept_ra'):
            (self.conf / k).write_text('-\n')
        e = dict(T_APN='internet', T_PDPTYPE='IP', T_PEERDNS='1', T_IPV6='', T_LEFT='', T_NO_REPLACE='',
                 SCRIPT=self.script_copy)
        e.update(env)
        # sleep as a function too: busybox ash runs its own sleep applet without looking at PATH
        r = self.sh(shell, 'sleep() { echo "sleep $*" >> "$STUBLOG/calls"; }\n' + HARNESS + f'{func} wan\n', **e)
        self.assertEqual(r.returncode, ok, r.stderr)
        return (self.tmp / 'calls').read_text().splitlines()

    def test_setup_update_is_external(self):
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup')
            self.assertIn('proto_init_update sipa_eth0 1 1', calls)
            self.assertIn('proto_add_ipv4_address 10.20.30.40 30', calls)
            self.assertIn('proto_send_update wan', calls)
            self.assertIn('mobile-data up internet env:1:IP:', calls)

    def test_setup_installs_v4_address_and_route_itself(self):
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup', T_LEFT='9.9.9.9/32 10.20.30.40/30 10.1.1.1/24')
            self.assertIn('ip -4 addr replace 10.20.30.40/30 dev sipa_eth0', calls)
            self.assertIn('ip -4 addr del 9.9.9.9/32 dev sipa_eth0', calls)
            self.assertIn('ip -4 addr del 10.1.1.1/24 dev sipa_eth0', calls)
            self.assertNotIn('ip -4 addr del 10.20.30.40/30 dev sipa_eth0', calls)
            self.assertIn('ip -4 route replace default dev sipa_eth0', calls)
            # installed before netifd is told about it
            self.assertLess(calls.index('ip -4 addr replace 10.20.30.40/30 dev sipa_eth0'),
                            calls.index('proto_send_update wan'))
            # R34: and once more after the leftovers are gone: a leftover primary in the new address's subnet takes
            # its secondary (the new address) with it when it is deleted
            last_del = max(i for i, c in enumerate(calls) if c.startswith('ip -4 addr del '))
            again = [i for i, c in enumerate(calls) if c == 'ip -4 addr replace 10.20.30.40/30 dev sipa_eth0']
            self.assertGreater(again[-1], last_del, calls)
            self.assertLess(again[-1], calls.index('proto_send_update wan'))

    def test_setup_adds_when_replace_fails(self):
        """R34: an `ip` that refuses `addr replace` still gets the address, by `addr add`."""
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup', T_NO_REPLACE='1')
            self.assertIn('ip -4 addr add 10.20.30.40/30 dev sipa_eth0', calls)
            self.assertLess(calls.index('ip -4 addr add 10.20.30.40/30 dev sipa_eth0'),
                            calls.index('proto_send_update wan'))

    def test_v4_bearer_switches_ipv6_off_after_the_update(self):
        """R34: an IPv4-only bearer gets disable_ipv6 1 (FINDINGS 13f), written after proto_send_update."""
        for shell in self.each_shell():
            self.run_proto(shell, 'proto_mu300cell_setup')
            self.assertEqual((self.conf / 'disable_ipv6').read_text().strip(), '1', shell)
            self.assertEqual((self.conf / 'accept_ra').read_text().strip(), '-', shell)

    def test_setup_flushes_v6_first(self):
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup')
            a = calls.index('ip -6 addr flush dev sipa_eth0 scope global')
            r = calls.index('ip -6 route flush dev sipa_eth0')
            self.assertLess(max(a, r), calls.index('proto_send_update wan'))

    def test_teardown(self):
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_teardown')
            self.assertEqual(calls[0], 'proto_kill_command wan')
            self.assertEqual(calls[1].split(' env:')[0], 'mobile-data down')
            for c in ('ip -4 addr flush dev sipa_eth0 scope global', 'ip -4 route del default dev sipa_eth0',
                      'ip -6 addr flush dev sipa_eth0 scope global', 'ip -6 route flush dev sipa_eth0'):
                self.assertIn(c, calls[2:])

    def test_attach_failure_still_sleeps_20(self):
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup', out='', rc=1, err='no carrier', ok=1)
            self.assertIn('proto_notify_error wan ATTACH_FAILED', calls)
            self.assertIn('sleep 20', calls)
            self.assertLess(calls.index('sleep 20'), calls.index('proto_setup_failed wan'))
            self.assertFalse(any(c.startswith('proto_send_update') for c in calls))

    def test_no_modem_blocks_restart(self):
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup', out='', rc=3, err='no modem', ok=1)
            self.assertIn('proto_notify_error wan NO_MODEM', calls)
            self.assertIn('proto_block_restart wan', calls)
            self.assertNotIn('sleep 20', calls)

    def test_ipv6_bearer_still_adds_extendprefix_interface(self):
        """Without ipv6 'relay' (plain OpenWrt, or the option unset or 'extend'): today's RFC 7278 design, no monitor."""
        for ipv6 in ('', 'extend'):
            for shell in self.each_shell():
                calls = self.run_proto(shell, 'proto_mu300cell_setup', out=UP_V6, T_PDPTYPE='IPV4V6', T_IPV6=ipv6)
                self.assertIn('ip -6 addr add fe80::0000:0000:1234:5678/64 dev sipa_eth0', calls)
                self.assertIn('json_add_string name wan_6', calls)
                self.assertIn('json_add_boolean extendprefix 1', calls)
                self.assertIn('proto_add_dynamic_defaults', calls)
                self.assertTrue(any(c.startswith('ubus call network add_dynamic') for c in calls))
                # the link-local is added after the flush
                self.assertLess(calls.index('ip -6 addr flush dev sipa_eth0 scope global'),
                                calls.index('ip -6 addr add fe80::0000:0000:1234:5678/64 dev sipa_eth0'))
                self.assertFalse([c for c in calls if c.startswith('proto_run_command')], calls)
                self.assertEqual((self.conf / 'accept_ra').read_text().strip(), '-', shell)

    def test_config_has_the_ipv6_option_and_renew(self):
        """K35: `option ipv6` (relay / extend) is a protocol option, and netifd may ask for a renew."""
        for shell in self.each_shell():
            (self.tmp / 'calls').write_text('')
            r = self.sh(shell, HARNESS + 'proto_mu300cell_init_config; echo "renew=$renew_handler"',
                        T_APN='', T_PDPTYPE='', T_PEERDNS='', T_IPV6='', SCRIPT=self.script_copy)
            self.assertIn('renew=1', r.stdout, r.stderr)
            self.assertIn('proto_config_add_string ipv6', (self.tmp / 'calls').read_text().splitlines())

    def test_relay_starts_the_monitor(self):
        """K35, K36, K64: ipv6 'relay' with a dual-stack context. mobile-data is told (MU300_IPV6=relay), sipa_eth0
        takes RAs (disable_ipv6 0, accept_ra 2, after the 1->0 and 0->2 cycles), and after the first update the event
        monitor runs as netifd's protocol task with the fork's arguments. No extendprefix interface: odhcpd relays."""
        for out in (UP_V4, UP_V6):          # the carrier filled +CGCONTRDP's v6 address, or did not
            for shell in self.each_shell():
                calls = self.run_proto(shell, 'proto_mu300cell_setup', out=out, T_PDPTYPE='IPV4V6', T_IPV6='relay')
                self.assertIn('mobile-data up internet env:1:IPV4V6:relay', calls)
                dns2 = '8.8.8.8' if out == UP_V4 else ''
                run = ('proto_run_command wan /lib/netifd/proto/mu300cell-v6.sh wan sipa_eth0 10.20.30.40 30 1.1.1.1 '
                       f'{dns2} 1')
                self.assertIn(run, calls)
                self.assertLess(calls.index('proto_send_update wan'), calls.index(run))
                self.assertEqual((self.conf / 'disable_ipv6').read_text().strip(), '0', shell)
                self.assertEqual((self.conf / 'accept_ra').read_text().strip(), '2', shell)
                self.assertFalse([c for c in calls if 'extendprefix' in c or c.startswith('ubus')], calls)
                self.assertTrue([c for c in calls if c.startswith('proto_init_update sipa_eth0 1 1')], calls)
        # the 1->0 and 0->2 cycles, in that order, after the v6 flush and before the first update
        text = PROTO.read_text()
        body = text[text.index('proto_mu300cell_setup() {'):text.index('proto_mu300cell_renew() {')]
        cycle = [body.index(s) for s in ('ip -6 route flush dev "$ifname"', 'echo 1 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"',
                                         'echo 0 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"',
                                         'echo 0 > "/proc/sys/net/ipv6/conf/$ifname/accept_ra"',
                                         'echo 2 > "/proc/sys/net/ipv6/conf/$ifname/accept_ra"', 'proto_send_update')]
        self.assertEqual(cycle, sorted(cycle))

    def test_relay_on_an_ipv4_context_is_ipv4(self):
        """ipv6 'relay' with pdptype IP: no monitor, no RAs, IPv6 off on the bearer as before."""
        for shell in self.each_shell():
            calls = self.run_proto(shell, 'proto_mu300cell_setup', T_PDPTYPE='IP', T_IPV6='relay')
            self.assertFalse([c for c in calls if c.startswith('proto_run_command')], calls)
            self.assertEqual((self.conf / 'disable_ipv6').read_text().strip(), '1', shell)
            self.assertEqual((self.conf / 'accept_ra').read_text().strip(), '-', shell)

    def test_renew_signals_the_monitor(self):
        """K35: renew sends SIGUSR1 to the protocol task (the monitor re-reads the bearer); nothing else. A shell
        that cannot name the signal (dash) sends nothing; netifd runs busybox ash, which can."""
        for shell in self.each_shell():
            num = subprocess.run(shell + ['-c', 'kill -l SIGUSR1'], capture_output=True, text=True).stdout.strip()
            calls = self.run_proto(shell, 'proto_mu300cell_renew')
            self.assertEqual(calls, [f'proto_kill_command wan {num}'] if num else [], shell)


class Relay(ShellTest):
    """The luci-overlay half of relay mode: mu300cell-v6.sh, ndp-learn, init.d/mu300-ndp, 91-mu300-luci."""

    def test_reap_kills_the_old_monitor_without_a_file(self):
        """Final review minor 6: reap() kills the processes a previous monitor left (matched in a ps snapshot) and
        writes no file: there was a fixed /tmp/mu300cell-reap.ps written by root."""
        text = MONITOR.read_text()
        m = re.search(r'\nreap\(\) \{\n.*?\n\}\n', text, re.S)
        self.assertTrue(m)
        self.assertNotIn('/tmp/', m.group(0))
        for shell in self.each_shell():
            old = subprocess.Popen(['sleep', '30'])
            other = subprocess.Popen(['sleep', '30'])
            try:
                self.stub('ps', f'''printf '%s\\n' '  PID USER       VSZ STAT COMMAND' \\
  ' {old.pid} root      1234 S    /bin/sh /lib/netifd/proto/mu300cell-v6.sh wan sipa_eth0 10.0.0.1' \\
  ' {other.pid} root      1234 S    /bin/sh /lib/netifd/proto/mu300cell-v6.sh wwan sipa_eth1 10.0.0.1' ''')
                before = sorted(self.tmp.rglob('*'))
                r = self.sh(shell, m.group(0) + 'cd "$STUBLOG" && reap "mu300cell-v6.sh wan sipa_eth0"')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(sorted(self.tmp.rglob('*')), before)
                self.assertIsNotNone(old.wait(timeout=5))
                self.assertIsNone(other.poll())
            finally:
                for p in (old, other):
                    if p.poll() is None:
                        p.kill()
                    p.wait()

    def test_monitor_probe_exits_at_once(self):
        """netifd probes every *.sh in its proto directory with '<script> "" dump'; the monitor is not a protocol and
        must exit at once (it would otherwise block the scan, or wait on a fifo for ever). /lib/functions.sh does not
        exist here, so getting past the probe check would fail."""
        for shell in self.each_shell():
            for args in (['', 'dump'], ['dump']):
                r = subprocess.run(shell + [str(MONITOR)] + args, capture_output=True, text=True, timeout=5,
                                   env=self.env())
                self.assertEqual((r.returncode, r.stdout, r.stderr), (0, '', ''), (shell, args))

    def test_monitor_once_reports_external(self):
        """K36: one report (--once): the v4 address and route, the RA's address with its lifetimes, the RA default
        route, the DNS servers - all address-external, as setup sent them."""
        text = MONITOR.read_text()
        harness = self.tmp / 'netifd.sh'
        harness.write_text('''rec() { printf '%s\\n' "$*" >> "$STUBLOG/calls"; }
proto_init_update() { rec proto_init_update "$@"; }
proto_add_ipv4_address() { rec proto_add_ipv4_address "$@"; }
proto_add_ipv4_route() { rec proto_add_ipv4_route "$@"; }
proto_add_ipv6_address() { rec proto_add_ipv6_address "$@"; }
proto_add_ipv6_route() { rec proto_add_ipv6_route "$@"; }
proto_add_dns_server() { rec proto_add_dns_server "$@"; }
proto_send_update() { rec proto_send_update "$@"; }
''')
        text = text.replace('. /lib/functions.sh\n', '').replace('. /lib/netifd/netifd-proto.sh', f'. "{harness}"')
        copy = self.tmp / 'mu300cell-v6.sh'
        copy.write_text(text)
        self.stub('ip', '''case "$*" in
  "-6 addr show dev sipa_eth0 scope global") printf '%s\\n' \\
    '5: sipa_eth0: <POINTOPOINT,UP,LOWER_UP> mtu 1500 state UNKNOWN qlen 1000' \\
    '    inet6 2001:db8:1:2:a:b:c:d/64 scope global dynamic mngtmpaddr' \\
    '       valid_lft 7100sec preferred_lft 3500sec' ;;
  "-6 route show dev sipa_eth0 default proto ra") echo 'default via fe80::1 proto ra metric 1024 expires 1700sec hoplimit 64 pref medium' ;;
esac''')
        for shell in self.each_shell():
            (self.tmp / 'calls').write_text('')
            r = subprocess.run(shell + [str(copy), 'wan', 'sipa_eth0', '10.20.30.40', '30', '1.1.1.1', '8.8.8.8', '1',
                                        '--once'], capture_output=True, text=True, timeout=10, env=self.env())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.tmp / 'calls').read_text().splitlines(), [
                'proto_init_update sipa_eth0 1 1', 'proto_add_ipv4_address 10.20.30.40 30',
                'proto_add_ipv4_route 0.0.0.0 0', 'proto_add_ipv6_address 2001:db8:1:2:a:b:c:d 64 3500 7100',
                'proto_add_ipv6_route :: 0 fe80::1 4096 1700', 'proto_add_dns_server 1.1.1.1',
                'proto_add_dns_server 8.8.8.8', 'proto_send_update wan'], shell)

    def test_ndp_learn_prefix(self):
        """K37: the bearer's /64 from /proc/net/if_inet6 (fixed-width hex, so compressed hextets cannot confuse it):
        only sipa_eth0's global (scope 00) address counts, never link-local or another interface."""
        fake = self.tmp / 'if_inet6'
        fake.write_text('fe800000000000000000000000000001 05 40 20 80 sipa_eth0\n'
                        '2a0200000db800010000000000000001 03 40 00 80    br-lan\n'
                        '240e0388000a12340000000000000abc 05 40 00 00 sipa_eth0\n')
        for shell in self.each_shell():
            r = self.script(shell, NDP_LEARN, '--prefix', MU300_IF_INET6=fake)
            self.assertEqual((r.returncode, r.stdout), (0, '240e:388:a:1234::/64\n'), (shell, r.stderr))
        fake.write_text('fe800000000000000000000000000001 05 40 20 80 sipa_eth0\n')
        for shell in self.each_shell():
            r = self.script(shell, NDP_LEARN, '--prefix', MU300_IF_INET6=fake)
            self.assertEqual((r.returncode, r.stdout), (0, ''), (shell, r.stderr))

    # Security review: ndp-learn takes nothing from the LAN. ip is a stub that logs every call to $STUBLOG/ipcalls;
    # the neighbour table on br-lan and the host routes on sipa_eth0 are hostile ($T_NEIGH, $T_WANROUTES).
    HOSTILE_NEIGH = ('2001:4860:4860::8888 lladdr 02:00:00:00:00:01 REACHABLE\n'      # off-prefix (a DNS server)
                     '240e:388:a:1234::5 lladdr 02:00:00:00:00:02 REACHABLE\n'        # inside the prefix
                     '240e:388:a:1234::1 lladdr 02:00:00:00:00:03 REACHABLE\n'        # the router's own address
                     '240e:388:a:1234:: lladdr 02:00:00:00:00:04 STALE\n'             # subnet-router anycast
                     'fe80::1 lladdr 02:00:00:00:00:05 REACHABLE\n'
                     'ff02::1 lladdr 33:33:00:00:00:01 NOARP\n'
                     '-6 lladdr 02:00:00:00:00:06 REACHABLE\n'
                     '2a00::1;reboot lladdr 02:00:00:00:00:07 REACHABLE\n')
    HOSTILE_WAN = ('240e:388:a:1234::5 proto static metric 1024\n'                   # odhcpd's stray host route
                   '2001:4860:4860::8888 proto static metric 1024\n'                 # off-prefix: not ours to delete
                   '240e:388:a:1234::6;reboot proto static\n'
                   '240e:388:a:1234:-x proto static\n'
                   '240e:388:a:1234::/64 proto ra metric 256\n'
                   'default via fe80::1 proto ra metric 1024\n')

    def ndp_once(self, shell, neigh, wan):
        fake = self.tmp / 'if_inet6'
        fake.write_text('240e0388000a12340000000000000001 05 40 00 00 sipa_eth0\n')
        (self.tmp / 'neigh').write_text(neigh)
        (self.tmp / 'wan').write_text(wan)
        (self.tmp / 'ipcalls').write_text('')
        self.stub('ip', '''echo "ip $*" >> "$STUBLOG/ipcalls"
case "$*" in
  "-6 neigh show"*) cat "$STUBLOG/neigh" ;;
  "-6 route show dev sipa_eth0") cat "$STUBLOG/wan" ;;
esac
exit 0''')
        self.stub('logger', 'exit 0')
        r = self.script(shell, NDP_LEARN, '--once', MU300_IF_INET6=fake)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.tmp / 'ipcalls').read_text().splitlines()

    def test_ndp_learn_takes_nothing_from_the_lan(self):
        """Security review: a LAN client's spoofed neighbour advertisements must not make the router route any
        address (off-prefix, its own, link-local, multicast, anycast, malformed) to br-lan: ndp-learn does not read
        the neighbour table at all, adds no host route and no proxy entry. The only route it installs is the
        bearer's /64 on br-lan, derived from the kernel's own address."""
        for shell in self.each_shell():
            calls = self.ndp_once(shell, self.HOSTILE_NEIGH, '')
            self.assertIn('ip -6 route replace 240e:388:a:1234::/64 dev br-lan metric 128', calls)
            self.assertFalse([c for c in calls if 'neigh' in c], calls)
            adds = [c for c in calls if ' add ' in f'{c} ' or c.startswith('ip -6 route replace')]
            self.assertEqual(set(adds), {'ip -6 route replace 240e:388:a:1234::/64 dev br-lan metric 128'}, calls)

    def test_ndp_learn_lan_route_wins_over_the_bearer(self):
        """Review I2: the carrier's RA puts the same /64 on sipa_eth0 at metric 256; the br-lan /64 must have a
        lower metric, or NAT66 replies to clients leave by the bearer. A re-run replaces it in place (one route per
        round), and the metric-1024 route an earlier ndp-learn installed is removed, never added."""
        for shell in self.each_shell():
            for _ in range(2):
                calls = self.ndp_once(shell, '', self.HOSTILE_WAN)
                lan = [c for c in calls if 'br-lan' in c and not c.startswith('ip -6 route show')]
                self.assertEqual(lan, ['ip -6 route replace 240e:388:a:1234::/64 dev br-lan metric 128',
                                       'ip -6 route del 240e:388:a:1234::/64 dev br-lan metric 1024'], (shell, calls))
            m = re.search(r'LAN_METRIC=(\d+)', NDP_LEARN.read_text())
            self.assertTrue(m and int(m.group(1)) < 256, 'the br-lan /64 must beat the RA route (metric 256)')

    def test_ndp_learn_removes_only_valid_in_prefix_wan_host_routes(self):
        """Host routes inside the /64 on sipa_eth0 (odhcpd's, which override the LAN /64) are removed; an
        off-prefix one, the /64, the default and anything that is not strictly an IPv6 address are left alone and
        never reach ip's arguments."""
        for shell in self.each_shell():
            calls = self.ndp_once(shell, '', self.HOSTILE_WAN)
            dels = [c for c in calls if ' del ' in c and 'sipa_eth0' in c]
            self.assertEqual(dels, ['ip -6 route del 240e:388:a:1234::5/128 dev sipa_eth0'], calls)
            self.assertFalse([c for c in calls if 'reboot' in c or ' -x' in c], calls)

    def test_ndp_learn_never_routes_a_bad_prefix(self):
        """A bearer address that is not global unicast (multicast, link-local) gives no prefix, so no route."""
        fake = self.tmp / 'if_inet6'
        for line in ('ff020000000000000000000000000001 05 40 00 00 sipa_eth0\n',
                     'fe800000000000000000000000000001 05 40 00 00 sipa_eth0\n',
                     'fd661126795600000000000000000001 05 40 00 00 sipa_eth0\n',     # ULA
                     '00000000000000000000ffff0a000001 05 40 00 00 sipa_eth0\n',     # v4-mapped
                     '240e0388000a12340000000000000001 05 40 00 00 sipa_eth0x\n',    # another interface
                     '240e0388000a1234000000000000001 05 40 00 00 sipa_eth0\n'):     # 31 digits
            fake.write_text(line)
            for shell in self.each_shell():
                r = self.script(shell, NDP_LEARN, '--prefix', MU300_IF_INET6=fake)
                self.assertEqual((r.returncode, r.stdout), (0, ''), (shell, line))

    def init_start(self, shell, ipv6):
        self.stub('uci', f'[ "$*" = "-q get network.wan.ipv6" ] && {{ [ -n "{ipv6}" ] && echo "{ipv6}"; exit 0; }}\n'
                         'exit 1')
        harness = ('rec() { printf \'%s\\n\' "$*" >> "$STUBLOG/calls"; }\n'
                   'procd_open_instance() { rec procd_open_instance "$@"; }\n'
                   'procd_set_param() { rec procd_set_param "$@"; }\n'
                   'procd_close_instance() { rec procd_close_instance "$@"; }\n'
                   f'. "{NDP_INIT}"\nstart_service\n')
        (self.tmp / 'calls').write_text('')
        r = self.sh(shell, harness)
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.tmp / 'calls').read_text().splitlines()

    def test_ndp_init_only_in_relay_mode(self):
        """K37: init.d/mu300-ndp starts ndp-learn only when network.wan.ipv6 is relay."""
        for shell in self.each_shell():
            for ipv6 in ('', 'extend'):
                self.assertEqual(self.init_start(shell, ipv6), [], (shell, ipv6))
            calls = self.init_start(shell, 'relay')
            self.assertIn('procd_open_instance', calls)
            self.assertIn('procd_set_param command /bin/sh /opt/mu300/bin/ndp-learn', calls)
        text = NDP_INIT.read_text()
        self.assertTrue(text.startswith('#!/bin/sh /etc/rc.common\n'))
        self.assertRegex(text, r'(?m)^START=\d+$')
        self.assertIn('USE_PROCD=1', text)

    def uci_db(self):
        """A uci stand-in over the flat file uci.db (lines k='v'): the file."""
        db = self.tmp / 'uci.db'
        db.write_text("firewall.@zone[0].name='lan'\nfirewall.@zone[1].name='wan'\n")
        # uci stand-in: "set k=v", "get k", "show [cfg]", "commit", "batch" (stdin, lines of set/delete)
        self.stub('uci', r'''db=$STUBLOG/uci.db
[ "$1" = -q ] && shift
setkv() { k=${1%%=*}; v=${1#*=}; v=${v#\'}; v=${v%\'}; awk -v k="$k=" 'index($0, k) != 1' "$db" > "$db.n"; echo "$k='$v'" >> "$db.n"; mv "$db.n" "$db"; }
case $1 in
  set) setkv "$2" ;;
  get) sed -n "s/^$2='\(.*\)'$/\1/p" "$db" | grep . ;;
  show) grep "^$2" "$db" ;;
  delete) grep -v "^$2[=.]" "$db" > "$db.n"; mv "$db.n" "$db" ;;
  commit) echo "commit $2" >> "$STUBLOG/commits" ;;
  batch) while read -r op kv; do case $op in set) setkv "$kv" ;; delete) grep -v "^$kv[=.]" "$db" > "$db.n"; mv "$db.n" "$db" ;; esac; done ;;
esac
exit 0''')
        return db

    def test_first_boot_selects_relay(self):
        """K30, D9: 91-mu300-luci sets ipv6 relay, pdptype IPV4V6 and the fork's RA/DHCPv6 relay and masq6; run twice
        (uci is a stand-in over a flat file), the result is the same. Review I1: no NDP relay on lan or wan (odhcpd's
        relay pins any LAN-spoofed neighbour, even off-prefix, as a /128 to br-lan), and an earlier ndp or
        ndproxy_routing value is removed. Review R38: the ULA OpenWrt generated is kept, never a fixed one."""
        db = self.uci_db()
        want = {
            "network.wan.ipv6": 'relay', "network.wan.pdptype": 'IPV4V6', "network.lan.ip6assign": '60',
            "network.globals.ula_prefix": 'fd12:3456:789a::/48', "dhcp.wan": 'dhcp', "dhcp.wan.interface": 'wan',
            "dhcp.wan.master": '1', "dhcp.wan.ra": 'relay', "dhcp.wan.dhcpv6": 'relay',
            "dhcp.lan.ra": 'relay', "dhcp.lan.dhcpv6": 'relay',
            "firewall.@zone[1].masq6": '1', "luci.main.mediaurlbase": '/luci-static/aurora', "luci.main.lang": 'en'}
        before = ("firewall.@zone[0].name='lan'\nfirewall.@zone[1].name='wan'\n"
                  "network.globals.ula_prefix='fd12:3456:789a::/48'\n"     # OpenWrt's own random ULA
                  "dhcp.lan.ndp='relay'\ndhcp.wan.ndp='hybrid'\n"           # an earlier run's or a user's value
                  "dhcp.lan.ndproxy_routing='1'\ndhcp.wan.ndproxy_routing='1'\n")
        for shell in self.each_shell():
            db.write_text(before)
            states = []
            for _ in range(2):
                r = self.script(shell, LUCI_DEFAULTS)
                self.assertEqual(r.returncode, 0, r.stderr)
                states.append(sorted(db.read_text().splitlines()))   # the stand-in appends what it sets
            self.assertEqual(states[0], states[1], shell)
            got = dict(l.split('=', 1) for l in states[0])
            for k, v in want.items():
                self.assertEqual(got.get(k), f"'{v}'", (shell, k))
            self.assertNotIn('firewall.@zone[0].masq6', got)
            for k in got:
                self.assertNotRegex(k, r'^dhcp\.(lan|wan)\.(ndp|ndproxy_routing)$', (shell, 'NDP relay left on'))
            self.assertEqual(got.get('luci.mu300.defaults'), "'1'", shell)
            commits = set((self.tmp / 'commits').read_text().split())
            self.assertTrue({'network', 'dhcp', 'firewall', 'luci'} <= commits, commits)

    def test_an_update_keeps_the_users_choices_and_still_removes_ndp_relay(self):
        """Final review I3: 91-mu300-luci runs again on the first boot after every update (a fresh rootfs, the kept
        /etc/config). The defaults are a first install's: the PDP type, IPv6 mode, relay settings, masq6, theme and
        language the user set since stay; the NDP relay options are deleted on every run, whoever set them."""
        db = self.uci_db()
        user = {'network.wan.pdptype': 'IP', 'network.wan.ipv6': 'extend', 'network.lan.ip6assign': '64',
                'dhcp.lan.ra': 'server', 'dhcp.lan.dhcpv6': 'server', 'dhcp.wan.master': '0',
                'firewall.@zone[1].masq6': '0', 'luci.main.mediaurlbase': '/luci-static/bootstrap',
                'luci.main.lang': 'tr'}
        for shell in self.each_shell():
            db.write_text("firewall.@zone[0].name='lan'\nfirewall.@zone[1].name='wan'\n")
            r = self.script(shell, LUCI_DEFAULTS)                      # the first install
            self.assertEqual(r.returncode, 0, r.stderr)
            text = db.read_text()
            for k, v in user.items():                                   # the user's choices since
                text = ''.join(l + '\n' for l in text.splitlines() if not l.startswith(k + '=')) + f"{k}='{v}'\n"
            text += "dhcp.lan.ndp='relay'\ndhcp.wan.ndproxy_routing='1'\n"  # NDP relay turned back on
            db.write_text(text)
            r = self.script(shell, LUCI_DEFAULTS)                      # the first boot after an update
            self.assertEqual(r.returncode, 0, r.stderr)
            got = dict(l.split('=', 1) for l in db.read_text().splitlines())
            for k, v in user.items():
                self.assertEqual(got.get(k), f"'{v}'", (shell, k))
            for k in got:
                self.assertNotRegex(k, r'^dhcp\.(lan|wan)\.(ndp|ndproxy_routing)$', (shell, 'NDP relay left on'))



class MobileDataRelay(ShellTest):
    """K64: mobile-data's side of relay mode, sourced (MU300_LIB=1) with bash, /proc/sys/net/ipv6/conf in the scratch
    directory. On the netifd path with MU300_IPV6=relay and a dual-stack context, sipa_eth0 takes the carrier's RA
    (disable_ipv6 0, accept_ra 2) even without an interface identifier; everywhere else nothing changes."""

    def run_relay(self, **env):
        if not shutil.which('bash'):
            self.skipTest('no bash')
        conf = self.tmp / 'conf' / 'sipa_eth0'
        conf.mkdir(parents=True, exist_ok=True)
        for k in ('disable_ipv6', 'accept_ra'):
            (conf / k).write_text('-\n')
        lib = self.tmp / 'mobile-data.lib'
        lib.write_text((BIN / 'mobile-data').read_text().replace('/proc/sys/net/ipv6/conf/', f'{self.tmp}/conf/'))
        e = dict(MU300_NETIFD='', MU300_IPV6='', MU300_PDP_TYPE='')
        e.update(env)
        r = self.sh(['bash'], f'MU300_LIB=1; . "{lib}"\nrc=0; v6_relay_ra || rc=$?; echo "rc=$rc"', **e)
        return r.stdout.strip(), (conf / 'disable_ipv6').read_text().strip(), (conf / 'accept_ra').read_text().strip()

    def test_relay_takes_the_ra(self):
        for pdp in ('IPV4V6', 'IPV6'):
            self.assertEqual(self.run_relay(MU300_NETIFD='1', MU300_IPV6='relay', MU300_PDP_TYPE=pdp),
                             ('rc=0', '0', '2'), pdp)

    def test_not_relay_changes_nothing(self):
        for env in (dict(MU300_NETIFD='1', MU300_IPV6='', MU300_PDP_TYPE='IPV4V6'),        # plain OpenWrt (extend)
                    dict(MU300_NETIFD='1', MU300_IPV6='extend', MU300_PDP_TYPE='IPV4V6'),
                    dict(MU300_NETIFD='1', MU300_IPV6='relay', MU300_PDP_TYPE='IP'),       # an IPv4 context
                    dict(MU300_NETIFD='1', MU300_IPV6='relay', MU300_PDP_TYPE=''),
                    dict(MU300_NETIFD='', MU300_IPV6='relay', MU300_PDP_TYPE='IPV4V6')):   # the systemd path
            self.assertEqual(self.run_relay(**env), ('rc=1', '-', '-'), env)

    def test_relay_replaces_v6_off_on_the_netifd_path_only(self):
        """Relay keeps IPv6 on where the bearer has no interface identifier; otherwise v6_off as before, and the
        systemd path still runs v6_up (test_device_scripts' test_systemd_path_keeps_v6_up)."""
        text = (BIN / 'mobile-data').read_text()
        start = text.index('\nup_locked() {')
        body = text[start:text.index('\ndown() {', start)]
        netifd = body.index('if [ "${MU300_NETIFD:-0}" = 1 ]; then')
        self.assertIn('v6_relay_ra || { [ -n "$iid" ] || v6_off; }', body[:netifd])



if __name__ == '__main__':
    unittest.main()
