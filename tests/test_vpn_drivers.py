"""mu300-vpn's profiles, settings and engine drivers, sourced for their functions (MU300_LIB=1) under every shell.

Store: the store under /etc/mu300/vpn (MU300_VPN_DIR, by default the directory of MU300_VPN_CONF + /vpn), its
settings with their validation, and the migration of a legacy vpn.conf into it."""
import os
import re
import shutil
import stat

from helpers import BIN, LIB, ShellTest

MARKER = ('# mu300-vpn: migrated to /etc/mu300/vpn (profile legacy); only ENABLE is read from this file now')
ID = re.compile(r'^[a-z0-9-]{1,32}$')


class Store(ShellTest):
    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.store = self.tmp / 'vpn'
        self.stub('ip', 'exit 0')
        self.stub('nft', 'cat >/dev/null')

    def vpn(self, shell, code, conf=None, confpath=None):
        """sources mu300-vpn with CONF (written first unless None) and runs CODE"""
        path = confpath or self.conf
        if conf is not None:
            path.write_text(conf)
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', MU300_LIB=1, MU300_VPN_CONF=path,
                       MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB, MU300_LAN_CONF=self.tmp / 'no',
                       MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt', MU300_DISK=self.tmp / 'disk')

    def reset(self):
        shutil.rmtree(self.store, ignore_errors=True)
        self.conf.unlink(missing_ok=True)

    def files(self):
        """{relative path: (mode, mtime_ns, contents)} of the store and the conf"""
        out = {}
        for p in [self.conf] + sorted(self.store.rglob('*')) + [self.store]:
            st = p.stat()
            out[str(p.relative_to(self.tmp))] = (stat.S_IMODE(st.st_mode), st.st_mtime_ns,
                                                 None if p.is_dir() else p.read_bytes())
        return out

    def kv(self, path):
        """KEY=VALUE lines as a dict, single quotes undone as mu300-vpn writes them"""
        out = {}
        for line in path.read_text().splitlines():
            k, v = line.split('=', 1)
            if len(v) >= 2 and v[0] == v[-1] == "'":
                v = v[1:-1].replace("'\\''", "'")
            out[k] = v
        return out

    LEGACY = "ENABLE=1\nENGINE=xray\nKILL_SWITCH=0\nVLESS_URI='vless://u@h:443'\nREMOTE_DNS=9.9.9.9\nTLS_PIN_SHA256=ab\n"

    def test_first_migration(self):
        for shell in self.each_shell():
            self.reset()
            r = self.vpn(shell, 'echo "$KILL_SWITCH $REMOTE_DNS $PTYPE $ACTIVE $ENABLE"', self.LEGACY)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stderr, '')
            self.assertEqual(r.stdout.strip(), '0 9.9.9.9 xray legacy 1')
            self.assertEqual((self.store / 'active').read_text().strip(), 'legacy')
            prof = self.store / 'profiles/legacy'
            self.assertEqual((prof / 'uri').read_text().strip(), 'vless://u@h:443')
            meta = self.kv(prof / 'meta')
            self.assertEqual(meta['TYPE'], 'xray')
            self.assertEqual(meta['TLS_PIN_SHA256'], 'ab')
            self.assertEqual(meta['NAME'], 'legacy')
            self.assertEqual(meta['SOURCE'], 'manual')
            self.assertRegex(meta['CREATED'], r'^[0-9]+$')
            settings = self.kv(self.store / 'settings')
            self.assertEqual(settings['KILL_SWITCH'], '0')
            self.assertEqual(settings['REMOTE_DNS'], '9.9.9.9')
            for p in [self.store] + list(self.store.rglob('*')):
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), 0o700 if p.is_dir() else 0o600, p)
            lines = self.conf.read_text().split('\n')
            self.assertEqual(lines[0], MARKER)
            self.assertEqual('\n'.join(lines[1:]), self.LEGACY)
            # the code below still finds the link where it always did
            r = self.vpn(shell, 'echo "$VLESS_URI $ENGINE $TLS_PIN_SHA256"')
            self.assertEqual(r.stdout.strip(), 'vless://u@h:443 xray ab')

    def test_migration_is_idempotent(self):
        for shell in self.each_shell():
            self.reset()
            self.vpn(shell, 'true', self.LEGACY)
            before = self.files()
            r = self.vpn(shell, 'echo "$KILL_SWITCH $REMOTE_DNS $PTYPE"')
            self.assertEqual(r.stdout.strip(), '0 9.9.9.9 xray', r.stderr)
            self.assertEqual(self.files(), before)
            self.assertEqual(self.conf.read_text().count(MARKER), 1)

    def test_an_edited_conf_wins_for_changed_keys(self):
        for shell in self.each_shell():
            self.reset()
            r = self.vpn(shell, 'kv_set "$SETTINGS" TAILSCALE 0', self.LEGACY)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.conf.write_text(self.conf.read_text().replace('REMOTE_DNS=9.9.9.9', 'REMOTE_DNS=8.8.8.8'))
            r = self.vpn(shell, 'echo "$REMOTE_DNS $TAILSCALE $KILL_SWITCH"')
            self.assertEqual(r.stdout.strip(), '8.8.8.8 0 0', r.stderr)
            self.conf.write_text(self.conf.read_text().replace('REMOTE_DNS=8.8.8.8\n', ''))
            r = self.vpn(shell, 'echo "$REMOTE_DNS $TAILSCALE"')
            self.assertEqual(r.stdout.strip(), '1.1.1.1 0', r.stderr)
            # a new pin in the conf (an older image's save_pin) reaches the profile
            self.conf.write_text(self.conf.read_text().replace('TLS_PIN_SHA256=ab', 'TLS_PIN_SHA256=cd'))
            r = self.vpn(shell, 'echo "$TLS_PIN_SHA256"')
            self.assertEqual(r.stdout.strip(), 'cd', r.stderr)

    def test_engine_default_follows_kill_switch(self):
        uri = "VLESS_URI='vless://u@h:443'\n"
        for shell in self.each_shell():
            for conf, want in ((uri, 'sing-box'), ('KILL_SWITCH=0\n' + uri, 'xray'),
                               ('KILL_SWITCH=yes\n' + uri, 'sing-box'), ('ENGINE=foo\n' + uri, 'sing-box')):
                self.reset()
                r = self.vpn(shell, 'echo "$PTYPE"', conf)
                self.assertEqual(self.kv(self.store / 'profiles/legacy/meta')['TYPE'], want, conf)
                self.assertEqual(r.stdout.strip(), want, conf)

    def test_no_link_no_profile(self):
        for shell in self.each_shell():
            self.reset()
            r = self.vpn(shell, 'echo "[$ACTIVE] [$PTYPE] $ENGINE"', 'ENABLE=1\nKILL_SWITCH=1\n')
            self.assertEqual(r.stdout.strip(), '[] [] sing-box', r.stderr)
            self.assertEqual(list((self.store / 'profiles').iterdir()), [])
            self.assertFalse((self.store / 'active').exists())
            # the link added later makes the profile, and it is the active one
            r = self.vpn(shell, 'echo "$ACTIVE $PTYPE"', "ENABLE=1\nKILL_SWITCH=1\nVLESS_URI='vless://u@h:443'\n")
            self.assertEqual(r.stdout.strip(), 'legacy sing-box', r.stderr)

    def test_not_writable_reads_in_memory(self):
        if os.geteuid() == 0:
            self.skipTest('root can write anywhere')
        d = self.tmp / 'ro'
        d.mkdir()
        conf = d / 'vpn.conf'
        conf.write_text("ENABLE=1\nKILL_SWITCH=0\nVLESS_URI='vless://u@h:443'\nREMOTE_DNS=9.9.9.9\n")
        d.chmod(0o555)
        try:
            for shell in self.each_shell():
                r = self.vpn(shell, 'echo "$PTYPE $KILL_SWITCH $REMOTE_DNS $ENABLE $VLESS_URI [$ACTIVE]"', confpath=conf)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stderr, '')
                self.assertEqual(r.stdout.strip(), 'xray 0 9.9.9.9 1 vless://u@h:443 []')
                self.assertEqual(sorted(p.name for p in d.iterdir()), ['vpn.conf'])
                self.assertNotIn(MARKER, conf.read_text())
        finally:
            d.chmod(0o755)

    def test_meta_never_executes(self):
        name = "a$(touch pwned)'b `touch pwned2` \"c\" kütük"
        for shell in self.each_shell():
            self.reset()
            code = (f"cd '{self.tmp}'; id=$(profile_new xray '{name.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}') "
                    '|| exit 1; echo "$id"; kv_get "$PROFILES/$id/meta" NAME; kv_get "$PROFILES/$id/meta" TYPE')
            r = self.vpn(shell, code, '')
            self.assertEqual(r.returncode, 0, r.stderr)
            pid, got, typ = r.stdout.split('\n')[:3]
            self.assertRegex(pid, ID)
            self.assertEqual(got, name)
            self.assertEqual(typ, 'xray')
            self.assertFalse((self.tmp / 'pwned').exists())
            self.assertFalse((self.tmp / 'pwned2').exists())
            pdir = self.store / 'profiles' / pid
            self.assertEqual(stat.S_IMODE(pdir.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((pdir / 'meta').stat().st_mode), 0o600)

    def test_profile_ids(self):
        for shell in self.each_shell():
            self.reset()
            r = self.vpn(shell, "profile_new wireguard 'My VPN!'; profile_new wireguard 'my vpn'; "
                                "profile_new openvpn '***'; profile_new xray Legacy; "
                                f"profile_new xray '{'x' * 40}'; profile_new xray '{'x' * 40}'", '')
            self.assertEqual(r.stdout.split(), ['my-vpn', 'my-vpn-2', 'openvpn', 'legacy-2', 'x' * 32,
                                                'x' * 30 + '-2'], r.stderr)

    def test_settings_validation(self):
        good = [('KILL_SWITCH', '0'), ('KILL_SWITCH', '1'), ('TAILSCALE', '0'), ('IPV6', '1'),
                ('REMOTE_DNS', '1.1.1.1'), ('REMOTE_DNS', '2606:4700::1111'), ('BOOTSTRAP_DNS', '8.8.4.4'),
                ('LAN_CIDRS', '10.0.0.0/8,fd00::/8'), ('LAN_CIDRS', ''), ('LAN_CIDRS', '192.168.1.0/24'),
                ('XRAY', '/x/xray'), ('HEV', '/x/hev'), ('SING_BOX', '/x/sb'),
                ('MIHOMO', '/x/m'), ('OPENVPN', '/usr/sbin/openvpn'), ('XRAY', '')]
        # (MIHOMO_CONTROLLER is no setting: mihomo gets no control API of any kind, see Mihomo.test_nothing_listens)
        bad = [('KILL_SWITCH', 'yes'), ('KILL_SWITCH', ''), ('IPV6', '2'), ('REMOTE_DNS', 'a;b'),
               ('REMOTE_DNS', '1.1.1.256'), ('REMOTE_DNS', '1.1.1'), ('REMOTE_DNS', ''), ('LAN_CIDRS', '10.0.0.0'),
               ('LAN_CIDRS', '10.0.0.0/33'), ('LAN_CIDRS', '10.0.0.0/8,'), ('LAN_CIDRS', 'fd00::/129'),
               ('MIHOMO_CONTROLLER', '127.0.0.1:9090'), ('MIHOMO_CONTROLLER', ''),
               ('XRAY', 'relative/xray'), ('UNKNOWN', 'x')]
        for shell in self.each_shell():
            self.reset()
            code = '; '.join(f"setting_valid {k} '{v}' && echo 1 || echo 0" for k, v in good + bad)
            r = self.vpn(shell, code, '')
            self.assertEqual(r.stdout.split(), ['1'] * len(good) + ['0'] * len(bad), r.stderr)
            # on read, an invalid value counts as the default
            (self.store / 'settings').write_text("KILL_SWITCH=yes\nREMOTE_DNS='a;b'\nIPV6=2\nTAILSCALE=0\n"
                                                 "LAN_CIDRS=10.0.0.0\nXRAY=xray\nHEV='/x/h e v'\n")
            r = self.vpn(shell, 'echo "$KILL_SWITCH $REMOTE_DNS $IPV6 $TAILSCALE [$_xray] [$_hev]"; '
                                'setting LAN_CIDRS; echo "[$(setting XRAY)]"')
            self.assertEqual(r.stdout.split('\n')[:3], ['1 1.1.1.1 0 0 [] [/x/h e v]', '', '[]'], r.stderr)

    def test_kv_round_trip(self):
        values = ["plain", "it's", "a'\\''b", "$(x) `y` \"z\"", "", "  spaced  ", "x=y=z"]
        for shell in self.each_shell():
            self.reset()
            f = self.tmp / 'kv'
            code = '; '.join(f"kv_set '{f}' K{i} '{v.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"
                             for i, v in enumerate(values))
            code += '; ' + '; '.join(f"kv_get '{f}' K{i}" for i in range(len(values)))
            # a key that is not there prints nothing at all
            code += f"; kv_set '{f}' K0 again; kv_del '{f}' K1; kv_get '{f}' K0; kv_get '{f}' K1; echo"
            code += f"; kv_set '{f}' K2 'a\nb' && echo set || echo refused"
            r = self.vpn(shell, code, '')
            self.assertEqual(r.stdout.split('\n')[:len(values) + 3], values + ['again', '', 'refused'], r.stderr)
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
            self.assertEqual(self.kv(f)['K2'], values[2])
            # kv_var, the shell's own reader the start-up uses, reads the same
            code = '; '.join(f"kv_var v '{f}' K{i}; printf '%s\\n' \"$v\"" for i in range(len(values)))
            r = self.vpn(shell, code)
            self.assertEqual(r.stdout.split('\n')[:len(values)], ['again', ''] + values[2:], r.stderr)

    def test_valid_id(self):
        good = ['a', 'my-vpn-2', 'a' * 32, '0']
        bad = ['', 'a' * 33, 'A', 'a/b', '..', 'a b', 'a_b', 'é']
        for shell in self.each_shell():
            code = '; '.join(f"valid_id '{v}' && echo 1 || echo 0" for v in good + bad)
            r = self.vpn(shell, code, '')
            self.assertEqual(r.stdout.split(), ['1'] * len(good) + ['0'] * len(bad), r.stderr)

    def test_set_enable(self):
        for shell in self.each_shell():
            self.reset()
            self.vpn(shell, 'true', self.LEGACY)
            before = self.conf.read_text()
            self.conf.chmod(0o640)
            r = self.vpn(shell, 'set_enable 0; echo "$ENABLE"')
            self.assertEqual(r.stdout.strip(), '0', r.stderr)
            self.assertEqual(self.conf.read_text(), before.replace('ENABLE=1', 'ENABLE=0'))
            self.assertEqual(stat.S_IMODE(self.conf.stat().st_mode), 0o640)
            r = self.vpn(shell, 'echo "$ENABLE"; set_enable 1; echo "$ENABLE"')
            self.assertEqual(r.stdout.split(), ['0', '1'], r.stderr)
            self.assertEqual(self.conf.read_text(), before)
            # no ENABLE line yet: one is added, after a last line without its newline
            self.conf.write_text('KILL_SWITCH=0')
            self.vpn(shell, 'set_enable 1')
            self.assertEqual(self.conf.read_text().split('\n')[-3:], ['KILL_SWITCH=0', 'ENABLE=1', ''])
            # no vpn.conf at all: one with just the switch
            self.reset()
            r = self.vpn(shell, 'set_enable 1; echo "$ENABLE"')
            self.assertEqual(r.stdout.strip(), '1', r.stderr)
            self.assertEqual(self.conf.read_text(), 'ENABLE=1\n')
            self.assertEqual(stat.S_IMODE(self.conf.stat().st_mode), 0o600)
            r = self.vpn(shell, 'echo "$ENABLE"')
            self.assertEqual(r.stdout.strip(), '1', r.stderr)


class Contract(ShellTest):
    """The driver loader and what every driver in /opt/mu300/lib/vpn provides; the routing the core installs for
    drivers that leave it to the core (DRV_ROUTES=core); and the resolve window, which lets the device's own DNS out
    past the kill switch for as long as server names are looked up."""

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=1\nKILL_SWITCH=1\n')
        self.ev = self.tmp / 'events'
        self.rules = self.tmp / 'rules'

    def vpn(self, shell, code, **env):
        e = dict(MU300_LIB=1, MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB,
                 MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt',
                 MU300_DISK=self.tmp / 'disk')
        e.update(env)
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', **e)

    def test_reserved_types(self):
        self.stub('ip', 'exit 0')
        for shell in self.each_shell():
            for t in ('l2tp', 'pptp', 'ikev2', 'tailscale-exit'):
                r = self.vpn(shell, f'load_driver {t}; echo LOADED')
                self.assertNotEqual(r.returncode, 0, t)
                self.assertNotIn('LOADED', r.stdout)
                self.assertIn(f'{t}: not available in this version', r.stderr)
            # nothing but a name of [a-z-] ever becomes a path, and a type without a driver is refused too
            for t in ('../x', 'x/y', 'X', '', 'nosuch'):
                r = self.vpn(shell, f"load_driver '{t}'; echo LOADED")
                self.assertNotEqual(r.returncode, 0, t)
                self.assertNotIn('LOADED', r.stdout, t)

    def test_only_complete_drivers_load(self):
        self.stub('ip', 'exit 0')
        lib = self.tmp / 'lib'
        shutil.copytree(LIB, lib)
        # a driver that lacks drv_alive: refused, and xray's (loaded before it) is not used in its place
        (lib / 'broken.sh').write_text('drv_engines() { :; }\ndrv_engines_ok() { :; }\ndrv_check() { :; }\n'
                                       'drv_gen() { :; }\ndrv_start() { :; }\ndrv_stop() { :; }\n'
                                       'drv_import() { :; }\n')
        for shell in self.each_shell():
            for t in ('uri', 'common', 'common-x'):
                r = self.vpn(shell, f'load_driver {t}; echo LOADED', MU300_VPN_LIB=lib)
                self.assertNotIn('LOADED', r.stdout, t)
                self.assertIn(f'{t}: invalid type', r.stderr)
            r = self.vpn(shell, 'load_driver xray || exit 9; load_driver broken && echo LOADED; '
                                'command -v drv_alive >/dev/null && echo STALE; echo "[$DRIVER]"', MU300_VPN_LIB=lib)
            self.assertNotIn('LOADED', r.stdout)
            self.assertNotIn('STALE', r.stdout)
            self.assertIn('[]', r.stdout)
            self.assertIn('broken: the driver is incomplete (no drv_alive)', r.stderr)

    def test_a_signal_closes_the_resolve_window(self):
        import signal
        import subprocess
        import time
        self.stub('nft', 'case "$1" in\n'
                         '  -f) r=$(cat); printf "%s\\n" "$r" > "$STUBLOG/nft.state"; echo "nft -f" >> "$STUBLOG/events" ;;\n'
                         '  *) echo "nft $*" >> "$STUBLOG/events" ;;\n'
                         'esac; exit 0')
        # a slow resolver: the service is stopped while it is looking the server up
        self.stub('getent', 'touch "$STUBLOG/resolving"; sleep 2; echo "203.0.113.5     STREAM srv.example"')
        self.stub('ip', 'exit 0')
        (self.tmp / 'resolv.conf').write_text('nameserver 10.177.0.34\n')
        for shell in self.each_shell():
            for p in ('events', 'resolving', 'nft.state'):
                (self.tmp / p).unlink(missing_ok=True)
            e = dict(MU300_LIB=1, MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB,
                     MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt',
                     MU300_DISK=self.tmp / 'disk', MU300_RESOLV_FILES=self.tmp / 'resolv.conf')
            p = subprocess.Popen(shell + ['-c', f'. "{BIN}/mu300-vpn"; vpn_resolve srv.example; echo DONE'],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=self.env(**e))
            deadline = time.time() + 20
            while not (self.tmp / 'resolving').exists() and time.time() < deadline:
                time.sleep(0.05)
            p.send_signal(signal.SIGTERM)
            out, err = p.communicate(timeout=30)
            self.assertNotEqual(p.returncode, 0, err)
            self.assertNotIn('DONE', out)
            # the window went up and the full kill switch came back over it
            self.assertEqual((self.tmp / 'events').read_text().count('nft -f'), 2, err)
            state = (self.tmp / 'nft.state').read_text()
            self.assertIn('counter drop', state)
            self.assertNotIn('dns4', state)

    def test_every_driver_defines_the_contract(self):
        self.stub('ip', 'exit 0')
        names = sorted(p.stem for p in LIB.glob('*.sh') if p.name != 'uri.sh' and not p.name.startswith('common'))
        self.assertIn('xray', names)
        self.assertIn('sing-box', names)
        funcs = 'drv_engines drv_engines_ok drv_check drv_gen drv_start drv_alive drv_stop drv_status drv_import'
        for shell in self.each_shell():
            for n in names:
                r = self.vpn(shell, f'load_driver {n}; for f in {funcs}; do command -v "$f" >/dev/null || '
                                    'echo "missing $f"; done; echo "extra=[$DRV_EXTRA] routes=$DRV_ROUTES"')
                self.assertEqual(r.returncode, 0, (n, r.stderr))
                self.assertNotIn('missing', r.stdout, n)
                self.assertRegex(r.stdout, r'routes=(core|self)\n', n)

    # the Tailscale ip stub of test_vpn: rules kept as the kernel lists them
    IP = ('r="$STUBLOG/rules"; touch "$r"\n'
          'case "$1 $2" in\n'
          '  "rule add") shift 2; [ "$1" = pref ] || exit 2; grep -qxF "$*" "$r" && exit 2\n'
          '      [ -e "$STUBLOG/fail-$2" ] && exit 2; echo "$*" >> "$r" ;;\n'
          '  "rule del") [ "$3" = pref ] || exit 2\n'
          '      awk -v p="$4" \'!d && $2 == p {d = 1; next} {print} END {exit !d}\' "$r" > "$r.new" || { rm -f "$r.new"; exit 2; }\n'
          '      mv "$r.new" "$r" ;;\n'
          '  "rule show") sort -s -n -k2,2 "$r" | sed "s/^pref \\([0-9]*\\) /\\1: /" ;;\n'
          '  "link show") [ -e "$STUBLOG/tun" ]; exit ;;\n'
          'esac\nexit 0')

    def test_core_routes(self):
        self.stub('ip', self.IP)
        self.stub('nft', '[ "$1" = -f ] && cat > /dev/null; exit 0')
        for shell in self.each_shell():
            self.rules.unlink(missing_ok=True)
            r = self.vpn(shell, 'TUN=wg-mu300; mkdir -p "$RUN"; '
                                "printf '203.0.113.9\\n198.51.100.1\\n' > \"$RUN/server-ip\"; routes_up")
            self.assertEqual(r.returncode, 0, r.stderr)
            rules = self.rules.read_text().splitlines()
            for want in ('pref 9000 fwmark 0x2d0 lookup main', 'pref 9002 to 203.0.113.9 lookup main',
                         'pref 9002 to 198.51.100.1 lookup main', 'pref 9010 lookup 2022'):
                self.assertIn(want, rules)
            r = self.vpn(shell, 'TUN=wg-mu300; routes_down')
            self.assertEqual(r.returncode, 0, r.stderr)
            left = [l for l in self.rules.read_text().splitlines() if 9000 <= int(l.split()[1]) <= 9010]
            self.assertEqual(left, [])

    def test_resolve_window(self):
        # the KillSwitch nft stub of test_vpn: the ruleset in force, and every call in order
        self.stub('nft', 'case "$1" in\n'
                         '  -f) r=$(cat); printf "%s\\n" "$r" > "$STUBLOG/nft.state.new"; mv "$STUBLOG/nft.state.new" "$STUBLOG/nft.state"\n'
                         '      { echo "nft -f"; printf "%s\\n" "$r" | sed "s/^/  | /"; } >> "$STUBLOG/events" ;;\n'
                         '  list) [ -s "$STUBLOG/nft.state" ] ;;\n'
                         '  *) echo "nft $*" >> "$STUBLOG/events"\n'
                         '     [ "$*" = "delete table inet mu300_vpn" ] && : > "$STUBLOG/nft.state"; exit 0 ;;\n'
                         'esac')
        self.stub('getent', '[ "$2" = srv.example ] && echo "203.0.113.5     STREAM srv.example"; exit 0')
        self.stub('ip', 'exit 0')
        (self.tmp / 'resolv.conf').write_text('nameserver 127.0.0.53\nnameserver 10.177.0.34\n')
        for shell in self.each_shell():
            for code in ('resolve_window; vpn_resolve srv.example; resolve_close',
                         # by itself it opens and closes the window around the lookup
                         'vpn_resolve srv.example'):
                self.ev.unlink(missing_ok=True)
                r = self.vpn(shell, code, MU300_RESOLV_FILES=self.tmp / 'resolv.conf')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(r.stdout.strip(), '203.0.113.5')
                ev = self.ev.read_text()
                sets = ev.split('nft -f\n')[1:]
                self.assertEqual(len(sets), 2, ev)
                window, full = ('\n'.join(l[4:] for l in s.splitlines() if l.startswith('  | ')) for s in sets)
                self.assertIn('@dns4', window)
                self.assertNotIn('dns4', full)
                self.assertNotIn('fetch4', full)
                adds = [l for l in ev.splitlines() if l.startswith('nft add element')]
                self.assertTrue(any('dns4 { 10.177.0.34 timeout 30s }' in a for a in adds), adds)
                self.assertFalse(any('fetch' in a for a in adds), adds)
                self.assertNotIn('nft delete table', ev)
            # without the kill switch there is nothing to open
            self.ev.unlink(missing_ok=True)
            self.conf.write_text('ENABLE=1\nKILL_SWITCH=0\n')
            r = self.vpn(shell, 'vpn_resolve srv.example', MU300_RESOLV_FILES=self.tmp / 'resolv.conf')
            self.conf.write_text('ENABLE=1\nKILL_SWITCH=1\n')
            self.assertEqual(r.stdout.strip(), '203.0.113.5')
            self.assertFalse(self.ev.exists())

    def test_a_failed_drv_start_step_routes_nothing(self):
        # drv_start runs without set -e (drv_start || exit 1): an "ip link set xtun up" that fails must end it,
        # and the core must never route into that tunnel
        self.stub('ip', self.IP.replace('  "link show")', '  "link set") exit 1 ;;\n  "link show")'))
        self.stub('nft', '[ "$1" = -f ] && cat > /dev/null; exit 0')
        self.stub('ss', 'echo "LISTEN 0 4096 127.0.0.1:10808 0.0.0.0:*"')
        self.stub('getent', 'echo "203.0.113.9     STREAM $2"')
        self.stub('pgrep', 'exit 1')
        d = self.tmp / 'disk/extra/vpn/bin'
        d.mkdir(parents=True)
        (d / 'xray').write_text('#!/bin/sh\n[ "$2" = -test ] && exit 0\nexec sleep 30\n')
        (d / 'hev-socks5-tunnel').write_text('#!/bin/sh\nexec sleep 30\n')
        for n in ('xray', 'hev-socks5-tunnel'):
            (d / n).chmod(0o755)
        (self.tmp / 'tun').write_text('')
        uri = 'vless://11111111-2222-3333-4444-555555555555@vpn.example.com:443?security=tls&type=tcp'
        for shell in self.each_shell():
            self.rules.unlink(missing_ok=True)
            self.conf.write_text(f"ENABLE=1\nENGINE=xray\nKILL_SWITCH=0\nVLESS_URI='{uri}'\n")
            r = self.script(shell, BIN / 'mu300-vpn', 'run', MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run',
                            MU300_VPN_LIB=LIB, MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN,
                            MU300_OPT=self.tmp / 'opt', MU300_DISK=self.tmp / 'disk')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('cannot bring xtun up', r.stderr)
            self.assertNotIn('tunnel up', r.stdout)
            rules = self.rules.read_text() if self.rules.exists() else ''
            self.assertNotIn('pref 9010', rules)
            self.assertFalse((self.tmp / 'run/iface').exists())

    def test_xray_runs_in_the_core_loop(self):
        # xray and hev-socks5-tunnel as stubs: the core routes the tunnel once both are up, keeps $RUN/iface while
        # it is, and takes it all down when one of them exits
        self.stub('ip', self.IP)
        self.stub('nft', '[ "$1" = -f ] && cat > /dev/null; exit 0')
        self.stub('ss', 'echo "LISTEN 0 4096 127.0.0.1:10808 0.0.0.0:*"')
        self.stub('getent', '[ "$2" = vpn.example.com ] && echo "203.0.113.9     STREAM vpn.example.com"; exit 0')
        self.stub('pgrep', 'exit 1')
        d = self.tmp / 'disk/extra/vpn/bin'
        d.mkdir(parents=True)
        (d / 'xray').write_text('#!/bin/sh\n[ "$2" = -test ] && exit 0\n'
                                'n=0; until [ -e "$MU300_VPN_RUN/iface" ] || [ $n -gt 100 ]; do sleep 0.1; n=$((n+1)); done\n'
                                'cp "$STUBLOG/rules" "$STUBLOG/rules-up"; cp "$MU300_VPN_RUN/iface" "$STUBLOG/iface-up"\n'
                                'echo "[Warning] gone"\n')
        (d / 'hev-socks5-tunnel').write_text('#!/bin/sh\nexec sleep 30\n')
        for n in ('xray', 'hev-socks5-tunnel'):
            (d / n).chmod(0o755)
        (self.tmp / 'tun').write_text('')
        uri = 'vless://11111111-2222-3333-4444-555555555555@vpn.example.com:443?security=tls&type=tcp'
        for shell in self.each_shell():
            for p in ('rules', 'rules-up', 'iface-up'):
                (self.tmp / p).unlink(missing_ok=True)
            self.conf.write_text(f"ENABLE=1\nENGINE=xray\nKILL_SWITCH=0\nVLESS_URI='{uri}'\n")
            r = self.script(shell, BIN / 'mu300-vpn', 'run', MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run',
                            MU300_VPN_LIB=LIB, MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN,
                            MU300_OPT=self.tmp / 'opt', MU300_DISK=self.tmp / 'disk')
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn('tunnel up on xtun', r.stdout)
            self.assertIn('[Warning] gone', r.stdout)
            self.assertIn('xray exited, tearing the tunnel down', r.stderr)
            self.assertNotIn('11111111', r.stdout + r.stderr)
            up = (self.tmp / 'rules-up').read_text().splitlines()
            self.assertIn('pref 9002 to 203.0.113.9 lookup main', up)
            self.assertIn('pref 9010 lookup 2022', up)
            self.assertEqual((self.tmp / 'iface-up').read_text().strip(), 'xtun')
            self.assertEqual([l for l in self.rules.read_text().splitlines() if l.split()[1] >= '9000'], [])
            self.assertFalse((self.tmp / 'run/iface').exists())


VMESS = {"v": "2", "ps": "n", "add": "vm.example", "port": "8443", "id": "11111111-2222-3333-4444-555555555555",
         "aid": "0", "scy": "auto", "net": "ws", "type": "none", "host": "h.example", "path": "/p", "tls": "tls",
         "sni": "s.example"}


def b64(s, urlsafe=False):
    import base64
    raw = s.encode()
    if urlsafe:
        return base64.urlsafe_b64encode(raw).decode().rstrip('=')
    return base64.b64encode(raw).decode()


def vmess_link(urlsafe=False, **over):
    import json
    d = dict(VMESS, **over)
    return 'vmess://' + b64(json.dumps(d), urlsafe)


class Uris(ShellTest):
    """parse_link for every kind of link the xray driver takes, and the outbound gen_xray writes from each: the
    right protocol, the server's resolved address, and the mark that lets it past the kill switch."""

    LINKS = [
        (vmess_link(), 'vmess',
         dict(PROTO='vmess', HOST='vm.example', PORT='8443', TYPE='ws', WSPATH='/p', WSHOST='h.example',
              SECURITY='tls', SNI='s.example', AID='0', METHOD='auto')),
        (vmess_link(urlsafe=True), 'vmess',
         dict(PROTO='vmess', HOST='vm.example', PORT='8443', TYPE='ws', WSPATH='/p', WSHOST='h.example',
              SECURITY='tls', SNI='s.example')),
        ('trojan://p%40ss@tr.example:443?type=grpc&serviceName=g&sni=x.example#t', 'trojan',
         dict(PROTO='trojan', PASSWORD='p@ss', HOST='tr.example', PORT='443', TYPE='grpc', SVC='g', SECURITY='tls',
              SNI='x.example')),
        ('ss://' + b64('aes-256-gcm:pw', urlsafe=True) + '@ss.example:8388#n', 'shadowsocks',
         dict(PROTO='ss', METHOD='aes-256-gcm', PASSWORD='pw', HOST='ss.example', PORT='8388', SECURITY='none')),
        ('ss://2022-blake3-aes-128-gcm:a%2Bb%3D@[2001:db8::2]:443', 'shadowsocks',
         dict(PROTO='ss', METHOD='2022-blake3-aes-128-gcm', PASSWORD='a+b=', HOST='2001:db8::2', PORT='443')),
        ('ss://' + b64('chacha20-ietf-poly1305:pw@1.2.3.4:8000') + '#legacy', 'shadowsocks',
         dict(PROTO='ss', METHOD='chacha20-ietf-poly1305', PASSWORD='pw', HOST='1.2.3.4', PORT='8000')),
        ('vless://11111111-2222-3333-4444-555555555555@vl.example:443?security=tls&type=tcp', 'vless',
         dict(PROTO='vless', HOST='vl.example', PORT='443', TYPE='tcp', SECURITY='tls')),
    ]
    BAD = ['ss://' + b64('aes-256-gcm:pw', urlsafe=True) + '@ss.example:8388/?plugin=obfs-local%3Bobfs%3Dhttp',
           'ss://' + b64('aes-256-gcm:pw') + '@ss.example:8388?plugin=obfs',
           'vmess://bm90IGpzb24',               # base64, but not JSON
           vmess_link(net='tcp', type='http'),   # TCP with an HTTP header: not something xray_stream_json writes
           vmess_link(port='x'),
           'trojan://@tr.example:443', 'trojan://pw@tr.example:99999', 'vless://u@h:443/?x\nmore',
           'ss://bm9jb2xvbg', 'https://example.com', 'vless://u@bad host:443']

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.stub('ip', 'exit 0')
        self.stub('nft', 'cat >/dev/null; exit 0')
        self.stub('getent', 'echo "203.0.113.10    STREAM $2"')
        self.stub('xray', 'echo "$*" >> "$STUBLOG/xray.args"')

    def vpn(self, shell, code):
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', MU300_LIB=1, MU300_VPN_CONF=self.conf,
                       MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB, MU300_LAN_CONF=self.tmp / 'no',
                       MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt', MU300_DISK=self.tmp / 'disk')

    def test_parse_link(self):
        for shell in self.each_shell():
            for uri, _, want in self.LINKS:
                code = f"parse_link '{uri}' || exit 9; " + '; '.join(f'echo "{k}=${k}"' for k in want)
                r = self.vpn(shell, code)
                self.assertEqual(r.returncode, 0, (uri, r.stderr))
                got = dict(line.split('=', 1) for line in r.stdout.splitlines())
                self.assertEqual(got, want, uri)
            for uri in self.BAD:
                r = self.vpn(shell, f"parse_link '{uri}' && echo PARSED")
                self.assertNotIn('PARSED', r.stdout, uri)
                self.assertNotEqual(r.returncode, 0, uri)
            r = self.vpn(shell, "parse_link '" + self.BAD[0] + "'")
            self.assertIn('ss plugins are not supported', r.stderr)
            # the vless-only entry point the sing-box driver uses still refuses everything else
            r = self.vpn(shell, f"VLESS_URI='{self.LINKS[2][0]}'; parse_uri; echo PARSED")
            self.assertNotIn('PARSED', r.stdout)

    def test_b64d(self):
        for shell in self.each_shell():
            r = self.vpn(shell, "b64d 'YWVzLTI1Ni1nY206cHc'; b64d 'YWVzLTI1Ni1nY206cHc='; b64d 'Pz8_'")
            self.assertEqual(r.stdout.split('\n')[:3], ['aes-256-gcm:pw', 'aes-256-gcm:pw', '???'], r.stderr)

    def test_gen_xray_outbounds(self):
        import json
        for shell in self.each_shell():
            for uri, proto, want in self.LINKS:
                (self.tmp / 'xray.args').unlink(missing_ok=True)
                r = self.vpn(shell, f"PURI='{uri}'; load_driver xray; XRAY='{self.stubs}/xray'; gen_xray")
                self.assertEqual(r.returncode, 0, (uri, r.stderr))
                cfg = json.loads((self.tmp / 'run/xray.json').read_text())
                out = cfg['outbounds'][0]
                self.assertEqual(out['protocol'], proto, uri)
                server = (out['settings'].get('vnext') or out['settings'].get('servers'))[0]
                # a name is resolved; an address is used as it is
                addr = want['HOST'] if want['HOST'][0].isdigit() else '203.0.113.10'
                self.assertEqual(server['address'], addr, uri)
                self.assertEqual(server['port'], int(want['PORT']), uri)
                self.assertEqual(out['streamSettings']['sockopt']['mark'], 720, uri)
                self.assertEqual(cfg['outbounds'][1]['streamSettings']['sockopt']['mark'], 720)
                if proto == 'vmess':
                    self.assertEqual(server['users'][0]['alterId'], 0)
                    self.assertEqual(server['users'][0]['security'], 'auto')
                    self.assertEqual(out['streamSettings']['wsSettings'], {'path': '/p', 'host': 'h.example'})
                    self.assertEqual(out['streamSettings']['tlsSettings']['serverName'], 's.example')
                if proto == 'trojan':
                    self.assertEqual(server['password'], 'p@ss')
                    self.assertEqual(out['streamSettings']['grpcSettings'], {'serviceName': 'g'})
                if proto == 'shadowsocks':
                    self.assertEqual((server['method'], server['password']), (want['METHOD'], want['PASSWORD']))
                    self.assertNotIn('security', out['streamSettings'])
                self.assertEqual((self.tmp / 'run/server-ip').read_text().strip(), addr)
                self.assertIn(f'run -test -c {self.tmp}/run/xray.json', (self.tmp / 'xray.args').read_text())
                # what gen prints names the server, never the credentials
                for secret in ('11111111', 'p@ss', 'a+b='):
                    self.assertNotIn(secret, r.stdout + r.stderr, uri)


class Cli(ShellTest):
    """The commands: profile list/show/add/import/edit/set/remove/use/export, settings, on/off; run as the
    script, with the service manager a stub that notes what it was told (MU300_VPN_SVC)."""

    UUID = '11111111-2222-3333-4444-555555555555'
    LINK = f'vless://{UUID}@vpn.example.com:443?security=tls&type=tcp#Home'
    LINK2 = f'vless://{UUID}@other.example.com:443?security=tls&type=ws&path=%2Fw'

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\n')
        self.store = self.tmp / 'vpn'
        self.svclog = self.tmp / 'svc.log'
        self.ev = self.tmp / 'events'
        self.stub('svc', 'echo "svc $*" >> "$STUBLOG/svc.log"')
        self.stub('ip', '[ "$1 $2" = "rule del" ] && exit 2; exit 0')
        self.stub('pgrep', 'exit 1')
        self.stub('getent', 'echo "203.0.113.10    STREAM $2"')
        self.stub('nft', 'case "$1" in\n'
                         '  -f) r=$(cat); printf "%s\\n" "$r" > "$STUBLOG/nft.state"\n'
                         '      { echo "nft -f"; printf "%s\\n" "$r" | sed "s/^/  | /"; } >> "$STUBLOG/events" ;;\n'
                         '  list) [ -s "$STUBLOG/nft.state" ] ;;\n'
                         '  *) echo "nft $*" >> "$STUBLOG/events"\n'
                         '     [ "$*" = "delete table inet mu300_vpn" ] && : > "$STUBLOG/nft.state"; exit 0 ;;\n'
                         'esac')

    def engines(self, names=('xray', 'hev-socks5-tunnel', 'sing-box')):
        d = self.tmp / 'disk/extra/vpn/bin'
        d.mkdir(parents=True, exist_ok=True)
        for n in names:
            (d / n).write_text('#!/bin/sh\necho "engine ${0##*/} $*" >> "$STUBLOG/events"\nexit 0\n')
            (d / n).chmod(0o755)

    def fresh(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.tmp / 'disk', ignore_errors=True)
        for p in (self.svclog, self.ev, self.tmp / 'nft.state'):
            p.unlink(missing_ok=True)
        self.conf.write_text('ENABLE=0\n')

    def vpn(self, shell, *args):
        return self.script(shell, BIN / 'mu300-vpn', *args, MU300_VPN_CONF=self.conf,
                           MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB, MU300_LAN_CONF=self.tmp / 'no',
                           MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt', MU300_DISK=self.tmp / 'disk',
                           MU300_VPN_SVC=self.stubs / 'svc', MU300_EXTRA_CMD=self.stubs / 'no-extra')

    def svc(self):
        return self.svclog.read_text().splitlines() if self.svclog.exists() else []

    def enable(self, v):
        self.conf.write_text(f'ENABLE={v}\n')

    def test_import_list_show_export(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.vpn(shell, 'profile', 'import', self.LINK, 'Home')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'home'), r.stderr)
            r = self.vpn(shell, 'profile', 'import', self.LINK, 'Home')
            self.assertEqual(r.stdout.strip(), 'home-2', r.stderr)
            # without a name: the link's own tag
            r = self.vpn(shell, 'profile', 'import', vmess_link(ps='My VMess'))
            self.assertEqual(r.stdout.strip(), 'my-vmess', r.stderr)
            r = self.vpn(shell, 'profile', 'add', 'sing-box', 'SB', self.LINK2)
            self.assertEqual(r.stdout.strip(), 'sb', r.stderr)
            r = self.vpn(shell, 'profile', 'list')
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            self.assertIn(' \thome\txray\tHome', lines)
            self.assertIn(' \tsb\tsing-box\tSB', lines)
            self.assertIn(' \tmy-vmess\txray\tMy VMess', lines)
            pdir = self.store / 'profiles/home'
            self.assertEqual(stat.S_IMODE((pdir / 'uri').stat().st_mode), 0o600)
            r = self.vpn(shell, 'profile', 'show', 'home')
            self.assertEqual(r.returncode, 0, r.stderr)
            show = dict(l.split('\t', 1) for l in r.stdout.splitlines())
            self.assertEqual((show['id'], show['name'], show['type'], show['source'], show['server']),
                             ('home', 'Home', 'xray', 'manual', 'vpn.example.com:443'))
            self.assertRegex(show['created'], r'^[0-9]+$')
            for out in (r.stdout + r.stderr, self.vpn(shell, 'profile', 'list').stdout):
                self.assertNotIn(self.UUID, out)
                self.assertNotIn('vless://', out)
            r = self.vpn(shell, 'profile', 'export', 'home')
            self.assertEqual(r.stdout, self.LINK + '\n')

    def test_refused_imports_leave_nothing(self):
        for shell in self.each_shell():
            self.fresh()
            for args, msg in ((['import', 'ss://' + b64('aes-256-gcm:pw') + '@h:1?plugin=obfs'], 'ss plugins'),
                              (['import', 'https://example.com/x'], 'not a kind of link'),
                              (['add', 'sing-box', 'X', vmess_link()], 'not a link this profile type takes'),
                              (['add', 'l2tp', 'X', self.LINK], 'l2tp: not available in this version'),
                              (['add', 'nosuch', 'X', self.LINK], 'nosuch: no driver')):
                r = self.vpn(shell, 'profile', *args)
                self.assertNotEqual(r.returncode, 0, args)
                self.assertIn(msg, r.stderr, args)
                self.assertNotIn('pw@', r.stderr)
                self.assertEqual(list((self.store / 'profiles').iterdir()), [], args)

    def test_use_restarts_a_running_vpn(self):
        for shell in self.each_shell():
            self.fresh()
            self.vpn(shell, 'profile', 'import', self.LINK, 'Home')
            r = self.vpn(shell, 'profile', 'use', 'home')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.store / 'active').read_text(), 'home\n')
            self.assertEqual(self.svc(), [])
            self.enable(1)
            r = self.vpn(shell, 'profile', 'use', 'home')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.svc(), ['svc restart'])
            r = self.vpn(shell, 'profile', 'list')
            self.assertIn('*\thome\txray\tHome', r.stdout.splitlines())

    def test_invalid_ids(self):
        for shell in self.each_shell():
            self.fresh()
            for args in (['use', '../x'], ['show', 'A'], ['remove', 'a/b'], ['export', ''], ['set', '..', 'NAME', 'x']):
                r = self.vpn(shell, 'profile', *args)
                self.assertEqual(r.returncode, 2, args)
                self.assertIn('invalid profile id', r.stderr, args)
            r = self.vpn(shell, 'profile', 'show', 'nosuch')
            self.assertEqual(r.returncode, 1)

    def test_remove(self):
        for shell in self.each_shell():
            self.fresh()
            self.vpn(shell, 'profile', 'import', self.LINK, 'Home')
            self.vpn(shell, 'profile', 'use', 'home')
            self.enable(1)
            r = self.vpn(shell, 'profile', 'remove', 'home')
            self.assertNotEqual(r.returncode, 0)
            self.assertTrue((self.store / 'profiles/home').is_dir())
            r = self.vpn(shell, 'off')
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.vpn(shell, 'profile', 'remove', 'home')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((self.store / 'profiles/home').exists())
            self.assertFalse((self.store / 'active').exists())

    def test_edit_and_set(self):
        for shell in self.each_shell():
            self.fresh()
            self.vpn(shell, 'profile', 'import', self.LINK, 'Home')
            uri = self.store / 'profiles/home/uri'
            # a link that does not parse leaves the old one
            r = self.vpn(shell, 'profile', 'edit', 'home', 'trojan://@x:1')
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(uri.read_text(), self.LINK + '\n')
            r = self.vpn(shell, 'profile', 'edit', 'home', vmess_link())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(uri.read_text(), vmess_link() + '\n')
            self.assertEqual([p.name for p in (self.store / 'profiles').iterdir()], ['home'])
            r = self.vpn(shell, 'profile', 'set', 'home', 'TLS_PIN_SHA256', 'ab' * 32)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("TLS_PIN_SHA256='" + 'ab' * 32 + "'", (self.store / 'profiles/home/meta').read_text())
            for key, val in (('TLS_PIN_SHA256', 'zz'), ('UPSTREAM_HTTP_PROXY', 'h:x'), ('TYPE', 'sing-box'),
                             ('MIHOMO_STACK', 'gvisor')):
                r = self.vpn(shell, 'profile', 'set', 'home', key, val)
                self.assertEqual(r.returncode, 2, (key, r.stderr))
            r = self.vpn(shell, 'profile', 'set', 'home', 'NAME', 'Büro "1"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('\thome\txray\tBüro "1"', self.vpn(shell, 'profile', 'list').stdout)

    def test_settings(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.vpn(shell, 'settings', 'set', 'KILL_SWITCH', 'yes')
            self.assertEqual(r.returncode, 2)
            r = self.vpn(shell, 'settings', 'set', 'NOPE', '1')
            self.assertEqual(r.returncode, 2)
            r = self.vpn(shell, 'settings', 'set', 'REMOTE_DNS', '9.9.9.9')
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.vpn(shell, 'settings', 'get', 'REMOTE_DNS')
            self.assertEqual(r.stdout, '9.9.9.9\n')
            r = self.vpn(shell, 'settings')
            got = dict(l.split('=', 1) for l in r.stdout.splitlines())
            self.assertEqual((got['REMOTE_DNS'], got['KILL_SWITCH'], got['LAN_CIDRS'], got['XRAY']),
                             ('9.9.9.9', '1', '', ''))
            self.assertEqual(len(got), 11)
            self.assertNotIn('MIHOMO_CONTROLLER', got)
            # empty: back to the default
            r = self.vpn(shell, 'settings', 'set', 'REMOTE_DNS', '')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.vpn(shell, 'settings', 'get', 'REMOTE_DNS').stdout, '1.1.1.1\n')

    def test_on_and_off(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.vpn(shell, 'on')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('no active profile', r.stderr)
            self.assertEqual(self.svc(), [])
            self.vpn(shell, 'profile', 'import', self.LINK, 'Home')
            self.vpn(shell, 'profile', 'use', 'home')
            # no engines: not turned on, with the command that gets them
            r = self.vpn(shell, 'on')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('mu300-vpn engines install', r.stderr)
            self.assertIn('ENABLE=0', self.conf.read_text())
            self.engines()
            r = self.vpn(shell, 'on')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('ENABLE=1', self.conf.read_text())
            self.assertEqual(self.svc(), ['svc enable', 'svc restart'])
            self.svclog.unlink()
            r = self.vpn(shell, 'restart')
            self.assertEqual(self.svc(), ['svc restart'])
            self.svclog.unlink()
            r = self.vpn(shell, 'off')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('ENABLE=0', self.conf.read_text())
            self.assertEqual(self.svc(), ['svc stop', 'svc disable'])
            self.assertIn('kill switch removed', r.stdout)
            self.assertIn('nft delete table inet mu300_vpn', self.ev.read_text())

    def test_switching_profiles_keeps_the_kill_switch(self):
        for shell in self.each_shell():
            self.fresh()
            self.engines()
            self.enable(1)
            self.assertEqual(self.vpn(shell, 'profile', 'add', 'sing-box', 'A', self.LINK).returncode, 0)
            self.assertEqual(self.vpn(shell, 'profile', 'add', 'xray', 'B', self.LINK2).returncode, 0)
            self.vpn(shell, 'profile', 'use', 'a')
            r = self.vpn(shell, 'run')
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.vpn(shell, 'profile', 'use', 'b')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.svc(), ['svc restart', 'svc restart'])
            # the service's next run, on B: an xray VLESS profile behind the kill switch runs on sing-box
            r = self.vpn(shell, 'run')
            self.assertEqual(r.returncode, 0, r.stderr)
            ev = self.ev.read_text()
            self.assertEqual(ev.count('nft -f\n'), 2, ev)
            self.assertNotIn('nft delete table inet mu300_vpn', ev)
            self.assertIn('other.example.com', (self.tmp / 'run/config.json').read_text())

    def test_nothing_secret_in_the_output(self):
        for shell in self.each_shell():
            self.fresh()
            self.engines()
            self.vpn(shell, 'settings', 'set', 'KILL_SWITCH', '0')
            links = [self.LINK, vmess_link(), f'trojan://{self.UUID}@tr.example:443?sni=x.example',
                     'ss://' + b64(f'aes-256-gcm:{self.UUID}') + '@ss.example:8388']
            for i, link in enumerate(links):
                r = self.vpn(shell, 'profile', 'import', link, f'p{i}')
                self.assertEqual(r.returncode, 0, r.stderr)
                self.enable(1)
                self.vpn(shell, 'profile', 'use', f'p{i}')
                outs = [self.vpn(shell, *a) for a in (['run'], ['status'], ['profile', 'list'],
                                                      ['profile', 'show', f'p{i}'], ['check'], ['on'])]
                for r in outs:
                    self.assertNotIn(self.UUID, r.stdout + r.stderr, (link, r.args))
                self.enable(0)


XRAY_RAW = {
    "log": {"loglevel": "debug"},
    "inbounds": [{"port": 1080, "listen": "0.0.0.0", "protocol": "socks"}],
    "outbounds": [
        {"tag": "proxy", "protocol": "vless",
         "settings": {"vnext": [{"address": "srv.example", "port": 443,
                                 "users": [{"id": "11111111-2222-3333-4444-555555555555", "encryption": "none"}]}]},
         "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": {"alpn": ["h2"]}}},
        {"tag": "direct", "protocol": "freedom"}],
    "routing": {"rules": [{"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"}]}}

# The shape of a rebuilt Xray outbound, as xray.sh's XRAY_JSON_SHAPE has it ("s" string, "n" number, "b" boolean,
# "a" any of the three, "h" a string or a list of strings, [x] a list of x, {"*": x} a map of x under any key), plus
# what the rebuild writes itself: sockopt (the mark and the config's own dialerProxy) and WireGuard's noKernelTun.
# A copy, kept by hand: test_a_panel_export_is_rebuilt_from_the_shape walks a rebuilt config against it.
X_SOCKOPT = {"mark": "n", "dialerProxy": "s"}
X_TLS = {"serverName": "s", "fingerprint": "s", "alpn": ["s"], "minVersion": "s", "maxVersion": "s",
         "cipherSuites": "s", "pinnedPeerCertificateChainSha256": ["s"], "pinnedPeerCertSha256": "h",
         "verifyPeerCertInNames": ["s"], "verifyPeerCertByName": "s", "curvePreferences": ["s"],
         "enableSessionResumption": "b", "echConfigList": "s", "serverNameToVerify": "s", "show": "b"}
X_REALITY = {"serverName": "s", "fingerprint": "s", "publicKey": "s", "shortId": "s", "spiderX": "s",
             "mldsa65Verify": "s", "show": "b"}
X_XHTTP0 = {"path": "s", "host": "s", "headers": {"*": "s"}, "mode": "s", "noGRPCHeader": "b", "noSSEHeader": "b",
            "xPaddingBytes": "s", "scMaxEachPostBytes": "a", "scMinPostsIntervalMs": "a", "scMaxBufferedPosts": "n",
            "scStreamUpServerSecs": "a",
            "xmux": {"maxConcurrency": "a", "maxConnections": "a", "cMaxReuseTimes": "a", "hMaxRequestTimes": "a",
                     "hMaxReusableSecs": "a", "hKeepAlivePeriod": "n"}}
X_XHTTP = dict(X_XHTTP0, extra=dict(X_XHTTP0, downloadSettings={
    "address": "s", "port": "n", "network": "s", "security": "s", "tlsSettings": X_TLS, "realitySettings": X_REALITY,
    "xhttpSettings": dict(X_XHTTP0, extra=X_XHTTP0), "sockopt": X_SOCKOPT}))
X_TCP = {"header": {"type": "s", "request": {"version": "s", "method": "s", "path": ["s"], "headers": {"*": "h"}},
                    "response": {"version": "s", "status": "s", "reason": "s", "headers": {"*": "h"}}}}
X_STREAM = {
    "network": "s", "security": "s", "tlsSettings": X_TLS, "realitySettings": X_REALITY,
    "wsSettings": {"path": "s", "host": "s", "headers": {"*": "s"}, "heartbeatPeriod": "n"},
    "httpupgradeSettings": {"path": "s", "host": "s", "headers": {"*": "s"}},
    "xhttpSettings": X_XHTTP,
    "grpcSettings": {"serviceName": "s", "authority": "s", "multiMode": "b", "user_agent": "s", "idle_timeout": "n",
                     "health_check_timeout": "n", "permit_without_stream": "b", "initial_windows_size": "n"},
    "kcpSettings": {"mtu": "n", "tti": "n", "uplinkCapacity": "n", "downlinkCapacity": "n", "congestion": "b",
                    "readBufferSize": "n", "writeBufferSize": "n", "header": {"type": "s", "domain": "s"}, "seed": "s"},
    "tcpSettings": X_TCP, "rawSettings": X_TCP,
    "httpSettings": {"host": ["s"], "path": "s", "method": "s", "headers": {"*": "h"}, "read_idle_timeout": "n",
                     "health_check_timeout": "n"},
    "quicSettings": {"security": "s", "key": "s", "header": {"type": "s"}},
    "sockopt": X_SOCKOPT}
X_VLESS_USER = {"id": "s", "encryption": "s", "flow": "s", "level": "n", "email": "s", "alterId": "n", "security": "s"}
X_VMESS_USER = {"id": "s", "security": "s", "level": "n", "email": "s", "alterId": "n"}
X_SETTINGS = {
    "vless": {"vnext": [{"address": "s", "port": "n", "users": [X_VLESS_USER]}]},
    "vmess": {"vnext": [{"address": "s", "port": "n", "users": [X_VMESS_USER]}]},
    "trojan": {"servers": [{"address": "s", "port": "n", "password": "s", "email": "s", "level": "n"}]},
    "shadowsocks": {"servers": [{"address": "s", "port": "n", "method": "s", "password": "s", "uot": "b",
                                 "UoTVersion": "n", "email": "s", "level": "n"}]},
    "socks": {"servers": [{"address": "s", "port": "n", "users": [{"user": "s", "pass": "s", "level": "n"}]}]},
    "http": {"servers": [{"address": "s", "port": "n", "users": [{"user": "s", "pass": "s"}]}]},
    "wireguard": {"secretKey": "s", "address": ["s"],
                  "peers": [{"publicKey": "s", "preSharedKey": "s", "endpoint": "s", "allowedIPs": ["s"],
                             "keepAlive": "n"}],
                  "mtu": "n", "reserved": ["n"], "workers": "n", "domainStrategy": "s", "noKernelTun": "b"},
    "freedom": {"domainStrategy": "s", "userLevel": "n", "fragment": {"packets": "s", "length": "s", "interval": "s"},
                "noises": [{"type": "s", "packet": "s", "delay": "s"}]},
    "blackhole": {"response": {"type": "s"}},
    "dns": {"network": "s", "address": "s", "port": "n", "nonIPQuery": "s", "blockTypes": ["n"]}}


def x_outbound_shape(protocol):
    return {"tag": "s", "protocol": "s", "settings": X_SETTINGS[protocol], "streamSettings": X_STREAM,
            "proxySettings": {"tag": "s", "transportLayer": "b"},
            "mux": {"enabled": "b", "concurrency": "n", "xudpConcurrency": "n", "xudpProxyUDP443": "s"}}


# A realistic export (what v2rayN hands out): every protocol the shape has, the keys panels write (alterId, email,
# show, allowInsecure, sockopt), the api/stats/policy block, routing rules and dns servers with an object entry.
# Only srv.example and tr.example resolve under the test's getent stub; the rest are literals.
XRAY_PANEL = {
    "log": {"loglevel": "warning", "access": "", "error": ""},
    "remarks": "panel",
    "inbounds": [{"tag": "socks", "port": 10808, "listen": "0.0.0.0", "protocol": "socks",
                  "settings": {"auth": "noauth", "udp": True}},
                 {"tag": "api", "port": 10085, "listen": "127.0.0.1", "protocol": "dokodemo-door",
                  "settings": {"address": "127.0.0.1"}}],
    "api": {"tag": "api", "services": ["StatsService"]}, "stats": {},
    "policy": {"system": {"statsOutboundUplink": True, "statsOutboundDownlink": True}},
    "outbounds": [
        {"tag": "proxy", "protocol": "vless",
         "settings": {"vnext": [{"address": "srv.example", "port": 443,
                                 "users": [{"id": "11111111-2222-3333-4444-555555555555", "alterId": 0,
                                            "email": "t@t.tt", "security": "auto", "encryption": "none",
                                            "flow": "xtls-rprx-vision"}]}]},
         "streamSettings": {"network": "xhttp", "security": "reality",
                            "realitySettings": {"serverName": "cover.example", "fingerprint": "chrome",
                                                "show": False, "publicKey": "pk", "shortId": "0123", "spiderX": "/"},
                            "xhttpSettings": {"path": "/up", "host": "cover.example", "mode": "auto",
                                              "headers": {"X-Padding": "x"},
                                              "extra": {"xmux": {"maxConcurrency": "16-32", "maxConnections": 0,
                                                                 "cMaxReuseTimes": 0, "hMaxRequestTimes": "600-900",
                                                                 "hMaxReusableSecs": "1800-3000",
                                                                 "hKeepAlivePeriod": 0}}},
                            "sockopt": {"mark": 255, "tcpFastOpen": True}},
         "mux": {"enabled": False, "concurrency": -1}},
        {"tag": "vm", "protocol": "vmess",
         "settings": {"vnext": [{"address": "203.0.113.20", "port": 443,
                                 "users": [{"id": "11111111-2222-3333-4444-555555555555", "alterId": 0,
                                            "email": "t@t.tt", "security": "auto"}]}]},
         "streamSettings": {"network": "ws", "security": "tls",
                            "tlsSettings": {"allowInsecure": False, "serverName": "vm.example",
                                            "alpn": ["http/1.1"], "fingerprint": "chrome"},
                            "wsSettings": {"path": "/ws", "headers": {"Host": "vm.example"}}},
         "mux": {"enabled": True, "concurrency": 8, "xudpConcurrency": 16, "xudpProxyUDP443": "reject"}},
        {"tag": "tr", "protocol": "trojan",
         "settings": {"servers": [{"address": "tr.example", "port": 443, "email": "t@t.tt",
                                   "password": "11111111-2222-3333-4444-555555555555", "level": 0}]},
         "streamSettings": {"network": "grpc", "security": "tls",
                            "tlsSettings": {"allowInsecure": True, "serverName": "tr.example"},
                            "grpcSettings": {"serviceName": "svc", "multiMode": False, "idle_timeout": 60,
                                             "health_check_timeout": 20, "permit_without_stream": False,
                                             "initial_windows_size": 0}}},
        {"tag": "ss", "protocol": "shadowsocks",
         "settings": {"servers": [{"address": "203.0.113.21", "port": 8388, "method": "2022-blake3-aes-128-gcm",
                                   "password": "11111111-2222-3333-4444-555555555555", "email": "t@t.tt"}]},
         "streamSettings": {"network": "tcp", "tcpSettings": {"header": {"type": "none"}}}},
        {"tag": "direct", "protocol": "freedom", "settings": {"domainStrategy": "UseIP"}},
        {"tag": "block", "protocol": "blackhole", "settings": {"response": {"type": "http"}}},
        {"tag": "dns-out", "protocol": "dns", "settings": {"network": "tcp", "address": "1.1.1.1", "port": 53}}],
    "routing": {"domainStrategy": "IPIfNonMatch",
                "rules": [{"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
                          {"type": "field", "port": "53", "network": "udp", "outboundTag": "dns-out"},
                          {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"},
                          {"type": "field", "domain": ["geosite:category-ads-all"], "outboundTag": "block"}]},
    "dns": {"hosts": {"dns.google": "8.8.8.8"},
            "servers": ["1.1.1.1", {"address": "8.8.8.8", "port": 53, "domains": ["geosite:google"]}]}}

SING_BOX_RAW = {
    "log": {"level": "info"},
    "dns": {"servers": [{"type": "tls", "tag": "dot", "server": "1.1.1.1"}]},
    "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "0.0.0.0", "listen_port": 2080}],
    "outbounds": [{"type": "trojan", "tag": "proxy", "server": "tr.example", "server_port": 443,
                   "password": "11111111-2222-3333-4444-555555555555"},
                  {"type": "direct", "tag": "direct"}],
    "route": {"final": "proxy", "default_domain_resolver": "x"}}


class RawJson(ShellTest):
    """Raw Xray and sing-box configs: imported as they are, parsed strictly, and rebuilt at every start from what an
    allowlist accepts, so that only the device's own inbound listens (no SOCKS port on the LAN), every connection the
    engine makes carries the mark the kill switch lets out, server names are looked up by the core, and the engine
    checks and runs only the rebuilt file. Also "-" as the source: a link or a config on stdin."""

    UUID = '11111111-2222-3333-4444-555555555555'

    def setUp(self):
        super().setUp()
        import json
        self.json = json
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.store = self.tmp / 'vpn'
        self.ev = self.tmp / 'events'
        self.stub('ip', 'exit 0')
        self.stub('svc', 'exit 0')
        self.stub('nft', 'case "$1" in -f) cat >/dev/null; echo "nft -f" >> "$STUBLOG/events" ;; esac; exit 0')
        self.stub('getent', 'echo "getent $2" >> "$STUBLOG/events"\n'
                            'case $2 in srv.example) echo "203.0.113.5     STREAM $2" ;;'
                            ' tr.example) echo "203.0.113.6     STREAM $2" ;; esac')
        self.stub('xray', 'echo "$*" >> "$STUBLOG/xray.args"')
        self.stub('sing-box', 'echo "$*" >> "$STUBLOG/sing-box.args"')
        self.xray = self.tmp / 'xray.json'
        self.xray.write_text(json.dumps(XRAY_RAW))
        self.sb = self.tmp / 'sb.json'
        self.sb.write_text(json.dumps(SING_BOX_RAW))

    def env(self, **extra):
        base = dict(MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB,
                    MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt',
                    MU300_DISK=self.tmp / 'disk', MU300_VPN_SVC=self.stubs / 'svc')
        base.update(extra)
        return super().env(**base)

    def lib(self, shell, code):
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', MU300_LIB=1)

    def cli(self, shell, *args, stdin=None):
        return self.script(shell, BIN / 'mu300-vpn', *args, stdin=stdin)

    def fresh(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.tmp / 'run', ignore_errors=True)
        for p in ('events', 'xray.args', 'sing-box.args'):
            (self.tmp / p).unlink(missing_ok=True)

    def gen(self, shell, pid, pre=''):
        return self.lib(shell, f'{pre}profile_load {pid}; load_driver "$PTYPE"; XRAY="{self.stubs}/xray"; '
                               f'BIN="{self.stubs}/sing-box"; drv_gen')

    def test_xray_config_is_rewritten(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', self.xray, 'Raw')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'raw'), r.stderr)
            pdir = self.store / 'profiles/raw'
            self.assertEqual(self.kv(pdir / 'meta')['TYPE'], 'xray')
            self.assertEqual(stat.S_IMODE((pdir / 'config.json').stat().st_mode), 0o600)
            self.assertFalse((pdir / 'uri').exists())
            r = self.gen(shell, 'raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = self.json.loads((self.tmp / 'run/xray.json').read_text())
            self.assertEqual(cfg['inbounds'], [{"tag": "socks-in", "listen": "127.0.0.1", "port": 10808,
                                                "protocol": "socks",
                                                "settings": {"auth": "noauth", "udp": True, "ip": "127.0.0.1"}}])
            self.assertEqual(cfg['log'], {"loglevel": "warning", "access": "none"})
            for out in cfg['outbounds']:
                self.assertEqual(out['streamSettings']['sockopt']['mark'], 720, out['tag'])
            proxy, direct = cfg['outbounds']
            self.assertEqual(proxy['settings']['vnext'][0]['address'], '203.0.113.5')
            self.assertNotIn('_name', proxy['settings']['vnext'][0])
            self.assertEqual(proxy['streamSettings']['tlsSettings'], {'alpn': ['h2'], 'serverName': 'srv.example'})
            # nothing is added to an outbound that has no servers
            self.assertNotIn('settings', direct)
            self.assertEqual(cfg['routing'], XRAY_RAW['routing'])
            self.assertEqual((self.tmp / 'run/server-ip').read_text().split(), ['203.0.113.5'])
            self.assertIn(f'run -test -c {self.tmp}/run/xray.json', (self.tmp / 'xray.args').read_text())
            self.assertTrue((self.tmp / 'run/hev.yml').exists())
            self.assertNotIn(self.UUID, r.stdout + r.stderr)
            r = self.cli(shell, 'profile', 'show', 'raw')
            self.assertIn('server\tsrv.example:443', r.stdout.splitlines())
            r = self.cli(shell, 'check', 'raw')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'profile raw: OK'), r.stderr)
            self.assertNotIn(self.UUID, r.stdout + r.stderr)

    def test_xray_names_kept_literals_and_the_resolve_window(self):
        raw = dict(XRAY_RAW)
        raw['outbounds'] = [
            {"protocol": "vless", "settings": {"vnext": [{"address": "srv.example", "port": 443, "users": []}]},
             "streamSettings": {"security": "reality", "realitySettings": {"serverName": "cover.example"}}},
            {"tag": "direct", "protocol": "trojan",
             "settings": {"servers": [{"address": "tr.example", "port": 443, "password": "x"},
                                      {"address": "198.51.100.7", "port": 443, "password": "y"}]},
             "streamSettings": {"security": "tls"}}]
        self.xray.write_text(self.json.dumps(raw))
        for shell in self.each_shell():
            self.fresh()
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            # behind the kill switch: one window around both lookups
            r = self.gen(shell, 'raw', 'ENABLE=1; KILL_SWITCH=1; ')
            self.assertEqual(r.returncode, 0, r.stderr)
            ev = self.ev.read_text().splitlines()
            self.assertEqual(ev, ['nft -f', 'getent srv.example', 'getent tr.example', 'nft -f'])
            cfg = self.json.loads((self.tmp / 'run/xray.json').read_text())
            vl, tr = cfg['outbounds']
            # a serverName the config has is its own
            self.assertEqual(vl['streamSettings']['realitySettings']['serverName'], 'cover.example')
            self.assertEqual(tr['streamSettings']['tlsSettings']['serverName'], 'tr.example')
            self.assertEqual([s['address'] for s in tr['settings']['servers']], ['203.0.113.6', '198.51.100.7'])
            self.assertEqual(sorted((self.tmp / 'run/server-ip').read_text().split()),
                             ['198.51.100.7', '203.0.113.5', '203.0.113.6'])
            # a name that does not resolve: nothing is written to run, and the kill switch is back
            self.fresh()
            raw2 = dict(XRAY_RAW, outbounds=[{"protocol": "vless", "settings": {"vnext": [
                {"address": "nx.example", "port": 1, "users": []}]}}, {"tag": "direct", "protocol": "freedom"}])
            self.xray.write_text(self.json.dumps(raw2))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            r = self.gen(shell, 'raw', 'ENABLE=1; KILL_SWITCH=1; ')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('cannot resolve the VPN server nx.example', r.stderr)
            self.assertEqual(self.ev.read_text().splitlines(), ['nft -f', 'getent nx.example', 'nft -f'])
            self.xray.write_text(self.json.dumps(raw))

    def test_sing_box_config_is_rewritten(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', self.sb, 'SB')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'sb'), r.stderr)
            self.assertEqual(self.kv(self.store / 'profiles/sb/meta')['TYPE'], 'sing-box')
            r = self.gen(shell, 'sb')
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = self.json.loads((self.tmp / 'run/config.json').read_text())
            self.assertEqual(cfg['inbounds'], [{"type": "tun", "tag": "tun-in", "stack": "gvisor",
                                                "interface_name": "sbtun", "address": ["172.19.0.1/30"],
                                                "mtu": 1400, "auto_route": True, "strict_route": True,
                                                "route_exclude_address": ["192.168.77.0/24"]}])
            self.assertEqual(cfg['route']['default_mark'], 720)
            self.assertIs(cfg['route']['auto_detect_interface'], True)
            self.assertEqual(cfg['route']['final'], 'proxy')
            # the config's own resolver is kept
            self.assertEqual(cfg['route']['default_domain_resolver'], 'x')
            self.assertEqual(cfg['dns']['servers'], SING_BOX_RAW['dns']['servers'] +
                             [{"type": "udp", "tag": "mu300-bootstrap", "server": "1.1.1.1"}])
            self.assertEqual(cfg['outbounds'], SING_BOX_RAW['outbounds'])
            self.assertIn(f'check -c {self.tmp}/run/config.json', (self.tmp / 'sing-box.args').read_text())
            self.assertNotIn(self.UUID, r.stdout + r.stderr)
            # without a resolver of its own, ours
            raw = dict(SING_BOX_RAW, route={"final": "proxy"})
            raw.pop('dns')
            self.sb.write_text(self.json.dumps(raw))
            self.assertEqual(self.cli(shell, 'profile', 'edit', 'sb', self.sb).returncode, 0)
            self.assertEqual(self.gen(shell, 'sb').returncode, 0)
            cfg = self.json.loads((self.tmp / 'run/config.json').read_text())
            self.assertEqual(cfg['route']['default_domain_resolver'], 'mu300-bootstrap')
            self.assertEqual(cfg['dns']['servers'], [{"type": "udp", "tag": "mu300-bootstrap", "server": "1.1.1.1"}])
            self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    @staticmethod
    def fold(key):
        """A key as the drivers' mu_fold compares it, and as Go's decoder matches it to a field: ASCII lowercased,
        after the long s and the Kelvin sign, which Go folds onto "s" and "k"."""
        key = key.replace('\u017f', 's').replace('\u212a', 'k')
        return ''.join(c.lower() if c.isascii() else c for c in key)

    def listeners(self, node, path=''):
        """Every listen address, listen port and controller in a generated config, wherever it sits and however
        its key is spelled, as (path, value)."""
        found = []
        if isinstance(node, dict):
            for k, v in node.items():
                if self.fold(k) in ('listen', 'listen_port', 'external_controller'):
                    found.append((f'{path}.{k}', v))
                found += self.listeners(v, f'{path}.{k}')
        elif isinstance(node, list):
            for i, v in enumerate(node):
                found += self.listeners(v, f'{path}[{i}]')
        return found

    def refused(self, shell, path, raw, *names):
        """The config (a dict, or the file's text as it is) is refused at import, naming each key in names, with no
        credential in the output and no profile left behind."""
        path.write_text(raw if isinstance(raw, str) else self.json.dumps(raw))
        self.fresh()
        r = self.cli(shell, 'profile', 'import', path, 'Raw')
        self.assertNotEqual(r.returncode, 0, (shell, raw))
        for n in names:
            self.assertIn(n, r.stderr, (shell, raw))
        self.assertNotIn(self.UUID, r.stdout + r.stderr)
        self.assertFalse((self.store / 'profiles/raw').exists())
        return r

    def test_xray_only_allowed_keys_reach_xray(self):
        # Everything in this config that listens, exposes control or writes a file is dropped; what a config may
        # carry (outbounds, routing, dns, fakedns, observatory) comes through unchanged.
        dns = {"servers": ["1.1.1.1", {"address": "8.8.8.8", "domains": ["geosite:google"]}]}
        raw = dict(XRAY_RAW,
                   log={"loglevel": "debug", "access": "/etc/passwd-log", "error": "/etc/err-log"},
                   inbounds=[{"tag": "api", "listen": "0.0.0.0", "port": 10085, "protocol": "dokodemo-door",
                              "settings": {"address": "127.0.0.1"}},
                             {"tag": "s", "listen": "0.0.0.0", "port": 1080, "protocol": "socks"}],
                   api={"tag": "api", "listen": "0.0.0.0:10086", "services": ["HandlerService", "StatsService"]},
                   stats={}, metrics={"tag": "metrics", "listen": "0.0.0.0:11111"},
                   policy={"system": {"statsInboundUplink": True}}, remarks="panel",
                   dns=dns, fakedns=[{"ipPool": "198.18.0.0/15", "poolSize": 65535}],
                   observatory={"subjectSelector": ["proxy"]},
                   routing={"domainStrategy": "AsIs",
                            "rules": [{"type": "field", "inboundTag": ["api"], "outboundTag": "api"},
                                      {"type": "field", "ip": ["geoip:private"], "outboundTag": "direct"}]})
        self.xray.write_text(self.json.dumps(raw))
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', self.xray, 'Raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.gen(shell, 'raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (self.tmp / 'run/xray.json').read_text()
            cfg = self.json.loads(text)
            self.assertEqual(sorted(cfg), ['dns', 'fakedns', 'inbounds', 'log', 'observatory', 'outbounds',
                                           'routing'])
            self.assertEqual([(i['protocol'], i['listen']) for i in cfg['inbounds']], [('socks', '127.0.0.1')])
            self.assertEqual(cfg['log'], {"loglevel": "warning", "access": "none"})
            self.assertEqual((cfg['dns'], cfg['fakedns'], cfg['observatory']),
                             (dns, raw['fakedns'], raw['observatory']))
            # the rule that led to the API's handler went with it; the config's own routing stays
            self.assertEqual(cfg['routing'], {"domainStrategy": "AsIs", "rules": [raw['routing']['rules'][1]]})
            self.assertEqual([o['protocol'] for o in cfg['outbounds']], ['vless', 'freedom'])
            self.assertNotIn('/etc/', text)
            self.assertNotIn('dokodemo-door', text)
            self.assertEqual(self.listeners(cfg), [('.inbounds[0].listen', '127.0.0.1')])
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_xray_other_keys_refuse_the_config(self):
        for shell in self.each_shell():
            self.refused(shell, self.xray, dict(XRAY_RAW, reverse={"portals": [{"tag": "p", "domain": "r.example"}]}),
                         'reverse')
            self.refused(shell, self.xray, dict(XRAY_RAW, transport={}, someFutureListener={"listen": "0.0.0.0"}),
                         'transport', 'someFutureListener')
            # a key name is printed only as printable characters, never as the file had it
            r = self.refused(shell, self.xray, dict(XRAY_RAW, **{"x\u001b[31m": 1}))
            self.assertNotIn('\x1b', r.stderr)
            # a config.json that changed on disk after the import is refused at start too
            self.fresh()
            self.xray.write_text(self.json.dumps(XRAY_RAW))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            (self.store / 'profiles/raw/config.json').write_text(self.json.dumps(dict(XRAY_RAW, reverse={})))
            r = self.gen(shell, 'raw')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('reverse', r.stderr)
            self.assertFalse((self.tmp / 'run/xray.json').exists())
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_sing_box_only_allowed_keys_reach_sing_box(self):
        route = {"rules": [{"ip_is_private": True, "outbound": "direct"}],
                 "rule_set": [{"tag": "ads", "type": "remote", "format": "binary", "url": "https://r.example/a.srs"}],
                 "final": "proxy", "default_domain_resolver": "x", "default_interface": "wlan0"}
        raw = dict(SING_BOX_RAW, route=route,
                   log={"level": "debug", "output": "/etc/x.log"},
                   inbounds=[{"type": "mixed", "tag": "m", "listen": "::", "listen_port": 2080}],
                   experimental={"clash_api": {"external_controller": "0.0.0.0:9090", "secret": "s"},
                                 "v2ray_api": {"listen": "0.0.0.0:8080"},
                                 "cache_file": {"enabled": True, "path": "/etc/x.db"},
                                 "debug": {"listen": "0.0.0.0:6060"}},
                   endpoints=[{"type": "wireguard", "tag": "wg", "listen_port": 51820, "address": ["10.0.0.2/32"],
                               "private_key": "k", "peers": []}])
        self.sb.write_text(self.json.dumps(raw))
        for shell in self.each_shell():
            self.fresh()
            self.assertEqual(self.cli(shell, 'profile', 'import', self.sb, 'SB').returncode, 0)
            r = self.gen(shell, 'sb')
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (self.tmp / 'run/config.json').read_text()
            cfg = self.json.loads(text)
            self.assertEqual(sorted(cfg), ['dns', 'endpoints', 'inbounds', 'log', 'outbounds', 'route'])
            self.assertEqual([i['type'] for i in cfg['inbounds']], ['tun'])
            self.assertEqual(cfg['log'], {"level": "warn", "timestamp": False})
            self.assertEqual(cfg['outbounds'], SING_BOX_RAW['outbounds'])
            self.assertEqual(cfg['dns']['servers'][:-1], SING_BOX_RAW['dns']['servers'])
            # a connection arriving through the endpoint is rejected first, then the config's own rules
            self.assertEqual(cfg['route']['rules'][0], {"inbound": ["wg"], "action": "reject"})
            self.assertEqual({k: cfg['route'][k] for k in ('rules', 'rule_set', 'final', 'default_domain_resolver')},
                             dict({k: route[k] for k in ('rules', 'rule_set', 'final', 'default_domain_resolver')},
                                  rules=[{"inbound": ["wg"], "action": "reject"}] + route['rules']))
            self.assertNotIn('default_interface', cfg['route'])
            # a WireGuard endpoint dials out from a port the kernel picks, and makes no interface of its own
            self.assertEqual(cfg['endpoints'], [{"type": "wireguard", "tag": "wg", "address": ["10.0.0.2/32"],
                                                 "private_key": "k", "peers": [], "system": False}])
            self.assertNotIn('/etc/', text)
            self.assertNotIn('9090', text)
            self.assertNotIn('8080', text)
            self.assertEqual(self.listeners(cfg), [])
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_sing_box_other_keys_refuse_the_config(self):
        for shell in self.each_shell():
            self.refused(shell, self.sb, dict(SING_BOX_RAW, services=[{"type": "ssm-api", "listen": "0.0.0.0"}]),
                         'services')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, ntp={"enabled": True}, certificate={}),
                         'ntp', 'certificate')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, endpoints=[{"type": "tailscale", "tag": "ts"}]),
                         'not WireGuard')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, route={"final": "proxy", "find_process": True}),
                         'route', 'find_process')
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_listener_guard(self):
        # The check behind the rewrites: a generated file with any listener but our loopback one is refused, so a
        # later change to a rewrite that let one through fails closed instead of opening a port.
        f = self.tmp / 'guard.json'
        for shell in self.each_shell():
            for doc, ok in (({"inbounds": [{"listen": "127.0.0.1"}]}, True),
                            ({"outbounds": []}, True),
                            ({"inbounds": [{"listen": "0.0.0.0"}]}, False),
                            ({"a": [{"b": {"listen": "::"}}]}, False),
                            ({"endpoints": [{"listen_port": 51820}]}, False),
                            ({"experimental": {"clash_api": {"external_controller": "127.0.0.1:9090"}}}, False),
                            # no listen_port at all, even next to a loopback listen
                            ({"inbounds": [{"listen": "127.0.0.1", "listen_port": 1080}]}, False),
                            # keys are matched as the engines match them, without regard to case
                            ({"a": {"Listen": "0.0.0.0"}}, False),
                            ({"a": {"LISTEN": "127.0.0.1"}}, True),
                            ({"a": {"Listen_Port": 1}}, False),
                            ({"a": {"li\u017ften": "0.0.0.0"}}, False)):
                f.write_text(self.json.dumps(doc))
                r = self.lib(shell, f'json_listens_loopback_only "{f}"')
                self.assertEqual(r.returncode == 0, ok, (shell, doc, r.stderr))

    def test_socket_options_are_ours(self):
        # A raw config's own socket options are removed wherever they sit; the mark is ours.
        out = {"tag": "proxy", "protocol": "vless",
               "settings": {"vnext": [{"address": "srv.example", "port": 443,
                                       "users": [{"id": self.UUID, "encryption": "none"}]}]},
               "sendThrough": "192.168.77.1",
               "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": {"serverName": "srv.example"},
                                  "sockopt": {"mark": 720, "interface": "wlan0"},
                                  "xhttpSettings": {"path": "/x", "SockOpt": {"mark": 1}}}}
        chained = {"tag": "chained", "protocol": "trojan",
                   "settings": {"servers": [{"address": "203.0.113.9", "port": 443, "password": self.UUID}]},
                   "streamSettings": {"sockopt": {"dialerProxy": "proxy", "interface": "wlan0"}}}
        wg = {"tag": "wg", "protocol": "wireguard", "settings": {"secretKey": "k", "peers": []}}
        raw = dict(XRAY_RAW, outbounds=[out, chained, wg, {"tag": "direct", "protocol": "freedom"}])
        sb = dict(SING_BOX_RAW,
                  outbounds=[dict(SING_BOX_RAW['outbounds'][0], routing_mark=720, bind_interface="wlan0",
                                  inet4_bind_address="192.168.77.1", Reuse_Addr=True,
                                  tls={"enabled": True, "tcp_fast_open": True}),
                             {"type": "direct", "tag": "direct", "netns": "/run/netns/x"}],
                  dns={"servers": [{"type": "tls", "tag": "dot", "server": "1.1.1.1", "bind_interface": "wlan0",
                                    "detour": "proxy"}]})
        for shell in self.each_shell():
            self.fresh()
            self.xray.write_text(self.json.dumps(raw))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            r = self.gen(shell, 'raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            cfg = self.json.loads((self.tmp / 'run/xray.json').read_text())
            o, c, w, d = cfg['outbounds']
            self.assertEqual(o['streamSettings']['sockopt'], {"mark": 720})
            self.assertNotIn('sendThrough', o)
            # a transport's path is kept: it is a URL path, not a file
            self.assertEqual(o['streamSettings']['xhttpSettings'], {"path": "/x"})
            # dialerProxy only chains through the config's own outbound, so it stays
            self.assertEqual(c['streamSettings']['sockopt'], {"mark": 720, "dialerProxy": "proxy"})
            self.assertEqual(d['streamSettings']['sockopt'], {"mark": 720})
            self.assertIs(w['settings']['noKernelTun'], True)
            self.assertFalse((self.tmp / 'run/xray.base.json').exists())
            self.sb.write_text(self.json.dumps(sb))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.sb, 'SB').returncode, 0)
            r = self.gen(shell, 'sb')
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (self.tmp / 'run/config.json').read_text()
            cfg = self.json.loads(text)
            for k in ('routing_mark', 'bind_interface', 'inet4_bind_address', 'Reuse_Addr', 'tcp_fast_open', 'netns',
                      'wlan0'):
                self.assertNotIn(k, text)
            self.assertEqual(cfg['outbounds'][0], dict(SING_BOX_RAW['outbounds'][0], tls={"enabled": True}))
            self.assertEqual(cfg['dns']['servers'][0], {"type": "tls", "tag": "dot", "server": "1.1.1.1",
                                                        "detour": "proxy"})
            self.assertEqual(cfg['route']['default_mark'], 720)
        self.xray.write_text(self.json.dumps(XRAY_RAW))
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_key_log_and_key_files_are_refused(self):
        # An engine run as root must not write a file of the config's choosing (the TLS key log) or read a key from a
        # path of its choosing: panels put keys inline.
        def xout(**stream):
            o = dict(XRAY_RAW['outbounds'][0])
            o['streamSettings'] = dict(o['streamSettings'], **stream)
            return dict(XRAY_RAW, outbounds=[o, XRAY_RAW['outbounds'][1]])
        def sout(**extra):
            return dict(SING_BOX_RAW, outbounds=[dict(SING_BOX_RAW['outbounds'][0], **extra),
                                                 SING_BOX_RAW['outbounds'][1]])
        for shell in self.each_shell():
            self.refused(shell, self.xray, xout(tlsSettings={"masterKeyLog": "/tmp/keys"}), 'masterkeylog')
            self.refused(shell, self.xray, xout(security="reality", realitySettings={"MasterKeyLog": "/tmp/keys"}),
                         'masterkeylog')
            self.refused(shell, self.xray, xout(tlsSettings={"certificates": [{"keyFile": "/etc/k", "usage": "x"}]}),
                         'keyfile')
            self.refused(shell, self.xray, xout(tlsSettings={"certificates": [{"certificateFile": "/etc/c"}]}),
                         'certificatefile')
            self.refused(shell, self.sb, sout(tls={"enabled": True, "client_key_path": "/etc/k"}), 'client_key_path')
            self.refused(shell, self.sb, sout(tls={"enabled": True, "ech": {"private_key_path": "/etc/k"}}),
                         'private_key_path')
            r = self.refused(shell, self.xray, xout(tlsSettings={"masterKeyLog": "/tmp/SECRETPATH"}))
            self.assertNotIn('SECRETPATH', r.stderr)
        self.xray.write_text(self.json.dumps(XRAY_RAW))
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_a_unix_socket_dialer_is_refused(self):
        def xout(**stream):
            o = dict(XRAY_RAW['outbounds'][0])
            o['streamSettings'] = dict(o['streamSettings'], **stream)
            return dict(XRAY_RAW, outbounds=[o, XRAY_RAW['outbounds'][1]])
        for shell in self.each_shell():
            self.refused(shell, self.xray, xout(network="domainsocket"), 'domainsocket')
            self.refused(shell, self.xray, xout(network="DomainSocket"), 'domainsocket')
            self.refused(shell, self.xray, xout(network="ds"), 'domainsocket')
            self.refused(shell, self.xray, xout(dsSettings={"path": "/run/x.sock"}), 'dssettings')
            # a transport that is not a socket is still fine
            self.fresh()
            self.xray.write_text(self.json.dumps(xout(network="ws")))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_every_nested_dialer_carries_the_mark(self):
        # The config's socket options go in any spelling Xray would read them in (SockOpt is sockopt to it), and
        # ours are written in their place: on the outbound and on xhttp's download dialer.
        out = dict(XRAY_RAW['outbounds'][0])
        out['streamSettings'] = {"network": "xhttp", "security": "tls", "SockOpt": {"Mark": 1, "interface": "wlan0"},
                                 "xhttpSettings": {"path": "/x", "extra": {
            "downloadSettings": {"address": "srv.example", "port": 443, "network": "xhttp",
                                 "SockOpt": {"interface": "wlan0"}, "security": "tls"}}}}
        raw = dict(XRAY_RAW, outbounds=[out, XRAY_RAW['outbounds'][1]])
        for shell in self.each_shell():
            self.fresh()
            self.xray.write_text(self.json.dumps(raw))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            r = self.gen(shell, 'raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (self.tmp / 'run/xray.json').read_text()
            cfg = self.json.loads(text)
            ss = cfg['outbounds'][0]['streamSettings']
            self.assertEqual(ss['sockopt'], {"mark": 720})
            dl = ss['xhttpSettings']['extra']['downloadSettings']
            self.assertEqual(dl['sockopt'], {"mark": 720})
            self.assertNotIn('wlan0', text)
            self.assertNotIn('SockOpt', text)
            self.assertNotIn('Mark', text)
            # a streamSettings inside downloadSettings is not something Xray reads: refused by name, not marked
            bad = self.json.loads(self.json.dumps(raw))
            bad['outbounds'][0]['streamSettings']['xhttpSettings']['extra']['downloadSettings']['streamSettings'] = {}
            self.refused(shell, self.xray, bad, 'downloadSettings.streamSettings')
            # DownloadSettings (any other spelling) would be read by Xray, not by the mark: refused
            bad = self.json.loads(self.json.dumps(raw))
            x = bad['outbounds'][0]['streamSettings']['xhttpSettings']['extra']
            x['DownloadSettings'] = x.pop('downloadSettings')
            self.refused(shell, self.xray, bad, 'downloadSettings')
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_keys_are_the_shapes_named_exactly(self):
        # Xray matches a key to a field without regard to case, so a key that is one of the shape's names in another
        # spelling is refused, naming the shape's key: it would be that field to Xray and nothing to the checks.
        # (the key is alone in its spelling: next to the exact one, json_strict refuses the pair first)
        o = XRAY_RAW['outbounds'][0]
        for shell in self.each_shell():
            for extra, name in (({"Mark": 1}, 'mark'), ({"Settings": {}}, 'settings'),
                                ({"StreamSettings": {}}, 'streamSettings'), ({"Protocol": "vless"}, 'protocol'),
                                ({"streamSettings": {"Network": "ws"}}, 'network'),
                                ({"streamSettings": {"xhttpSettings": {"extra": {"downloadsettings": {}}}}},
                                 'downloadSettings')):
                p = {k: v for k, v in o.items() if k != name}
                p.update(extra)
                self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[p, XRAY_RAW['outbounds'][1]]),
                             'a key spelled differently from ' + name)
            # a header name is data: the config's own, kept as it is
            ws = dict(o, streamSettings={"network": "ws", "wsSettings": {"headers": {"Host": "h", "HOST-x": "y"}}})
            self.xray.write_text(self.json.dumps(dict(XRAY_RAW, outbounds=[ws, XRAY_RAW['outbounds'][1]])))
            self.fresh()
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            self.assertEqual(self.gen(shell, 'raw').returncode, 0)
            cfg = self.json.loads((self.tmp / 'run/xray.json').read_text())
            self.assertEqual(cfg['outbounds'][0]['streamSettings']['wsSettings'], {"headers": {"Host": "h", "HOST-x": "y"}})
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_freedom_domain_strategy(self):
        o, d = XRAY_RAW['outbounds']
        for shell in self.each_shell():
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[o, dict(d, settings={"redirect": "127.0.0.1:22"})]),
                         'redirect')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[o, dict(d, settings={"domainStrategy": "x"})]),
                         'a domainStrategy it does not know')
            self.xray.write_text(self.json.dumps(dict(XRAY_RAW, outbounds=[o, dict(d, settings={
                "domainStrategy": "UseIP", "userLevel": 0,
                "fragment": {"packets": "tlshello", "length": "100-200", "interval": "10-20"}})])))
            self.fresh()
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            self.assertEqual(self.gen(shell, 'raw').returncode, 0)
            cfg = self.json.loads((self.tmp / 'run/xray.json').read_text())
            self.assertEqual(cfg['outbounds'][1]['settings'], {
                "domainStrategy": "UseIP", "userLevel": 0,
                "fragment": {"packets": "tlshello", "length": "100-200", "interval": "10-20"}})
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_unknown_keys_and_wrong_types_are_refused_by_name(self):
        o, d = XRAY_RAW['outbounds']
        def with_user(**u):
            return dict(o, settings={"vnext": [{"address": "srv.example", "port": 443, "users": [dict(
                {"id": self.UUID, "encryption": "none"}, **u)]}]})
        def with_stream(**s):
            return dict(o, streamSettings=dict(o['streamSettings'], **s))
        for shell in self.each_shell():
            for out, name in ((dict(o, protocol="hysteria"), 'outbound protocol hysteria'),
                              (dict(o, protocol=self.UUID), 'an outbound protocol it does not know'),
                              (dict(o, settings={"foo": 1}), 'key settings.foo'),
                              (with_user(bar=1), 'key settings.vnext[0].users[0].bar'),
                              (with_stream(certificates=[]), 'key streamSettings.certificates'),
                              (with_stream(tlsSettings={"certificates": [{"certificate": ["x"]}]}),
                               'key streamSettings.tlsSettings.certificates'),
                              (with_stream(tlsSettings={"disableSystemRoot": True}), 'disableSystemRoot'),
                              (dict(o, mux={"enabled": True, "foo": 1}), 'key mux.foo'),
                              (dict(o, sendThrough="0.0.0.0", unknownTop=1), 'key unknownTop'),
                              (dict(o, settings={"vnext": [{"address": "srv.example", "port": "443", "users": []}]}),
                               'key settings.vnext[0].port is not a number'),
                              (with_user(level="0"), 'users[0].level is not a number'),
                              (with_stream(tlsSettings={"alpn": "h2"}), 'tlsSettings.alpn is not a list'),
                              (with_stream(tlsSettings={"alpn": [1]}), 'tlsSettings.alpn[0] is not a string'),
                              (with_stream(network=1), 'key streamSettings.network is not a string'),
                              (with_stream(network="x"), 'a network it does not know'),
                              (with_stream(security="xtls"), 'a security it does not know'),
                              (with_stream(tcpSettings={"header": {"type": "srtp"}}), 'TCP header type'),
                              (dict(o, settings="x"), 'key settings is not an object'),
                              (dict(o, proxySettings={"tag": "direct", "transportLayer": "yes"}),
                               'key proxySettings.transportLayer is not a boolean')):
                r = self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[out, d]), name)
                self.assertNotIn('srv.example', r.stderr)
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def walk(self, node, shape, path):
        """node holds only keys of shape, each of shape's type; a map ("*") takes any key."""
        if isinstance(shape, str):
            if shape == 'n':
                self.assertNotIsInstance(node, bool, path)
            self.assertIsInstance(node, {'s': str, 'n': (int, float), 'b': bool, 'a': (str, int, float, bool),
                                         'h': (str, list)}[shape], path)
            if shape == 'h' and isinstance(node, list):
                for i, v in enumerate(node):
                    self.assertIsInstance(v, str, f'{path}[{i}]')
        elif isinstance(shape, list):
            self.assertIsInstance(node, list, path)
            for i, v in enumerate(node):
                self.walk(v, shape[0], f'{path}[{i}]')
        else:
            self.assertIsInstance(node, dict, path)
            for k, v in node.items():
                if '*' in shape:
                    self.walk(v, shape['*'], f'{path}.{k}')
                else:
                    self.assertIn(k, shape, path)
                    self.walk(v, shape[k], f'{path}.{k}')

    def test_a_panel_export_is_rebuilt_from_the_shape(self):
        # What a panel's export turns into: every outbound a new object holding exactly the shape's keys (the same
        # keys the config had, minus sockopt and allowInsecure), with our mark, the names resolved, and nothing else.
        def ours(node):
            if isinstance(node, dict):
                return {k: ours(v) for k, v in node.items() if self.fold(k) not in ('sockopt', 'allowinsecure')}
            return [ours(v) for v in node] if isinstance(node, list) else node
        want = []
        for o in XRAY_PANEL['outbounds']:
            o = ours(o)
            o.setdefault('streamSettings', {})['sockopt'] = {"mark": 720}
            want.append(o)
        want[0]['settings']['vnext'][0]['address'] = '203.0.113.5'
        want[2]['settings']['servers'][0]['address'] = '203.0.113.6'
        self.xray.write_text(self.json.dumps(XRAY_PANEL))
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', self.xray, 'Raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.gen(shell, 'raw')
            self.assertEqual(r.returncode, 0, r.stderr)
            text = (self.tmp / 'run/xray.json').read_text()
            cfg = self.json.loads(text)
            self.assertEqual(cfg['outbounds'], want)
            for i, o in enumerate(cfg['outbounds']):
                self.walk(o, x_outbound_shape(o['protocol']), f'outbounds[{i}]')
                self.assertEqual(o['streamSettings']['sockopt'], {"mark": 720}, o['tag'])
            for gone in ('allowInsecure', 'tcpFastOpen', '255', 'api', 'StatsService', 'remarks', 'dokodemo'):
                self.assertNotIn(gone, text)
            self.assertEqual(sorted(cfg), ['dns', 'inbounds', 'log', 'outbounds', 'routing'])
            self.assertEqual(cfg['routing'], dict(XRAY_PANEL['routing'], rules=XRAY_PANEL['routing']['rules'][1:]))
            self.assertEqual(cfg['dns'], XRAY_PANEL['dns'])
            self.assertEqual(self.listeners(cfg), [('.inbounds[0].listen', '127.0.0.1')])
            self.assertEqual(sorted((self.tmp / 'run/server-ip').read_text().split()),
                             ['203.0.113.20', '203.0.113.21', '203.0.113.5', '203.0.113.6'])
            # xray checks the rebuilt file, and only that
            self.assertEqual((self.tmp / 'xray.args').read_text().splitlines(),
                             [f'run -test -c {self.tmp}/run/xray.json'])
            self.assertNotIn(self.UUID, r.stdout + r.stderr)
        self.xray.write_text(self.json.dumps(XRAY_RAW))

    def test_the_size_cap_comes_before_any_full_read(self):
        # A file over 1 MiB is refused by the cap before the sniff or is_json reads it whole: the cap is the first
        # thing either runs, so a function that reads the file would show up in a stub that fails when called.
        big = self.tmp / 'big.json'
        big.write_text('{"outbounds": [], "pad": "' + 'x' * (1 << 20) + '"}')
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', big)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('1 MiB', r.stderr)
            r = self.lib(shell, f'. "{LIB}/uri.sh" 2>/dev/null; tr() {{ echo TR-RAN; }}; is_json "{big}" || echo no')
            self.assertEqual(r.stdout.strip(), 'no', r.stderr)
            self.assertNotIn('TR-RAN', r.stdout)

    def test_tags_must_be_the_configs_own(self):
        sb_out = SING_BOX_RAW['outbounds']
        xr_out = XRAY_RAW['outbounds']
        for shell in self.each_shell():
            # known: kept
            ok = dict(SING_BOX_RAW, outbounds=[dict(sb_out[0], detour="direct"), sb_out[1]])
            self.sb.write_text(self.json.dumps(ok))
            self.fresh()
            self.assertEqual(self.cli(shell, 'profile', 'import', self.sb, 'SB').returncode, 0)
            self.assertEqual(self.gen(shell, 'sb').returncode, 0)
            cfg = self.json.loads((self.tmp / 'run/config.json').read_text())
            self.assertEqual(cfg['outbounds'][0]['detour'], 'direct')
            # unknown: refused, the tag never printed
            for raw in (dict(SING_BOX_RAW, outbounds=[dict(sb_out[0], detour="nowhere-tag"), sb_out[1]]),
                        dict(SING_BOX_RAW, dns={"servers": [{"type": "udp", "tag": "d", "server": "1.1.1.1",
                                                             "detour": "nowhere-tag"}]}),
                        dict(SING_BOX_RAW, route={"final": "nowhere-tag"}),
                        dict(SING_BOX_RAW, route={"rules": [{"ip_is_private": True, "outbound": "nowhere-tag"}]}),
                        dict(SING_BOX_RAW, outbounds=sb_out + [{"type": "selector", "tag": "s",
                                                                "outbounds": ["proxy", "nowhere-tag"]}]),
                        dict(SING_BOX_RAW, dns={"servers": [{"type": "tls", "tag": "d", "server": "dns.example",
                                                             "domain_resolver": "nowhere-tag"}]})):
                r = self.refused(shell, self.sb, raw)
                self.assertNotIn('nowhere-tag', r.stderr)
            r = self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=[dict(sb_out[0], detour="x"), sb_out[1]]),
                             'detour')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[dict(xr_out[0], proxySettings={"tag": "nowhere"}),
                                                                     xr_out[1]]), 'proxySettings')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[
                dict(xr_out[0], streamSettings={"sockopt": {"dialerProxy": "nowhere"}}), xr_out[1]]), 'dialerProxy')
            self.refused(shell, self.xray, dict(XRAY_RAW, routing={"rules": [{"type": "field", "outboundTag": "x"}]}),
                         'outboundTag')
            ok = dict(XRAY_RAW, outbounds=[dict(xr_out[0], proxySettings={"tag": "direct"}), xr_out[1]])
            self.xray.write_text(self.json.dumps(ok))
            self.fresh()
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            self.assertEqual(self.gen(shell, 'raw').returncode, 0)
            cfg = self.json.loads((self.tmp / 'run/xray.json').read_text())
            self.assertEqual(cfg['outbounds'][0]['proxySettings'], {"tag": "direct"})
        self.xray.write_text(self.json.dumps(XRAY_RAW))
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_only_strict_json(self):
        # What jq and the engine's decoder could read differently is refused before anything else looks at it.
        x = self.json.dumps(XRAY_RAW)
        big = dict(XRAY_RAW, routing={"rules": [{"type": "field", "domain": ["d%07d.example" % i for i in
                                                                               range(60000)],
                                                 "outboundTag": "direct"}]})
        for shell in self.each_shell():
            # the same key twice, at the top and deeper, with a scalar or an object
            self.refused(shell, self.xray, x[:-1] + ', "outbounds": []}', 'twice')
            self.refused(shell, self.xray, x.replace('"protocol": "freedom"',
                                                     '"protocol": "freedom", "protocol": "dokodemo-door"'), 'twice')
            self.refused(shell, self.xray, x.replace('"streamSettings": {',
                                                     '"streamSettings": {"sockopt": {"mark": 1}}, "streamSettings": {'),
                         'twice')
            # keys that fold to one name, and a lone key spelled differently from one the checks read
            self.refused(shell, self.xray, x.replace('"protocol": "freedom"',
                                                     '"protocol": "freedom", "Protocol": "dokodemo-door"'),
                         'case', 'protocol')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=[dict(SING_BOX_RAW['outbounds'][0],
                                                                            Type="tor")]), 'case', 'type')
            self.refused(shell, self.xray, x.replace('"protocol": "freedom"', '"Protocol": "dokodemo-door"'),
                         'protocol')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=[dict(SING_BOX_RAW['outbounds'][0],
                                                                            transport={"Listen": "0.0.0.0"})]),
                         'listen')
            # Go folds the long s onto "s" and the Kelvin sign onto "k"
            self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=[dict(SING_BOX_RAW['outbounds'][0],
                                                                            **{"li\u017ften": "0.0.0.0"})]), 'listen')
            # not JSON: a comment, a trailing comma, a second document, nan, a top level that is not an object
            self.refused(shell, self.xray, x[:-1] + ' // a comment\n}', 'not one JSON object')
            self.refused(shell, self.xray, x[:-1] + ' /* a comment */}', 'not one JSON object')
            self.refused(shell, self.xray, x[:-1] + ',}', 'not one JSON object')
            self.refused(shell, self.xray, x.replace('"direct"}]', '"direct"},]', 1), 'not one JSON object')
            self.refused(shell, self.xray, x + x, 'not one JSON object')
            self.refused(shell, self.xray, x.replace('443', 'nan', 1), 'number')
            self.refused(shell, self.xray, '[' + x + ']')
            # larger than 1 MiB
            self.refused(shell, self.xray, big, '1 MiB')
            # a config.json that became a duplicate-key file on disk is refused at start too, and nothing is written
            self.fresh()
            self.xray.write_text(x)
            self.assertEqual(self.cli(shell, 'profile', 'import', self.xray, 'Raw').returncode, 0)
            (self.store / 'profiles/raw/config.json').write_text(x[:-1] + ', "outbounds": []}')
            r = self.gen(shell, 'raw')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('twice', r.stderr)
            self.assertEqual(list((self.tmp / 'run').iterdir()), [])
        self.assertGreater(len(self.json.dumps(big)), 1 << 20)
        self.xray.write_text(self.json.dumps(XRAY_RAW))
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_types_are_a_list(self):
        sb_out = SING_BOX_RAW['outbounds']
        xr_out = XRAY_RAW['outbounds']
        for shell in self.each_shell():
            self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=sb_out + [
                {"type": "tor", "tag": "t", "executable_path": "/bin/sh", "torrc": {"x": self.UUID}}]), 'tor')
            # a type it does not know is not printed: it is a value, and could be anything
            r = self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=sb_out + [{"type": self.UUID, "tag": "u"}]),
                             'does not know')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, outbounds=[sb_out[0], {"type": "direct", "tag": "direct",
                                                                                  "override_address": "10.0.0.1"}]),
                         'override_address')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, dns={"servers": [{"type": "tailscale", "tag": "ts",
                                                                              "endpoint": "ts"}]}), 'tailscale')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, dns={"servers": [{"tag": "old",
                                                                              "address": "tls://1.1.1.1"}]}),
                         'without a type')
            self.refused(shell, self.sb, dict(SING_BOX_RAW, route={"rules": [{"action": "route-options",
                                                                              "override_port": 53}]}), 'override_port')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=xr_out + [
                {"tag": "in", "protocol": "dokodemo-door", "settings": {"address": "127.0.0.1"}}]), 'dokodemo-door')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=xr_out + [{"tag": "l", "protocol": "Loopback"}]),
                         'loopback')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[xr_out[0], dict(xr_out[1], settings={
                "redirect": "127.0.0.1:22"})]), 'redirect')
            self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=[xr_out[0], dict(xr_out[1], settings={
                "reverse": {"tag": "r"}})]), 'reverse')
            r = self.refused(shell, self.xray, dict(XRAY_RAW, outbounds=xr_out + [{"tag": "u", "protocol": self.UUID}]),
                             'does not know')
        self.xray.write_text(self.json.dumps(XRAY_RAW))
        self.sb.write_text(self.json.dumps(SING_BOX_RAW))

    def test_import_sniffing(self):
        bad = self.tmp / 'bad.json'
        bad.write_text('{"outbounds": [ {"protocol": ')
        noout = self.tmp / 'noout.json'
        noout.write_text('{"inbounds": []}')
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', self.xray)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'xray'), r.stderr)
            r = self.cli(shell, 'profile', 'import', self.sb)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'sb'), r.stderr)
            lines = self.cli(shell, 'profile', 'list').stdout.splitlines()
            self.assertIn(' \txray\txray\txray', lines)
            self.assertIn(' \tsb\tsing-box\tsb', lines)
            for f, args in ((bad, ['import']), (noout, ['import']), (bad, ['add', 'xray', 'B']),
                            (bad, ['add', 'sing-box', 'B']), (self.xray, ['add', 'sing-box', 'B']),
                            (noout, ['add', 'xray', 'B'])):
                r = self.cli(shell, 'profile', *args, f)
                self.assertNotEqual(r.returncode, 0, (f, args))
                self.assertEqual(sorted(p.name for p in (self.store / 'profiles').iterdir()), ['sb', 'xray'],
                                 (f, args))
            # a raw profile is never run on sing-box in xray's place, whatever the kill switch says
            r = self.lib(shell, 'profile_load xray; load_driver xray; KILL_SWITCH=1; ENGINE=sing-box; '
                                'vless_on_sing_box; echo "driver=$DRIVER"')
            self.assertIn('driver=xray', r.stdout, r.stderr)

    def test_stdin(self):
        link = f'vless://{self.UUID}@vpn.example.com:443?security=tls&type=tcp#Home'
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', '-', stdin=link + '\n')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'home'), r.stderr)
            self.assertEqual((self.store / 'profiles/home/uri').read_text(), link + '\n')
            r = self.cli(shell, 'profile', 'import', '-', 'Raw', stdin=self.xray.read_text())
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'raw'), r.stderr)
            self.assertEqual(self.json.loads((self.store / 'profiles/raw/config.json').read_text()), XRAY_RAW)
            # with no name: the type, not the name of a temporary file
            r = self.cli(shell, 'profile', 'import', '-', stdin=self.sb.read_text())
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'sing-box'), r.stderr)
            r = self.cli(shell, 'profile', 'add', 'xray', 'Two', '-', stdin='  \r\n' + link + '\r\n\n')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'two'), r.stderr)
            self.assertEqual((self.store / 'profiles/two/uri').read_text(), link + '\n')
            # edit from stdin: the link replaced by a config, and back
            r = self.cli(shell, 'profile', 'edit', 'home', '-', stdin=self.xray.read_text())
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((self.store / 'profiles/home/config.json').exists())
            self.assertFalse((self.store / 'profiles/home/uri').exists())
            r = self.cli(shell, 'profile', 'edit', 'home', '-', stdin=link)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((self.store / 'profiles/home/uri').read_text(), link + '\n')
            self.assertFalse((self.store / 'profiles/home/config.json').exists())
            # refused: nothing on stdin, two links, garbage - and nothing of it left anywhere
            for data in ('', link + '\n' + link + '\n', 'garbage\n'):
                r = self.cli(shell, 'profile', 'import', '-', stdin=data)
                self.assertNotEqual(r.returncode, 0, repr(data))
                self.assertNotIn(self.UUID, r.stdout + r.stderr)
            self.assertEqual(sorted(p.name for p in (self.store / 'profiles').iterdir()),
                             ['home', 'raw', 'sing-box', 'two'])
            self.assertEqual([p.name for p in (self.tmp / 'run').iterdir()] if (self.tmp / 'run').exists() else [],
                             [])

    def kv(self, path):
        out = {}
        for line in path.read_text().splitlines():
            k, _, v = line.partition('=')
            out[k] = v.strip("'")
        return out


WG_PRIV = 'P' * 43 + '='
WG_PUB = 'B' * 43 + '='
WG_PSK = 'S' * 43 + '='
WG_CONF = f"""[Interface]
PrivateKey = {WG_PRIV}
Address = 10.7.0.2/32, fd00:7::2/128
DNS = 10.7.0.1, example.org
MTU = 1380
PostUp = iptables -A FORWARD -i %i -j ACCEPT
Table = off
ListenPort = 51821
FwMark = 0x1

[Peer]
PublicKey = {WG_PUB}
PresharedKey = {WG_PSK}
Endpoint = wg.example:51820
AllowedIPs = 0.0.0.0/0, ::/0
PersistentKeepalive = 25
"""


class WireGuard(ShellTest):
    """The wireguard driver: the wg-quick file is reduced to what wg setconf takes, the Endpoint name is looked up
    by the core, the interface is made with ip and marked with wg, and no key is ever printed."""

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.store = self.tmp / 'vpn'
        self.ev = self.tmp / 'events'
        self.ip_stub()
        self.stub('wg', 'echo "$*" >> "$STUBLOG/wg.log"\n'
                        'case "$*" in\n'
                        f'  "show wg-mu300 latest-handshakes") printf "{WG_PUB}\\t%s\\n" "$(( $(date +%s) - 30 ))" ;;\n'
                        f'  "show wg-mu300 transfer") printf "{WG_PUB}\\t100\\t200\\n" ;;\n'
                        'esac; exit 0')
        self.stub('svc', 'exit 0')
        self.stub('nft', 'case "$1" in -f) cat >/dev/null; echo "nft -f" >> "$STUBLOG/events" ;; esac; exit 0')
        self.stub('getent', 'echo "getent $2" >> "$STUBLOG/events"\n'
                            'case $2 in wg.example) echo "203.0.113.7     STREAM $2" ;; esac')
        self.src = self.tmp / 'x.conf'
        self.src.write_text(WG_CONF)

    def kv(self, path):
        out = {}
        for line in path.read_text().splitlines():
            k, _, v = line.partition('=')
            out[k] = v.strip("'")
        return out

    def iplog(self):
        # (sourcing mu300-vpn asks ip about the LAN too: only what the driver does is of interest)
        return [l for l in (self.tmp / 'ip.log').read_text().splitlines() if l.split()[0] in ('link', 'addr')]

    def ip_stub(self, kernel=True):
        # "link show" finds nothing (no tunnel yet); "link add ... type wireguard" works only on a kernel that has it
        add = 'exit 0' if kernel else 'exit 2'
        self.stub('ip', 'echo "$*" >> "$STUBLOG/ip.log"\n'
                        'case "$*" in\n'
                        '  "link show"*) exit 1 ;;\n'
                        f'  "link add"*) {add} ;;\n'
                        'esac; exit 0')

    def env(self, **extra):
        base = dict(MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB,
                    MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt',
                    MU300_DISK=self.tmp / 'disk', MU300_VPN_SVC=self.stubs / 'svc',
                    MU300_WG_SYSMOD=self.tmp / 'no-module')
        base.update(extra)
        return super().env(**base)

    def lib(self, shell, code):
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', MU300_LIB=1)

    def cli(self, shell, *args, stdin=None):
        return self.script(shell, BIN / 'mu300-vpn', *args, stdin=stdin)

    def fresh(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.tmp / 'run', ignore_errors=True)
        for p in ('events', 'ip.log', 'wg.log'):
            (self.tmp / p).unlink(missing_ok=True)

    def setup_profile(self, shell, text=WG_CONF):
        self.fresh()
        self.src.write_text(text)
        r = self.cli(shell, 'profile', 'import', self.src, 'Wg')
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'wg'), r.stderr)

    def run_lib(self, shell, code, pre=''):
        return self.lib(shell, f'{pre}profile_load wg; load_driver "$PTYPE"; {code}')

    def no_keys(self, r):
        for secret in (WG_PRIV, WG_PSK, 'PPPPPPPP', 'SSSSSSSS'):
            self.assertNotIn(secret, r.stdout + r.stderr)

    def test_import_sniffs_and_stores_0600(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            pdir = self.store / 'profiles/wg'
            self.assertEqual(self.kv(pdir / 'meta')['TYPE'], 'wireguard')
            self.assertEqual(stat.S_IMODE((pdir / 'wg.conf').stat().st_mode), 0o600)
            self.assertEqual((pdir / 'wg.conf').read_text(), WG_CONF)
            r = self.cli(shell, 'profile', 'show', 'wg')
            self.assertIn('server\twg.example:51820', r.stdout.splitlines())
            self.no_keys(r)
            r = self.cli(shell, 'check', 'wg')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'profile wg: OK'), r.stderr)
            self.no_keys(r)
            # the same from stdin, with the section and keys in any case
            self.fresh()
            r = self.cli(shell, 'profile', 'import', '-', 'Low',
                         stdin=WG_CONF.replace('[Interface]', '[interface]').replace('PrivateKey', 'PRIVATEKEY'))
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'low'), r.stderr)

    def test_gen_reduces_the_config(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.no_keys(r)
            run = self.tmp / 'run'
            gen = (run / 'wg.conf').read_text()
            # (a config opens no port, and the mark is ours, set by wg set)
            for gone in ('Address', 'DNS', 'MTU', 'PostUp', 'Table', 'iptables', 'wg.example', 'ListenPort', '51821',
                         'FwMark', '0x1'):
                self.assertNotIn(gone, gen)
            self.assertIn('Endpoint = 203.0.113.7:51820', gen.splitlines())
            for kept in (f'PrivateKey = {WG_PRIV}', f'PublicKey = {WG_PUB}', f'PresharedKey = {WG_PSK}',
                         'AllowedIPs = 0.0.0.0/0, ::/0', 'PersistentKeepalive = 25', '[Peer]'):
                self.assertIn(kept, gen.splitlines())
            self.assertEqual(stat.S_IMODE((run / 'wg.conf').stat().st_mode), 0o600)
            self.assertEqual((run / 'wg.addr').read_text().split(), ['10.7.0.2/32', 'fd00:7::2/128'])
            self.assertEqual((run / 'wg.mtu').read_text().strip(), '1380')
            self.assertEqual((run / 'dns').read_text().strip(), '10.7.0.1')
            self.assertEqual((run / 'server-ip').read_text().split(), ['203.0.113.7'])

    def test_keys_spelled_differently(self):
        text = (WG_CONF.replace('Address = ', 'address=').replace('DNS = ', 'dns\t=\t')
                .replace('MTU = 1380', 'mtu = 1400   # tuned').replace('PostUp', 'POSTUP')
                .replace('Endpoint = wg.example:51820', 'endpoint=[2001:db8::7]:51820'))
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            run = self.tmp / 'run'
            gen = (run / 'wg.conf').read_text()
            for gone in ('ddress', 'dns', 'mtu', 'POSTUP', 'iptables'):
                self.assertNotIn(gone, gen)
            # a literal address is kept, and nothing is looked up
            self.assertIn('endpoint = [2001:db8::7]:51820', gen.splitlines())
            self.assertEqual((run / 'server-ip').read_text().split(), ['2001:db8::7'])
            self.assertFalse(self.ev.exists())
            self.assertEqual((run / 'wg.mtu').read_text().strip(), '1400')
            self.assertEqual((run / 'dns').read_text().strip(), '10.7.0.1')

    def test_start_alive_stop(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            for p in ('ip.log', 'wg.log'):
                (self.tmp / p).unlink(missing_ok=True)
            r = self.run_lib(shell, 'drv_start && echo STARTED; echo "tun=$TUN"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('tunnel up on wg-mu300', r.stdout)
            self.assertIn('tun=wg-mu300', r.stdout)
            self.no_keys(r)
            ip = self.iplog()
            wg = (self.tmp / 'wg.log').read_text().splitlines()
            self.assertEqual(ip, ['link del wg-mu300', 'link add wg-mu300 type wireguard',
                                  'addr add 10.7.0.2/32 dev wg-mu300', 'link set wg-mu300 mtu 1380 up'])
            self.assertEqual(wg, [f'setconf wg-mu300 {self.tmp}/run/wg.conf', 'set wg-mu300 fwmark 0x2d0'])
            # with IPV6=1 the IPv6 address goes on too
            (self.tmp / 'ip.log').unlink()
            r = self.run_lib(shell, 'IPV6=1; drv_start')
            self.assertIn('addr add fd00:7::2/128 dev wg-mu300', (self.tmp / 'ip.log').read_text())
            # alive follows the interface; stop removes it and the runtime copy of the config
            r = self.run_lib(shell, 'drv_alive || echo "alive=$?"')
            self.assertIn('alive=1', r.stdout)
            (self.tmp / 'ip.log').unlink()
            r = self.run_lib(shell, 'drv_stop; echo "stop=$?"')
            self.assertIn('stop=0', r.stdout)
            self.assertEqual(self.iplog(), ['link del wg-mu300'])
            self.assertFalse((self.tmp / 'run/wg.conf').exists())

    def test_start_fails_closed(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            # a wg that rejects the config says so without quoting it
            self.stub('wg', f'echo "Key is not the correct length: {WG_PRIV}" >&2; exit 1')
            r = self.run_lib(shell, 'drv_start && echo STARTED')
            self.assertNotIn('STARTED', r.stdout)
            self.assertIn('wg setconf rejected the config', r.stderr)
            self.no_keys(r)
            self.stub('wg', 'exit 0')
            self.ip_stub(kernel=False)
            r = self.run_lib(shell, 'drv_start && echo STARTED')
            self.assertNotIn('STARTED', r.stdout)
            self.assertIn('cannot create wg-mu300', r.stderr)
            self.ip_stub()

    def test_check_warns_about_the_default_route(self):
        text = WG_CONF.replace('AllowedIPs = 0.0.0.0/0, ::/0', 'AllowedIPs = 10.0.0.0/8')
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            r = self.cli(shell, 'check', 'wg')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('0.0.0.0/0', r.stderr)
            self.assertIn('warning', r.stderr)
            self.no_keys(r)

    def test_refused_imports(self):
        cases = {
            'no PrivateKey': (WG_CONF.replace(f'PrivateKey = {WG_PRIV}\n', ''), 'no PrivateKey'),
            'no [Interface]': ('[Peer]\n' + WG_CONF.split('[Peer]\n')[1], 'no [Interface]'),
            'no peer': (WG_CONF.split('[Peer]')[0], 'no [Peer]'),
            'no peer key': (WG_CONF.replace(f'PublicKey = {WG_PUB}\n', ''), 'without a PublicKey'),
            'no endpoint': (WG_CONF.replace('Endpoint = wg.example:51820\n', ''), 'without an Endpoint'),
            'bad endpoint': (WG_CONF.replace('wg.example:51820', 'wg.example'), 'Endpoint that is not'),
            'option as host': (WG_CONF.replace('wg.example:51820', '-x:51820'), 'Endpoint that is not'),
            'bad key': (WG_CONF.replace(WG_PRIV, 'short'), 'PrivateKey that is not a WireGuard key'),
            'bad mtu': (WG_CONF.replace('1380', '12'), 'MTU'),
            'bad address': (WG_CONF.replace('10.7.0.2/32', '10.7.0.2;reboot'), 'Address'),
        }
        for shell in self.each_shell():
            for name, (text, msg) in cases.items():
                self.fresh()
                self.src.write_text(text)
                r = self.cli(shell, 'profile', 'add', 'wireguard', 'X', self.src)
                self.assertNotEqual(r.returncode, 0, name)
                self.assertIn(msg, r.stderr, name)
                self.no_keys(r)
                profiles = self.store / 'profiles'
                self.assertEqual(list(profiles.iterdir()) if profiles.exists() else [], [], name)

    def test_a_kernel_without_wireguard_fails_the_check(self):
        self.ip_stub(kernel=False)
        for shell in self.each_shell():
            self.fresh()
            r = self.cli(shell, 'profile', 'import', self.src, 'Wg')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('this kernel has no WireGuard', r.stderr)
            # the module is loaded: the probe is not needed
            (self.tmp / 'no-module').mkdir(exist_ok=True)
            r = self.cli(shell, 'profile', 'import', self.src, 'Wg')
            self.assertEqual(r.returncode, 0, r.stderr)
            (self.tmp / 'no-module').rmdir()

    def test_engines(self):
        for shell in self.each_shell():
            r = self.lib(shell, 'load_driver wireguard; echo "[$DRV_EXTRA] [$DRV_PKG] [$TUN] [$DRV_ROUTES]"; '
                                'drv_engines; drv_engines_ok && echo "ok=$?"')
            self.assertIn('[] [wireguard-tools] [wg-mu300] [core]', r.stdout)
            self.assertIn(f'{self.stubs}/wg', r.stdout.splitlines())
            # wg is there and the probe's temporary interface can be made
            self.assertIn('ok=0', r.stdout)
            self.assertIn('link add wg-mu300-t type wireguard', (self.tmp / 'ip.log').read_text())
            self.assertIn('link del wg-mu300-t', (self.tmp / 'ip.log').read_text())
            # no wg: not ok, whatever the kernel says
            (self.stubs / 'wg').rename(self.tmp / 'wg.away')
            r = self.lib(shell, 'load_driver wireguard; drv_engines_ok || echo "ok=$?"')
            (self.tmp / 'wg.away').rename(self.stubs / 'wg')
            self.assertIn('ok=1', r.stdout)

    def test_status_shows_no_keys(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'drv_status')
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = r.stdout.splitlines()
            self.assertEqual(len(lines), 2, r.stdout)
            self.assertRegex(lines[0], r'^handshake: (29|3\d)s ago$')
            self.assertEqual(lines[1], 'transfer: 100 bytes received, 200 bytes sent')
            self.no_keys(r)
            self.assertNotIn(WG_PUB, r.stdout + r.stderr)

    def test_names_are_looked_up_in_the_resolve_window(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'drv_gen', 'ENABLE=1; KILL_SWITCH=1; ')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.ev.read_text().splitlines(), ['nft -f', 'getent wg.example', 'nft -f'])
            # a name that does not resolve: nothing is written, and the kill switch is back
            self.fresh()
            self.src.write_text(WG_CONF.replace('wg.example', 'nx.example'))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.src, 'Wg').returncode, 0)
            r = self.run_lib(shell, 'drv_gen', 'ENABLE=1; KILL_SWITCH=1; ')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('cannot resolve the VPN server nx.example', r.stderr)
            self.assertEqual(self.ev.read_text().splitlines(), ['nft -f', 'getent nx.example', 'nft -f'])
            self.assertFalse((self.tmp / 'run/wg.conf').exists())


OVPN_CA = """<ca>
-----BEGIN CERTIFICATE-----
CAKEYCAKEYCAKEY
-----END CERTIFICATE-----
</ca>"""
OVPN_KEY = """<key>
-----BEGIN PRIVATE KEY-----
PRIVKEYPRIVKEY
-----END PRIVATE KEY-----
</key>"""
OVPN_TLS = """<tls-crypt>
#
# 2048 bit OpenVPN static key
#
-----BEGIN OpenVPN Static key V1-----
0123456789abcdefTLSKEY0123456789
-----END OpenVPN Static key V1-----
</tls-crypt>"""
# What a panel or easy-rsa export looks like: the DNS helper scripts, routes and DNS of its own, all left out.
OVPN_CONF = f"""client
dev tun0
proto udp
remote vpn.example 1194 udp
remote 198.51.100.2 443 tcp
up /etc/openvpn/update-resolv-conf
down /etc/openvpn/update-resolv-conf
script-security 2
redirect-gateway def1
route 10.0.0.0 255.0.0.0
dhcp-option DNS 192.0.2.53
auth-user-pass
nobind
cipher AES-256-GCM
remote-cert-tls server
verb 3
{OVPN_CA}
{OVPN_KEY}
{OVPN_TLS}
"""
# the directive names our generated config may contain
OVPN_WRITTEN = {'client', 'tls-client', 'pull', 'remote', 'remote-random', 'proto', 'port', 'resolv-retry', 'nobind',
                'float', 'persist-key', 'persist-tun', 'cipher', 'data-ciphers', 'data-ciphers-fallback', 'auth',
                'tls-version-min', 'tls-version-max', 'tls-cipher', 'tls-ciphersuites', 'tls-groups',
                'remote-cert-tls', 'remote-cert-eku', 'remote-cert-ku', 'verify-x509-name', 'key-direction',
                'compress', 'tun-mtu', 'mssfix', 'fragment', 'ping', 'ping-restart', 'keepalive',
                'explicit-exit-notify', 'server-poll-timeout', 'connect-retry', 'connect-retry-max', 'connect-timeout',
                'hand-window', 'auth-nocache', 'auth-retry', 'reneg-sec', 'sndbuf', 'rcvbuf', 'txqueuelen',
                'mute-replay-warnings'}
OVPN_BLOCKS = {'ca', 'cert', 'key', 'tls-auth', 'tls-crypt', 'tls-crypt-v2', 'dh', 'extra-certs', 'pkcs12'}


class OpenVpn(ShellTest):
    """The openvpn driver: the .ovpn is parsed into an allowlist and openvpn reads only the config we write, its
    names are looked up by the core, openvpn is started with our own options and up script, and no secret is
    printed."""

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.store = self.tmp / 'vpn'
        self.run_dir = self.tmp / 'run'
        self.ev = self.tmp / 'events'
        self.stub('ip', 'echo "$*" >> "$STUBLOG/ip.log"\nexit 0')
        self.stub('svc', 'exit 0')
        self.stub('nft', 'case "$1" in -f) cat >/dev/null; echo "nft -f" >> "$STUBLOG/events" ;; esac; exit 0')
        self.stub('getent', 'echo "getent $2" >> "$STUBLOG/events"\n'
                            'case $2 in vpn.example) echo "203.0.113.8     STREAM $2" ;; esac')
        # records its arguments, runs the --up script the way openvpn does, and stays until it is told to stop
        self.openvpn_stub()
        self.src = self.tmp / 'client.ovpn'
        self.src.write_text(OVPN_CONF)

    def openvpn_stub(self, body=None):
        self.stub('openvpn', body or (
            'printf "%s\\n" "$@" > "$STUBLOG/ovpn.args"\n'
            'while [ $# -gt 0 ]; do case $1 in --up) up=$2 ;; --setenv) export "$2=$3" ;; esac; shift; done\n'
            'foreign_option_1="dhcp-option DOMAIN x" foreign_option_2="dhcp-option DNS 10.8.0.1" '
            'foreign_option_3="dhcp-option DNS 10.8.0.9" "$up" tun-mu300 1500 1553 10.8.0.6 10.8.0.5 init || exit 3\n'
            'exec sleep 60'))

    def env(self, **extra):
        base = dict(MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.run_dir, MU300_VPN_LIB=LIB,
                    MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt',
                    MU300_DISK=self.tmp / 'disk', MU300_VPN_SVC=self.stubs / 'svc',
                    MU300_OPENWRT_RELEASE=self.tmp / 'no-openwrt')
        base.update(extra)
        return super().env(**base)

    def lib(self, shell, code, stdin=None):
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', stdin=stdin, MU300_LIB=1)

    def cli(self, shell, *args, stdin=None):
        return self.script(shell, BIN / 'mu300-vpn', *args, stdin=stdin)

    def fresh(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.run_dir, ignore_errors=True)
        for p in ('events', 'ip.log', 'ovpn.args'):
            (self.tmp / p).unlink(missing_ok=True)

    def setup_profile(self, shell, text=OVPN_CONF):
        self.fresh()
        if isinstance(text, bytes):
            self.src.write_bytes(text)
        else:
            self.src.write_text(text)
        r = self.cli(shell, 'profile', 'import', self.src, 'Vpn')
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'vpn'), r.stderr)

    def run_lib(self, shell, code, pre='', stdin=None):
        return self.lib(shell, f'{pre}profile_load vpn; load_driver "$PTYPE"; {code}', stdin=stdin)

    def refused(self, shell, text, msg=None, name=None):
        """imports TEXT, which must be refused (with MSG in the message), leaving no profile and no secret said"""
        self.fresh()
        if isinstance(text, bytes):
            self.src.write_bytes(text)
        else:
            self.src.write_text(text)
        r = self.cli(shell, 'profile', 'add', 'openvpn', 'X', self.src)
        self.assertNotEqual(r.returncode, 0, name or text)
        if msg:
            self.assertIn(msg, r.stderr, name or text)
        for secret in ('PRIVKEY', 'CAKEY', 'TLSKEY', 'hunter2', 'evil'):
            self.assertNotIn(secret, r.stdout + r.stderr, name or text)
        profiles = self.store / 'profiles'
        self.assertEqual(list(profiles.iterdir()) if profiles.exists() else [], [], name or text)
        return r

    def written(self):
        """the generated config, parsed: (directive lines as word lists, {block: body lines})"""
        dirs, blocks, op = [], {}, None
        for line in (self.run_dir / 'openvpn.conf').read_text().split('\n')[:-1]:
            if op:
                if line == f'</{op}>':
                    op = None
                else:
                    blocks[op].append(line)
                continue
            if line.startswith('<'):
                op = line[1:-1]
                self.assertEqual(line, f'<{op}>')
                self.assertIn(op, OVPN_BLOCKS)
                blocks[op] = []
                continue
            words = line.split()
            self.assertIn(words[0], OVPN_WRITTEN, line)
            dirs.append(words)
        self.assertIsNone(op)
        return dirs, blocks

    def test_import_sniffs_and_stores_0600(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            pdir = self.store / 'profiles/vpn'
            self.assertIn('TYPE=', (pdir / 'meta').read_text())
            self.assertIn('openvpn', (pdir / 'meta').read_text())
            self.assertEqual(stat.S_IMODE((pdir / 'client.ovpn').stat().st_mode), 0o600)
            self.assertEqual((pdir / 'client.ovpn').read_text(), OVPN_CONF)
            r = self.cli(shell, 'profile', 'show', 'vpn')
            self.assertIn('server\tvpn.example:1194', r.stdout.splitlines())
            r = self.cli(shell, 'check', 'vpn')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('profile vpn: OK', r.stdout)
            # the notes name directives, never values; the missing credentials are pointed out
            self.assertIn('not used', r.stderr)
            for name in ('up', 'down', 'script-security', 'redirect-gateway', 'route', 'dhcp-option'):
                self.assertIn(f' {name}', r.stderr)
            self.assertIn('OVPN_USER', r.stderr)
            for secret in ('PRIVKEY', 'CAKEY', 'TLSKEY', 'update-resolv-conf', '192.0.2.53', 'def1'):
                self.assertNotIn(secret, r.stdout + r.stderr)
            self.fresh()
            r = self.cli(shell, 'profile', 'import', '-', 'Low', stdin=OVPN_CONF)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'low'), r.stderr)

    def test_gen_writes_only_what_is_allowed(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            gen = (self.run_dir / 'openvpn.conf').read_text()
            self.assertEqual(stat.S_IMODE((self.run_dir / 'openvpn.conf').stat().st_mode), 0o600)
            for gone in ('dev', 'up ', 'down', 'script-security', 'redirect-gateway', 'route', 'dhcp-option',
                         'auth-user-pass', 'verb', 'vpn.example', 'update-resolv-conf'):
                self.assertNotIn(gone, gen)
            dirs, blocks = self.written()
            self.assertEqual(dirs, [['client'], ['proto', 'udp'], ['remote', '203.0.113.8', '1194', 'udp'],
                                    ['remote', '198.51.100.2', '443', 'tcp'], ['nobind'], ['cipher', 'AES-256-GCM'],
                                    ['remote-cert-tls', 'server']])
            # the blocks are the file's, byte for byte
            for block in (OVPN_CA, OVPN_KEY, OVPN_TLS):
                self.assertIn(block + '\n', gen)
            self.assertEqual(set(blocks), {'ca', 'key', 'tls-crypt'})
            self.assertEqual((self.run_dir / 'server-ip').read_text().split(), ['203.0.113.8', '198.51.100.2'])
            self.assertEqual(self.ev.read_text().split('\n')[:-1], ['getent vpn.example'])

    def test_directives_are_read_the_way_openvpn_reads_them(self):
        # quotes group a word, a leading "--" is allowed, "#" and ";" start a comment only at the start of a word,
        # and every argument is written again by us
        text = f'''  client\t
--nobind
"persist-key"
remote 'a.example' 443 tcp-client # the first server
remote 2001:db8::7 1194 udp6 ; the second
; comment
  # comment
verify-x509-name 'C=US, CN=srv #1; x' subject
cipher AES-256-GCM#not-a-comment-in-openvpn
keepalive 10 60
{OVPN_CA}
'''
        self.stub('getent', 'echo "getent $2" >> "$STUBLOG/events"\n'
                            'case $2 in a.example) echo "203.0.113.1     STREAM $2" ;; esac')
        for shell in self.each_shell():
            self.fresh()
            self.src.write_text(text)
            r = self.cli(shell, 'profile', 'import', self.src, 'Vpn')
            # "AES-256-GCM#not-a-comment..." is one word in openvpn, and not a cipher name
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('line 9: cipher takes one algorithm name', r.stderr)
            self.setup_profile(shell, text.replace('#not-a-comment-in-openvpn', ' #a comment'))
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            lines = (self.run_dir / 'openvpn.conf').read_text().splitlines()
            self.assertEqual(lines[:7], ['client', 'nobind', 'persist-key', 'remote 203.0.113.1 443 tcp-client',
                                         'remote 2001:db8::7 1194 udp6', 'verify-x509-name "C=US, CN=srv #1; x" subject',
                                         'cipher AES-256-GCM'])
            self.assertEqual(lines[7:], ['keepalive 10 60'] + OVPN_CA.split('\n'))
            self.assertEqual((self.run_dir / 'server-ip').read_text().split(), ['203.0.113.1', '2001:db8::7'])

    def test_crlf_file_and_blocks_byte_identical(self):
        text = OVPN_CONF.replace('\n', '\r\n').encode()
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            gen = (self.run_dir / 'openvpn.conf').read_bytes()
            self.assertNotIn(b'\r', gen)
            for block in (OVPN_CA, OVPN_KEY, OVPN_TLS):
                self.assertIn((block + '\n').encode(), gen)

    def test_a_bom_on_the_first_line_is_taken(self):
        # a Windows export starts with a UTF-8 BOM; it is not part of the first directive, and not written
        text = b'\xef\xbb\xbf' + OVPN_CONF.encode()
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            r = self.cli(shell, 'check', 'vpn')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'profile vpn: OK'), r.stderr)
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            gen = (self.run_dir / 'openvpn.conf').read_bytes()
            self.assertNotIn(b'\xef\xbb\xbf', gen)
            self.assertEqual(gen.splitlines()[0], b'client')
            # only on the first line: one later is a word openvpn would not know either
            self.refused(shell, OVPN_CONF.encode().replace(b'nobind\n', b'\xef\xbb\xbfnobind\n'), 'line 13: has a directive this driver does not know')

    def test_certificate_text_outside_the_pem_is_left_out(self):
        ca = OVPN_CA.replace('<ca>\n', '<ca>\nCertificate:\n    Data:\n        Version: 3 (0x2)\n')
        for shell in self.each_shell():
            self.setup_profile(shell, OVPN_CONF.replace(OVPN_CA, ca))
            r = self.run_lib(shell, 'drv_gen')
            self.assertEqual(r.returncode, 0, r.stderr)
            gen = (self.run_dir / 'openvpn.conf').read_text()
            self.assertIn(OVPN_CA, gen)
            self.assertNotIn('Certificate:', gen)
            r = self.cli(shell, 'check', 'vpn')
            self.assertIn('text around the PEM blocks', r.stderr)

    def test_scripts_are_refused_but_dns_helpers(self):
        base = OVPN_CONF.replace('up /etc/openvpn/update-resolv-conf\ndown /etc/openvpn/update-resolv-conf\n', '')
        helpers = ('/etc/openvpn/update-resolv-conf', '/etc/openvpn/update-systemd-resolved',
                   '/etc/openvpn/scripts/update-systemd-resolved')
        refused = {
            'up /bin/sh': (base.replace('client\n', 'client\nup /bin/sh\n'), 'line 2: up runs a script'),
            'down evil': (base.replace('client\n', 'client\ndown /tmp/evil\n'), 'line 2: down runs a script'),
            'helper with args': (base.replace('client\n', 'client\nup "/etc/openvpn/update-resolv-conf evil"\n'),
                                 'up runs a script'),
            'helper and a script': (OVPN_CONF.replace('client\n', 'client\nroute-up /tmp/evil\n'),
                                    'route-up is not a directive this driver takes'),
            'script-security 2 alone': (base, 'script-security without one of the known DNS helper scripts'),
            'script-security 3': (OVPN_CONF.replace('script-security 2', 'script-security 3'),
                                  'script-security is set by this driver'),
            'plugin': (OVPN_CONF.replace('client\n', 'client\nplugin /tmp/evil.so\n'), 'plugin is not a directive'),
            'quoted up': (base.replace('client\n', 'client\n"up" /tmp/evil\n'), 'up runs a script'),
            'dashed up': (base.replace('client\n', 'client\n--up /tmp/evil\n'), 'up runs a script'),
        }
        for shell in self.each_shell():
            for name, (text, msg) in refused.items():
                self.refused(shell, text, msg, name)
            # each known helper, in up or down, with script-security 1 or 2, is taken and left out
            for helper in helpers:
                for level in ('1', '2'):
                    text = base.replace('client\n', f'client\ndown {helper}\n').replace('script-security 2',
                                                                                          f'script-security {level}')
                    self.setup_profile(shell, text)
                    r = self.run_lib(shell, 'drv_gen')
                    self.assertEqual(r.returncode, 0, (helper, level, r.stderr))
                    gen = (self.run_dir / 'openvpn.conf').read_text()
                    self.assertNotIn(helper, gen)
                    self.assertNotIn('script-security', gen)
            # and a file without script-security at all
            self.setup_profile(shell, base.replace('script-security 2\n', ''))

    def test_lexing_is_strict(self):
        cases = {
            'semicolon in remote': (OVPN_CONF.replace('vpn.example', 'vpn.example;reboot'), 'remote that is not a plain'),
            'command in remote': (OVPN_CONF.replace('vpn.example', 'vpn$(touch evil)'), 'remote that is not a plain'),
            'backtick in remote': (OVPN_CONF.replace('vpn.example', 'vpn`evil`'), 'remote that is not a plain'),
            'space in quotes': (OVPN_CONF.replace('vpn.example', '"vpn.example evil"'), 'remote that is not a plain'),
            'dash host': (OVPN_CONF.replace('vpn.example', '-evil.example'), 'remote that is not a plain'),
            'bad port': (OVPN_CONF.replace('1194', '99999'), 'port'),
            'bad proto': (OVPN_CONF.replace('443 tcp', '443 sctp'), 'protocol'),
            'unclosed quote': (OVPN_CONF.replace('nobind', 'cipher "AES-256-GCM'), 'quote that is not closed'),
            'glued quote': (OVPN_CONF.replace('nobind', 'cipher "AES"-256'), 'quoted word followed by more text'),
            'quote in word': (OVPN_CONF.replace('nobind', 'cipher AES"x"'), 'quote inside a word'),
            'backslash': (OVPN_CONF.replace('nobind', 'cipher AES\\x'), 'backslash'),
            'vertical tab': (OVPN_CONF.replace('nobind', 'nobind\v').encode(), 'control character'),
            'form feed': (OVPN_CONF.replace('nobind', 'nobind\fup /tmp/evil').encode(), 'control character'),
            'nul': (OVPN_CONF.replace('nobind', 'nobind\0').encode(), 'control character'),
            'lone cr': (OVPN_CONF.replace('nobind\n', 'nobind\rup evil\n').encode(), 'carriage return'),
            'long line': (OVPN_CONF.replace('nobind', 'nobind ' + '#' * 1100), 'longer than 1024'),
            'too big': (OVPN_CONF + ('#' * 1000 + '\n') * 300, 'larger than 256 KiB'),
        }
        for shell in self.each_shell():
            for name, (text, msg) in cases.items():
                self.refused(shell, text, msg, name)

    def test_blocks_are_strict(self):
        cases = {
            'close with junk': (OVPN_CONF.replace('CAKEYCAKEYCAKEY\n', 'CAKEYCAKEYCAKEY\n</ca>junk\nup evil\n'),
                                'closing tag inside <ca> that is not exactly </ca>'),
            'other close tag': (OVPN_CONF.replace('PRIVKEYPRIVKEY\n', 'PRIVKEYPRIVKEY\n</ca>\n'),
                                'closing tag inside <key>'),
            'tag with comment': (OVPN_CONF.replace('<ca>', '<ca> # x'), 'not exactly one of the inline blocks'),
            'up tag': (OVPN_CONF + '<up>\n#!/bin/sh\nevil\n</up>\n', 'inline block <up> that this driver does not take'),
            'unknown tag': (OVPN_CONF + '<frobnicate>\nevil\n</frobnicate>\n', 'inline block this driver does not know'),
            'connection': (OVPN_CONF + '<connection>\nremote 198.51.100.9\n</connection>\n', '<connection> blocks'),
            'auth tag': (OVPN_CONF + '<auth-user-pass>\nalice\nhunter2\n</auth-user-pass>\n', '<auth-user-pass>'),
            'open block': (OVPN_CONF + '<tls-auth>\n-----BEGIN OpenVPN Static key V1-----\n', 'never closed'),
            'not pem': (OVPN_CONF.replace('CAKEYCAKEYCAKEY', 'CAKEY CAKEY'), 'not PEM'),
            'no armour': (OVPN_CONF.replace(OVPN_KEY, '<key>\n</key>'), 'no PEM block in <key>'),
            'unended armour': (OVPN_CONF.replace('-----END PRIVATE KEY-----\n', ''), 'not ended'),
            'encrypted key': (OVPN_CONF.replace('PRIVKEYPRIVKEY', 'Proc-Type: 4,ENCRYPTED\nPRIVKEYPRIVKEY'),
                              'encrypted private key'),
            'twice': (OVPN_CONF + OVPN_CA + '\n', 'second <ca>'),
        }
        for shell in self.each_shell():
            for name, (text, msg) in cases.items():
                self.refused(shell, text, msg, name)

    def test_directives_outside_the_allowlist_are_refused(self):
        # (each with the value a message must not repeat, where it has one of its own)
        cases = {
            'setenv': ('setenv FOO evil1', 'evil1'), 'dns-updown': ('dns-updown /tmp/evil2', 'evil2'),
            'server': ('server 10.8.0.0 255.255.255.0', '255.255'), 'mode': ('mode server', None),
            'config': ('config /tmp/evil3.ovpn', 'evil3'), 'management': ('management 0.0.0.0 7505', '7505'),
            'log': ('log /tmp/evil4', 'evil4'), 'ca': ('ca /etc/ssl/ca.pem', 'ca.pem'),
            'pull-filter': ('pull-filter accept route', 'accept'), 'comp-lzo': ('comp-lzo', None),
            'mark': ('mark 720', '720'), 'tls-server': ('tls-server', None),
            'ifconfig': ('ifconfig 10.9.9.1 10.9.9.2', '10.9.9'), 'ignore-unknown-option': ('ignore-unknown-option up', None),
            'auth-user-pass': ('auth-user-pass /tmp/creds5', 'creds5'), 'remote-cert-tls': ('remote-cert-tls client', None),
            'auth-retry': ('auth-retry interact', None), 'dev-node': ('dev-node /dev/net/tun', '/dev/net'),
            'connect-retry': ('connect-retry hunter2', None),
        }
        for shell in self.each_shell():
            for name, (line, value) in cases.items():
                r = self.refused(shell, OVPN_CONF.replace('nobind\n', f'nobind\n{line}\n'), 'line 14: ', name)
                if value:
                    self.assertNotIn(value, r.stderr, name)
            # an unknown first word is not repeated: it could be a password on a line of its own
            r = self.refused(shell, OVPN_CONF.replace('nobind\n', 'nobind\nhunter2\n'), 'line 14: has a directive this driver does not know')
            # a tap profile, no remote, and a file that is not a client
            self.refused(shell, OVPN_CONF.replace('dev tun0', 'dev tap0'), 'tap')
            self.refused(shell, OVPN_CONF.replace('dev tun0', 'dev-type tap'), 'tap')
            self.refused(shell, OVPN_CONF.replace('remote vpn.example 1194 udp\n', '').replace('remote 198.51.100.2 443 tcp\n', ''),
                         'no remote server')
            self.refused(shell, OVPN_CONF.replace('client\n', ''), 'not a client profile')
            self.refused(shell, OVPN_CONF.replace(OVPN_CA, ''), 'no inline <ca>')

    def test_start_alive_stop(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            r = self.run_lib(shell, 'drv_start && echo STARTED; echo "tun=$TUN"; drv_alive && echo ALIVE; '
                                    'drv_stop; echo "stop=$?"; drv_alive || echo "gone=$DRV_GONE"')
            self.assertEqual(r.returncode, 0, r.stderr)
            for want in ('tunnel up on tun-mu300', 'STARTED', 'tun=tun-mu300', 'ALIVE', 'stop=0', 'gone=openvpn'):
                self.assertIn(want, r.stdout)
            args = (self.tmp / 'ovpn.args').read_text().splitlines()
            run = self.run_dir
            # the config first, then every option of ours after it, so that ours win. The pushed options are held
            # to an accept list (first match wins, so the accepts come first and the catch-all last): what the
            # session needs and the data-channel negotiation decided, nothing that runs, names a file or routes.
            self.assertEqual(args, ['--config', f'{run}/openvpn.conf', '--dev', 'tun-mu300', '--dev-type', 'tun',
                                    '--route-noexec',
                                    '--pull-filter', 'accept', 'ifconfig', '--pull-filter', 'accept', 'ifconfig-ipv6',
                                    '--pull-filter', 'accept', 'topology', '--pull-filter', 'accept', 'dhcp-option DNS',
                                    '--pull-filter', 'accept', 'ping', '--pull-filter', 'accept', 'ping-restart',
                                    '--pull-filter', 'accept', 'peer-id', '--pull-filter', 'accept', 'cipher',
                                    '--pull-filter', 'accept', 'auth-token', '--pull-filter', 'accept', 'route-gateway',
                                    '--pull-filter', 'accept', 'protocol-flags', '--pull-filter', 'accept', 'key-derivation',
                                    '--pull-filter', 'accept', 'tun-mtu', '--pull-filter', 'ignore', '',
                                    '--mark', '720', '--script-security', '2', '--up', f'{LIB}/openvpn-up',
                                    '--setenv', 'MU300_VPN_RUN', str(run), '--auth-nocache', '--verb', '3'])
            # pushed DNS still reaches the up script: --route-nopull would drop it
            self.assertNotIn('--route-nopull', args)
            # nothing pushed is accepted that the list does not name: no accept of a route, a script or a setenv,
            # and the catch-all comes after every accept
            for word in ('route', 'route-ipv6', 'redirect-gateway', 'setenv', 'dhcp-option DOMAIN', 'dhcp-option',
                         'block-outside-dns', 'compress', 'comp-lzo', 'dns', 'client-nat', 'up', 'down'):
                self.assertNotIn(word, args)
            self.assertEqual(args.index('ignore'), max(i for i, a in enumerate(args) if a == 'accept') + 3)
            # OpenVPN 2.6 does not know --dns-updown: it must not be given (2.7 is a follow-up)
            self.assertNotIn('--dns-updown', args)
            # the first pushed resolver; the up script marked the session
            self.assertEqual((run / 'dns').read_text().strip(), '10.8.0.1')
            self.assertFalse((run / 'ovpn-up').exists())
            # the runtime copy of the config is gone with the tunnel
            self.assertFalse((run / 'openvpn.conf').exists())

    def test_credentials_go_to_auth_txt(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            pdir = self.store / 'profiles/vpn'
            self.assertEqual(self.cli(shell, 'profile', 'set', 'vpn', 'OVPN_USER', 'alice').returncode, 0)
            r = self.cli(shell, 'profile', 'set', 'vpn', 'OVPN_PASS', '-', stdin='s3cr et pass\n')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((pdir / 'auth.txt').read_text(), 'alice\ns3cr et pass\n')
            self.assertEqual(stat.S_IMODE((pdir / 'auth.txt').stat().st_mode), 0o600)
            self.assertNotIn('s3cr', (pdir / 'meta').read_text())
            for args in (('profile', 'show', 'vpn'), ('check', 'vpn'), ('profile', 'list')):
                r = self.cli(shell, *args)
                self.assertNotIn('s3cr', r.stdout + r.stderr)
                self.assertNotIn('OVPN_USER', r.stderr)      # credentials exist: no reminder
            # started with a copy in the runtime directory (0600), which goes with the tunnel
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            auth = self.run_dir / 'ovpn.auth'
            r = self.run_lib(shell, f'drv_start; ls -l "{auth}"; cat "{auth}" | wc -l; drv_stop; '
                                    f'[ -e "{auth}" ] || echo AUTH-GONE')
            args = (self.tmp / 'ovpn.args').read_text().splitlines()
            i = args.index('--auth-user-pass')
            self.assertEqual(args[i + 1], str(auth))
            self.assertGreater(i, args.index('--config'))
            self.assertIn('-rw------- ', r.stdout)
            self.assertIn('AUTH-GONE', r.stdout)
            self.assertNotIn('s3cr', r.stdout + r.stderr)
            # one at a time, and an empty value clears
            self.assertEqual(self.cli(shell, 'profile', 'set', 'vpn', 'OVPN_USER', 'bob').returncode, 0)
            self.assertEqual((pdir / 'auth.txt').read_text(), 'bob\ns3cr et pass\n')
            self.cli(shell, 'profile', 'set', 'vpn', 'OVPN_PASS', '')
            self.assertEqual((pdir / 'auth.txt').read_text(), 'bob\n\n')
            self.cli(shell, 'profile', 'set', 'vpn', 'OVPN_USER', '')
            self.assertFalse((pdir / 'auth.txt').exists())
            # a line break would make a third line, and a key of another type is not accepted
            r = self.cli(shell, 'profile', 'set', 'vpn', 'OVPN_USER', 'a\nb')
            self.assertEqual(r.returncode, 2)
            self.assertFalse((pdir / 'auth.txt').exists())
            self.assertEqual(self.cli(shell, 'profile', 'set', 'vpn', 'MIHOMO_STACK', 'x').returncode, 2)
            # the driver itself checks the key before it reads stdin
            r = self.run_lib(shell, 'rc=0; drv_set BOGUS - || rc=$?; echo "rc=$rc"; IFS= read -r x; echo "left=$x"',
                             stdin='hunter2\n')
            self.assertIn('rc=2', r.stdout)
            self.assertIn('left=hunter2', r.stdout)
            self.assertFalse((pdir / 'auth.txt').exists())

    def test_up_script_takes_only_addresses(self):
        for shell in self.each_shell():
            self.run_dir.mkdir(parents=True, exist_ok=True)
            up = LIB / 'openvpn-up'
            for opt, want in (('dhcp-option DNS 1.2.3.4;rm -rf x', None), ('dhcp-option DNS $(touch pwned)', None),
                              ('dhcp-option DNS 1.2.3.4 extra', None), ('dhcp-option DNS 999.1.1.1', None),
                              ('dhcp-option DNS example.org', None), ('dhcp-option DOMAIN x', None),
                              ('dhcp-option DNS 010.0.0.1', None), ('dhcp-option DNS 1.2.3', None),
                              ('dhcp-option DNS :::', None), ('dhcp-option DNS 1::2::3', None),
                              ('dhcp-option DNS 12345::1', None), ('dhcp-option DNS 1:2:3:4:5:6:7:8:9', None),
                              ('dhcp-option DNS abc:', None), ('dhcp-option DNS ::1.2.3', None),
                              ('dhcp-option DNS 10.8.0.1', '10.8.0.1'), ('dhcp-option DNS 2001:db8::53', '2001:db8::53'),
                              ('dhcp-option DNS ::ffff:192.0.2.1', '::ffff:192.0.2.1'),
                              ('dhcp-option DNS 1:2:3:4:5:6:7:8', '1:2:3:4:5:6:7:8'),
                              # DNS6 is the IPv6 resolver (OpenVPN pushes it for an IPv6 one); it takes no IPv4
                              ('dhcp-option DNS6 2001:db8::53', '2001:db8::53'),
                              ('dhcp-option DNS6 10.8.0.1', None), ('dhcp-option DNS6 example.org', None),
                              ('dhcp-option DNS6 2001:db8::53;x', None), ('dhcp-option DNS7 2001:db8::53', None),
                              ('dhcp-option dns 10.8.0.1', None)):
                shutil.rmtree(self.run_dir); self.run_dir.mkdir()
                r = self.script(shell, up, 'tun-mu300', foreign_option_1=opt, MU300_VPN_RUN=self.run_dir,
                                SECRET_ENV='hunter2')
                self.assertEqual(r.returncode, 0, (opt, r.stderr))
                self.assertEqual((r.stdout, r.stderr), ('', ''))
                dns = self.run_dir / 'dns'
                self.assertEqual(dns.read_text().strip() if dns.exists() else None, want, opt)
                self.assertEqual((self.run_dir / 'ovpn-up').read_text().strip(), 'tun-mu300')
            self.assertFalse((self.tmp / 'pwned').exists())
            # the first valid one of several, and no run directory is an error, not a write somewhere else
            shutil.rmtree(self.run_dir); self.run_dir.mkdir()
            r = self.script(shell, up, 'tun-mu300', foreign_option_1='dhcp-option DNS x', foreign_option_2='dhcp-option DNS 10.0.0.2',
                            foreign_option_3='dhcp-option DNS 10.0.0.3', MU300_VPN_RUN=self.run_dir)
            self.assertEqual((self.run_dir / 'dns').read_text().strip(), '10.0.0.2')
            r = self.script(shell, up, 'tun-mu300', MU300_VPN_RUN='')
            self.assertNotEqual(r.returncode, 0)

    def test_a_start_that_fails_returns_1(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            (self.store / 'profiles/vpn/auth.txt').write_text('alice\nhunter2\n')
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            self.openvpn_stub('echo "Options error: bad thing" >&2; exit 1')
            r = self.run_lib(shell, 'drv_start && echo STARTED')
            self.assertNotIn('STARTED', r.stdout)
            self.assertIn('openvpn exited during start', r.stderr)
            # the keys and the password do not stay behind
            self.assertFalse((self.run_dir / 'openvpn.conf').exists())
            self.assertFalse((self.run_dir / 'ovpn.auth').exists())
            # and one that does come up is started
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            self.openvpn_stub()
            r = self.run_lib(shell, 'drv_start && echo STARTED; drv_stop')
            self.assertIn('STARTED', r.stdout)

    def test_stop_kills_one_that_ignores_term(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            self.openvpn_stub('trap "" TERM\n'
                              'printf "%s\\n" "$@" > "$STUBLOG/ovpn.args"\n'
                              ': > "$STUBLOG/run/ovpn-up"\n'
                              'while :; do sleep 1; done')
            r = self.run_lib(shell, 'drv_start; p=$OVPN_PID; drv_stop; kill -0 $p 2>/dev/null && echo SURVIVED; echo done')
            self.assertIn('done', r.stdout)
            self.assertNotIn('SURVIVED', r.stdout)

    def test_engine_and_package(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'echo "pkg=$DRV_PKG extra=[$DRV_EXTRA]"; drv_engines; drv_engines_ok && echo OK')
            self.assertIn('pkg=openvpn extra=[]', r.stdout)
            self.assertIn(str(self.stubs / 'openvpn'), r.stdout)
            self.assertIn('OK', r.stdout)
            # the OPENVPN setting names another binary
            r = self.run_lib(shell, 'drv_engines; drv_engines_ok || echo MISSING', f'_openvpn={self.tmp}/none; ')
            self.assertIn(f'{self.tmp}/none', r.stdout)
            self.assertIn('MISSING', r.stdout)
            # OpenWrt's package carries the TLS library
            (self.tmp / 'owrt').write_text('x')
            r = self.sh(shell, f'. "{BIN}/mu300-vpn"; load_driver openvpn; echo "pkg=$DRV_PKG"', MU300_LIB=1,
                        MU300_OPENWRT_RELEASE=self.tmp / 'owrt')
            self.assertIn('pkg=openvpn-openssl', r.stdout)

    def test_names_are_looked_up_in_the_resolve_window(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'drv_gen', 'ENABLE=1; KILL_SWITCH=1; ')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.ev.read_text().splitlines(), ['nft -f', 'getent vpn.example', 'nft -f'])
            self.fresh()
            self.src.write_text(OVPN_CONF.replace('vpn.example', 'nx.example'))
            self.assertEqual(self.cli(shell, 'profile', 'import', self.src, 'Vpn').returncode, 0)
            r = self.run_lib(shell, 'drv_gen', 'ENABLE=1; KILL_SWITCH=1; ')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('cannot resolve the VPN server nx.example', r.stderr)
            self.assertEqual(self.ev.read_text().splitlines(), ['nft -f', 'getent nx.example', 'nft -f'])
            self.assertFalse((self.run_dir / 'openvpn.conf').exists())


# a Clash/mihomo YAML as subscriptions give them: ports, a LAN listener, a controller with a secret, its own tun and
# dns, then the proxies and rules; only the last two survive the driver's reduction
MH_CONF = '''port: 7890
allow-lan: true
external-controller: 0.0.0.0:9090
secret: s
tun:
  enable: true
  auto-route: true
dns:
  enhanced-mode: fake-ip
proxies:
  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}
rules:
  - MATCH,a
'''
MH_OURS = ('routing-mark', 'allow-lan', 'bind-address', 'tun', 'dns')
# the smallest file the driver takes: one proxy and one rule
MH_BASE = ('proxies:\n  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}\n'
           'rules:\n  - MATCH,a\n')


class Mihomo(ShellTest):
    """The mihomo driver: the YAML is reduced to the top-level keys the spec allows (awk, no YAML parser), ours
    (routing-mark, allow-lan, bind-address, tun, dns) are appended, nothing of the file listens (no port, no
    controller or API of any kind), interface-name and routing-mark go from every proxy and group, mihomo checks and
    runs only the file we wrote, and no secret is printed."""

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.store = self.tmp / 'vpn'
        self.run_dir = self.tmp / 'run'
        self.home = self.store / 'cache/mihomo'
        self.ev = self.tmp / 'events'
        # "link show mh-mu300" finds the tunnel once the stub mihomo has been started (not with -t)
        self.stub('ip', 'echo "$*" >> "$STUBLOG/ip.log"\n'
                        'case "$*" in\n'
                        '  "link show mh-mu300") [ -e "$STUBLOG/mh-up" ]; exit ;;\n'
                        '  "link show"*) exit 1 ;;\n'
                        'esac; exit 0')
        self.stub('svc', 'exit 0')
        self.stub('nft', 'case "$1" in -f) cat >/dev/null; echo "nft -f" >> "$STUBLOG/events" ;; esac; exit 0')
        self.mihomo_stub()
        self.src = self.tmp / 'sub.yaml'
        self.src.write_text(MH_CONF)

    def mihomo_stub(self, body=None):
        # -t records its arguments and passes; a run records them too, makes the tunnel appear and stays
        self.stub('mihomo', body or (
            'case " $* " in *" -t "*) printf "%s\\n" "$@" > "$STUBLOG/mihomo.t.args"; exit 0 ;; esac\n'
            'printf "%s\\n" "$@" > "$STUBLOG/mihomo.args"\n'
            'env | grep "^SAFE_PATHS=\\|^SKIP_SAFE_PATH_CHECK=" > "$STUBLOG/mihomo.env"\n'
            ': > "$STUBLOG/mh-up"\n'
            'exec sleep 60'))

    def env(self, **extra):
        base = dict(MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.run_dir, MU300_VPN_LIB=LIB,
                    MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.tmp / 'opt',
                    MU300_DISK=self.tmp / 'disk', MU300_VPN_SVC=self.stubs / 'svc',
                    SAFE_PATHS='/tmp', SKIP_SAFE_PATH_CHECK='1')
        base.update(extra)
        return super().env(**base)

    def lib(self, shell, code, stdin=None):
        return self.sh(shell, f'. "{BIN}/mu300-vpn"; {code}', stdin=stdin, MU300_LIB=1)

    def cli(self, shell, *args, stdin=None):
        return self.script(shell, BIN / 'mu300-vpn', *args, stdin=stdin)

    def fresh(self):
        shutil.rmtree(self.store, ignore_errors=True)
        shutil.rmtree(self.run_dir, ignore_errors=True)
        for p in ('events', 'ip.log', 'mihomo.args', 'mihomo.t.args', 'mihomo.env', 'mh-up'):
            (self.tmp / p).unlink(missing_ok=True)

    def setup_profile(self, shell, text=MH_CONF):
        self.fresh()
        if isinstance(text, bytes):
            self.src.write_bytes(text)
        else:
            self.src.write_text(text)
        r = self.cli(shell, 'profile', 'import', self.src, 'Sub')
        self.assertEqual((r.returncode, r.stdout.strip()), (0, 'sub'), r.stderr)

    def run_lib(self, shell, code, pre='', stdin=None):
        return self.lib(shell, f'{pre}profile_load sub; load_driver "$PTYPE"; {code}', stdin=stdin)

    def no_secrets(self, r, name=None):
        for secret in ('hunter2', 'ss.example', 'aes-256-gcm', '0.0.0.0:9090', 'secret: s', 'eth0'):
            self.assertNotIn(secret, r.stdout + r.stderr, name)

    def refused(self, shell, text, msg=None, name=None):
        """imports TEXT, which must be refused (with MSG in the message), leaving no profile and no secret said"""
        self.fresh()
        if isinstance(text, bytes):
            self.src.write_bytes(text)
        else:
            self.src.write_text(text)
        r = self.cli(shell, 'profile', 'add', 'mihomo', 'X', self.src)
        self.assertNotEqual(r.returncode, 0, name or text)
        if msg:
            self.assertIn(msg, r.stderr, name or text)
        self.no_secrets(r, name or text)
        profiles = self.store / 'profiles'
        self.assertEqual(list(profiles.iterdir()) if profiles.exists() else [], [], name or text)
        return r

    def gen(self, shell, pre=''):
        r = self.run_lib(shell, 'drv_gen', pre)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.no_secrets(r)
        return (self.run_dir / 'mihomo.yaml').read_text()

    @staticmethod
    def top_keys(text):
        """the column-0 keys of a generated file, in order"""
        return [l.split(':')[0] for l in text.splitlines() if l and l[0] not in ' \t#']

    @staticmethod
    def block(text, key):
        """the lines of the top-level KEY block (the key line and what is indented under it)"""
        out, inside = [], False
        for l in text.splitlines():
            if l.startswith(key + ':'):
                inside = True
            elif l and l[0] not in ' \t#':
                inside = False
            if inside:
                out.append(l)
        return out

    def test_import_sniffs_and_stores_0600(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            pdir = self.store / 'profiles/sub'
            self.assertIn("TYPE='mihomo'", (pdir / 'meta').read_text())
            self.assertEqual(stat.S_IMODE((pdir / 'config.yaml').stat().st_mode), 0o600)
            self.assertEqual((pdir / 'config.yaml').read_text(), MH_CONF)
            self.assertEqual(self.cli(shell, 'profile', 'export', 'sub').stdout, MH_CONF)
            r = self.cli(shell, 'profile', 'list')
            self.assertIn('\tsub\tmihomo\tSub', r.stdout)
            r = self.cli(shell, 'check', 'sub')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'profile sub: OK'), r.stderr)
            self.no_secrets(r)
            # the check names the top-level keys it does not use, nothing else of the file
            for k in ('port', 'allow-lan', 'external-controller', 'secret', 'tun', 'dns'):
                self.assertIn(f' {k}', r.stderr)
            # nothing for the profile is left in its directory by the check, and the check ran without mihomo
            self.assertEqual(sorted(p.name for p in pdir.iterdir()), ['config.yaml', 'meta'])
            self.assertFalse((self.tmp / 'mihomo.t.args').exists())
            # from stdin, and with the type given
            self.fresh()
            r = self.cli(shell, 'profile', 'import', '-', 'Low', stdin=MH_CONF)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'low'), r.stderr)
            self.fresh()
            r = self.cli(shell, 'profile', 'add', 'mihomo', 'Two', self.src)
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'two'), r.stderr)
            # a file with proxy-providers and no proxies is a mihomo config too
            self.fresh()
            self.src.write_text('proxy-providers:\n  p:\n    type: http\n    url: https://sub.example/x\n    path: ./p.yaml\n'
                                'proxy-groups:\n  - {name: g, type: select, use: [p]}\nrules:\n  - MATCH,g\n')
            r = self.cli(shell, 'profile', 'import', self.src, 'Prov')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'prov'), r.stderr)
            # not a mihomo config: JSON, a file with neither, a WireGuard file given the type
            self.refused(shell, '{"proxies": [], "rules": []}', 'not a mihomo config')
            self.refused(shell, 'mode: rule\nrules:\n  - MATCH,DIRECT\n', 'no proxies or proxy-providers')
            self.refused(shell, '[Interface]\nPrivateKey = x\n', None)

    def test_gen_reduces_the_config(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            gen = self.gen(shell)
            self.assertEqual(stat.S_IMODE((self.run_dir / 'mihomo.yaml').stat().st_mode), 0o600)
            # the kept blocks as they were, then ours; nothing else at the top level
            self.assertEqual(self.top_keys(gen), ['proxies', 'rules'] + list(MH_OURS))
            self.assertEqual(self.block(gen, 'proxies'),
                             ['proxies:', '  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}'])
            self.assertEqual(self.block(gen, 'rules'), ['rules:', '  - MATCH,a'])
            for gone in ('port: 7890', 'external-controller', 'secret', 'allow-lan: true', 'auto-route: true',
                         'fake-ip', '0.0.0.0'):
                self.assertNotIn(gone, gen)
            lines = gen.splitlines()
            self.assertEqual(lines.count('tun:'), 1)
            self.assertEqual(lines.count('dns:'), 1)
            self.assertIn('routing-mark: 720', lines)
            self.assertIn('allow-lan: false', lines)
            self.assertIn("bind-address: '127.0.0.1'", lines)
            self.assertEqual(self.block(gen, 'tun'),
                             ['tun:', '  enable: true', '  device: mh-mu300', '  stack: gvisor', '  auto-route: false',
                              '  auto-redirect: false', '  auto-detect-interface: false', '  dns-hijack: []',
                              '  mtu: 1400', '  inet4-address: [198.18.8.1/30]'])
            self.assertEqual(self.block(gen, 'dns'),
                             ['dns:', '  enable: true', '  ipv6: false', '  respect-rules: true',
                              "  default-nameserver: ['1.1.1.1']", "  proxy-server-nameserver: ['1.1.1.1']",
                              "  nameserver: ['1.1.1.1']"])
            # mihomo checked the written file, from its home under the store, and nothing else
            t = (self.tmp / 'mihomo.t.args').read_text().splitlines()
            self.assertEqual(t, ['-t', '-d', str(self.home), '-f', str(self.run_dir / 'mihomo.yaml')])
            self.assertEqual(stat.S_IMODE(self.home.stat().st_mode), 0o700)
            self.assertFalse((self.tmp / 'mihomo.args').exists())
            # no server address to keep off the tunnel: mihomo marks its own sockets
            self.assertEqual((self.run_dir / 'server-ip').read_text(), '')
            # the settings go in: the resolvers
            r = self.cli(shell, 'settings', 'set', 'REMOTE_DNS', '9.9.9.9')
            self.assertEqual(r.returncode, 0, r.stderr)
            r = self.cli(shell, 'settings', 'set', 'BOOTSTRAP_DNS', '8.8.8.8')
            self.assertEqual(r.returncode, 0, r.stderr)
            gen = self.gen(shell)
            self.assertIn("  nameserver: ['9.9.9.9']", gen.splitlines())
            self.assertIn("  default-nameserver: ['8.8.8.8']", gen.splitlines())
            self.assertIn("  proxy-server-nameserver: ['8.8.8.8']", gen.splitlines())
            self.assertNotIn('external-controller', gen)
            # a controller is written for nobody: not for a setting of an older store, not for a legacy vpn.conf
            (self.store / 'settings').write_text("MIHOMO_CONTROLLER='127.0.0.1:9090'\n")
            gen = self.gen(shell, 'MIHOMO_CONTROLLER=127.0.0.1:9090; ')
            self.assertNotIn('external-controller', gen)
            self.assertNotIn('9090', gen)
            self.assertEqual(self.top_keys(gen), ['proxies', 'rules'] + list(MH_OURS))
            # a mihomo that rejects the file fails the gen, without repeating what mihomo said
            self.mihomo_stub('echo "yaml: cannot unmarshal !!str hunter2" >&2; exit 1')
            r = self.run_lib(shell, 'drv_gen')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('mihomo -t', r.stderr)
            self.no_secrets(r)
            self.mihomo_stub()

    def test_stack_option(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            meta = self.store / 'profiles/sub/meta'
            for v in ('system', 'mixed', 'gvisor'):
                r = self.cli(shell, 'profile', 'set', 'sub', 'MIHOMO_STACK', v)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn(f"MIHOMO_STACK='{v}'", meta.read_text())
                self.assertIn(f'  stack: {v}', self.gen(shell).splitlines())
            r = self.cli(shell, 'profile', 'set', 'sub', 'MIHOMO_STACK', 'x')
            self.assertEqual(r.returncode, 2)
            self.assertIn("MIHOMO_STACK='gvisor'", meta.read_text())
            r = self.cli(shell, 'profile', 'set', 'sub', 'MIHOMO_STACK', '')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn('MIHOMO_STACK', meta.read_text())
            self.assertIn('  stack: gvisor', self.gen(shell).splitlines())
            # a value written into meta by hand that is not a stack: the default
            meta.write_text(meta.read_text() + "MIHOMO_STACK='bogus'\n")
            self.assertIn('  stack: gvisor', self.gen(shell).splitlines())
            # the keys of the other types are not this type's
            for k in ('TLS_PIN_SHA256', 'OVPN_USER', 'UPSTREAM_HTTP_PROXY'):
                self.assertEqual(self.cli(shell, 'profile', 'set', 'sub', k, 'x').returncode, 2, k)

    def test_interface_name_and_routing_mark_go_from_proxies_and_groups(self):
        text = '''proxies:
  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2, interface-name: eth0, routing-mark: 1}
  - {name: b, type: ss, interface-name: 'eth0', server: ss.example, port: 1, cipher: c, password: "hu,nter2", routing-mark: 2}
  - {interface-name: eth0, name: c, type: socks5, server: s, port: 1, routing-mark: 3}
  - {name: d, type: http, server: s, port: 1, headers: {X: [eth0, 1]}, Interface-Name: eth0}
  - {name: e, type: vmess, server: s, port: 1, uuid: u, ws-opts: {path: /x, headers: {Host: h}}, routing-mark: {a: 1}}
  - name: f
    type: ss
    interface-name: eth0
    server: ss.example
    port: 8388
    routing-mark: 5
    cipher: aes-256-gcm
    password: hunter2
  - interface-name: eth0
    name: g
    type: socks5
    server: s
    port: 1
  - routing-mark: |
      1
      2
    name: h
    type: socks5
    server: s
    port: 1
proxy-groups:
  - name: sel
    type: select
    interface-name: wan
    proxies: [a, b]
  - {name: auto, type: url-test, interface-name: wan, routing-mark: 7, proxies: [a], url: 'http://x', interval: 300}
rules:
  - MATCH,sel
'''
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            gen = self.gen(shell)
            self.assertNotIn('interface-name', gen.lower())
            self.assertNotIn('routing-mark: 1', gen)
            self.assertNotIn('routing-mark: 2', gen)
            self.assertNotIn('routing-mark: 3', gen)
            self.assertNotIn('routing-mark: 5', gen)
            self.assertNotIn('routing-mark: 7,', gen)
            self.assertNotIn('routing-mark: {', gen)
            self.assertNotIn('wan', gen)
            self.assertEqual(gen.count('routing-mark'), 1)
            self.assertEqual(self.block(gen, 'proxies'), [
                'proxies:',
                '  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}',
                '  - {name: b, type: ss, server: ss.example, port: 1, cipher: c, password: "hu,nter2"}',
                '  - {name: c, type: socks5, server: s, port: 1}',
                '  - {name: d, type: http, server: s, port: 1, headers: {X: [eth0, 1]}}',
                '  - {name: e, type: vmess, server: s, port: 1, uuid: u, ws-opts: {path: /x, headers: {Host: h}}}',
                '  - name: f', '    type: ss', '    server: ss.example', '    port: 8388', '    cipher: aes-256-gcm',
                '    password: hunter2',
                '  -', '    name: g', '    type: socks5', '    server: s', '    port: 1',
                '  -', '    name: h', '    type: socks5', '    server: s', '    port: 1'])
            self.assertEqual(self.block(gen, 'proxy-groups'), [
                'proxy-groups:',
                '  - name: sel', '    type: select', '    proxies: [a, b]',
                "  - {name: auto, type: url-test, proxies: [a], url: 'http://x', interval: 300}"])
            # a spelling of either key that awk cannot take out is refused, naming the key
            for bad, key in (('"interface-name": eth0', 'interface-name'), ("'routing-mark': 1", 'routing-mark'),
                             ('x: &k interface-name\n    *k : eth0', 'interface-name'),
                             ('server: s # interface-name', 'interface-name'),
                             ('x: "Interface-Name"', 'interface-name'), ('x: ROUTING-MARK', 'routing-mark')):
                r = self.refused(shell, f'proxies:\n  - name: a\n    type: socks5\n    {bad}\n    server: s\n    port: 1\n'
                                        '    password: hunter2\nrules:\n  - MATCH,a\n', 'refused', bad)
                self.assertIn(key, r.stderr, bad)
            # the keys in another case go the same way, and a comment line that mentions them is only a comment
            self.setup_profile(shell, '# interface-name: eth0 and routing-mark: 1 are set by mu300\n'
                                      'proxies:\n  - name: a\n    type: socks5\n    INTERFACE-NAME: eth0\n    server: s\n'
                                      '    Routing-Mark: 1\n    port: 1\n  - {name: b, type: socks5, server: s, port: 1, Interface-Name: eth0}\n'
                                      'rules:\n  - MATCH,a\n')
            gen = self.gen(shell)
            self.assertEqual(self.block(gen, 'proxies'),
                             ['proxies:', '  - name: a', '    type: socks5', '    server: s', '    port: 1',
                              '  - {name: b, type: socks5, server: s, port: 1}'])
            self.assertNotIn('eth0', gen)

    def test_listening_and_control_blocks_go(self):
        text = '''mixed-port: 7890
socks-port: 7891
redir-port: 7892
tproxy-port: 7893
allow-lan: true
bind-address: '*'
lan-allowed-ips: [0.0.0.0/0]
authentication: ["user:hunter2"]
mode: rule
log-level: info
ipv6: true
external-controller: 0.0.0.0:9090
external-controller-tls: 0.0.0.0:9443
external-controller-unix: /tmp/x.sock
external-ui: /tmp/ui
external-ui-url: https://x.example/ui.zip
secret: hunter2
listeners:
  - name: ss-in
    type: shadowsocks
    port: 8388
    listen: 0.0.0.0
    cipher: aes-256-gcm
    password: hunter2
tunnels:
  - tcp/udp,127.0.0.1:6553,114.114.114.114:53,proxy
ntp:
  enable: true
  write-to-system: true
  server: time.apple.com
ebpf:
  auto-redir: [eth0]
iptables:
  enable: true
interface-name: eth0
routing-mark: 6666
tun:
  enable: true
  stack: system
  auto-route: true
  auto-redirect: true
  dns-hijack: [any:53]
dns:
  enable: true
  listen: 0.0.0.0:53
  enhanced-mode: fake-ip
  nameserver: [https://dns.example/dns-query]
hosts:
  'router.example': 192.168.78.1
geodata-mode: true
geodata-loader: memconservative
geox-url:
  geoip: https://x.example/geoip.dat
profile:
  store-selected: true
sniffer:
  enable: true
  sniff:
    HTTP:
      ports: [80]
proxies:
  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}
proxy-groups:
  - {name: g, type: select, proxies: [a]}
rule-providers:
  ads:
    type: http
    behavior: domain
    url: https://x.example/ads.yaml
    path: ./ads.yaml
    interval: 86400
sub-rules:
  sub:
    - MATCH,a
rules:
  - RULE-SET,ads,REJECT
  - SUB-RULE,(DOMAIN,x.example),sub
  - MATCH,g
'''
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            gen = self.gen(shell)
            self.assertEqual(self.top_keys(gen),
                             ['mode', 'log-level', 'ipv6', 'hosts', 'geodata-mode', 'geodata-loader', 'geox-url',
                              'profile', 'sniffer', 'proxies', 'proxy-groups', 'rule-providers', 'sub-rules', 'rules']
                             + list(MH_OURS))
            for gone in ('mixed-port', 'socks-port', 'redir-port', 'tproxy-port', 'lan-allowed-ips', 'authentication',
                         'external-controller', 'external-ui', 'secret', 'listeners', 'ss-in', 'tunnels', '6553',
                         'ntp', 'write-to-system', 'ebpf', 'iptables', 'eth0', '6666', 'stack: system',
                         'auto-route: true', 'auto-redirect: true', 'any:53', '0.0.0.0', 'fake-ip', 'dns.example',
                         "bind-address: '*'", 'allow-lan: true'):
                self.assertNotIn(gone, gen, gone)
            self.assertEqual(self.block(gen, 'sniffer'), ['sniffer:', '  enable: true', '  sniff:', '    HTTP:', '      ports: [80]'])
            self.assertEqual(self.block(gen, 'hosts'), ['hosts:', "  'router.example': 192.168.78.1"])
            self.assertEqual(self.block(gen, 'sub-rules'), ['sub-rules:', '  sub:', '    - MATCH,a'])
            self.assertIn('  - SUB-RULE,(DOMAIN,x.example),sub', self.block(gen, 'rules'))
            self.assertEqual(self.block(gen, 'geox-url'), ['geox-url:', '  geoip: https://x.example/geoip.dat'])
            # the check tells which top-level keys were not used, by name only
            r = self.cli(shell, 'check', 'sub')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('not used', r.stderr)
            for k in ('listeners', 'ntp', 'secret', 'interface-name', 'routing-mark', 'mixed-port'):
                self.assertIn(f' {k}', r.stderr)
            self.no_secrets(r)
            self.assertNotIn('time.apple.com', r.stderr)

    def test_refusals_name_the_rule_and_nothing_of_the_file(self):
        base = ('proxies:\n  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}\n'
                'rules:\n  - MATCH,a\n')
        for shell in self.each_shell():
            for name, text, msg in (
                    ('second document', base + '---\nproxies: []\ntun:\n  enable: true\n', 'second YAML document'),
                    ('second document with content', base + '--- # x\n', 'second YAML document'),
                    ('document end', base + '...\n', 'document end'),
                    ('directive', '%YAML 1.2\n---\n' + base, 'directive'),
                    ('tab at column 0', base.replace('  - MATCH,a', '\t- MATCH,a'), 'TAB'),
                    ('tab at column 0 of a key', base + '\ttun:\n  enable: true\n', 'TAB'),
                    ('a long line', base + 'rule-providers:\n  x: ' + 'a' * 4100 + '\n', '4096'),
                    ('a NUL', base.encode() + b'rules:\n  - MATCH,\x00a\n', 'control character'),
                    ('an escape', base.encode() + b'rules:\n  - MATCH,\x1ba\n', 'control character'),
                    ('a form feed', base.encode() + b'rules:\n  - MATCH,a\x0c\n', 'control character'),
                    ('explicit key', base + 'proxy-groups:\n  - ? "interface-\\\n      name"\n    : eth0\n', 'explicit key'),
                    ('explicit flow key', base + 'proxy-groups:\n  - {? x: 1}\n', 'explicit key'),
                    # yaml.v3 ends a line at a lone CR, NEL, LS and PS too: one line to awk, several to mihomo
                    ('a lone CR', base.encode() + b'proxy-groups:\n  - name: x\rexternal-controller: 0.0.0.0:9090\n', 'line break'),
                    ('a NEL', base.encode() + b'proxy-groups:\n  - name: x\xc2\x85external-controller: 0.0.0.0:9090\n', 'line break'),
                    ('an LS', base.encode() + b'proxy-groups:\n  - name: x\xe2\x80\xa8external-controller: 0.0.0.0:9090\n', 'line break'),
                    ('a PS', base.encode() + b'proxy-groups:\n  - name: x\xe2\x80\xa9listeners:\n', 'line break'),
                    # a tag, a line continued by a backslash and a quoted scalar left open: the three ways a key could
                    # be spelled over more than one line, or without its text
                    ('a tag', base + 'proxy-groups:\n  - !!binary aW50ZXJmYWNlLW5hbWU=: eth0\n', 'tag'),
                    ('a tag before a key', base + 'proxy-groups:\n  - name: x\n    !!str interface-name: eth0\n', 'tag'),
                    ('a tag in a flow mapping', base + 'proxy-groups:\n  - {!!binary aW50ZXJmYWNlLW5hbWU=: eth0}\n', 'tag'),
                    ('a backslash continuation', base + 'proxy-groups:\n  - "interface-\\\n    name": eth0\n', 'backslash'),
                    ('an open double-quoted scalar', base + 'proxy-groups:\n  - "interface-\n    name": eth0\n', 'not closed'),
                    ('an open single-quoted scalar', base + "proxy-groups:\n  - 'interface-\n    name': eth0\n", 'not closed'),
                    ('hex escape', base.replace('ss.example', '"interface\\x2dname"'), 'escape'),
                    ('unicode escape', base.replace('ss.example', '"interface\\u002dname"'), 'escape'),
                    ('a list at the top', base + '- tun:\n    enable: true\n', 'top-level line'),
                    ('a quoted top-level key', base + '"tun":\n  enable: true\n', 'top-level line'),
                    ('a flow collection at column 0', 'proxies: [\n{name: a, type: ss, server: s, port: 1, password: hunter2}\n]\n', 'top-level line'),
                    ('a merge key', base + '<<: {tun: {enable: true}}\n', 'top-level line'),
                    ('a merge key of an anchor', base + 'x: &x {tun: {enable: true}}\n<<: *x\n', 'top-level line'),
                    ('an alias at column 0', base + 'x: &x {tun: {enable: true}}\n*x\n', 'top-level line'),
                    ('an anchor at column 0', base + '&x tun:\n  enable: true\n', 'top-level line'),
                    ('a merge tag', base + 'x: &x {udp: true}\nproxy-groups:\n  - !!merge <<: *x\n', 'tag'),
                    ('a name reserved for the driver', base + 'mu300-anchor-1: {}\n', 'reserved'),
                    ('a reserved name in another case', base + 'MU300-Anchor-1: &p {}\n', 'reserved'),
                    ('a kept key twice', base + 'rules:\n  - MATCH,a\n', 'twice'),
                    ('no proxies', 'rules:\n  - MATCH,DIRECT\n', 'no proxies'),
                    ('empty', '', 'no proxies'),
                    ('a JSON file', '{"proxies": []}', 'not a mihomo config')):
                with self.subTest(what=name):
                    r = self.refused(shell, text, msg, name)
                    self.assertNotIn('MATCH', r.stderr)
                    for planted in ('external-controller', 'listeners', 'aW50', 'eth0'):
                        self.assertNotIn(planted, r.stderr, name)
            # a "!" or a quote in the middle of a quoted value is the value's, and stays
            for name, text, kept in (
                    ('a ! in a password', base.replace('password: hunter2', 'password: "hu!nter2"'), 'password: "hu!nter2"'),
                    ('a quote in a password', base.replace('password: hunter2', 'password: "hu\\"nter2"'), 'password: "hu\\"nter2"'),
                    ('a double quote in a single-quoted password', base.replace('password: hunter2', "password: 'hu\"nter2'"), "password: 'hu\"nter2'"),
                    ('a single quote in a single-quoted password', base.replace('password: hunter2', "password: 'hu''nter2'"), "password: 'hu''nter2'"),
                    ('a quote in a comment', base + '# it is "fine\n', 'MATCH,a'),
                    ('a trailing comment with a quote', base.replace('  - MATCH,a', '  - MATCH,a # "x'), 'MATCH,a')):
                with self.subTest(what=name):
                    self.setup_profile(shell, text)
                    gen = self.gen(shell)
                    self.assertIn(kept, gen, name)
                    self.assertEqual(self.top_keys(gen), ['proxies', 'rules'] + list(MH_OURS))
            # too large: refused before anything reads it
            big = base + '# ' + 'x' * (1 << 20) + '\n'
            r = self.refused(shell, big, '1 MiB', 'too large')
            # a first line that is the document start, a BOM and CRLF line ends are taken, and a blank before the
            # colon is the same key to YAML and to the driver (here: tun, dropped)
            for name, text in (('document start', '---\n' + base), ('BOM', '\ufeff# a subscription\n' + base),
                               ('CRLF', base.replace('\n', '\r\n')),
                               ('a blank before the colon', base + 'tun :\n  enable: true\n')):
                with self.subTest(what=name):
                    self.setup_profile(shell, text)
                    gen = self.gen(shell)
                    self.assertEqual(self.block(gen, 'rules'), ['rules:', '  - MATCH,a'])
                    self.assertEqual(self.top_keys(gen), ['proxies', 'rules'] + list(MH_OURS))
                    self.assertNotIn('\r', gen)
                    self.assertNotIn('\ufeff', gen)
                    self.assertNotIn('---', gen)
                    self.assertEqual(gen.count('enable: true'), 2)

    def test_a_line_break_hidden_in_a_line_never_reaches_mihomo(self):
        # the reviewer's probe: one kept "proxies" line to awk, five top-level lines to yaml.v3 (a controller on
        # every address and a listener among them). Whatever the import said, the rebuild writes no file for it and
        # mihomo is never started on it.
        for sep in (b'\r', b'\xc2\x85', b'\xe2\x80\xa8', b'\xe2\x80\xa9'):
            probe = (b'proxies:\n  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}\n'
                     b'  - name: x' + sep + b'external-controller: 0.0.0.0:9090' + sep + b'listeners:' + sep
                     + b'  - {name: l, type: socks, port: 9999, listen: 0.0.0.0}' + sep + b'secret: s\n'
                     b'rules:\n  - MATCH,a\n')
            for shell in self.each_shell():
                with self.subTest(sep=sep, shell=shell):
                    self.setup_profile(shell)
                    (self.store / 'profiles/sub/config.yaml').write_bytes(probe)
                    r = self.run_lib(shell, 'drv_gen')
                    self.assertNotEqual(r.returncode, 0)
                    self.assertIn('line break', r.stderr)
                    self.no_secrets(r)
                    self.assertFalse((self.run_dir / 'mihomo.yaml').exists())
                    self.assertFalse((self.tmp / 'mihomo.t.args').exists())
                    r = self.cli(shell, 'check', 'sub')
                    self.assertNotEqual(r.returncode, 0)
                    self.no_secrets(r)

    def test_anchors_of_dropped_keys_are_kept_inert(self):
        # subscription templates (and mihomo's own example) put the defaults of providers and groups under keys of
        # their own and merge them with <<: *name; dropping those keys would leave the aliases dangling
        text = '''p: &p {type: http, interval: 3600, health-check: {enable: true, url: "https://g.example/204?a=1&b=2", interval: 300}}
pg: &pg
  type: select
  proxies: [auto, a]
  use: [sub]
tun: &t
  enable: true
  stack: system
secret: "x&y"
proxy-providers:
  sub:
    <<: *p
    url: "https://sub.example/link?token=abc&x=1"
    path: ./sub.yaml
proxies:
  - {name: a, type: ss, server: ss.example, port: 8388, cipher: aes-256-gcm, password: hunter2}
proxy-groups:
  - {name: Proxy, <<: *pg}
  - name: auto
    type: url-test
    <<: *p
    proxies: [a]
rules:
  - MATCH,Proxy
'''
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            gen = self.gen(shell)
            # (x&y is not an anchor: secret goes with the other dropped keys)
            self.assertEqual(self.top_keys(gen),
                             ['mu300-anchor-1', 'mu300-anchor-2', 'mu300-anchor-3',
                              'proxy-providers', 'proxies', 'proxy-groups', 'rules'] + list(MH_OURS))
            lines = gen.splitlines()
            self.assertIn('mu300-anchor-1: &p {type: http, interval: 3600, health-check: {enable: true, url: "https://g.example/204?a=1&b=2", interval: 300}}', lines)
            self.assertEqual(self.block(gen, 'mu300-anchor-2'), ['mu300-anchor-2: &pg', '  type: select', '  proxies: [auto, a]', '  use: [sub]'])
            self.assertEqual(self.block(gen, 'mu300-anchor-3'), ['mu300-anchor-3: &t', '  enable: true', '  stack: system'])
            self.assertNotIn('x&y', gen)
            self.assertIn('    <<: *p', lines)
            self.assertIn('  - {name: Proxy, <<: *pg}', lines)
            self.assertNotRegex(gen, r'(?m)^(p|pg|tun: &t|secret):')
            self.assertEqual(lines.count('tun:'), 1)
            r = self.cli(shell, 'check', 'sub')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('kept for the anchors', r.stderr)
            self.assertIn(' p pg tun\n', r.stderr)
            self.assertIn(' secret', r.stderr)
            # what an anchored block holds goes through the same removals and the same text check
            self.setup_profile(shell, text.replace('pg: &pg\n', 'pg: &pg\n  routing-mark: 9\n'))
            gen = self.gen(shell)
            self.assertNotIn('routing-mark: 9', gen)
            self.assertEqual(self.block(gen, 'mu300-anchor-2'), ['mu300-anchor-2: &pg', '  type: select', '  proxies: [auto, a]', '  use: [sub]'])
            r = self.refused(shell, text.replace('p: &p {type: http,', 'p: &p {type: http, "interface-name": eth0,'), 'interface-name')
            # a dropped block without an anchor is still gone, "&" in a URL or a password is not an anchor
            self.setup_profile(shell, MH_CONF + 'x:\n  url: "https://a.example/?a=1&b=2"\n  password: "p&q"\n')
            self.assertEqual(self.top_keys(self.gen(shell)), ['proxies', 'rules'] + list(MH_OURS))

    def test_written_file_guard_fails_closed(self):
        # the guard behind the rebuild, on files that are not what the driver writes
        good = ('proxies:\n  - {name: a, type: ss}\nrules:\n  - MATCH,a\nrouting-mark: 720\nallow-lan: false\n'
                "bind-address: '127.0.0.1'\ntun:\n  enable: true\ndns:\n  enable: true\n")
        for shell in self.each_shell():
            self.setup_profile(shell)
            f = self.tmp / 'w.yaml'
            for name, text, ok in (
                    ('as written', good, True),
                    ('a controller', good + "external-controller: '127.0.0.1:9090'\n", False),
                    ('a unix controller', good + "external-controller-unix: /run/x.sock\n", False),
                    ('a tls controller', good + "external-controller-tls: '127.0.0.1:9443'\n", False),
                    ('a pipe controller', good + "external-controller-pipe: x\n", False),
                    ('an external ui', good + "external-ui: /x\n", False),
                    ('a key of ours in another case', good + "External-Controller: '127.0.0.1:9090'\n", False),
                    ('two tun', good + 'tun:\n  enable: true\n', False),
                    ('two dns', good + 'dns:\n  enable: true\n', False),
                    ('no tun', good.replace('tun:\n  enable: true\n', ''), False),
                    ('a stray secret', good + 'secret: x\n', False),
                    ('a stray listener', good + 'listeners:\n  - x\n', False),
                    ('a stray port', good + 'mixed-port: 7890\n', False),
                    ('an anchor holder of ours', good + 'mu300-anchor-12: &p {type: http}\n', True),
                    ('an anchor holder spelled otherwise', good + 'mu300-anchor-x: &p {type: http}\n', False),
                    ('allow-lan true', good.replace('allow-lan: false', 'allow-lan: true'), False),
                    ('another mark', good.replace('routing-mark: 720', 'routing-mark: 721'), False),
                    ('no mark', good.replace('routing-mark: 720\n', ''), False),
                    ('a quoted key', good + '"x": 1\n', False),
                    ('a list', good + '- x\n', False),
                    # the guard's line model is yaml.v3's: a line break hidden in a line is several lines to mihomo
                    ('a lone CR in a line', good.encode().replace(b'type: ss}\n', b'type: ss}\rlisteners: []\n'), False),
                    ('a NEL in a line', good.encode().replace(b'type: ss}\n', b'type: ss}\xc2\x85listeners: []\n'), False),
                    ('an LS in a line', good.encode().replace(b'type: ss}\n', b'type: ss}\xe2\x80\xa8listeners: []\n'), False),
                    ('a PS in a line', good.encode().replace(b'type: ss}\n', b'type: ss}\xe2\x80\xa9listeners: []\n'), False),
                    ('a CR at the end of a line', good.encode().replace(b'type: ss}\n', b'type: ss}\r\n'), False)):
                if isinstance(text, bytes):
                    f.write_bytes(text)
                else:
                    f.write_text(text)
                r = self.run_lib(shell, f'mihomo_written_ok "{f}" && echo OK')
                self.assertEqual('OK' in r.stdout, ok, (name, r.stderr))

    def test_engine_and_extra(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'echo "pkg=[$DRV_PKG] extra=[$DRV_EXTRA] tun=$TUN routes=$DRV_ROUTES fg=$DRV_FOREGROUND keys=[$DRV_KEYS]"; '
                                    'drv_engines; drv_engines_ok && echo OK')
            self.assertIn('pkg=[] extra=[vpn-mihomo] tun=mh-mu300 routes=core fg=0 keys=[MIHOMO_STACK]', r.stdout)
            self.assertIn(str(self.stubs / 'mihomo'), r.stdout)
            self.assertIn('OK', r.stdout)
            # the extra's copy comes first, the MIHOMO setting before it
            d = self.tmp / 'disk/extra/vpn-mihomo/bin'
            d.mkdir(parents=True, exist_ok=True)
            shutil.copy(self.stubs / 'mihomo', d / 'mihomo')
            r = self.run_lib(shell, 'drv_engines; drv_engines_ok && echo OK')
            self.assertEqual(r.stdout.splitlines(), [str(d / 'mihomo'), 'OK'])
            r = self.run_lib(shell, 'drv_engines; drv_engines_ok || echo MISSING', f'_mihomo={self.tmp}/none; ')
            self.assertEqual(r.stdout.splitlines(), [f'{self.tmp}/none', 'MISSING'])
            shutil.rmtree(self.tmp / 'disk')
            # without any: the message names the extra
            (self.stubs / 'mihomo').unlink()
            self.assertEqual(self.cli(shell, 'profile', 'use', 'sub').returncode, 0)
            r = self.cli(shell, 'status')
            self.assertIn('mu300-extra install vpn-mihomo', r.stdout + r.stderr)
            r = self.cli(shell, 'on')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('engines install mihomo', r.stderr)
            self.mihomo_stub()

    def test_start_alive_stop(self):
        for shell in self.each_shell():
            self.setup_profile(shell)
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            (self.tmp / 'ip.log').unlink()
            r = self.run_lib(shell, 'drv_start && echo "STARTED pids=[$DRV_PIDS]"; drv_alive && echo ALIVE; '
                                    'p=$DRV_PIDS; drv_stop; echo "stop=$?"; kill -0 $p 2>/dev/null && echo SURVIVED; '
                                    'drv_alive || echo "gone=$DRV_GONE"')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('tunnel up on mh-mu300', r.stdout)
            self.assertRegex(r.stdout, r'STARTED pids=\[[0-9]+\]')
            for want in ('ALIVE', 'stop=0', 'gone=mihomo'):
                self.assertIn(want, r.stdout)
            self.assertNotIn('SURVIVED', r.stdout)
            self.no_secrets(r)
            # mihomo ran the written file from its home, without the path escapes in its environment
            self.assertEqual((self.tmp / 'mihomo.args').read_text().splitlines(),
                             ['-d', str(self.home), '-f', str(self.run_dir / 'mihomo.yaml')])
            self.assertEqual((self.tmp / 'mihomo.env').read_text(), '')
            ip = [l for l in (self.tmp / 'ip.log').read_text().splitlines() if l.startswith('link')]
            self.assertIn('link set mh-mu300 up', ip)
            # the runtime copy (it holds the credentials) goes with the stop
            self.assertFalse((self.run_dir / 'mihomo.yaml').exists())
            # one that exits at once, and one that ignores TERM
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            (self.tmp / 'mh-up').unlink()
            self.mihomo_stub('echo "FATAL hunter2" >&2; exit 1')
            r = self.run_lib(shell, 'drv_start && echo STARTED; echo "pids=[$DRV_PIDS]"')
            self.assertNotIn('STARTED', r.stdout)
            self.assertIn('mihomo exited during start', r.stderr)
            self.assertIn('pids=[]', r.stdout)
            self.mihomo_stub('trap "" TERM\n: > "$STUBLOG/mh-up"\nwhile :; do sleep 1; done')
            r = self.run_lib(shell, 'drv_start; p=$DRV_PIDS; drv_stop; kill -0 $p 2>/dev/null && echo SURVIVED; echo done')
            self.assertIn('done', r.stdout)
            self.assertNotIn('SURVIVED', r.stdout)
            self.mihomo_stub()

    def test_status_says_no_secret(self):
        for shell in self.each_shell():
            self.setup_profile(shell, 'mode: global\n' + MH_CONF)
            self.assertEqual(self.run_lib(shell, 'drv_gen').returncode, 0)
            r = self.run_lib(shell, 'drv_status')
            self.assertEqual(r.stdout.splitlines(), ['mode: global', 'proxies: 1'])
            self.no_secrets(r)

    # ---- the gates the JSON drivers have, one for one (RawJson) ----
    def test_nothing_listens(self):
        # RawJson.test_listener_guard's sibling: every port, listener, control API and UI a Clash file can carry is
        # gone from the written file, in any spelling; the driver writes no controller for anybody (there is no
        # MIHOMO_CONTROLLER setting, and a value of an older store or a legacy vpn.conf is not read), and the guard
        # behind the rebuild refuses a file that has one
        text = ('mixed-port: 7890\nport: 7891\nsocks-port: 7892\nredir-port: 7893\ntproxy-port: 7894\n'
                'allow-lan: true\nbind-address: "*"\nlan-allowed-ips: [0.0.0.0/0]\nlan-disallowed-ips: []\n'
                'authentication: ["u:ctl-secret"]\nskip-auth-prefixes: [127.0.0.1/8]\n'
                "external-controller: '127.0.0.1:9090'\nexternal-controller-tls: 0.0.0.0:9443\n"
                'external-controller-unix: /run/mihomo.sock\nexternal-controller-pipe: x\n'
                'external-controller-cors: {allow-origins: ["*"]}\nexternal-ui: /tmp/ui\nexternal-ui-name: x\n'
                'external-ui-url: https://x.example/ui.zip\nexternal-doh-server: /dns-query\nsecret: ctl-secret\n'
                'External-Controller-Unix: /run/x.sock\nEXTERNAL-UI: /tmp/ui\n'
                'tls: {certificate: /etc/ssl/x.pem, private-key: /etc/ssl/x.key}\n'
                'listeners:\n  - {name: l, type: socks, port: 9999, listen: 0.0.0.0}\n'
                'tunnels: [tcp/udp,127.0.0.1:6553,8.8.8.8:53,proxy]\n'
                'ss-config: ss://x@0.0.0.0:1\nvmess-config: x\ntuic-server: {enable: true, listen: 0.0.0.0:443}\n'
                'dns:\n  enable: true\n  listen: 0.0.0.0:53\n'
                'tun:\n  enable: true\n  auto-route: true\n  auto-detect-interface: true\n  auto-redirect: true\n'
                + MH_BASE)
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            (self.store / 'settings').write_text("MIHOMO_CONTROLLER='127.0.0.1:9090'\n")
            gen = self.gen(shell, 'MIHOMO_CONTROLLER=127.0.0.1:9090; ')
            self.assertEqual(self.top_keys(gen), ['proxies', 'rules'] + list(MH_OURS))
            for gone in ('\nport:', '-port:', 'listen', 'external', 'External', 'EXTERNAL', 'secret', 'ctl-secret', 'authentication',
                         'skip-auth', 'lan-allowed', 'lan-disallowed', '/etc/ssl', 'certificate', 'private-key',
                         'tunnels', 'ss-config', 'vmess-config', 'tuic-server', '0.0.0.0', '9090', '9443', '.sock',
                         'auto-route: true', 'auto-detect-interface: true', 'auto-redirect: true', 'dns-query', '/tmp/ui'):
                self.assertNotIn(gone, gen, gone)
            self.assertIn('  auto-route: false', self.block(gen, 'tun'))
            self.assertIn('  auto-detect-interface: false', self.block(gen, 'tun'))
            self.assertNotIn('listen', '\n'.join(self.block(gen, 'dns')))
            r = self.cli(shell, 'check', 'sub')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.no_secrets(r)
            self.assertNotIn('ctl-secret', r.stdout + r.stderr)
            # nothing can ask for a controller
            r = self.cli(shell, 'settings', 'set', 'MIHOMO_CONTROLLER', '127.0.0.1:9090')
            self.assertNotEqual(r.returncode, 0)
            r = self.cli(shell, 'settings', 'get')
            self.assertNotIn('MIHOMO_CONTROLLER', r.stdout + r.stderr)
            r = self.run_lib(shell, 'mihomo_ours gvisor; echo "ours=[$MIHOMO_OURS]"', 'MIHOMO_CONTROLLER=127.0.0.1:9090; ')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn('external', r.stdout)
            self.assertNotIn('9090', r.stdout)
            self.assertIn('ours=[routing-mark allow-lan bind-address tun dns]', r.stdout)

    def test_keys_spelled_differently_are_refused(self):
        # RawJson.test_keys_are_the_shapes_named_exactly's sibling: a top-level key that is one of the kept names
        # or ours in another spelling (another case, _ for -) is refused, naming the name it collides with and
        # nothing of the file. (mihomo's reader is case-sensitive and would not read it; the file is refused rather
        # than reduced to something its author did not mean, as the JSON drivers do.)
        for shell in self.each_shell():
            for extra, name in (('Proxies: []\n', 'proxies'), ('proxy_groups: []\n', 'proxy-groups'),
                                ('RULES: []\n', 'rules'), ('Rule_Providers: {}\n', 'rule-providers'),
                                ('Tun:\n  enable: true\n', 'tun'), ('DNS: {listen: 0.0.0.0:53}\n', 'dns'),
                                ('Routing_Mark: 1\n', 'routing-mark'), ('Allow-LAN: true\n', 'allow-lan'),
                                ('Bind_Address: "*"\n', 'bind-address'), ('Mode: global\n', 'mode')):
                with self.subTest(what=extra):
                    r = self.refused(shell, MH_BASE + extra, 'spelled differently from ' + name, extra)
                    self.assertNotIn(extra.split(':')[0], r.stderr)
                    self.assertNotIn('0.0.0.0', r.stderr)
            # the exact spelling next to the other one is refused the same way, not taken as "twice"
            r = self.refused(shell, MH_BASE + 'Rules: []\n', 'spelled differently from rules')
            self.assertNotIn('twice', r.stderr)

    def test_the_size_cap_comes_before_any_read(self):
        # RawJson.test_the_size_cap_comes_before_any_full_read's sibling: the cap is the first thing the reader
        # and the import run, before the control-character count and before awk sees a line
        big = self.tmp / 'big.yaml'
        big.write_text(MH_BASE + '# ' + 'x' * (1 << 20) + '\n')
        for shell in self.each_shell():
            self.setup_profile(shell)
            r = self.run_lib(shell, 'awk() { echo AWK-RAN; }; '
                                    f'mihomo_read check "{big}" || echo no; mihomo_read gen "{big}" || echo no; '
                                    f'drv_import "{big}" || echo no')
            self.assertEqual(r.stdout.splitlines(), ['the mihomo config is larger than 1 MiB', 'no', 'no', 'no'], r.stderr)
            self.assertIn('1 MiB', r.stderr)
            self.assertNotIn('AWK-RAN', r.stdout + r.stderr)
            self.assertEqual((self.store / 'profiles/sub/config.yaml').read_text(), MH_CONF)
        text = (LIB / 'mihomo.sh').read_text()
        for fn in ('mihomo_read() {', 'drv_import() {'):
            body = text[text.index(fn):text.index('\n}\n', text.index(fn))]
            for reader in (' awk ', ' tr ', ' cat ', ' is_json ', ' mihomo_read '):
                if reader in body:
                    self.assertLess(body.index('json_size_ok'), body.index(reader), (fn, reader))

    def test_an_alias_cannot_bring_a_key_in(self):
        # the JSON drivers strip the dial fields at every depth; here what an alias or a merge key can bring into
        # a kept block comes from an anchored block that went through the same removals and the same text check,
        # and the top-level keys stay the lines the reader saw (a merge key, an alias or an anchor at column 0 is
        # no KEY: line, see test_refusals_name_the_rule_and_nothing_of_the_file)
        text = ('x: &x\n  Interface-Name: eth0\n  routing-mark: 9\n  udp: true\n'
                't: &t {enable: true, auto-route: true, auto-detect-interface: true, interface-name: eth0}\n'
                'd: &d {enable: true, listen: 0.0.0.0:53, ROUTING-MARK: 9}\n'
                + MH_BASE + 'proxy-groups:\n  - name: g\n    type: select\n    <<: *x\n    proxies: [a]\n'
                'profile: *t\nsniffer: *d\n')
        for shell in self.each_shell():
            self.setup_profile(shell, text)
            gen = self.gen(shell)
            lines = gen.splitlines()
            self.assertEqual(self.top_keys(gen), ['mu300-anchor-1', 'mu300-anchor-2', 'mu300-anchor-3',
                                                  'proxies', 'rules', 'proxy-groups', 'profile', 'sniffer'] + list(MH_OURS))
            self.assertEqual(self.block(gen, 'mu300-anchor-1'), ['mu300-anchor-1: &x', '  udp: true'])
            self.assertIn('mu300-anchor-2: &t {enable: true, auto-route: true, auto-detect-interface: true}', lines)
            self.assertIn('mu300-anchor-3: &d {enable: true, listen: 0.0.0.0:53}', lines)
            self.assertIn('    <<: *x', lines)
            self.assertIn('profile: *t', lines)
            for gone in ('eth0', 'routing-mark: 9', 'ROUTING-MARK', 'Interface-Name', 'interface-name'):
                self.assertNotIn(gone, gen, gone)
            self.assertEqual(lines.count('tun:'), 1)
            self.assertEqual(lines.count('dns:'), 1)
            self.assertIn('  auto-route: false', self.block(gen, 'tun'))
            self.assertEqual(gen.count('routing-mark'), 1)
            self.assertIn('routing-mark: 720', lines)
            # the written file passes its own guard, and the check says which blocks were kept for their anchors
            r = self.cli(shell, 'check', 'sub')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(' x t d\n', r.stderr)
            self.no_secrets(r)


class EnginesCmd(ShellTest):
    """mu300-vpn engines: one TSV line per engine, present with its path or missing with how to get it, with the
    exit status of the active profile's engines; engines install ENGINE runs mu300-extra or this system's package
    manager (apk on OpenWrt, else apt-get, else pacman)."""

    # the tools the script needs, on a PATH of its own: a real wg, openvpn, mihomo, apt-get or pacman of this
    # machine must not be found, since the lines and the package command depend on what is there
    TOOLS = ('sh', 'sed', 'awk', 'grep', 'cat', 'tr', 'cut', 'head', 'tail', 'mkdir', 'chmod', 'rm', 'mv', 'cp',
             'ln', 'date', 'wc', 'sort', 'uniq', 'od', 'basename', 'dirname', 'readlink', 'stat', 'touch', 'find',
             'mktemp', 'env', 'id', 'true', 'false', 'sleep', 'printf', 'echo', 'test', 'expr', 'xargs', 'tee',
             'ls', 'cmp', 'diff', 'uname', 'jq', 'openssl', 'base64', 'dd', 'sync', 'busybox', 'bash', 'dash')

    def setUp(self):
        super().setUp()
        self.conf = self.tmp / 'vpn.conf'
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.store = self.tmp / 'vpn'
        self.disk = self.tmp / 'disk'
        self.opt = self.tmp / 'opt'
        self.sysroot = self.tmp / 'sysroot'
        self.tools = self.tmp / 'tools'
        self.tools.mkdir()
        for t in self.TOOLS:
            p = shutil.which(t)
            if p:
                os.symlink(p, self.tools / t)
        self.stub('svc', 'exit 0')
        self.stub('nft', 'exit 0')
        self.stub('extra', 'echo "extra $*" >> "$STUBLOG/extra.log"; exit 0')
        self.kernel(True)
        self.src = self.tmp / 'wg.conf'
        self.src.write_text(WG_CONF)

    def kernel(self, has):
        # "link show" finds no tunnel; "link add ... type wireguard" works only on a kernel that has WireGuard
        add = 'exit 0' if has else 'exit 2'
        self.stub('ip', 'case "$*" in "link show"*) exit 1 ;; "link add"*) %s ;; esac; exit 0' % add)

    def pkg(self, *names):
        """only these package managers exist, each noting its call (and failing when told to with PKG_FAIL)"""
        for n in ('apk', 'apt-get', 'pacman'):
            (self.stubs / n).unlink(missing_ok=True)
        for n in names:
            self.stub(n, f'echo "{n} $*" >> "$STUBLOG/pkg.log"; exit "${{PKG_FAIL:-0}}"')
        (self.tmp / 'pkg.log').unlink(missing_ok=True)

    def pkglog(self):
        return (self.tmp / 'pkg.log').read_text().splitlines() if (self.tmp / 'pkg.log').exists() else []

    def engine(self, name, where):
        """an executable NAME in the vpn extra, the vpn-mihomo extra, /opt/mu300/bin or on PATH; its path"""
        d = {'vpn': self.disk / 'extra/vpn/bin', 'vpn-mihomo': self.disk / 'extra/vpn-mihomo/bin',
             'opt': self.opt / 'bin', 'path': self.stubs}[where]
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text('#!/bin/sh\nexit 0\n')
        (d / name).chmod(0o755)
        return str(d / name)

    def fresh(self):
        for d in (self.store, self.disk, self.opt, self.sysroot, self.tmp / 'run'):
            shutil.rmtree(d, ignore_errors=True)
        for n in ('wg', 'openvpn', 'mihomo'):
            (self.stubs / n).unlink(missing_ok=True)
        for n in ('extra.log', 'pkg.log'):
            (self.tmp / n).unlink(missing_ok=True)
        self.conf.write_text('ENABLE=0\nKILL_SWITCH=0\n')
        self.pkg('apt-get')

    def openwrt(self):
        (self.sysroot / 'etc').mkdir(parents=True, exist_ok=True)
        (self.sysroot / 'etc/openwrt_release').write_text("DISTRIB_ID='OpenWrt'\n")

    def vpn(self, shell, *args, **extra):
        env = dict(MU300_VPN_CONF=self.conf, MU300_VPN_RUN=self.tmp / 'run', MU300_VPN_LIB=LIB,
                   MU300_LAN_CONF=self.tmp / 'no', MU300_BIN=BIN, MU300_OPT=self.opt, MU300_DISK=self.disk,
                   MU300_VPN_SVC=self.stubs / 'svc', MU300_EXTRA_CMD=self.stubs / 'extra',
                   MU300_WG_SYSMOD=self.tmp / 'no-module', MU300_SYSROOT=self.sysroot,
                   PATH=f'{self.stubs}{os.pathsep}{self.tools}')
        env.update(extra)
        return self.script(shell, BIN / 'mu300-vpn', *args, **env)

    def extra_log(self):
        return (self.tmp / 'extra.log').read_text().splitlines() if (self.tmp / 'extra.log').exists() else []

    def test_every_engine_missing_says_how(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.vpn(shell, 'engines')
            self.assertEqual(r.stdout.splitlines(), [
                'xray\tmissing\tmu300-extra install vpn',
                'hev-socks5-tunnel\tmissing\tmu300-extra install vpn',
                'sing-box\tmissing\tmu300-extra install vpn',
                'mihomo\tmissing\tmu300-extra install vpn-mihomo',
                'wireguard\tmissing\tmu300-vpn engines install wireguard (apt-get install -y wireguard-tools)',
                'openvpn\tmissing\tmu300-vpn engines install openvpn (apt-get install -y openvpn)'], r.stderr)
            # no active profile: the status is the vpn extra's engines for the default type
            self.assertEqual(r.returncode, 1)
            self.assertIn('mu300-extra install vpn', r.stderr)
            # the package command is this system's: apk on OpenWrt (where openvpn is openvpn-openssl), pacman
            # without apt-get, and none at all is said
            self.openwrt(); self.pkg('apk', 'apt-get')
            lines = self.vpn(shell, 'engines').stdout.splitlines()
            self.assertEqual(lines[4:], [
                'wireguard\tmissing\tmu300-vpn engines install wireguard (apk add wireguard-tools)',
                'openvpn\tmissing\tmu300-vpn engines install openvpn (apk add openvpn-openssl)'])
            shutil.rmtree(self.sysroot); self.pkg('pacman')
            lines = self.vpn(shell, 'engines').stdout.splitlines()
            self.assertEqual(lines[4:], [
                'wireguard\tmissing\tmu300-vpn engines install wireguard (pacman -S --noconfirm --needed wireguard-tools)',
                'openvpn\tmissing\tmu300-vpn engines install openvpn (pacman -S --noconfirm --needed openvpn)'])
            self.pkg()
            lines = self.vpn(shell, 'engines').stdout.splitlines()
            self.assertEqual(lines[4:], [
                'wireguard\tmissing\tmu300-vpn engines install wireguard (no apk, apt-get or pacman here: wireguard-tools by hand)',
                'openvpn\tmissing\tmu300-vpn engines install openvpn (no apk, apt-get or pacman here: openvpn by hand)'])

    def test_every_engine_present_with_its_path(self):
        for shell in self.each_shell():
            self.fresh()
            want = ['xray\tpresent\t' + self.engine('xray', 'vpn'),
                    'hev-socks5-tunnel\tpresent\t' + self.engine('hev-socks5-tunnel', 'vpn'),
                    'sing-box\tpresent\t' + self.engine('sing-box', 'vpn'),
                    'mihomo\tpresent\t' + self.engine('mihomo', 'vpn-mihomo'),
                    'wireguard\tpresent\t' + self.engine('wg', 'path'),
                    'openvpn\tpresent\t' + self.engine('openvpn', 'path')]
            r = self.vpn(shell, 'engines')
            self.assertEqual(r.stdout.splitlines(), want, r.stderr)
            self.assertEqual((r.returncode, r.stderr), (0, ''))
            # an older image's own copy, and a package's on PATH, are found where the extra has none
            shutil.rmtree(self.disk)
            want = ['xray\tpresent\t' + self.engine('xray', 'opt'),
                    'hev-socks5-tunnel\tpresent\t' + self.engine('hev-socks5-tunnel', 'path'),
                    'sing-box\tpresent\t' + self.engine('sing-box', 'opt'),
                    'mihomo\tpresent\t' + self.engine('mihomo', 'opt')]
            r = self.vpn(shell, 'engines')
            self.assertEqual(r.stdout.splitlines()[:4], want, r.stderr)
            self.assertEqual(r.returncode, 0, r.stderr)
            # the settings naming other binaries: those are what is reported
            r = self.vpn(shell, 'engines', MIHOMO=self.tmp / 'none', OPENVPN=self.tmp / 'none')
            self.assertIn('mihomo\tmissing\tmu300-extra install vpn-mihomo', r.stdout.splitlines())
            self.assertIn('openvpn\tmissing\tmu300-vpn engines install openvpn (apt-get install -y openvpn)',
                          r.stdout.splitlines())

    def test_wireguard_needs_the_kernel_too(self):
        for shell in self.each_shell():
            self.fresh()
            wg = self.engine('wg', 'path')
            self.kernel(False)
            r = self.vpn(shell, 'engines')
            self.assertIn('wireguard\tmissing\tmu300-vpn engines install wireguard (apt-get install -y wireguard-tools)',
                          r.stdout.splitlines())
            # the module directory alone says the kernel has it
            (self.tmp / 'no-module').mkdir()
            r = self.vpn(shell, 'engines')
            (self.tmp / 'no-module').rmdir()
            self.assertIn(f'wireguard\tpresent\t{wg}', r.stdout.splitlines())
            self.kernel(True)
            r = self.vpn(shell, 'engines')
            self.assertIn(f'wireguard\tpresent\t{wg}', r.stdout.splitlines())

    def test_exit_status_follows_the_active_profile(self):
        for shell in self.each_shell():
            self.fresh()
            r = self.vpn(shell, 'profile', 'import', self.src, 'Wg')
            self.assertEqual((r.returncode, r.stdout.strip()), (0, 'wg'), r.stderr)
            self.assertEqual(self.vpn(shell, 'profile', 'use', 'wg').returncode, 0)
            # the vpn extra's engines do not help a wireguard profile
            for n in ('xray', 'hev-socks5-tunnel', 'sing-box'):
                self.engine(n, 'vpn')
            r = self.vpn(shell, 'engines')
            self.assertEqual(r.returncode, 1, r.stdout)
            self.assertEqual(len(r.stdout.splitlines()), 6)
            self.assertIn('wireguard engine is not installed: run mu300-vpn engines install wireguard', r.stderr)
            self.engine('wg', 'path')
            self.kernel(False)
            self.assertEqual(self.vpn(shell, 'engines').returncode, 1)
            self.kernel(True)
            r = self.vpn(shell, 'engines')
            self.assertEqual((r.returncode, r.stderr), (0, ''), r.stdout)
            # the lines are the same whatever the active profile; the loaded driver leaves no trace in them
            state = [l.split('\t')[1] for l in r.stdout.splitlines()]
            self.assertEqual(state, ['present', 'present', 'present', 'missing', 'present', 'missing'])
            # no engines at all, no profile: as before profiles existed
            self.fresh()
            r = self.vpn(shell, 'engines')
            self.assertEqual(r.returncode, 1)
            for n in ('xray', 'hev-socks5-tunnel'):
                self.engine(n, 'vpn')
            self.assertEqual(self.vpn(shell, 'engines').returncode, 0)

    def test_install_runs_the_extra_or_the_package_manager(self):
        for shell in self.each_shell():
            self.fresh()
            for eng, extra in (('xray', 'vpn'), ('hev-socks5-tunnel', 'vpn'), ('sing-box', 'vpn'),
                               ('mihomo', 'vpn-mihomo')):
                (self.tmp / 'extra.log').unlink(missing_ok=True)
                r = self.vpn(shell, 'engines', 'install', eng)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertEqual(self.extra_log(), [f'extra install {extra}'])
            self.assertEqual(self.pkglog(), [])
            # OpenWrt: apk, and openvpn's package carries the TLS library
            self.openwrt(); self.pkg('apk', 'apt-get', 'pacman')
            r = self.vpn(shell, 'engines', 'install', 'openvpn')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(self.pkglog(), ['apk add openvpn-openssl'])
            self.pkg('apk')
            self.assertEqual(self.vpn(shell, 'engines', 'install', 'wireguard').returncode, 0)
            self.assertEqual(self.pkglog(), ['apk add wireguard-tools'])
            # Ubuntu: apt-get, its lists refreshed first
            shutil.rmtree(self.sysroot); self.pkg('apt-get', 'pacman')
            self.assertEqual(self.vpn(shell, 'engines', 'install', 'openvpn').returncode, 0)
            self.assertEqual(self.pkglog(), ['apt-get update', 'apt-get install -y openvpn'])
            # Arch: pacman
            self.pkg('pacman')
            self.assertEqual(self.vpn(shell, 'engines', 'install', 'wireguard').returncode, 0)
            self.assertEqual(self.pkglog(), ['pacman -S --noconfirm --needed wireguard-tools'])
            # a package manager that fails: so does the command
            self.pkg('pacman')
            r = self.vpn(shell, 'engines', 'install', 'openvpn', PKG_FAIL='3')
            self.assertEqual(r.returncode, 3)
            self.assertEqual(self.pkglog(), ['pacman -S --noconfirm --needed openvpn'])
            # none: a message that names the package
            self.pkg()
            r = self.vpn(shell, 'engines', 'install', 'openvpn')
            self.assertEqual(r.returncode, 1)
            self.assertIn('openvpn', r.stderr)
            self.assertEqual(r.stdout, '')
            self.assertEqual(self.extra_log(), ['extra install vpn-mihomo'])

    def test_install_takes_only_a_known_engine(self):
        for shell in self.each_shell():
            self.fresh()
            for args in (('install', 'foo'), ('install',), ('install', 'openvpn', 'now'), ('list',),
                         ('install', '../x'), ('install', 'vpn')):
                r = self.vpn(shell, 'engines', *args)
                self.assertEqual(r.returncode, 2, args)
                self.assertIn('usage: mu300-vpn engines [install ', r.stderr)
                self.assertEqual(r.stdout, '', args)
            self.assertEqual(self.extra_log(), [])
            self.assertEqual(self.pkglog(), [])
