"""The LuCI control panel's rpcd backend (luci-app-mu300's mu300dash) runs as root on input from the web UI: every
parameter is checked against an allow-list before anything runs, untrusted text reaches the adapters only as one exact
argument (or on stdin), and every reply is JSON whatever the adapters and the modem print.

`mu300dash call <method>` runs with the request on stdin, as rpcd runs it, under each shell. Every command it calls
is a stub that records its arguments (one file per call, NUL-separated) and prints what the test chose. jsonfilter is
an OpenWrt tool not found on the test machine: a stand-in in Python behaves as it does for what mu300dash asks of it
(an `@.key` / `@` path, a string printed raw, anything else as JSON, one value parsed and trailing text ignored,
raw control characters inside strings accepted), except that a NUL inside a string is printed instead of ending it,
which is the harder case for the backend."""
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from helpers import GIT_CHECKOUT, TOP, ShellTest

APP = TOP / 'openwrt' / 'luci-app-mu300' / 'root'
DASH = APP / 'usr' / 'libexec' / 'rpcd' / 'mu300dash'
ADAPTERS = APP / 'usr' / 'libexec' / 'unisoc-modem'
ACL = APP / 'usr' / 'share' / 'rpcd' / 'acl.d' / 'luci-app-mu300.json'

JSONFILTER = r'''
import json, re, sys
args, src, exprs = sys.argv[1:], None, []
while args:
    opt, val, args = args[0], args[1], args[2:]
    if opt == '-s':
        src = val
    elif opt == '-i':
        src = open(val, 'rb').read().decode('utf-8', 'surrogateescape')
    elif opt == '-e':
        exprs.append(val)
    else:
        sys.exit(2)
if src is None:
    src = sys.stdin.buffer.read().decode('utf-8', 'surrogateescape')
try:
    doc = json.JSONDecoder(strict=False).raw_decode(src.lstrip())[0]
except ValueError:
    sys.stderr.write('Failed to parse json data\n')
    sys.exit(125)
found = []
for e in exprs:
    m = re.fullmatch(r'[@$]((?:\.[A-Za-z_][A-Za-z0-9_]*|\[(?:\*|\d+)\])*)', e)
    if not m:
        sys.exit(2)
    vals = [doc]
    for key, idx in re.findall(r'\.([A-Za-z_][A-Za-z0-9_]*)|\[(\*|\d+)\]', m.group(1)):
        nxt = []
        for v in vals:
            if key and isinstance(v, dict) and key in v:
                nxt.append(v[key])
            elif idx == '*' and isinstance(v, list):
                nxt.extend(v)
            elif idx and idx != '*' and isinstance(v, list) and int(idx) < len(v):
                nxt.append(v[int(idx)])
        vals = nxt
    found += vals
out = sys.stdout.buffer
for v in found:
    if isinstance(v, str):
        s = v
    elif v is None:
        s = 'null'
    elif isinstance(v, bool):
        s = 'true' if v else 'false'
    else:
        s = json.dumps(v, ensure_ascii=False)
    out.write(s.encode('utf-8', 'surrogateescape') + b'\n')
sys.exit(0 if found else 1)
'''

# A recording stub: one file per call in $STUB_CALLS (name and arguments, NUL-separated), what came on stdin for
# an SMS send, then the output the test put in $STUB_OUT/<name> (or the default given here).
RECORDER = r'''#!/bin/sh
f=$(mktemp "$STUB_CALLS/call.XXXXXX")
printf '%s\0' "{name}" "$@" > "$f"
[ "{name}" = sms ] && [ "${{1:-}}" = send ] && cat > "$f.stdin"
if [ "{name}" = cell ] && [ -f "$STUB_OUT/sig.json" ]; then cp "$STUB_OUT/sig.json" "$MU300_DASH_DIR/sig.json"; fi
if [ -f "$STUB_OUT/{name}" ]; then cat "$STUB_OUT/{name}"; else printf '%s\n' '{default}'; fi
[ -f "$STUB_OUT/{name}.rc" ] && exit "$(cat "$STUB_OUT/{name}.rc")"
exit 0
'''

DEFAULTS = {
    'dashboard-info': '{"ok":1,"host":"f50"}', 'cell': '{"ok":1}', 'action': '{"ok":1,"op":"x"}',
    'lock': '{"ok":1,"mode":{"label":"auto"}}', 'device-usb': '{"ok":1}', 'at': 'OK', 'sms': 'sent (12)',
    'languages': '{"ok":1}', 'power': '{"ok":1}', 'ttl': '{"ok":1}',
}

# The methods that start something with setsid (in the background of mu300dash)
DETACHED = {'act', 'lock_set', 'sms_sync', 'status'}

# Hostile values: each is refused by every field that takes a fixed set, a number or a name. The NUL cases: the
# stand-in jsonfilter passes the NUL on (the backend maps it to \001 and refuses); the real jsonfilter prints strings
# with %s and so ends the value at the NUL - on the device "a\u0000b" arrives as "a", neutralised rather than refused.
HOSTILE = {
    'single quote': "'", 'double quote': '"', 'newline': 'x\ny', 'semicolon': ';reboot', 'subst': '$(reboot)',
    'backtick': '`reboot`', 'pipe': '|reboot', 'ampersand': '&reboot', 'leading dash': '-rf', 'nul': '\x00',
    'long': 'A' * 10000, 'non-ascii': 'ğüş中', 'object': {'a': 1}, 'array': [1],
}


def hostile_variants(valid):
    """The hostile values alone, and appended to a valid value (an exact pattern refuses both)."""
    out = dict(HOSTILE)
    for k, v in HOSTILE.items():
        if isinstance(v, str):
            out[k + ' after ' + valid] = valid + v
    out['trailing newline'] = valid + '\n'
    out['leading space'] = ' ' + valid
    return out


class Mu300Dash(ShellTest):
    def setUp(self):
        super().setUp()
        (self.stubs / 'jsonfilter.py').write_text(JSONFILTER)
        self.stub('jsonfilter', f'exec python3 "{self.stubs}/jsonfilter.py" "$@"')
        self.stub('uci', 'exit 1')
        self.stub('logger', 'exit 0')
        # setsid: record what would have been started detached, start nothing
        # it runs in the background of mu300dash, so it writes its record whole (rename) and call() waits for it
        self.stub('setsid', 't=$(mktemp "$STUB_CALLS/.tmp.XXXXXX"); printf "%s\\0" setsid "$@" > "$t"; '
                            'mv "$t" "$STUB_CALLS/call.${t##*.}"')
        self.adapters = self.tmp / 'adapters'
        self.adapters.mkdir()
        for name, default in DEFAULTS.items():
            p = self.adapters / name
            p.write_text(RECORDER.format(name=name, default=default))
            p.chmod(0o755)
        self.out = self.tmp / 'out'
        self.out.mkdir()
        self.n = 0

    def output(self, name, text):
        """What the stub NAME prints from now on."""
        (self.out / name).write_text(text)

    def call(self, shell, method, params=None, raw=None, **extra):
        """Run `mu300dash call METHOD` with PARAMS (JSON) on stdin: (CompletedProcess, [[name, arg...], ...],
        {call index: stdin text})."""
        self.n += 1
        run = self.tmp / f'run{self.n}'
        calls = run / 'calls'
        calls.mkdir(parents=True)
        (run / 'dash').mkdir()
        for cache in ('cell.json', 'sig.json'):   # the collector's caches, as the stubs' output
            if (self.out / cache).exists():
                (run / 'dash' / cache).write_bytes((self.out / cache).read_bytes())
        stdin = raw if raw is not None else json.dumps(params or {}, ensure_ascii=False)
        env = self.env(STUB_CALLS=calls, STUB_OUT=self.out, MU300_DASH_BIN=self.adapters,
                       MU300_DASH_DIR=run / 'dash', MU300_AT=self.adapters / 'at', MU300_SMS_BIN=self.adapters / 'sms',
                       MU300_SMS_POOL=run / 'pool')
        env.update({k: str(v) for k, v in extra.items()})
        env = {k: v for k, v in env.items() if v != ''}
        r = subprocess.run(shell + [str(DASH), 'call', method], input=stdin.encode(), capture_output=True,
                           env=env, timeout=60)
        r.stdout, r.stderr = r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
        # a detached start may land a moment after mu300dash has answered: wait until two looks 0.1 s apart agree
        if method in DETACHED:
            seen, deadline = None, time.monotonic() + 3
            while time.monotonic() < deadline:
                now = sorted(calls.glob('call.*'))
                if now == seen:
                    break
                seen = now
                time.sleep(0.1)
        recs, stdins = [], {}
        for f in sorted(calls.glob('call.*')):
            if f.suffix == '.stdin':
                continue
            rec = [a.decode('utf-8', 'surrogateescape') for a in f.read_bytes().split(b'\0')[:-1]]
            if rec[0] == 'setsid':
                rec = ['setsid', Path(rec[1]).name] + rec[2:]
            sin = f.with_name(f.name + '.stdin')
            if sin.exists():
                stdins[len(recs)] = sin.read_text()
            recs.append(rec)
        return r, recs, stdins

    def reply(self, r):
        """The reply: one JSON object, whatever happened."""
        try:
            obj = json.loads(r.stdout)
        except ValueError as e:
            self.fail(f'not JSON ({e}): {r.stdout!r} stderr={r.stderr!r}')
        self.assertIsInstance(obj, dict, r.stdout)
        return obj

    def calls_parallel(self, shell, jobs):
        """[(label, method, params)] -> [(label, CompletedProcess, calls, stdins)], several at a time."""
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda j: (j[0],) + self.call(shell, j[1], j[2]), jobs))
        return res

    def assert_refused(self, shell, jobs):
        for label, r, recs, _ in self.calls_parallel(shell, jobs):
            with self.subTest(case=label):
                obj = self.reply(r)
                self.assertEqual(obj.get('ok'), 0, (label, r.stdout))
                self.assertTrue(obj.get('error'), r.stdout)
                self.assertEqual(recs, [], f'{label}: something ran')


class Inventory(Mu300Dash):
    METHODS = {'sysinfo', 'status', 'signal', 'act', 'at', 'at_history', 'lock_get', 'lock_set', 'sms_list',
               'sms_show', 'sms_send', 'sms_delete', 'sms_sync', 'usb_get', 'usb_set', 'usb_net_list', 'usb_net_add',
               'lang_get', 'lang_set', 'power_get', 'power_set',
               'ttl_get', 'ttl_set', 'cpu_get', 'cpu_set'}

    def test_list_declares_every_method(self):
        for shell in self.each_shell():
            r = self.script(shell, DASH, 'list')
            self.assertEqual(set(json.loads(r.stdout)), self.METHODS)

    def test_an_unknown_method_runs_nothing(self):
        for shell in self.each_shell():
            r, recs, _ = self.call(shell, 'rm -rf /', {})
            self.assertEqual(self.reply(r)['ok'], 0)
            self.assertEqual(recs, [])

    def test_a_request_too_large_is_refused(self):
        for shell in self.each_shell():
            r, recs, _ = self.call(shell, 'sms_send', {'num': '123', 'text': 'x' * 20000})
            self.assertEqual(self.reply(r)['ok'], 0)
            self.assertEqual(recs, [])

    def test_the_changed_scripts_parse(self):
        for shell in self.each_shell():
            for p in [DASH, LIB] + [ADAPTERS / n for n in ('action', 'at', 'boot-replay', 'cell', 'dashboard-info',
                                                         'device-usb', 'lock', 'languages', 'power', 'ttl', 'cpu')]:
                with self.subTest(p=p.name):
                    r = subprocess.run(shell + ['-n', str(p)], capture_output=True, text=True)
                    self.assertEqual(r.returncode, 0, r.stderr)


class Refusals(Mu300Dash):
    """Every hostile value in every field is refused with ok:0 before anything runs."""

    FIELDS = [
        # (method, valid params, field, a valid value of the field)
        ('act', {'op': 'radio', 'arg': 'on'}, 'op', 'radio'),
        ('act', {'op': 'radio', 'arg': 'on'}, 'arg', 'on'),
        ('act', {'op': 'data', 'arg': 'up'}, 'arg', 'up'),
        ('act', {'op': 'wifi', 'arg': 'off'}, 'arg', 'off'),
        ('act', {'op': 'vpn', 'arg': 'start'}, 'arg', 'start'),
        ('act', {'op': 'os', 'arg': 'android'}, 'arg', 'android'),
        ('act', {'op': 'os', 'arg': 'lock'}, 'arg', 'lock'),
        ('act', {'op': 'reboot'}, 'arg', ''),
        ('act', {'op': 'modem-reset'}, 'arg', ''),
        ('lock_get', {}, 'fresh', '1'),
        ('lock_set', {'kind': 'endc', 'val': 'on'}, 'kind', 'endc'),
        ('lock_set', {'kind': 'mode', 'val': 'sa'}, 'val', 'sa'),
        ('lock_set', {'kind': 'endc', 'val': 'on'}, 'val', 'on'),
        ('lock_set', {'kind': 'auto_apply', 'val': 'off'}, 'val', 'off'),
        ('lock_set', {'kind': 'lte', 'val': '1,3'}, 'val', '1,3'),
        ('lock_set', {'kind': 'nr', 'val': '78'}, 'val', '78'),
        ('lock_set', {'kind': 'cell', 'val': 'nr:627264,393'}, 'val', 'nr:627264,393'),
        ('lock_set', {'kind': 'cell', 'val': 'off-lte'}, 'val', 'off-lte'),
        ('lock_set', {'kind': 'reset', 'val': 'auto'}, 'kind', 'reset'),
        ('lock_set', {'kind': 'reset', 'val': 'auto'}, 'val', 'auto'),
        ('sms_list', {}, 'page', '2'),
        ('sms_show', {}, 'id', '12'),
        ('sms_send', {'num': '+905551112233', 'text': 'hi'}, 'num', '+905551112233'),
        ('sms_delete', {'id': '3'}, 'id', '3'),
        ('sms_delete', {'id': '3'}, 'sim', '1'),
        ('usb_set', {'kind': 'role', 'value': 'host', 'scope': '', 'auto': '0'}, 'kind', 'role'),
        ('lang_set', {'op': 'enable', 'codes': 'de'}, 'op', 'enable'),
        ('power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': '15'}, 'op', 'set'),
        ('power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': '15'}, 'key', 'battery.WIFI_IDLE'),
        ('power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': '15'}, 'value', '15'),
        ('power_set', {'op': 'wake'}, 'key', ''),
        ('power_set', {'op': 'wake'}, 'value', ''),
        ('lang_set', {'op': 'enable', 'codes': 'de'}, 'codes', 'de'),
        ('lang_set', {'op': 'disable', 'codes': 'de pt_br'}, 'codes', 'de pt_br'),
        ('lang_set', {'op': 'use', 'codes': 'en'}, 'codes', 'en'),
        ('lang_set', {'op': 'install', 'source': 'file'}, 'source', 'file'),
        ('usb_set', {'kind': 'role', 'value': 'host', 'scope': '', 'auto': '0'}, 'value', 'host'),
        ('usb_set', {'kind': 'role', 'value': 'host', 'scope': '', 'auto': '0'}, 'auto', '0'),
        ('usb_set', {'kind': 'role', 'value': 'host', 'scope': '', 'auto': '0'}, 'scope', ''),
        ('usb_set', {'kind': 'net', 'value': 'ncm', 'scope': 'once', 'auto': '1'}, 'value', 'ncm'),
        ('usb_set', {'kind': 'net', 'value': 'ncm', 'scope': 'once', 'auto': '1'}, 'scope', 'once'),
        ('usb_set', {'kind': 'net', 'value': 'ncm', 'scope': 'once', 'auto': '1'}, 'auto', '1'),
        ('usb_net_add', {}, 'iface', 'eth1'),
        ('ttl_set', {}, 'value', '64'),
        ('ttl_set', {}, 'value', 'off'),
    ]

    def test_hostile_values_are_refused(self):
        jobs = []
        for method, base, field, valid in self.FIELDS:
            for name, bad in hostile_variants(valid).items():
                if name.startswith('leading space') and valid == '':
                    continue
                if field == 'iface' and name == 'leading dash after eth1':
                    continue   # eth1-rf is a valid interface name, and not an option
                jobs.append((f'{method}.{field}={name}', method, dict(base, **{field: bad})))
        for shell in self.each_shell():
            self.assert_refused(shell, jobs)

    def test_values_out_of_range_are_refused(self):
        jobs = [
            ('act op unknown', 'act', {'op': 'shell', 'arg': 'on'}),
            ('lock val mode', 'lock_set', {'kind': 'mode', 'val': '5g'}),
            ('lock lte too many', 'lock_set', {'kind': 'lte', 'val': ','.join(['1'] * 33)}),
            ('lock lte four digits', 'lock_set', {'kind': 'lte', 'val': '1000'}),
            ('lock lte empty item', 'lock_set', {'kind': 'lte', 'val': '1,,3'}),
            ('lock cell arfcn', 'lock_set', {'kind': 'cell', 'val': 'nr:12345678,1'}),
            ('lock cell pci', 'lock_set', {'kind': 'cell', 'val': 'lte:1650,12345'}),
            ('lock cell two pairs', 'lock_set', {'kind': 'cell', 'val': 'nr:1,2,3'}),
            ('lock cell rat', 'lock_set', {'kind': 'cell', 'val': 'gsm:1,2'}),
            ('lock reset empty', 'lock_set', {'kind': 'reset', 'val': ''}),
            ('lock reset other', 'lock_set', {'kind': 'reset', 'val': 'on'}),
            ('lock reset with bands', 'lock_set', {'kind': 'reset', 'val': 'auto,1'}),
            ('lock kind resets', 'lock_set', {'kind': 'resets', 'val': 'auto'}),
            ('sms id seven digits', 'sms_show', {'id': '1234567'}),
            ('sms id empty', 'sms_show', {'id': ''}),
            ('sms delete id', 'sms_delete', {'id': 'all2'}),
            ('sms num too long', 'sms_send', {'num': '1' * 21, 'text': 'hi'}),
            ('sms num plus only', 'sms_send', {'num': '+', 'text': 'hi'}),
            ('sms num inner plus', 'sms_send', {'num': '12+3', 'text': 'hi'}),
            ('sms page', 'sms_list', {'page': '1234567'}),
            ('usb role mode', 'usb_set', {'kind': 'role', 'value': 'ncm', 'scope': '', 'auto': '0'}),
            ('usb net role', 'usb_set', {'kind': 'net', 'value': 'host', 'scope': 'once', 'auto': '0'}),
            ('usb iface dots', 'usb_net_add', {'iface': '..'}),
            ('usb iface slash', 'usb_net_add', {'iface': 'eth1/../x'}),
            ('usb iface 16', 'usb_net_add', {'iface': 'e' * 16}),
            ('usb iface empty', 'usb_net_add', {'iface': ''}),
            ('lang op', 'lang_set', {'op': 'shell', 'codes': 'de'}),
            ('lang no codes', 'lang_set', {'op': 'enable', 'codes': ''}),
            ('lang code long', 'lang_set', {'op': 'enable', 'codes': 'deutsch'}),
            ('lang code upper', 'lang_set', {'op': 'enable', 'codes': 'DE'}),
            ('lang code region', 'lang_set', {'op': 'enable', 'codes': 'pt-br'}),
            ('lang two spaces', 'lang_set', {'op': 'enable', 'codes': 'de  fr'}),
            ('lang 65 codes', 'lang_set', {'op': 'enable', 'codes': ' '.join(['de'] * 65)}),
            ('lang all and more', 'lang_set', {'op': 'enable', 'codes': 'all de'}),
            ('lang enable en', 'lang_set', {'op': 'enable', 'codes': 'en'}),
            ('lang use two', 'lang_set', {'op': 'use', 'codes': 'de fr'}),
            ('lang use all', 'lang_set', {'op': 'use', 'codes': 'all'}),
            ('lang source path', 'lang_set', {'op': 'install', 'source': '/etc/shadow'}),
            ('lang source url', 'lang_set', {'op': 'install', 'source': 'http://x/y.tar.gz'}),
            ('lang install codes', 'lang_set', {'op': 'install', 'source': 'file', 'codes': 'de'}),
            ('lang enable source', 'lang_set', {'op': 'enable', 'codes': 'de', 'source': 'file'}),
            ('lang remove codes', 'lang_set', {'op': 'remove', 'codes': 'de'}),
            ('power key colour', 'power_set', {'op': 'set', 'key': 'battery.COLOUR', 'value': 'red'}),
            ('power value chained', 'power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': '15; reboot'}),
            ('power value long', 'power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': '123456'}),
            ('power value upper', 'power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': 'OFF'}),
            ('power op format', 'power_set', {'op': 'format'}),
            ('power wake with key', 'power_set', {'op': 'wake', 'key': 'PROFILE', 'value': 'saver'}),
            ('power set no value', 'power_set', {'op': 'set', 'key': 'PROFILE', 'value': ''}),
            ('cpu unknown profile', 'cpu_set', {'profile': 'turbo'}),
            ('cpu profile chained', 'cpu_set', {'profile': 'saving; reboot'}),
            ('cpu profile empty', 'cpu_set', {'profile': ''}),
            ('ttl zero', 'ttl_set', {'value': '0'}),
            ('ttl 256', 'ttl_set', {'value': '256'}),
            ('ttl 999', 'ttl_set', {'value': '999'}),
            ('ttl four digits', 'ttl_set', {'value': '1000'}),
            ('ttl leading zero', 'ttl_set', {'value': '064'}),
            ('ttl negative', 'ttl_set', {'value': '-1'}),
            ('ttl empty', 'ttl_set', {'value': ''}),
            ('ttl missing', 'ttl_set', {}),
            ('ttl OFF', 'ttl_set', {'value': 'OFF'}),
            ('ttl word', 'ttl_set', {'value': 'on'}),
            ('ttl float', 'ttl_set', {'value': '64.5'}),
            ('ttl hex', 'ttl_set', {'value': '0x40'}),
            ('ttl two', 'ttl_set', {'value': '64 65'}),
        ]
        for shell in self.each_shell():
            self.assert_refused(shell, jobs)


class Passthrough(Mu300Dash):
    """A valid value reaches the adapter as one exact argument."""

    CASES = [
        # (method, params, the calls wanted)
        ('act', {'op': 'radio', 'arg': 'on'}, [['setsid', 'action', 'radio', 'on']]),
        ('act', {'op': 'reboot', 'arg': None}, [['setsid', 'action', 'reboot', '']]),
        ('act', {'op': 'vpn', 'arg': 'stop'}, [['setsid', 'action', 'vpn', 'stop']]),
        ('act', {'op': 'wifi', 'arg': 'off'}, [['action', 'wifi', 'off']]),
        ('act', {'op': 'os', 'arg': 'android'}, [['action', 'os', 'android']]),
        ('act', {'op': 'os', 'arg': 'lock'}, [['action', 'os', 'lock']]),
        ('act', {'op': 'os', 'arg': 'unlock'}, [['action', 'os', 'unlock']]),
        ('lock_get', {}, [['lock', 'get']]),
        ('lock_get', {'fresh': '1'}, [['lock', 'get', 'fresh']]),
        ('lock_set', {'kind': 'lte', 'val': '1,3,41'}, [['setsid', 'lock', 'apply', 'lte', '1,3,41']]),
        ('lock_set', {'kind': 'nr', 'val': ''}, [['setsid', 'lock', 'apply', 'nr', '']]),
        ('lock_set', {'kind': 'cell', 'val': 'lte:1650,211'}, [['setsid', 'lock', 'apply', 'cell', 'lte:1650,211']]),
        ('lock_set', {'kind': 'cell', 'val': 'auto'}, [['setsid', 'lock', 'apply', 'cell', 'auto']]),
        ('lock_set', {'kind': 'mode', 'val': '4g'}, [['setsid', 'lock', 'apply', 'mode', '4g']]),
        ('lock_set', {'kind': 'reset', 'val': 'auto'}, [['setsid', 'lock', 'reset']]),
        ('sms_list', {'page': 2}, [['sms', 'list', '2']]),
        ('sms_list', {}, [['sms', 'list', '1']]),
        ('sms_show', {'id': '12'}, [['sms', 'show', '12']]),
        ('sms_delete', {'id': 'all', 'sim': True}, [['sms', 'delete', 'all', '--sim']]),
        ('sms_delete', {'id': '7', 'sim': False}, [['sms', 'delete', '7']]),
        ('sms_delete', {'id': '7', 'sim': '1'}, [['sms', 'delete', '7', '--sim']]),
        ('sms_sync', {}, [['setsid', 'sms', 'sync']]),
        ('usb_get', {}, [['device-usb', 'get']]),
        ('usb_set', {'kind': 'role', 'value': 'device', 'scope': '', 'auto': '0'},
         [['device-usb', 'set-role', 'device', '0']]),
        ('usb_set', {'kind': 'net', 'value': 'rndis', 'scope': 'permanent', 'auto': '1'},
         [['device-usb', 'set-net', 'rndis', 'permanent', '1']]),
        ('usb_net_list', {}, [['device-usb', 'net-list']]),
        ('usb_net_add', {'iface': 'eth1'}, [['device-usb', 'net-add', 'eth1']]),
        ('usb_net_add', {'iface': 'enx00e04c680001'}, [['device-usb', 'net-add', 'enx00e04c680001']]),
        ('lang_get', {}, [['languages', 'get']]),
        ('lang_set', {'op': 'enable', 'codes': 'de pt_br'}, [['languages', 'enable', 'de', 'pt_br']]),
        ('lang_set', {'op': 'disable', 'codes': 'all'}, [['languages', 'disable', 'all']]),
        ('lang_set', {'op': 'use', 'codes': 'auto'}, [['languages', 'use', 'auto']]),
        ('lang_set', {'op': 'use', 'codes': 'zh_cn'}, [['languages', 'use', 'zh_cn']]),
        ('lang_set', {'op': 'install', 'source': 'release'}, [['languages', 'install', 'release']]),
        ('lang_set', {'op': 'install', 'source': 'file'}, [['languages', 'install', 'file']]),
        ('lang_set', {'op': 'remove'}, [['languages', 'remove']]),
        ('power_get', {}, [['power', 'get']]),
        ('power_set', {'op': 'set', 'key': 'battery.WIFI_IDLE', 'value': '15'}, [['power', 'set', 'battery.WIFI_IDLE', '15']]),
        ('power_set', {'op': 'set', 'key': 'PROFILE', 'value': 'saver'}, [['power', 'set', 'PROFILE', 'saver']]),
        ('power_set', {'op': 'wake'}, [['power', 'wake']]),
        ('power_set', {'op': 'idle'}, [['power', 'idle']]),
        ('ttl_get', {}, [['ttl', 'get']]),
        ('ttl_set', {'value': '64'}, [['ttl', 'set', '64']]),
        ('ttl_set', {'value': 128}, [['ttl', 'set', '128']]),
        ('ttl_set', {'value': '255'}, [['ttl', 'set', '255']]),
        ('ttl_set', {'value': '1'}, [['ttl', 'set', '1']]),
        ('ttl_set', {'value': 'off'}, [['ttl', 'set', 'off']]),
    ]

    def test_valid_values_reach_the_adapter(self):
        jobs = [(f'{m} {p}', m, p) for m, p, _ in self.CASES]
        for shell in self.each_shell():
            for (label, r, recs, _), (_, _, want) in zip(self.calls_parallel(shell, jobs), self.CASES):
                with self.subTest(case=label):
                    self.reply(r)
                    self.assertEqual(recs, want, r.stdout)

    def test_at_commands_pass_as_one_exact_argument(self):
        ok = ['AT', 'at+cgsn', 'AT+SP5GCMDS="get nr support_band"', "AT+X='a'", 'AT$(reboot)', 'AT`reboot`',
              'AT|reboot', 'AT&F', 'AT -rf', 'AT+' + 'A' * 509]
        bad = ['', 'ATI;reboot', 'AT\nreboot', 'AT\rAT+CFUN=0', 'AT\x00x', 'AT' + 'A' * 10000, 'AT+' + 'A' * 510,
               'ATğ', '-tAT', ' AT', 'reboot', 'AT+SPENGMD=0,1,0', 'at+spengmd=0,1,0', 'AT+SPENGMD = 0,1,0', 'AT\t',
               {'a': 1}]
        for shell in self.each_shell():
            res = self.calls_parallel(shell, [(repr(c), 'at', {'cmd': c}) for c in ok])
            for (label, r, recs, _), c in zip(res, ok):
                with self.subTest(cmd=label):
                    self.assertEqual(self.reply(r), {'ok': 1, 'cmd': c, 'reply': 'OK'})
                    self.assertEqual(recs, [['at', '-t', '8', c]])
            self.assert_refused(shell, [(repr(c), 'at', {'cmd': c}) for c in bad])

    def test_sms_text_goes_on_stdin(self):
        texts = ["-n it's \"quoted\" $(reboot) `id` | & ; \\ end", 'two\nlines\tand tab', 'ğüşçöı 中文 😀',
                 '-', 'ğ' * 480]
        for shell in self.each_shell():
            for t in texts:
                with self.subTest(text=t[:20]):
                    r, recs, stdins = self.call(shell, 'sms_send', {'num': '+905551112233', 'text': t})
                    self.assertEqual(self.reply(r)['ok'], 1, r.stdout)
                    self.assertEqual(recs, [['sms', 'send', '--stdin', '+905551112233']])
                    self.assertEqual(stdins, {0: t})
            self.assert_refused(shell, [
                ('empty', 'sms_send', {'num': '123', 'text': ''}),
                ('nul', 'sms_send', {'num': '123', 'text': 'a\x00b'}),
                ('bell', 'sms_send', {'num': '123', 'text': 'a\x07b'}),
                ('cr', 'sms_send', {'num': '123', 'text': 'a\rb'}),
                ('481', 'sms_send', {'num': '123', 'text': 'a' * 481}),
                ('10000', 'sms_send', {'num': '123', 'text': 'a' * 10000}),
            ])
            # a JSON object where the text belongs is only text: it travels on stdin like any other
            r, recs, stdins = self.call(shell, 'sms_send', {'num': '123', 'text': {'a': '$(id)'}})
            self.assertEqual(recs, [['sms', 'send', '--stdin', '123']])
            self.assertEqual(json.loads(stdins[0]), {'a': '$(id)'})


NASTY = 'he said "hi" \\ back\\slash\nnew line\ttab\rcr \x01 \x1f end'
NASTY_JSON = json.dumps({'ok': 1, 'op': NASTY, 'name': NASTY, 'nested': {'k': [NASTY]}}, ensure_ascii=False)


class Replies(Mu300Dash):
    """Whatever an adapter, the modem or the SMS pool prints, the reply is one JSON object."""

    VALID = [
        ('sysinfo', {}), ('status', {}), ('signal', {}), ('act', {'op': 'wifi', 'arg': 'on'}),
        ('act', {'op': 'radio', 'arg': 'off'}), ('at', {'cmd': 'ATI'}), ('at_history', {}), ('lock_get', {}),
        ('lock_get', {'fresh': '1'}), ('lock_set', {'kind': 'lte', 'val': '1'}), ('sms_list', {}),
        ('sms_show', {'id': '1'}), ('sms_send', {'num': '123', 'text': 'x'}), ('sms_delete', {'id': '1'}),
        ('sms_sync', {}), ('usb_get', {}), ('usb_set', {'kind': 'role', 'value': 'device', 'auto': '0'}),
        ('usb_net_list', {}), ('usb_net_add', {'iface': 'eth1'}), ('ttl_get', {}), ('ttl_set', {'value': '64'}),
    ]
    OUTPUTS = {
        'garbage': NASTY,
        'json with nasty strings': NASTY_JSON,
        'json then garbage': '{"ok":1} "}, "x": "',
        'json injection': '{"ok":1,"error":"x"}","admin":true,"y":"',
        'empty': '',
        'array': '[1,2]',
    }

    def test_every_reply_is_json(self):
        for shell in self.each_shell():
            for oname, text in self.OUTPUTS.items():
                for name in list(DEFAULTS) + ['cell.json', 'sig.json']:
                    self.output(name, text)
                res = self.calls_parallel(shell, [(f'{oname}: {m}', m, p) for m, p in self.VALID])
                for label, r, _, _ in res:
                    with self.subTest(case=label):
                        self.reply(r)

    def test_adapter_json_is_passed_through_as_json(self):
        for name in DEFAULTS:
            self.output(name, NASTY_JSON)
        want = json.loads(NASTY_JSON)
        for shell in self.each_shell():
            for m, p in [('sysinfo', {}), ('act', {'op': 'wifi', 'arg': 'on'}), ('lock_get', {}), ('usb_get', {}),
                         ('usb_net_list', {}), ('ttl_get', {}), ('ttl_set', {'value': 'off'})]:
                with self.subTest(method=m):
                    r, _, _ = self.call(shell, m, p)
                    self.assertEqual(self.reply(r), want)
            r, _, _ = self.call(shell, 'status', {})
            self.assertEqual(self.reply(r)['info'], want)

    def test_modem_and_sms_text_is_escaped(self):
        text = NASTY.replace('\r', '')
        for shell in self.each_shell():
            self.output('at', text)
            r, _, _ = self.call(shell, 'at', {'cmd': 'AT+COPS?'})
            self.assertEqual(self.reply(r)['reply'], text)
            self.output('sms', text)
            r, _, _ = self.call(shell, 'sms_show', {'id': '4'})
            self.assertEqual(self.reply(r)['text'], text)
            r, _, _ = self.call(shell, 'sms_send', {'num': '123', 'text': 'sent'})
            self.assertEqual(self.reply(r)['ok'], 0)

    def test_sms_list_fields_are_escaped(self):
        row = '%-7s %-7s %-3s %-18s %-21s %s' % ('3', 'unread', 'mt', 'A"B\\C', '26/10/05,12:00:00',
                                                   'say "hi" \\o/ \x01 end')
        self.output('sms', 'pool: 1 message(s), 1 unread - page 1/1 (10 per page)\n' + row + '\n')
        for shell in self.each_shell():
            r, _, _ = self.call(shell, 'sms_list', {'page': '1'})
            obj = self.reply(r)
            self.assertEqual(obj['total'], 1)
            self.assertEqual(obj['msgs'][0]['peer'], 'A"B\\C')
            self.assertEqual(obj['msgs'][0]['preview'], 'say "hi" \\o/ \x01 end')

    def test_at_history_is_escaped(self):
        for shell in self.each_shell():
            r, _, _ = self.call(shell, 'at', {'cmd': 'AT+X="a\\b"'})
            self.reply(r)
            hist = self.tmp / f'run{self.n}' / 'dash' / 'at-history'
            hist.write_text(hist.read_text() + 'x "quoted" \\ \x02\n')
            r = subprocess.run(shell + [str(DASH), 'call', 'at_history'], input='{}', capture_output=True, text=True,
                               env=self.env(MU300_DASH_DIR=hist.parent), timeout=60)
            obj = self.reply(r)
            self.assertIn('AT+X="a\\b"', obj['history'])
            self.assertIn('x "quoted" \\ \x02', obj['history'])


class Adapters(Mu300Dash):
    """The adapters mu300dash starts guard their own input and escape what the modem and sysfs say."""

    def adapter(self, shell, name, *args, **env):
        calls = self.tmp / f'adapter{self.n}'
        self.n += 1
        calls.mkdir()
        e = dict(STUB_CALLS=calls, STUB_OUT=self.out, MU300_AT=self.adapters / 'at', MU300_DASH_DIR=self.tmp / 'run',
                 UNISOC_APPLY_DIR=self.tmp / 'apply')
        e.update(env)
        r = self.script(shell, ADAPTERS / name, *args, **e)
        recs = [f.read_bytes().split(b'\0')[:-1] for f in calls.glob('call.*')]
        return r, recs

    def test_lock_apply_refuses_what_it_does_not_know(self):
        bad = [('mode', '5g'), ('mode', 'sa;reboot'), ('endc', 'yes'), ('auto_apply', 'on\n'), ('lte', '1,3;x'),
               ('lte', '-1'), ('nr', '78,'), ('nr', ',78'), ('nr', '1,,3'), ('lte', '1' * 128),
               ('cell', 'nr:627264,393;x'), ('cell', 'nr:627264'), ('cell', 'gsm:1,2'), ('cell', 'nr:12345678,1'),
               ('cell', 'lte:1,2,3'), ('cell', 'lte:$(id),1'), ('cell', 'nr:123'), ('shell', 'on')]
        for shell in self.each_shell():
            for kind, val in bad:
                with self.subTest(kind=kind, val=val):
                    r, recs = self.adapter(shell, 'lock', 'apply', kind, val)
                    self.assertEqual(r.returncode, 2, r.stderr)
                    self.assertEqual(recs, [])

    def test_lock_get_escapes_the_modem(self):
        self.output('at', '+SPTESTMODE: 1"2\\,134,0\n+SPLBAND: 0,"x\\\x01\n+SP5GRAN: 1\n+ENDC: 1\nOK')
        for shell in self.each_shell():
            r, _ = self.adapter(shell, 'lock', 'get', 'fresh')
            obj = json.loads(r.stdout)
            self.assertEqual(obj['mode']['work'], '1"2\\')
            self.assertEqual(obj['lte']['raw'], '0,"x\\\x01')

    def test_device_usb_escapes_sysfs_and_refuses_odd_names(self):
        role = self.tmp / 'role'
        role.write_text('ho"st\\\n')
        for shell in self.each_shell():
            r, _ = self.adapter(shell, 'device-usb', 'get', MU300_USB_ROLE_FILE=role)
            self.assertEqual(json.loads(r.stdout)['role'], 'ho"st\\')
            role.write_text('host\n')
            for name in ['-x', '..', '.', 'e' * 16, 'a/b', 'a b', 'a"b']:
                with self.subTest(name=name):
                    (self.tmp / 'net' / name.replace('/', '_')).mkdir(parents=True, exist_ok=True)
                    r, recs = self.adapter(shell, 'device-usb', 'net-add', name, MU300_USB_ROLE_FILE=role,
                                           MU300_USB_NET_CLASS=self.tmp / 'net', MU300_USB_IP_BIN=self.adapters / 'at')
                    self.assertEqual(json.loads(r.stdout), {'ok': 0, 'error': 'Not a USB network interface'})
                    self.assertEqual(recs, [])
            role.write_text('ho"st\\\n')

    def test_action_replies_are_json(self):
        self.stub('wifi', 'exit 0')
        for shell in self.each_shell():
            for args in [('wifi', 'on'), ('vpn', 'start'), ('os', 'android'), ('nonsense', '"\\')]:
                with self.subTest(args=args):
                    r, _ = self.adapter(shell, 'action', *args)
                    self.assertIsInstance(json.loads(r.stdout.splitlines()[-1]), dict)

    def test_at_adapter_sends_one_command(self):
        for shell in self.each_shell():
            for cmd in ['AT\rAT+CFUN=0', 'AT\nAT+CFUN=0']:
                r, _ = self.adapter(shell, 'at', '-t', '8', cmd)
                self.assertEqual(r.returncode, 2, r.stderr)


class LanguagesAdapter(ShellTest):
    """unisoc-modem/languages: what the Languages page gets and starts, through a stub mu300-extra and uci"""

    def setUp(self):
        super().setUp()
        self.disk = self.tmp / 'disk'
        self.job = self.tmp / 'job'
        self.job.mkdir(mode=0o700)
        self.upload = self.tmp / 'upload.tar.gz'
        # mu300-extra: records its arguments and MU300_EXTRA_FILE (and what that file holds), prints a list
        self.stub('mu300-extra', 'printf "%s|" "$@" >> "$STUBLOG/extra.log"; '
                                 'printf "file=%s\\n" "${MU300_EXTRA_FILE:-}" >> "$STUBLOG/extra.log"; '
                                 '[ -z "${MU300_EXTRA_FILE:-}" ] || cat "$MU300_EXTRA_FILE" >> "$STUBLOG/extra.log"; '
                                 'case "$1 ${2:-}" in "lang list"|"lang ") '
                                 'printf "de\\tenabled\\tDeutsch (German)\\nja\\tdisabled\\tA \\"q\\" \\\\\\\\ b\\n" ;; esac')
        self.stub('setsid', '"$@"')
        self.uci = {'luci.main.lang': 'en', 'luci.languages.tr': 'T\u00fcrk\u00e7e (Turkish)', 'luci.languages.de': 'Deutsch (German)'}
        lines = ''.join(f"{k}) printf '%s\\n' '{v}' ;; " for k, v in self.uci.items())
        show = ''.join(f"printf \"%s='%s'\\n\" '{k}' '{v}'; " for k, v in self.uci.items() if k.startswith('luci.languages.'))
        self.stub('uci', 'echo "$*" >> "$STUBLOG/uci.log"; a=; for x; do [ "$x" = -q ] || a="$a $x"; done; set -- $a; '
                         f'case $1 in get) case $2 in {lines} *) exit 1 ;; esac ;; '
                         f'show) printf "luci.languages=internal\\n"; {show} ;; esac; exit 0')

    def run_ad(self, shell, *args):
        r = self.script(shell, ADAPTERS / 'languages', *args, MU300_EXTRA_CMD=self.stubs / 'mu300-extra',
                        MU300_DISK=self.disk, MU300_LANG_UPLOAD=self.upload, MU300_LANG_JOB_DIR=self.job)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def wait_job(self):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and (self.job / 'lang-job.state').read_text().strip() == 'running':
            time.sleep(0.05)
        time.sleep(0.1)

    def log(self):
        p = self.tmp / 'extra.log'
        t = p.read_text() if p.exists() else ''
        p.unlink(missing_ok=True)
        return t

    def test_get_reports_and_escapes(self):
        for shell in self.each_shell():
            r = self.run_ad(shell, 'get')
            self.assertEqual(r['extra']['installed'], 0)
            self.assertEqual(r['current'], 'en')
            self.assertEqual(sorted(l['code'] for l in r['luci']), ['de', 'tr'])
            (self.disk / 'extra/lang/i18n').mkdir(parents=True, exist_ok=True)
            (self.disk / 'extra/lang/i18n/mu300.de.lmo').write_text('x')
            (self.disk / 'extra/lang/release').write_text('v1\n')
            r = self.run_ad(shell, 'get')
            self.assertEqual(r['extra'], {'installed': 1, 'release': 'v1', 'languages': [
                {'code': 'de', 'name': 'Deutsch (German)', 'enabled': 1, 'panel': 1},
                {'code': 'ja', 'name': 'A "q" \\ b', 'enabled': 0, 'panel': 0}]}, shell)
            shutil.rmtree(self.disk)

    def test_switch_and_use_check_again(self):
        (self.disk / 'extra/lang/i18n').mkdir(parents=True)
        for shell in self.each_shell():
            self.assertEqual(self.run_ad(shell, 'enable', 'de', 'ja'), {'ok': 1})
            self.assertEqual(self.log(), 'lang|enable|de|ja|file=\n')
            for bad in (('enable', 'de;x'), ('disable', '-rf'), ('enable',)):
                self.assertEqual(self.run_ad(shell, *bad)['ok'], 0, bad)
            self.assertEqual(self.log(), '')
            self.assertEqual(self.run_ad(shell, 'use', 'de'), {'ok': 1})
            self.assertEqual(self.run_ad(shell, 'use', 'auto'), {'ok': 1})
            # only a language LuCI offers
            self.assertEqual(self.run_ad(shell, 'use', 'fr')['ok'], 0)
            self.assertEqual(self.run_ad(shell, 'use', 'de;x')['ok'], 0)
            self.assertIn('set luci.main.lang=de', (self.tmp / 'uci.log').read_text())
            self.assertNotIn('lang=fr', (self.tmp / 'uci.log').read_text())

    def test_an_upload_is_moved_out_of_tmp_before_anything_reads_it(self):
        for shell in self.each_shell():
            self.upload.write_bytes(b'PACK')
            r = self.run_ad(shell, 'install', 'file')
            self.assertEqual(r, {'ok': 1, 'started': 1})
            self.assertFalse(self.upload.exists(), 'the upload is moved away')
            self.wait_job()
            # mu300-extra got the private copy, which is gone after the job
            log = self.log()
            self.assertEqual(log, f'install|lang|file={self.job}/lang-upload.tar.gz\nPACK', shell)
            self.assertFalse((self.job / 'lang-upload.tar.gz').exists())
            self.assertEqual(self.run_ad(shell, 'get')['job']['state'], 'done')
            # a link planted at the upload path is not followed
            secret = self.tmp / 'secret'
            secret.write_text('root:x')
            os.symlink(secret, self.upload)
            r = self.run_ad(shell, 'install', 'file')
            self.assertEqual(r['ok'], 0)
            self.assertEqual(self.log(), '')
            self.upload.unlink()
            self.assertEqual(self.run_ad(shell, 'install', 'file')['ok'], 0)   # nothing uploaded
            self.assertEqual(self.run_ad(shell, 'install', '/etc/shadow')['ok'], 0)
            self.assertEqual(self.run_ad(shell, 'install', 'release'), {'ok': 1, 'started': 1})
            self.wait_job()
            self.assertEqual(self.log(), 'install|lang|file=\n')
            # a job that died without saying how it ended (killed, a reboot) is a failed one, not one running forever
            (self.job / 'lang-job.state').write_text('running\n')
            (self.job / 'lang-job.pid').write_text('999999\n')
            self.assertEqual(self.run_ad(shell, 'get')['job']['state'], 'failed')
            (self.job / 'lang-job.pid').unlink()


class TtlAdapter(ShellTest):
    """unisoc-modem/ttl: mu300-ttl's state as JSON for the TTL page, and set/off with the value checked again"""

    def setUp(self):
        super().setUp()
        self.state = self.tmp / 'state'
        self.state.write_text('TTL=64\nBACKEND=tc\nIFACES=sipa_eth0 sipa_eth1\nOFFLOAD=1\n')
        # mu300-ttl: records its arguments; "state" prints $STUBLOG/state; set fails with $STUBLOG/fail's text
        self.stub('mu300-ttl', 'echo "$*" >> "$STUBLOG/ttl.log"\n'
                               'case $1 in state) cat "$STUBLOG/state" ;;\n'
                               '  *) echo "TTL: something"; [ -e "$STUBLOG/fail" ] && { cat "$STUBLOG/fail" >&2; exit 1; } ;; esac\n'
                               'exit 0')

    def run_ad(self, shell, *args):
        r = self.script(shell, ADAPTERS / 'ttl', *args, MU300_TTL_CMD=self.stubs / 'mu300-ttl')
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def log(self):
        p = self.tmp / 'ttl.log'
        t = p.read_text() if p.exists() else ''
        p.unlink(missing_ok=True)
        return t

    def test_get(self):
        for shell in self.each_shell():
            self.state.write_text('TTL=64\nBACKEND=tc\nIFACES=sipa_eth0 sipa_eth1\nOFFLOAD=1\n')
            self.assertEqual(self.run_ad(shell, 'get'), {'ok': 1, 'enabled': 1, 'value': 64, 'backend': 'tc',
                                                         'offload': 1, 'iface': ['sipa_eth0', 'sipa_eth1']})
            self.state.write_text('TTL=128\nBACKEND=nft\nIFACES=\nOFFLOAD=0\n')
            self.assertEqual(self.run_ad(shell, 'get'), {'ok': 1, 'enabled': 1, 'value': 128, 'backend': 'nft',
                                                         'offload': 0, 'iface': []})
            # off, Ubuntu (no fw4), and whatever odd text: still JSON, nothing odd passed on
            self.state.write_text('TTL=\nBACKEND=none\nIFACES=\nOFFLOAD=\n')
            self.assertEqual(self.run_ad(shell, 'get'), {'ok': 1, 'enabled': 0, 'value': None, 'backend': 'none',
                                                         'offload': None, 'iface': []})
            self.state.write_text('TTL=6"4\nBACKEND=x"y\nIFACES=sipa_eth0 a"b\\c\nOFFLOAD=1"\n')
            self.assertEqual(self.run_ad(shell, 'get'), {'ok': 1, 'enabled': 0, 'value': None, 'backend': 'none',
                                                         'offload': None, 'iface': ['sipa_eth0']})

    def test_set_and_off(self):
        for shell in self.each_shell():
            self.log()
            for v in ('1', '64', '65', '128', '255'):
                self.assertEqual(self.run_ad(shell, 'set', v), {'ok': 1}, v)
                self.assertEqual(self.log(), f'set {v}\n')
            self.assertEqual(self.run_ad(shell, 'set', 'off'), {'ok': 1})
            self.assertEqual(self.log(), 'off\n')

    def test_bad_values_run_nothing(self):
        for shell in self.each_shell():
            self.log()
            for v in ('0', '256', '1000', '064', '-1', '', 'abc', '6 4', '64;reboot', '$(id)', '--help', 'OFF'):
                with self.subTest(v=v):
                    r = self.run_ad(shell, 'set', v)
                    self.assertEqual(r, {'ok': 0, 'error': 'Invalid TTL'})
                    self.assertEqual(self.log(), '')
            self.assertEqual(self.run_ad(shell, 'rm')['ok'], 0)
            self.assertEqual(self.log(), '')

    def test_a_failure_says_why(self):
        (self.tmp / 'fail').write_text('first\nthe rule could not be set "x" \\ (tc and nftables)\n')
        for shell in self.each_shell():
            r = self.run_ad(shell, 'set', '64')
            self.assertEqual(r, {'ok': 0, 'error': 'The TTL could not be set',
                                 'detail': 'the rule could not be set "x" \\ (tc and nftables)'})


class Acl(unittest.TestCase):
    # SMS bodies (one-time codes) and the AT history (AT+CPIN PINs) are not for read-only users (ruling R14)
    READ = {'sysinfo', 'status', 'signal', 'lock_get', 'usb_get', 'usb_net_list', 'lang_get', 'power_get', 'ttl_get',
            'cpu_get'}
    WRITE = {'act', 'at', 'at_history', 'lock_set', 'sms_list', 'sms_show', 'sms_send', 'sms_delete', 'sms_sync',
             'usb_set', 'usb_net_add', 'lang_set', 'power_set', 'ttl_set', 'cpu_set'}

    def test_actions_need_write_access(self):
        acl = json.loads(ACL.read_text())['luci-app-mu300']
        read = set(acl['read']['ubus']['mu300dash'])
        write = set(acl['write']['ubus']['mu300dash'])
        self.assertEqual(read, self.READ)
        self.assertEqual(write, self.WRITE)
        self.assertEqual(read | write, Inventory.METHODS)
        # the Languages page uploads to one fixed path, and only with write access
        self.assertEqual(acl['write'].get('cgi-io'), ['upload'])
        self.assertEqual(acl['write'].get('file'), {'/tmp/mu300-extra-lang.tar.gz': ['write']})
        self.assertNotIn('cgi-io', acl['read'])
        self.assertNotIn('file', acl['read'])


LIB = APP / 'usr' / 'share' / 'unisoc-modem' / 'lib.sh'


class Lib(ShellTest):
    """The shared lib.sh: the one JSON escaper, and the allow-lists for uci options naming programs, paths, ttys."""

    def lib(self, shell, code, **env):
        return self.sh(shell, f'. "{LIB}"; {code}', **env)

    def test_json_str(self):
        texts = ['', 'plain', 'q"uote', 'back\\slash', 'new\nline', 'tab\tcr\r', ''.join(chr(c) for c in range(1, 32)),
                 'del\x7f', 'ğüş 中文 😀', '\\"\\n', 'trailing\n\n', '\n']
        for shell in self.each_shell():
            for t in texts:
                with self.subTest(text=t):
                    (self.tmp / 'in').write_text(t)
                    r = self.lib(shell, f'json_str "$(cat "{self.tmp}/in"; printf x)"')
                    out = json.loads(r.stdout)
                    self.assertEqual(out, t + 'x')
                    self.assertTrue(all(ord(c) >= 32 for c in r.stdout), repr(r.stdout))
            r = self.lib(shell, 'printf "%s|%s" "$(json_str_or_null "")" "$(json_str_or_null a)"')
            self.assertEqual(r.stdout, 'null|"a"')

    def test_json_num(self):
        cases = {'0': '0', '12': '12', '-3': '-3', '45.5': '45.5', '-0.5': '-0.5', '': 'null', '-': 'null',
                 '1-2': 'null', '1.2.3': 'null', '.5': 'null', '5.': 'null', '007': 'null', '1e5': 'null',
                 '1;2': 'null', '--1': 'null'}
        for shell in self.each_shell():
            for v, want in cases.items():
                with self.subTest(v=v):
                    self.assertEqual(self.lib(shell, f"json_num '{v}'").stdout.strip(), want)

    def test_uci_allow_lists(self):
        cases = [
            ('safe_iface wan x', 'wan'), ('safe_iface br-lan x', 'br-lan'), ('safe_iface eth0.2 x', 'eth0.2'),
            ("safe_iface '-x' d", 'd'), ("safe_iface '..' d", 'd'), ("safe_iface 'a/b' d", 'd'),
            ("safe_iface \"x'\" d", 'd'), ("safe_iface 'a b' d", 'd'), (f"safe_iface {'e' * 16} d", 'd'),
            ("safe_iface '' d", 'd'),
            ('safe_state_dir /etc/unisoc-modem/lock-state.d d', '/etc/unisoc-modem/lock-state.d'),
            ('safe_state_dir /etc/mu300/sms-pool d', '/etc/mu300/sms-pool'),
            ('safe_state_dir /etc/unisoc-modem/../init.d d', 'd'), ('safe_state_dir /etc/init.d d', 'd'),
            ('safe_state_dir /tmp/x d', 'd'), ('safe_state_dir /etc/mu300x d', 'd'),
            ("safe_state_dir '/etc/mu300/a b' d", 'd'), ('safe_state_dir /etc/mu300/.x d', 'd'),
            ('safe_tty /dev/stty_nr1 d', '/dev/stty_nr1'), ('safe_tty /dev/ttyUSB2 d', '/dev/ttyUSB2'),
            ('safe_tty /dev/sda d', 'd'), ('safe_tty /dev/tty d', 'd'), ('safe_tty /dev/ttyX/../sda d', 'd'),
            ('safe_tty /etc/passwd d', 'd'),
            ('safe_program /opt/mu300/bin/mu300-sms /opt/mu300/bin/mu300-sms', '/opt/mu300/bin/mu300-sms'),
            ('safe_program /bin/sh /opt/mu300/bin/mu300-sms', ''), ('safe_program /tmp/x', ''),
            ('safe_program /P/adapter', '/P/adapter'), ('safe_program /P/../bin/sh', ''),
            ('safe_program /P/sub/x', ''), ('safe_program /P/.hidden', ''), ('safe_program /P/', ''),
            ("safe_program '/P/a b'", ''),
        ]
        for shell in self.each_shell():
            for code, want in cases:
                with self.subTest(code=code):
                    r = self.lib(shell, code, MU300_PLATFORM_DIR='/P')
                    self.assertEqual(r.stdout.strip(), want, r.stderr)


class FixRound1(Mu300Dash):
    def test_spengmd_streaming_is_denied_in_any_spelling(self):
        bad = ['AT+SPENGMD=0,1,0', 'at+spengmd=0,1,0', 'AT+SPENGMD = 0 , 1 , 0', 'AT+SPENGMD=0,1,00',
               'AT+SPENGMD=0,01,0', 'AT+SPENGMD=00,1,0', 'AT+SPENGMD="0","1","0"', 'AT+SPENGMD=0,1',
               'AT+SPENGMD=0,1,0,5', 'ATE0+SPENGMD=0,1,0', 'AT+SpEnGmD=0,1,7']
        good = ['AT+SPENGMD=0,6,0', 'AT+SPENGMD=0,14,1', 'AT+SPENGMD=0,10,0', 'AT+SPENGMD?', 'AT+SPENGMD=1,1,0']
        for shell in self.each_shell():
            self.assert_refused(shell, [(c, 'at', {'cmd': c}) for c in bad])
            for c in good:
                r, recs, _ = self.call(shell, 'at', {'cmd': c})
                self.assertEqual(recs, [['at', '-t', '8', c]], c)

    def test_sms_failures_carry_a_fixed_error_and_a_detail(self):
        self.output('sms', 'no message "4"\\x')
        self.output('sms.rc', '1')
        for shell in self.each_shell():
            r, _, _ = self.call(shell, 'sms_show', {'id': '4'})
            self.assertEqual(self.reply(r), {'ok': 0, 'error': 'Read failed', 'detail': 'no message "4"\\x'})
            r, _, _ = self.call(shell, 'sms_send', {'num': '123', 'text': 'hi'})
            self.assertEqual(self.reply(r), {'ok': 0, 'error': 'Sending failed', 'detail': 'no message "4"\\x'})
            r, _, _ = self.call(shell, 'sms_delete', {'id': '4'})
            self.assertEqual(self.reply(r), {'ok': 0, 'error': 'Delete failed', 'detail': 'no message "4"\\x'})

    def test_errors_are_english_sentences_in_the_catalogs(self):
        # the page shows _(error): each error is one fixed English sentence that tools/luci-i18n.py extracts (so it
        # is in po/tr and po/zh_Hans), never Chinese; the value it carries, if any, is in detail
        known = set(subprocess.run([sys.executable, str(TOP / 'tools' / 'luci-i18n.py'), 'extract'], check=True,
                                   capture_output=True, text=True, encoding='utf-8').stdout.splitlines())
        busy = 'The AT channel is busy; the command was not sent, try again'
        cases = [
            # (label, method, params, {stub: output}, error)
            ('number', 'sms_send', {'num': '12a', 'text': 'hi'}, {},
             'The number may only contain digits (and a leading +)'),
            ('empty', 'sms_send', {'num': '12', 'text': ''}, {}, 'The message is empty'),
            ('too long', 'sms_send', {'num': '12', 'text': 'x' * 481}, {},
             'The message is too long (over 480 characters)'),
            ('sms busy', 'sms_send', {'num': '12', 'text': 'hi'}, {'sms': 'mu300-at: busy\n'}, busy),
            ('at busy', 'at', {'cmd': 'ATI'}, {'at': 'mu300-at: busy\n'}, busy),
            ('no sms', 'sms_list', {}, {'sms': ''},
             'mu300-sms is not available (the SMS service is not installed or not running)'),
            ('read', 'sms_show', {'id': '4'}, {'sms': ''}, 'Read failed'),
            ('op', 'act', {'op': 'dance'}, {}, 'Unknown op'),
            ('kind', 'lock_set', {'kind': 'x', 'val': 'on'}, {}, 'Unknown lock kind'),
            ('id', 'sms_show', {'id': 'x'}, {}, 'Bad ID'),
            ('wedge', 'at', {'cmd': 'AT+SPENGMD=0,1,0'}, {}, 'Denied: this command wedges the AT port until a reboot'),
            ('not at', 'at', {'cmd': 'ti'}, {}, 'Must be an AT command'),
            ('usb', 'usb_set', {'kind': 'x', 'auto': '0'}, {}, 'Unknown USB setting'),
            ('lock read', 'lock_get', {}, {'lock': 'garbage'}, 'Lock read failed'),
            ('method', 'nosuch', {}, {}, 'No such method'),
        ]
        for shell in self.each_shell():
            for label, method, params, outputs, error in cases:
                with self.subTest(case=label):
                    for p in self.out.iterdir():
                        p.unlink()
                    for name, text in outputs.items():
                        self.output(name, text)
                    obj = self.reply(self.call(shell, method, params)[0])
                    self.assertEqual(obj.get('error'), error, obj)
                    self.assertIn(error, known)
                    self.assertNotIn('detail', obj)

    def test_busy_is_the_at_clients_own_line_not_the_modems_word(self):
        # "busy" is what mu300-at and the plugin's at adapter print when they gave up on the AT lock; a modem reply
        # with the word in it ("+CME ERROR: SIM busy") is a reply that came back, shown as one
        busy = {'ok': 0, 'busy': 1, 'error': 'The AT channel is busy; the command was not sent, try again'}
        for shell in self.each_shell():
            for label, text in (('mu300-at', 'mu300-at: busy\n'), ('unisoc-at', 'unisoc-at: busy\n')):
                with self.subTest(client=label):
                    self.output('at', text)
                    self.assertEqual(self.reply(self.call(shell, 'at', {'cmd': 'ATI'})[0]), busy)
                    # mu300-sms passes mu300-at's line on, with its own after it
                    self.output('sms', text + 'mu300-sms: the modem did not take the message\n')
                    self.output('sms.rc', '1')
                    self.assertEqual(self.reply(self.call(shell, 'sms_send', {'num': '12', 'text': 'hi'})[0]), busy)
            self.output('at', '+CME ERROR: SIM busy\n')
            obj = self.reply(self.call(shell, 'at', {'cmd': 'AT+CPMS?'})[0])
            self.assertEqual((obj['ok'], obj.get('busy'), obj['reply']), (1, None, '+CME ERROR: SIM busy'))
            self.output('sms', 'mu300-sms: the modem did not take the message: +CMS ERROR: SIM busy\n')
            obj = self.reply(self.call(shell, 'sms_send', {'num': '12', 'text': 'hi'})[0])
            self.assertEqual((obj['ok'], obj.get('busy'), obj['error']), (0, None, 'Sending failed'))
            self.assertIn('SIM busy', obj['detail'])

    def test_the_runtime_directory_is_root_only(self):
        for shell in self.each_shell():
            r, _, _ = self.call(shell, 'at', {'cmd': 'ATI'})
            self.reply(r)
            d = self.tmp / f'run{self.n}' / 'dash'
            self.assertEqual(d.stat().st_mode & 0o777, 0o700)

    def test_sms_command_outside_the_allow_list_is_ignored(self):
        self.stub('uci', '[ "$*" = "-q get unisoc_modem.main.sms_command" ] && echo "$STUB_SMS_COMMAND"; exit 0')
        evil = self.tmp / 'evil'
        evil.write_text('#!/bin/sh\ntouch "$STUBLOG/evil-ran"\n')
        evil.chmod(0o755)
        self.stub('mu300-sms', 'f=$(mktemp "$STUB_CALLS/call.XXXXXX"); printf "%s\\0" mu300-sms "$@" > "$f"; '
                               'echo "pool: 0 message(s), 0 unread - page 1/1 (10 per page)"')
        for shell in self.each_shell():
            r, recs, _ = self.call(shell, 'sms_list', {}, MU300_SMS_BIN='', STUB_SMS_COMMAND=evil)
            self.assertEqual(recs, [['mu300-sms', 'list', '1']], r.stdout)
            self.assertFalse((self.tmp / 'evil-ran').exists())

    def test_at_custom_command_must_be_in_the_platform_directory(self):
        plat = self.tmp / 'platform'
        plat.mkdir()
        for p in (self.tmp / 'evil', plat / 'adapter'):
            p.write_text('#!/bin/sh\necho "ran $0 $*"\n')
            p.chmod(0o755)
        for shell in self.each_shell():
            for cmd, ran in [(self.tmp / 'evil', False), (plat / 'adapter', True)]:
                self.stub('uci', f'case "$*" in *at_backend) echo custom ;; *at_command) echo "{cmd}" ;; esac; exit 0')
                r = self.script(shell, ADAPTERS / 'at', '-t', '3', 'ATI', MU300_PLATFORM_DIR=plat)
                self.assertEqual('ran ' in r.stdout, ran, (cmd, r.stdout, r.stderr))

    def test_cell_escapes_operator_names_and_registration(self):
        at = self.tmp / 'modem'
        at.write_text(r"""#!/bin/sh
case $3 in
    'AT+CFUN?') echo '+CFUN: 1' ;;
    'AT+CEREG?') printf '%s\n' '+CEREG: 2,1,"01\F0","0A\\B",13' ;;
    'AT+COPS?') printf '+COPS: 0,0,"Op\\er\001ator",7\n' ;;
    'AT+CGMI') printf '%s\n' 'Uni"soc\' ;;
    'AT+CGSN') echo 123456789012345 ;;
    'AT+CGEQOSRDP=1') echo '+CGEQOSRDP: 1,x"y,0,0,0,0,0,0' ;;
esac
""")
        at.chmod(0o755)
        for shell in self.each_shell():
            run = self.tmp / f'cell{self.n}'
            self.n += 1
            r = self.script(shell, ADAPTERS / 'cell', MU300_AT=at, MU300_DASH_DIR=run, MU300_DASH_POOL_DIR=run / 'pool',
                            MU300_DASH_IDENT_DIR=run / 'ident')
            cell = json.loads((run / 'cell.json').read_text())
            self.assertEqual(cell['operator']['name'], 'Op\\er\x01ator', r.stderr)
            self.assertEqual(cell['reg']['tac'], '01\\F0')
            self.assertEqual(cell['ident']['mfg'], 'Uni"soc\\')
            self.assertIsNone(cell['qos'])
            json.loads((run / 'sig.json').read_text())
            self.assertEqual((run / 'cell.json').stat().st_mode & 0o777, 0o600)

    def test_dashboard_info_escapes_names(self):
        self.stub('busybox', 'shift 4; exec "$@"')   # busybox timeout -s KILL N CMD...
        self.stub('uci', r"""case "$*" in
    '-q get system.@system[0].hostname') printf 'h"o\\st\001\n' ;;
    '-q show wireless') printf '%s\n' "wireless.default_radio0=wifi-iface" "wireless.default_radio0.ssid='my \"wifi\" \\ net'" ;;
    '-q get unisoc_modem.main.lan_device') echo "br-lan'/w /tmp/x" ;;
    '-q get unisoc_modem.main.wifi_device') echo '../../etc' ;;
    *) exit 1 ;;
esac""")
        for name in ('ubus', 'ip', 'iw'):
            self.stub(name, 'exit 1')
        for shell in self.each_shell():
            r = self.script(shell, ADAPTERS / 'dashboard-info')
            info = json.loads(r.stdout)
            self.assertEqual(info['host'], 'h"o\\st\x01')
            self.assertEqual(info['wifi']['ssid'], 'my "wifi" \\ net')


class RuntimeDir(Mu300Dash):
    """The runtime directory (SMS text, AT history, method log) is under a root-owned parent, and a directory someone
    else made first - a symlink, another owner's, group- or world-writable - is refused, never written through."""

    def private_dir(self, shell, path):
        return self.sh(shell, f'. "{LIB}"; private_dir "$D"; echo "rc=$?"', D=path)

    def test_the_default_is_under_var_run_not_tmp(self):
        for path in (DASH, ADAPTERS / 'cell', ADAPTERS / 'lock'):
            text = path.read_text()
            self.assertTrue('${MU300_DASH_DIR:-$RUN_DIR}' in text, path.name)
            self.assertFalse('/tmp/unisoc-modem' in text, path.name)
        self.assertIn('RUN_DIR=/var/run/unisoc-modem', LIB.read_text())
        if not GIT_CHECKOUT:
            self.skipTest('no git checkout here')
        r = subprocess.run(['git', 'grep', '-l', '/tmp/unisoc-modem', '--', 'openwrt', 'rootfs', 'README.md',
                            'docs/BUILD.md'], cwd=TOP, capture_output=True, text=True)
        if r.returncode not in (0, 1):
            self.skipTest('no git checkout here: ' + r.stderr.strip())
        self.assertEqual(r.stdout, '')

    def test_a_new_or_own_directory_becomes_owner_only(self):
        for shell in self.each_shell():
            new = self.tmp / f'new{self.n}'
            own = self.tmp / f'own{self.n}'
            self.n += 1
            own.mkdir(mode=0o755)
            for d in (new, own):
                r = self.private_dir(shell, d)
                self.assertEqual(r.stdout.strip(), 'rc=0', r.stderr)
                self.assertEqual(d.stat().st_mode & 0o777, 0o700)

    def test_hostile_directories_are_refused(self):
        target = self.tmp / 'target'
        for shell in self.each_shell():
            target.mkdir(mode=0o755, exist_ok=True)
            target.chmod(0o755)
            link = self.tmp / f'link{self.n}'
            link.symlink_to(target)
            plain = self.tmp / f'file{self.n}'
            plain.write_text('')
            loose = {}
            for mode in (0o777, 0o770, 0o1777, 0o702):
                d = self.tmp / f'loose{self.n}-{mode:o}'
                d.mkdir()
                d.chmod(mode)
                loose[d] = mode
            self.n += 1
            for d in [link, plain] + list(loose):
                with self.subTest(path=d.name):
                    r = self.private_dir(shell, d)
                    self.assertEqual(r.stdout.strip(), 'rc=1')
                    self.assertIn('refusing the runtime directory', r.stderr)
            self.assertEqual(target.stat().st_mode & 0o777, 0o755)   # no chmod through the symlink
            for d, mode in loose.items():
                self.assertEqual(d.stat().st_mode & 0o7777, mode)

    @unittest.skipUnless(hasattr(os, 'geteuid') and os.geteuid() == 0, 'needs root to make a directory another '
                         'user owns (the busybox docker run is root)')
    def test_another_users_directory_is_refused(self):
        for shell in self.each_shell():
            d = self.tmp / f'other{self.n}'
            self.n += 1
            d.mkdir(mode=0o700)
            os.chown(d, 65534, 65534)
            r = self.private_dir(shell, d)
            self.assertEqual(r.stdout.strip(), 'rc=1')
            self.assertIn('not ours', r.stderr)

    def test_the_backend_and_adapters_write_nothing_through_a_planted_symlink(self):
        victim = self.tmp / 'victim'
        link = None
        for shell in self.each_shell():
            if victim.exists():
                shutil.rmtree(victim)
            victim.mkdir(mode=0o755)
            link = self.tmp / f'planted{self.n}'
            self.n += 1
            link.symlink_to(victim)
            r, recs, _ = self.call(shell, 'at', {'cmd': 'ATI'}, MU300_DASH_DIR=link)
            self.assertEqual(self.reply(r), {'ok': 0, 'error': 'The runtime directory is not safe; nothing was run'})
            self.assertEqual(recs, [])
            for name, args in (('cell', ()), ('lock', ('get',))):
                r = self.script(shell, ADAPTERS / name, *args, MU300_AT=self.adapters / 'at', MU300_DASH_DIR=link,
                                STUB_CALLS=self.tmp, STUB_OUT=self.out, MU300_DASH_POOL_DIR=self.tmp / 'pool',
                                MU300_DASH_IDENT_DIR=self.tmp / 'ident', UNISOC_APPLY_DIR=self.tmp / 'apply')
                self.assertNotEqual(r.returncode, 0, name)
                self.assertIn('refusing the runtime directory', r.stderr)
            self.assertEqual(list(victim.iterdir()), [])
            self.assertEqual(victim.stat().st_mode & 0o777, 0o755)
        # the method list still answers: rpcd needs it to register the object
        r = subprocess.run(self.shells[0] + [str(DASH), 'list'], capture_output=True, text=True, timeout=60,
                           env=self.env(MU300_DASH_DIR=link))
        self.assertIn('"status"', r.stdout)


# mobile-data as the panel meets it: radio-busy and radio-locked (MD_BUSY set: another radio sequence holds the lock)
MOBILE_DATA_STUB = r"""#!/bin/sh
echo "md $* wait=${MU300_RADIO_LOCK_WAIT:-} locked=${MU300_RADIO_LOCKED:-}" >> "$STUBLOG/md"
case $1 in
    radio-busy) [ -n "${MD_BUSY:-}" ] && { echo 4242; exit 0; }; exit 1 ;;
    radio-locked)
        [ -n "${MD_BUSY:-}" ] && { echo "mobile-data: the radio is busy (pid 4242)" >&2; exit 75; }
        shift; exec "$@" ;;
esac
exit 0
"""
BUSY_RADIO = 'The radio is busy: the dial or the watchdog is switching it, try again shortly'


class RadioLock(Mu300Dash):
    """Final review minor 3: the panel's radio on/off and modem reset run under mobile-data's radio lock (through
    mobile-data radio-locked, never a copy of its locking), so they never race the dial's or the watchdog's radio_on;
    a held lock is answered "busy" (translated) and nothing reaches the modem."""

    def setUp(self):
        super().setUp()
        self.md = self.tmp / 'mobile-data'
        self.md.write_text(MOBILE_DATA_STUB)
        self.md.chmod(0o755)
        self.at = self.tmp / 'modem'
        self.at.write_text('#!/bin/sh\necho "at $* locked=${MU300_RADIO_LOCKED:-}" >> "$STUBLOG/at.log"\n'
                           'echo "+CFUN: 1"; echo OK\n')
        self.at.chmod(0o755)
        for name in ('ifup', 'ifdown'):
            self.stub(name, 'exit 0')

    def log(self, name):
        p = self.tmp / name
        text = p.read_text().splitlines() if p.exists() else []
        p.unlink(missing_ok=True)
        return text

    def action(self, shell, *args, **env):
        e = dict(MU300_AT=self.at, MU300_MOBILE_DATA=self.md, MU300_DASH_DIR=self.tmp / 'run')
        e.update(env)
        return self.script(shell, ADAPTERS / 'action', *args, **e)

    def test_radio_ops_run_under_the_lock(self):
        for shell in self.each_shell():
            for args, op, sent in ((('radio', 'off'), 'radio off', ['at -t 6 AT+CFUN=0 locked=1']),
                                   (('radio', 'on'), 'radio on', ['at -t 20 AT+SFUN=4 locked=1',
                                                                  'at -t 4 AT+CFUN? locked=1'])):
                with self.subTest(op=op):
                    r = self.action(shell, *args)
                    self.assertEqual(json.loads(r.stdout), {'ok': 1, 'op': op}, r.stderr)
                    self.assertEqual(self.log('md'), [f'md radio-locked {ADAPTERS / "action"} {" ".join(args)} '
                                                      'wait= locked=1'])
                    self.assertEqual(self.log('at.log'), sent)
            r = self.action(shell, 'modem-reset')
            self.assertEqual(json.loads(r.stdout), {'ok': 1, 'op': 'modem-reset'}, r.stderr)
            self.assertEqual(self.log('md'), [f'md radio-locked {ADAPTERS / "action"} modem-reset wait= locked=1',
                                              'md sim-reset wait= locked=1'])

    def test_a_busy_radio_is_answered_busy_and_nothing_is_sent(self):
        for shell in self.each_shell():
            for args, op in ((('radio', 'on'), 'radio on'), (('radio', 'off'), 'radio off'),
                             (('modem-reset',), 'modem-reset')):
                with self.subTest(op=op):
                    r = self.action(shell, *args, MD_BUSY=1)
                    self.assertEqual(json.loads(r.stdout), {'ok': 0, 'op': op, 'error': BUSY_RADIO})
                    self.assertEqual(self.log('at.log'), [])
                    self.assertEqual([l.split()[1] for l in self.log('md')], ['radio-locked'])

    def test_without_mobile_data_the_ops_run_as_before(self):
        for shell in self.each_shell():
            r = self.action(shell, 'radio', 'off', MU300_MOBILE_DATA=self.tmp / 'none')
            self.assertEqual(json.loads(r.stdout), {'ok': 1, 'op': 'radio off'}, r.stderr)
            self.assertEqual(self.log('at.log'), ['at -t 6 AT+CFUN=0 locked=1'])

    def test_the_backend_says_busy_before_starting_anything(self):
        known = set(subprocess.run([sys.executable, str(TOP / 'tools' / 'luci-i18n.py'), 'extract'], check=True,
                                   capture_output=True, text=True, encoding='utf-8').stdout.splitlines())
        self.assertIn(BUSY_RADIO, known)
        for shell in self.each_shell():
            for params in ({'op': 'radio', 'arg': 'on'}, {'op': 'radio', 'arg': 'off'}, {'op': 'modem-reset'}):
                with self.subTest(params=params):
                    r, recs, _ = self.call(shell, 'act', params, MU300_MOBILE_DATA=self.md, MD_BUSY=1)
                    self.assertEqual(self.reply(r), {'ok': 0, 'busy': 1, 'error': BUSY_RADIO})
                    self.assertEqual(recs, [])
                    r, recs, _ = self.call(shell, 'act', params, MU300_MOBILE_DATA=self.md)
                    self.assertEqual(self.reply(r).get('started'), 1, r.stdout)
                    self.assertEqual(recs[0][:3], ['setsid', 'action', params['op']])
            # the other ops never ask
            self.log('md')
            r, recs, _ = self.call(shell, 'act', {'op': 'data', 'arg': 'up'}, MU300_MOBILE_DATA=self.md, MD_BUSY=1)
            self.assertEqual(self.reply(r).get('ok'), 1, r.stdout)
            self.assertEqual(self.log('md'), [])



class AtBudget(Mu300Dash):
    """Final review minor 4: the AT terminal's whole wait (channel lock plus answer, mu300-at's MU300_AT_LOCK_WAIT and
    MU300_AT_BUDGET) stays under rpcd's 30 s limit, and a budget that runs out is a translated "busy", not a call
    rpcd kills."""

    def test_the_wait_is_capped_under_30_seconds(self):
        at = self.tmp / 'modem'
        at.write_text('#!/bin/sh\necho "lock=$MU300_AT_LOCK_WAIT budget=$MU300_AT_BUDGET" > "$STUBLOG/env"\n'
                      'case $3 in AT+SLOW) echo "mu300-at: no answer from the daemon" >&2; exit 1 ;; esac\necho OK\n')
        at.chmod(0o755)
        slow = 'The modem did not answer in time; the command may still run, check before sending it again'
        known = set(subprocess.run([sys.executable, str(TOP / 'tools' / 'luci-i18n.py'), 'extract'], check=True,
                                   capture_output=True, text=True, encoding='utf-8').stdout.splitlines())
        self.assertIn(slow, known)
        for shell in self.each_shell():
            r, _, _ = self.call(shell, 'at', {'cmd': 'ATI'}, MU300_AT=at)
            self.assertEqual(self.reply(r).get('ok'), 1, r.stdout)
            env = dict(kv.split('=') for kv in (self.tmp / 'env').read_text().split())
            self.assertLess(int(env['lock']) + int(env['budget']), 30)
            r, _, _ = self.call(shell, 'at', {'cmd': 'AT+SLOW'}, MU300_AT=at)
            self.assertEqual(self.reply(r), {'ok': 0, 'busy': 1, 'error': slow})


if __name__ == '__main__':
    unittest.main()
