"""The dashboard collector's SIM identity tier: what it caches, and what it refuses to cache.

A modem reply that fails is not the same as an empty one. `tr -cd 0-9` over "+CME ERROR: 10" leaves "10",
which passes an "is it non-empty" test and then holds the page for the whole six hours of the identity TTL
(field case: imsi and iccid both "10" in /etc/unisoc-modem/sim.json). The identity tier is therefore run
here for real - the function and the block are extracted from cell, the AT adapter is a stub - under every
shell the device uses, with the replies a modem gives in each state.
"""
import json
import os
import unittest

from helpers import TOP, ShellTest

CELL = TOP / 'openwrt' / 'luci-app-mu300' / 'root' / 'usr' / 'libexec' / 'unisoc-modem' / 'cell'

# Sample values only: a real subscriber's identifiers do not belong in a test file. The lengths are what the
# tier's guards are about (15/15, 14-15 and 18-20 digits), and the shapes are a real modem's answers.
IMEI = '000000000000000'
IMSI = '001010000000001'
ICCID = '89000000000000000001'
MFG = 'Spreadtrum Communication CO.'
MODEL = 'V1.0.1-B7'
FW = 'Platform Version: MOCORTM_V2_22C_W25.39.4_Debug'

# The names the adapter stub reads, so these keys are the stub's interface, not a label of our own: an entry
# exported under any other name answers nothing, and every test that expects a round to write nothing then
# passes for the wrong reason. test_the_stub_reads_every_reply_this_file_exports holds the two together.
REPLIES = {
    'CGMI_REPLY': f'{MFG}\r\nOK\r\n',
    'CGMM_REPLY': f'{MODEL}\r\nOK\r\n',
    'CGMR_REPLY': f'{FW}\r\nOK\r\n',
    'CGSN_REPLY': f'{IMEI}\r\nOK\r\n',
    'CIMI_REPLY': f'{IMSI}\r\nOK\r\n',
    'CCID_REPLY': f'+CCID: "{ICCID}"\r\nOK\r\n',
}

# The adapter stub: it answers from REPLY_* and records the commands it was asked (ATLOG), because the tier's
# contract is also how many of them it sends. A command it has no reply for is logged as unanswered, so a
# round that "read nothing" can be told apart from a round that was never given anything to read.
STUB_AT = r'''#!/bin/sh
cmd=$1
[ "$cmd" = "-t" ] && { shift 2; cmd=$1; }
printf '%s\n' "$cmd" >> "$ATLOG"
case $cmd in
    AT+CGSN) reply=$CGSN_REPLY ;;
    AT+CGMI) reply=$CGMI_REPLY ;;
    AT+CGMM) reply=$CGMM_REPLY ;;
    AT+CGMR) reply=$CGMR_REPLY ;;
    AT+CIMI) reply=$CIMI_REPLY ;;
    AT+CCID) reply=$CCID_REPLY ;;
    *)       reply= ;;
esac
[ -n "$reply" ] || printf '%s\n' "$cmd" >> "$ATLOG.unanswered"
printf '%s' "$reply"
exit 0
'''


def cell_function(name):
    """The body of the shell function NAME in cell, verbatim (its lines start in column 0)."""
    body = []
    for line in CELL.read_text().splitlines():
        if line.startswith(f'{name}() {{'):
            body = [line]
        elif body:
            body.append(line)
            if line == '}':
                return '\n'.join(body)
    raise AssertionError(f'{name}() not found in {CELL}')


def identity_tier():
    """The identity tier of cell, verbatim: `IDENT_AGE=` through the `fi` that closes its own `if`.

    The end of the block is located structurally, never by counting to the first `elif`: the tier's own `if`
    is the last branch of the `$MODE = full` guard, and the `fi` that closes it is the one at the same
    indentation as `IDENT_AGE=`. Stopping a line too early leaves an unbalanced fragment no shell will parse.
    """
    lines = CELL.read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip() == 'IDENT_AGE=999999')
    indent = len(lines[start]) - len(lines[start].lstrip())
    for i in range(start + 1, len(lines)):
        line = lines[i]
        if line.strip() and len(line) - len(line.lstrip()) == indent and line.strip() == 'fi':
            return '\n'.join(lines[start:i + 1])
    raise AssertionError(f'the identity tier is not closed in {CELL}')


def indented(text, pad=4):
    """TEXT with every non-empty line padded, so it can sit inside a shell function or subshell."""
    return '\n'.join(((' ' * pad) + l if l.strip() else l) for l in text.splitlines())


def shell_path(path):
    """PATH as the shell sees it: a Windows path becomes the /c/... form an MSYS shell understands.

    helpers.ShellTest hands the scratch directory to every shell the same way, so a shell that is native to
    Windows would otherwise be handed a path whose backslashes it eats.
    """
    text = str(path)
    if os.name == 'nt' and len(text) > 1 and text[1] == ':':
        drive, rest = text[0].lower(), text[2:].replace('\\', '/')
        return f'/{drive}{rest}'
    return text


def identity_harness(old_identity, age_the_file=True):
    """One cell identity round with the modem stubbed: the tier itself, plus a sim.json dated out of the TTL.

    The tier is verbatim, wrapped in a subshell that prints the identity JSON the round would publish -
    wrapped, not quoted, because the code has quotes of its own. `at` is the script's own adapter with the
    pool directories forced away from the device's, so the stub is the only thing that can answer; `qs` and
    `now` are the pair lib.sh and the round provide; the guard that needs a registered modem is stated.
    """
    age = 'touch -t 197001010100 "$IDENT"' if age_the_file else ':'
    seed = ''
    if old_identity is not None:
        seed = (f"printf '%s\\n' '{old_identity}' > \"$IDENT.part\" && "
                f'mv "$IDENT.part" "$IDENT"\n{age}')
    return f'''set -u
AT=$TESTDIR/stub/at
ATLOG=$TESTDIR/at.log
ATC=$TESTDIR/no-pool-channel
MU300_DASH_AT_DIR=$TESTDIR/none
IDENT_DIR=$TESTDIR/state
IDENT=$TESTDIR/state/sim.json
IDENT_MAXAGE=21600
STATE_DIR=$IDENT_DIR
mkdir -p "$IDENT_DIR"
{seed}
CEREG='+CEREG: 0,1,"3000","03253070",11'
MODE=full
REGISTERED=1
export AT ATLOG ATC MU300_DASH_AT_DIR IDENT IDENT_DIR IDENT_MAXAGE STATE_DIR CEREG MODE REGISTERED
{cell_function('ident_digits')}
at() {{
    local cmd=$1 timeout=${{2:-5}} d out seen=
    for d in "$ATC" /run/mu300-at6 /run/mu300-at7 /run/mu300-at; do
        [ -n "$d" ] && [ -p "$d/cmd" ] || continue
        case " $seen " in *" $d "*) continue ;; esac
        seen="$seen $d"
        out=$(MU300_AT_LOCK_WAIT=0 MU300_AT_DIR=$d "$AT" -t "$timeout" "$cmd" 2>/dev/null) || continue
        printf '%s\\n' "$out" | tr -d '\\r'
        return 0
    done
    out=$("$AT" -t "$timeout" "$cmd" 2>/dev/null) || return 1
    printf '%s\\n' "$out" | tr -d '\\r'
}}
now() {{ date +%s; }}
json_str_or_null() {{ printf '"%s"' "$1"; }}
qs() {{ json_str_or_null "$1"; }}
(
    IDENT_JSON=null
{indented(identity_tier())}
    printf '%s\\n' "$IDENT_JSON"
)
'''


class IdentityDigits(ShellTest):
    """ident_digits: the digits of a reply that answered, and nothing for one that refused."""

    def digits(self, shell, reply, low, high):
        code = f'{cell_function("ident_digits")}\nident_digits "$REPLY" {low} {high}\n'
        return self.sh(shell, code, REPLY=reply).stdout

    def test_a_refusal_is_never_read_as_a_value(self):
        """The bug itself: "+CME ERROR: 10" must not become "10"."""
        for shell in self.each_shell():
            for reply in ('+CME ERROR: 10', '+CME ERROR: 4', '+CMS ERROR: 10', 'ERROR',
                          '+CME ERROR: SIM not inserted', '\r\n+CME ERROR: 10\r\n', ''):
                for name, low, high in (('IMSI', 14, 15), ('ICCID', 18, 20)):
                    with self.subTest(shell=' '.join(shell), reply=reply, value=name):
                        self.assertEqual(self.digits(shell, reply, low, high), '')

    def test_a_real_reply_keeps_its_digits(self):
        for shell in self.each_shell():
            cases = [('+CCID: "89000000000000000001"', 18, 20, '89000000000000000001'),
                     ('89000000000000000001', 18, 20, '89000000000000000001'),
                     ('001010000000001', 14, 15, '001010000000001'),
                     ('00101000000000', 14, 15, '00101000000000'),        # a 14-digit IMSI
                     ('000000000000000', 15, 15, '000000000000000')]
            for reply, low, high, want in cases:
                with self.subTest(shell=' '.join(shell), reply=reply):
                    self.assertEqual(self.digits(shell, reply, low, high).strip(), want)

    def test_a_length_no_sim_has_is_refused(self):
        """A truncated or mangled reply goes the way of the error one."""
        for shell in self.each_shell():
            for reply, low, high in (('00101000000000', 15, 15), ('89000000000000000', 18, 20),
                                     ('0010100000000011', 14, 15), ('890000000000000000011', 18, 20)):
                with self.subTest(shell=' '.join(shell), reply=reply):
                    self.assertEqual(self.digits(shell, reply, low, high), '')


class IdentityTier(ShellTest):
    """The tier around it: a good reading is cached, a refused one is not."""

    def setUp(self):
        super().setUp()
        stub = self.tmp / 'stub'
        stub.mkdir()
        self.stub('at', STUB_AT)
        os.replace(self.stubs / 'at', stub / 'at')
        self.identity = self.tmp / 'state' / 'sim.json'
        self.log = self.tmp / 'at.log'

    def run_tier(self, shell, replies=None, old='{}', age_the_file=True):
        """One round; returns (the identity JSON it published, the CompletedProcess)."""
        env = dict(REPLIES if replies is None else replies)
        r = self.sh(shell, identity_harness(old, age_the_file), TESTDIR=shell_path(self.tmp), **env)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout.strip() or 'null'), r

    def cached(self):
        return json.loads(self.identity.read_text()) if self.identity.exists() else None

    def asked(self):
        return self.log.read_text().split() if self.log.exists() else []

    def unanswered(self):
        """The commands the stub had no reply for: a round must never "read nothing" silently."""
        missing = self.log.with_name(self.log.name + '.unanswered')
        return missing.read_text().split() if missing.exists() else []

    def test_the_stub_reads_every_reply_this_file_exports(self):
        """A reply exported under a name the stub does not read answers nothing.

        Every test that expects a round to write nothing then passes for the wrong reason - which is how a
        wrong key in REPLIES hid behind three green tests until a reviewer ran them.
        """
        for name in REPLIES:
            with self.subTest(reply=name):
                self.assertIn(f'${name}', STUB_AT, 'the stub never reads this reply')
        self.assertEqual(sorted(REPLIES), ['CCID_REPLY', 'CGMI_REPLY', 'CGMM_REPLY', 'CGMR_REPLY',
                                           'CGSN_REPLY', 'CIMI_REPLY'])

    def test_a_good_reading_is_cached(self):
        for shell in self.each_shell():
            with self.subTest(shell=' '.join(shell)):
                published, _ = self.run_tier(shell)
                self.assertEqual({k: published[k] for k in ('mfg', 'model', 'fw', 'imei', 'imsi', 'iccid')},
                                 {'mfg': MFG, 'model': MODEL, 'fw': FW,
                                  'imei': IMEI, 'imsi': IMSI, 'iccid': ICCID})
                self.assertIsInstance(published['ts'], int)
                self.assertEqual(self.cached()['imsi'], IMSI, 'the reading is written to sim.json')
                self.assertIn('AT+CIMI', self.asked())
                self.assertIn('AT+CCID', self.asked())
                self.assertEqual(self.unanswered(), [], 'the stub answered every command')

    def test_a_refused_reading_is_not_cached(self):
        """The regression: sim.json must never hold the digits of an error.

        The IMEI still answers here, so the round reaches the write and is stopped by the two refusals - not
        by having read nothing at all (which would pass this test without proving anything).
        """
        for shell in self.each_shell():
            with self.subTest(shell=' '.join(shell)):
                published, _ = self.run_tier(shell, dict(REPLIES, CIMI_REPLY='\r\n+CME ERROR: 10\r\n',
                                                         CCID_REPLY='\r\n+CME ERROR: 10\r\n'), old=None)
                self.assertEqual(self.unanswered(), [], 'the stub answered every command')
                self.assertIsNone(self.cached(), 'a refused read must leave no sim.json behind')
                self.assertNotIn('10', (published or {}).get('imsi', ''), 'no error digits are published')

    def test_a_refused_reading_keeps_the_cached_identity(self):
        """The page keeps working: the last good identity is served, and it is not rewritten."""
        old = ('{"ts":1,"mfg":"M","model":"D","fw":"F","imei":"%s","imsi":"%s","iccid":"%s"}'
               % (IMEI, IMSI, ICCID))
        for shell in self.each_shell():
            with self.subTest(shell=' '.join(shell)):
                published, _ = self.run_tier(shell, dict(REPLIES, CIMI_REPLY='+CME ERROR: 10'), old=old)
                self.assertEqual(self.unanswered(), [], 'the stub answered every command')
                self.assertEqual(published['imsi'], IMSI, 'the cached identity is the answer')
                self.assertEqual(self.identity.read_text().strip(), old, 'the cache is not rewritten')

    def test_a_fresh_identity_is_served_without_asking_the_modem(self):
        """Inside the TTL the cache is the answer: not one identity command is sent."""
        fresh = ('{"ts":1,"mfg":"M","model":"D","fw":"F","imei":"%s","imsi":"%s","iccid":"%s"}'
                 % (IMEI, IMSI, ICCID))
        for shell in self.each_shell():
            with self.subTest(shell=' '.join(shell)):
                published, _ = self.run_tier(shell, old=fresh, age_the_file=False)
                self.assertEqual(published['imsi'], IMSI)
                self.assertEqual([c for c in self.asked() if c in
                                  ('AT+CGSN', 'AT+CGMI', 'AT+CGMM', 'AT+CGMR', 'AT+CIMI', 'AT+CCID')], [])


if __name__ == '__main__':
    unittest.main()
