"""The control panel's catalogs: complete in Turkish and Chinese, no Chinese outside them (spec, Translations)."""
import importlib.util, json, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path
from helpers import GIT_CHECKOUT, TOP

TOOL = [sys.executable, str(TOP / 'tools' / 'luci-i18n.py')]
APP = TOP / 'openwrt' / 'luci-app-mu300'
CJK = '\u4e2d\u6587'        # written as escapes: this file is not one of the places Chinese is allowed

VIEW = 'htdocs/luci-static/resources/view/mu300/home.js'
DASH = 'root/usr/libexec/rpcd/mu300dash'


def run(*args):
    return subprocess.run(TOOL + list(args), capture_output=True, text=True, encoding='utf-8')


def po(header_lang, pairs):
    out = f'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: {header_lang}\\n"\n'
    for k, v in pairs:
        out += f'\nmsgid "{k}"\nmsgstr "{v}"\n'
    return out


# A small app with every kind of source; check passes on it, and each test breaks one thing.
MINI = {
    'root/usr/share/luci/menu.d/luci-app-mu300.json':
        '{\n "admin/home": {\n  "title": "Dashboard",\n  "order": 5\n }\n}\n',
    'root/usr/share/rpcd/acl.d/luci-app-mu300.json':
        '{\n "luci-app-mu300": {\n  "description": "MU300 control panel",\n  "read": {}\n }\n}\n',
    VIEW: (
        "'use strict';\n"
        "// _('Not a message: a comment') and /* _('nor this') */\n"
        "var s = \"_('nor a string')\", re = /_\\('nor a regex'\\)/;\n"
        "return L.view.extend({ render: function(res, carrier) {\n"
        "  var n = 3, a = n / 2 / 1;\n"
        "  E('p', {}, _('It\\'s \"quoted\" \\u0041')); x._('not the translate function');\n"
        "  E('p', {}, _(\"· %d messages\").format(n));\n"
        "  E('p', {}, `${_('In a template')}`);\n"
        "  E('p', {}, [ _(res.error), _( res.message ), _(carrier.name) ]);\n"
        "} });\n"),
    DASH: (
        "#!/bin/sh\n"
        "refuse() { printf '{\"ok\":0,\"error\":%s}\\n' \"$(json_str \"$1\")\"; }\n"
        "reply_obj() { json_obj \"$1\" || refuse \"$2\"; }\n"
        "m_a() { printf '{\"ok\":0,\"error\":\"Literal error\"}\\n'; }\n"
        "m_b() { [ -n \"$x\" ] || { refuse 'Refused here'; return; }; }\n"
        "m_c() { reply_obj \"$(foo)\" 'No valid reply'; }\n"
        "m_d() {\n"
        "    # i18n: Built elsewhere\n"
        "    printf '{\"ok\":0,\"error\":%s}\\n' \"$(json_str \"$msg\")\"\n"
        "}\n"),
    'root/usr/libexec/unisoc-modem/action': (
        "#!/bin/sh\n"
        "fail() { printf '{\"ok\":0,\"op\":%s,\"error\":%s}\\n' \"$(json_str \"$1\")\" \"$(json_str \"$2\")\"; }\n"
        "radio_on || fail \"radio on\" \"Radio did not come up\"\n"
        "printf '{\"ok\":1,\"message\":\"Done\"}\\n'\n"),
    'root/usr/libexec/unisoc-modem/device-usb': (
        "#!/bin/sh\n"
        "error() { printf '{\"ok\":0,\"error\":%s}\\n' \"$(json_str \"$1\")\"; exit 1; }\n"
        "[ -w \"$F\" ] || error 'USB role switch is unavailable'\n"),
}
MESSAGES = ['Dashboard', 'MU300 control panel', 'It\'s "quoted" A', '· %d messages', 'In a template',
            'Literal error', 'Refused here', 'No valid reply', 'Built elsewhere', 'Radio did not come up', 'Done',
            'USB role switch is unavailable']


def po_str(m):
    return m.replace('\\', '\\\\').replace('"', '\\"')


class Catalogs(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mu300-test-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def mini(self):
        root = self.tmp / 'mini'
        for rel, text in MINI.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding='utf-8')
        for lang, mark in (('tr', 'TR'), ('zh_Hans', CJK)):
            (root / 'po' / lang).mkdir(parents=True)
            (root / 'po' / lang / 'mu300.po').write_text(
                po(lang, [(po_str(m), po_str(m.replace('messages', 'x') + ' ' + mark)) for m in MESSAGES]),
                encoding='utf-8')
        return root

    @unittest.skipUnless(GIT_CHECKOUT, 'no git checkout here: the check reads what git tracks')
    def test_check_is_clean(self):
        r = run('check')
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    @unittest.skipUnless(shutil.which('git'), 'no git')
    def test_default_check_scans_the_repository(self):
        # without --root the check reads the files git tracks: Chinese in a shared script is found, Chinese in the
        # installers' i18n data is not (a copy of the tool, the app and two such files in a scratch repository)
        repo = self.tmp / 'repo'
        shutil.copytree(APP, repo / 'openwrt' / 'luci-app-mu300')
        shutil.copy(TOP / 'openwrt' / 'luci-languages.tsv', repo / 'openwrt' / 'luci-languages.tsv')
        (repo / 'tools').mkdir()
        for name in ('luci-i18n.py', 'po2lmo.py'):
            shutil.copy(TOP / 'tools' / name, repo / 'tools' / name)
        (repo / 'tools' / 'i18n.sh').write_text('# %s\n' % CJK, encoding='utf-8')
        (repo / 'rootfs' / 'overlay').mkdir(parents=True)
        (repo / 'rootfs' / 'overlay' / 'x.sh').write_text('echo %s\n' % CJK, encoding='utf-8')
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
        r = subprocess.run([sys.executable, str(repo / 'tools' / 'luci-i18n.py'), 'check'], capture_output=True,
                           text=True, encoding='utf-8')
        self.assertNotIn('Traceback', r.stderr)
        self.assertEqual(r.stdout, 'cjk: rootfs/overlay/x.sh:1: echo %s\n' % CJK)

    def test_extract_finds_every_kind_of_message_and_nothing_else(self):
        r = run('extract', '--root', str(self.mini()))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.splitlines(), MESSAGES)

    def test_minimal_app_is_clean(self):
        r = run('check', '--root', str(self.mini()))
        self.assertEqual((r.returncode, r.stdout), (0, ''), r.stderr)

    def test_every_catalog_is_checked(self):
        # a third language is held to the same rules as tr and zh_Hans; CJK is fine in any catalog; a catalog
        # directory the language table does not know is an error (the build could not name its .lmo)
        root = self.mini()
        (root / 'po' / 'ja').mkdir()
        (root / 'po' / 'ja' / 'mu300.po').write_text(
            po('ja', [(po_str(m), po_str(m.replace('messages', 'x') + ' ' + CJK)) for m in MESSAGES[1:]]),
            encoding='utf-8')
        (root / 'po' / 'xx').mkdir()
        (root / 'po' / 'xx' / 'mu300.po').write_text(
            po('xx', [(po_str(m), po_str(m.replace('messages', 'x') + ' X')) for m in MESSAGES]), encoding='utf-8')
        r = run('check', '--root', str(root))
        self.assertEqual(r.returncode, 1)
        lines = r.stdout.splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[0].startswith('missing: po/ja/mu300.po:0: "Dashboard" (used at '), lines)
        self.assertEqual(lines[1], 'language: po/xx/mu300.po:0: po/xx has no row in openwrt/luci-languages.tsv')
        # update keeps every catalog, the third one included
        run('update', '--root', str(root))
        self.assertIn('msgid "Dashboard"', (root / 'po' / 'ja' / 'mu300.po').read_text(encoding='utf-8'))

    def test_language_table(self):
        # one row per catalog of the app; codes as LuCI names its .lmo files; no row for English (the source)
        rows = [l.split('\t') for l in (TOP / 'openwrt' / 'luci-languages.tsv').read_text(encoding='utf-8')
                .splitlines() if l and not l.startswith('#')]
        self.assertTrue(all(len(r) == 3 for r in rows), rows)
        dirs = [r[0] for r in rows]
        self.assertEqual(len(dirs), len(set(dirs)))
        self.assertNotIn('en', dirs)
        for d, code, name in rows:
            self.assertRegex(code, r'^[a-z]{2,3}(-[a-z]{2})?$', d)
            self.assertRegex(name, r'^[^\t"\'\\$`]+ \([A-Z][A-Za-z ]+\)$', d)
        cats = sorted(p.parent.name for p in (APP / 'po').glob('*/mu300.po'))
        self.assertTrue(set(cats) <= set(dirs), set(cats) - set(dirs))
        self.assertGreaterEqual(len(cats), 25, 'the panel speaks at least the 23 languages asked for, tr and zh')

    def test_update_adds_missing_and_removes_stale_in_order_of_first_use(self):
        root = self.mini()
        tr = root / 'po' / 'tr' / 'mu300.po'
        tr.write_text(po('tr', [('Done', 'Tamam'), ('Gone', 'Yok')]), encoding='utf-8')
        shutil.rmtree(root / 'po' / 'zh_Hans')
        r = run('update', '--root', str(root))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        want = po('tr', [(po_str(m), 'Tamam' if m == 'Done' else '') for m in MESSAGES])
        self.assertEqual(tr.read_text(encoding='utf-8'), want)
        zh = (root / 'po' / 'zh_Hans' / 'mu300.po').read_text(encoding='utf-8')
        self.assertIn('"Language: zh_Hans\\n"', zh)
        self.assertEqual(zh.count('msgstr ""'), len(MESSAGES) + 1)
        r = run('check', '--root', str(root))       # still failing: the new entries have no translation yet
        self.assertEqual(r.returncode, 1)
        self.assertIn('empty msgstr', r.stdout)
        self.assertNotIn('stale', r.stdout)

    def test_checker_catches_each_rule(self):
        # each rule against a temporary copy of the app: the problems the defect adds must name the rule
        def append(rel, text):
            def apply(root):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                with open(root / rel, 'a', encoding='utf-8') as f:
                    f.write(text)
            return apply

        def tr_entry(msgid, msgstr):
            return append('po/tr/mu300.po', f'\nmsgid "{msgid}"\nmsgstr "{msgstr}"\n')

        def both(*steps):
            def apply(root):
                for s in steps:
                    s(root)
            return apply

        defects = [
            ('cjk', append(VIEW, f"\nvar label = '{CJK}';\n")),
            ('cjk', append('root/etc/init.d/unisoc-modem-ui', f'\n# {CJK}\n')),
            ('missing', append(VIEW, "\nE('p', {}, _('A message nobody translated'));\n")),
            ('missing', append(DASH, "\nm_z() { refuse 'A refusal nobody translated'; }\n")),
            ('missing', append(DASH, "\nm_y() { printf '{\"ok\":0,\"error\":\"A printf nobody translated\"}\\n'; }\n")),
            ('missing', append(DASH, '\n# i18n: A comment message nobody translated\n')),
            ('missing', both(append(VIEW, "\nE('p', {}, _('Empty in tr'));\n"), tr_entry('Empty in tr', ''))),
            ('missing', append(DASH, '\nm_x() { awk \'END { print "{\\"error\\":\\"Escaped nobody translated\\"}" }\'; }\n')),
            ('placeholder', both(append(VIEW, "\nE('p', {}, _('%d new messages').format(n));\n"),
                                 tr_entry('%d new messages', '%s yeni mesaj'))),
            ('stale', tr_entry('A message no source uses', 'Kimse kullanmiyor')),
            ('dynamic', append(VIEW, "\nE('p', {}, _(someVariable));\n")),
            ('dynamic', append(VIEW, "\nE('p', {}, _('Half ' + 'a sentence'));\n")),
            ('dynamic', append(DASH, '\nm_w() { printf \'{"ok":0,"error":%s}\\n\' "$(json_str "$msg")"; }\n')),
            ('dynamic', append(DASH, '\nm_v() { printf \'{"ok":0,"error":"%s"}\\n\' "$msg"; }\n')),
            ('plural', append(VIEW, "\nE('p', {}, N_(n, 'One item', '%d items').format(n));\n")),
        ]
        for base_name, base in (('the app', APP), ('a clean app', self.mini())):
            before = run('check', '--root', str(base))
            for n, (rule, defect) in enumerate(defects):
                with self.subTest(base=base_name, rule=rule, n=n):
                    root = self.tmp / f'{base.name}-{n}'
                    shutil.copytree(base, root)
                    defect(root)
                    after = run('check', '--root', str(root))
                    self.assertEqual(after.returncode, 1, after.stdout + after.stderr)
                    old = set(before.stdout.splitlines())      # paths are printed relative to --root
                    new = [line for line in after.stdout.splitlines() if line not in old]
                    self.assertTrue(any(line.startswith(rule + ': ') for line in new),
                                    f'{rule}: not among the new problems:\n' + '\n'.join(new))
                    shutil.rmtree(root)


COMMON = APP / 'htdocs/luci-static/resources/mu300/common.js'
BUILD = TOP / 'openwrt' / 'build-rootfs.sh'


def catalog(lang):
    """{msgid: msgstr} of po/<lang>/mu300.po, read as the tool reads it."""
    spec = importlib.util.spec_from_file_location('luci_i18n', TOP / 'tools' / 'luci-i18n.py')
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    return {e['msgid']: e['msgstr'] for e in tool.read_po(APP / 'po' / lang / 'mu300.po')[1]}


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the LuCI JS tests')
class Languages(unittest.TestCase):
    """common.js under Node, with LuCI's _() and String.prototype.format stubbed: _ looks a message up in the
    catalog LuCI would load for the browser's language (none for English or a language the app does not have).
    The Chinese expectations are written as escapes, as everywhere in this file."""

    def run_js(self, lang, body):
        """Run body (an async function body) with M = common.js loaded for lang; returns {result: body's value,
        used: every _() argument, in order}. The stubs: one DOM element per createElement, every getElementById the
        toast container (notes collects what it is given), window.setInterval keeps its callback as tick, rpc calls
        answer rpcReply, and setTimeout does nothing."""
        cat = catalog(lang) if lang in ('tr', 'zh_Hans') else {}
        harness = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const CATALOG = %s;
String.prototype.format = function() {
    const args = arguments; let i = 0;
    return this.replace(/%%(%%|s|d)/g, (m, c) => c === '%%' ? '%%' : c === 'd' ? String(Math.trunc(args[i++])) : String(args[i++]));
};
const used = [];
const _ = (s) => { used.push(s); return Object.prototype.hasOwnProperty.call(CATALOG, s) ? CATALOG[s] : s; };
let aurora = '', selected, tick, rpcReply = {};
const notes = [];
const toasts = { appendChild: (t) => notes.push(t) };
const element = () => { const parts = {}; return { classList: { add: () => {} }, addEventListener: () => {},
    remove: () => {}, querySelector: (sel) => parts[sel] || (parts[sel] = {}) }; };
const root = { classList: { remove: () => {}, toggle: (name, value) => { selected = value; } } };
const document = { documentElement: root, body: { appendChild: () => {} }, getElementById: () => toasts,
    createElement: element, head: { appendChild: () => {} } };
const style = () => ({ getPropertyValue: (key) => key === '--surface' ? aurora : key === '--background-color-high' ? '#fff' : '' });
const window = { setInterval: (fn) => { tick = fn; } };
const flush = () => new Promise((r) => setImmediate(r));
const M = new Function('rpc', 'baseclass', '_', 'document', 'getComputedStyle', 'window', 'setTimeout', src)(
    { declare: () => () => rpcReply }, { extend: (obj) => obj }, _, document, style, window, () => 0);
(async function() { %s })().then((result) => process.stdout.write(JSON.stringify({ result: result, used: used })),
    (e) => { console.error(e); process.exit(1); });
''' % (json.dumps(cat, ensure_ascii=True), body)
        r = subprocess.run(['node', '-', str(COMMON)], input=harness, capture_output=True, text=True,
                           encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    RENDER = '''
const sms = (id, peer) => ({ id: String(id), dir: 'mt', peer: peer, preview: 'text ' + id });
M.watchSms();
rpcReply = { msgs: [ sms(1, '10086') ] }; tick(); await flush();          // the first read only sets the baseline
rpcReply = { msgs: [ sms(3, ''), sms(2, '10086'), sms(1, '10086') ] }; tick(); await flush();
return {
    quality: [ M.qLabel(-85), M.qLabel(-95), M.qLabel(-105), M.qLabel(-115), M.qLabel() ],
    uptime: [ M.fmtUptime(90061), M.fmtUptime(3720), M.fmtUptime(300) ],
    neighbours: M.neighborRows({}),
    locks: M.neighborRows({ neigh: [ { rat: 'nr', band: 78, pci: 1, arfcn: 2, rsrp: -80 },
                                     { rat: 'lte', band: 3, pci: 4, arfcn: 5, rsrp: -90 } ] }, 'nr:2,1'),
    colour: M.qCol(M.qLevel(-115)),
    sms: notes.map((n) => n.querySelector('b').textContent)
};'''

    def test_three_languages(self):
        # The fork's case was a sentence assembled from fragments ('Link & traffic' + ' · ' + 'No response', a pair
        # that exists only in its test). common.js's own assembled sentence was the new-SMS banner, ('new SMS · ' in
        # Chinese) + sender; it is now one message with a placeholder, rendered whole in each language, with the unknown-
        # sender fallback translated inside it.
        want = {
            None: (['Excellent', 'Good', 'Fair', 'Poor', 'Unknown'], ['1 d 1 h', '1 h 2 min', '5 min'],
                   'No neighbor-cell data', 'Locked', 'Lock', ['New SMS · Unknown number', 'New SMS · 10086']),
            # tr's catalog is complete but holds the English msgids: only zh_Hans is translated, so tr renders English
            'tr': (['Excellent', 'Good', 'Fair', 'Poor', 'Unknown'], ['1 d 1 h', '1 h 2 min', '5 min'],
                   'No neighbor-cell data', 'Locked', 'Lock', ['New SMS · Unknown number', 'New SMS · 10086']),
            'zh_Hans': (['\u4f18\u79c0', '\u826f\u597d', '\u4e00\u822c', '\u8f83\u5dee', '\u672a\u77e5'],
                        ['1 \u5929 1 \u5c0f\u65f6', '1 \u5c0f\u65f6 2 \u5206', '5 \u5206'],
                        '\u6682\u65e0\u90bb\u533a\u6570\u636e', '\u5df2\u9501\u5b9a', '\u9501\u5b9a',
                        ['\u65b0\u77ed\u4fe1 \xb7 \u672a\u77e5\u53f7\u7801', '\u65b0\u77ed\u4fe1 \xb7 10086']),
        }
        for lang, (quality, uptime, empty, locked, lock, sms) in want.items():
            with self.subTest(lang=lang):
                r = self.run_js(lang, self.RENDER)['result']
                self.assertEqual(r['quality'], quality)
                self.assertEqual(r['uptime'], uptime)
                self.assertIn('>%s</td>' % empty, r['neighbours'])
                self.assertIn('>%s</button>' % locked, r['locks'])
                self.assertIn('>%s</button>' % lock, r['locks'])
                self.assertEqual(r['colour'], 'var(--danger, #E25555)')   # a level's colour, whatever the language
                self.assertEqual(r['sms'], sms)

    LEVELS = ('excellent', 'good', 'fair', 'poor', 'unknown')

    def test_quality_colour_is_the_same_in_every_language(self):
        # qCol takes a level key, never a translated label: a page that grades by itself (home.js: the Wi-Fi
        # clients, the temperatures, no modem answer) gets the same colour in every language, and qLabel/qLevel
        # agree for every reading
        body = '''
const levels = %s, readings = [ [ -85 ], [ -95 ], [ -105 ], [ -115 ], [], [ null, null, 25 ], [ null, -12 ] ];
return { colours: levels.map((l) => M.qCol(l)),
         graded: readings.map((r) => [ M.qLevel.apply(null, r), M.qLabel.apply(null, r) ]),
         names: levels.map((l) => M.qLevelLabel(l)) };''' % json.dumps(self.LEVELS)
        runs = {lang: self.run_js(lang, body)['result'] for lang in (None, 'tr', 'zh_Hans')}
        colours = runs[None]['colours']
        self.assertEqual(len(set(colours)), 5, colours)                   # five levels, five colours
        self.assertIn('var(--text-subtle', colours[4])                    # unknown is the neutral grey
        for lang, r in runs.items():
            with self.subTest(lang=lang):
                self.assertEqual(r['colours'], colours)
                names = dict(zip(self.LEVELS, r['names']))
                self.assertEqual([g[0] for g in r['graded']],
                                 ['excellent', 'good', 'fair', 'poor', 'unknown', 'excellent', 'fair'])
                self.assertEqual([g[1] for g in r['graded']], [names[g[0]] for g in r['graded']])

    def test_views_pass_level_keys_to_qcol(self):
        # every qCol argument in the views is a level key literal or a qLevel result, never a (Chinese or
        # translated) label; the literals the pages grade with (home.js) are all level keys
        views = APP / 'htdocs/luci-static/resources/view/mu300'
        for js in sorted(views.glob('*.js')):
            src = js.read_text(encoding='utf-8')
            for arg in re.findall(r'M\.qCol\(([^()]*(?:\([^()]*\))?[^()]*)\)', src):
                with self.subTest(view=js.name, arg=arg):
                    lit = re.fullmatch(r"'([^']*)'", arg)
                    self.assertTrue(lit and lit.group(1) in self.LEVELS or arg.startswith('M.qLevel(')
                                    or arg in ('level', 'l', 'lab'), arg)
        home = (views / 'home.js').read_text(encoding='utf-8')
        for var in ('l', 'lab'):
            # the variable passed to qCol is assigned only level keys
            assign = re.search(r'var %s = ([^;]*);' % var, home).group(1)
            self.assertEqual(set(re.findall(r"'([^']*)'", assign)) - set(self.LEVELS), set(), assign)

    def test_carrier_names_follow_locale(self):
        # the fork's cases (a COPS name, a PLMN from the table) with the name COPS gives in English
        body = '''return [ M.carrierName({ name: 'China Unicom' }), M.carrierName({ plmn: '46001' }),
                          M.carrierName({ plmn: '46000' }), M.carrierName({ name: 'Turkcell' }),
                          M.carrierName({ plmn: '28601' }), M.carrierName(null) ];'''
        unicom, mobile = '\u4e2d\u56fd\u8054\u901a', '\u4e2d\u56fd\u79fb\u52a8'
        for lang, want in ((None, ['China Unicom', 'China Unicom', 'China Mobile']),
                           ('tr', ['China Unicom', 'China Unicom', 'China Mobile']),
                           ('zh_Hans', [unicom, unicom, mobile])):
            with self.subTest(lang=lang):
                # a name the catalogs do not know, a PLMN outside the table and no operator pass through
                self.assertEqual(self.run_js(lang, body)['result'], want + ['Turkcell', '28601', '--'])

    def test_unknown_language_is_english(self):
        # German has no catalog: every _() returns its msgid, and every msgid rendered is one the catalogs carry
        out = self.run_js('de', '''
M.injectCss();
if (selected !== true) throw Error('the Bootstrap token bridge must survive the conversion');''' + self.RENDER)
        r, used = out['result'], set(out['used'])
        self.assertEqual(r['quality'], ['Excellent', 'Good', 'Fair', 'Poor', 'Unknown'])
        self.assertEqual(r['uptime'], ['1 d 1 h', '1 h 2 min', '5 min'])
        self.assertIn('>No neighbor-cell data</td>', r['neighbours'])
        self.assertIn('>Locked</button>', r['locks'])
        self.assertEqual(r['sms'], ['New SMS · Unknown number', 'New SMS · 10086'])
        extracted = set(subprocess.run(TOOL + ['extract'], capture_output=True, text=True, encoding='utf-8',
                                       check=True).stdout.splitlines())
        self.assertLessEqual(used, extracted)
        for lang in ('tr', 'zh_Hans'):
            self.assertLessEqual(used, set(catalog(lang)), lang)

    def test_common_menu_and_acl_have_no_chinese_and_are_in_both_catalogs(self):
        # Task 13's files: the catalog check finds no problem in them (the views and backend are Tasks 14-16)
        r = run('check')
        mine = ('mu300/common.js', 'menu.d/luci-app-mu300.json', 'acl.d/luci-app-mu300.json')
        self.assertEqual([l for l in r.stdout.splitlines() if any(m in l for m in mine)], [])
        self.assertEqual([l for l in r.stdout.splitlines() if l.startswith(('stale', 'po:', 'placeholder'))], [])
        self.assertFalse((APP / 'po' / 'en').exists(), 'English is the source: no po/en catalog')

    def test_build_requires_the_chinese_catalog(self):
        # once po/zh_Hans exists, the build stops when mu300.zh-cn.lmo (LuCI's code for zh_Hans) was
        # not compiled from it: without it the panel is in English in a Chinese browser
        self.assertTrue((APP / 'po' / 'zh_Hans' / 'mu300.po').is_file())
        self.assertTrue('[ -s "$CAT/mu300.zh-cn.lmo" ] ||' in BUILD.read_text(encoding='utf-8'),
                        'build-rootfs.sh does not stop without the Chinese panel catalog')


VIEWS = APP / 'htdocs/luci-static/resources/view/mu300'
VIEW_NAMES = ('home', 'locks', 'sms', 'at', 'settings', 'device', 'languages', 'ttl')
CJK_RE = re.compile('[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef]')


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the LuCI JS tests')
class Views(unittest.TestCase):
    """The six pages under Node: each view module is evaluated as LuCI evaluates it (a function body whose
    'require'd modules are arguments), with view/uci/poll/form/ui/dom stubbed, the real common.js as M and _ looking
    messages up in the chosen catalog. A small DOM stub keeps one element per id, so what a page writes into
    #mud-<id> can be read back; setTimeout only queues (timers), the body runs what it wants."""

    HARNESS = r'''
const fs = require('fs');
const CATALOG = __CATALOG__;
String.prototype.format = function() {
    const args = arguments; let i = 0;
    return this.replace(/%(%|s|d)/g, (m, c) => c === '%' ? '%' : c === 'd' ? String(Math.trunc(args[i++])) : String(args[i++]));
};
const used = [];
const _ = (s) => { used.push(s); return Object.prototype.hasOwnProperty.call(CATALOG, s) ? CATALOG[s] : s; };
const els = {}, toasts = [], timers = [];
const el = (id) => { const e = { id: id, innerHTML: '', textContent: '', className: '', style: {}, children: [],
    value: '', disabled: false, checked: false, firstChild: { nodeValue: '' }, lastChild: { textContent: '' },
    classList: { add: () => {}, remove: () => {}, toggle: () => {}, contains: () => false },
    on: {}, removeEventListener: () => {}, insertBefore: (c) => c,
    remove: () => {}, focus: () => {}, setAttribute: () => {}, getAttribute: () => null, contains: () => true,
    querySelector: (sel) => sel[0] === '#' ? get(sel.slice(1)) : el(''), querySelectorAll: () => [] };
    e.appendChild = (c) => { e.children.push(c); return c; };
    e.addEventListener = (type, fn) => { (e.on[type] = e.on[type] || []).push(fn); };
    e.replaceChildren = () => { e.children = []; e.textContent = ''; };
    return e; };
const get = (id) => els[id] || (els[id] = el(id));
get('mud-toasts').appendChild = (t) => { toasts.push(t); return t; };
const document = { getElementById: get, createElement: () => el(''), documentElement: el('html'), body: el('body'),
    head: el('head'), addEventListener: () => {}, removeEventListener: () => {}, contains: () => true };
// everything a page shows: every element's text and markup, the children it appended, and the toasts
const shown = () => { const out = [], walk = (e) => { out.push(e.textContent, e.innerHTML, e.placeholder || '',
    e.title || ''); e.children.forEach(walk); }; Object.values(els).forEach(walk); return out.concat(notes()); };
const getComputedStyle = () => ({ getPropertyValue: () => '' });
const window = { setInterval: () => 0, location: { reload: () => {} } };
const setTimeout = (fn) => { timers.push(fn); return timers.length; };
const clearTimeout = () => {};
let rpcReply = {};
const rpc = { declare: () => () => Promise.resolve(rpcReply) };
const L = { resolveDefault: (p, d) => Promise.resolve(p).catch(() => d), env: {}, bind: (f, self) => f.bind(self),
    url: (p) => '/cgi-bin/luci/' + p };
const M = new Function('rpc', 'baseclass', '_', 'document', 'getComputedStyle', 'window', 'setTimeout', 'clearTimeout',
    fs.readFileSync(process.argv[2], 'utf8'))(rpc, { extend: (o) => o }, _, document, getComputedStyle, window,
    setTimeout, clearTimeout);
const stub = () => new Proxy(function() {}, { get: (t, k) => k === 'then' ? undefined : stub(), apply: () => stub(),
    construct: () => stub() });
const view = { extend: (o) => o };
const uci = { load: () => Promise.resolve(), get: () => null, set: () => {}, save: () => Promise.resolve() };
const poll = { add: () => {}, remove: () => {} };
const V = new Function('view', 'uci', 'poll', 'form', 'ui', 'dom', 'M', '_', 'L', 'document', 'window', 'setTimeout',
    'clearTimeout', 'getComputedStyle', 'E', fs.readFileSync(process.argv[3], 'utf8'))(view, uci, poll, stub(), stub(),
    stub(), M, _, L, document, window, setTimeout, clearTimeout, getComputedStyle, stub());
const flush = () => new Promise((r) => setImmediate(r));
const text = (id) => get('mud-' + id).textContent, html = (id) => get('mud-' + id).innerHTML;
const notes = () => toasts.map((t) => t.lastChild.textContent);
(async function() { __BODY__ })().then((result) => process.stdout.write(JSON.stringify({ result: result, used: used })),
    (e) => { console.error(e); process.exit(1); });
'''

    def run_view(self, name, lang, body):
        cat = catalog(lang) if lang in ('tr', 'zh_Hans') else {}
        harness = self.HARNESS.replace('__CATALOG__', json.dumps(cat, ensure_ascii=True)).replace('__BODY__', body)
        r = subprocess.run(['node', '-', str(COMMON), str(VIEWS / f'{name}.js')], input=harness, capture_output=True,
                           text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def assert_english_and_catalogued(self, out):
        # no Chinese left in what the page shows, and every message it used is extracted and in both catalogs
        self.assertIsNone(CJK_RE.search(json.dumps(out['result'], ensure_ascii=False)), out['result'])
        self.assertLessEqual(set(out['used']), set(run('extract').stdout.splitlines()))
        for lang in ('tr', 'zh_Hans'):
            self.assertLessEqual(set(out['used']), set(catalog(lang)), lang)

    def test_every_view_loads(self):
        # the module of each page evaluates and returns a view object with render()
        for name in VIEW_NAMES:
            with self.subTest(view=name):
                r = self.run_view(name, None, "return [ typeof V, typeof V.render ];")['result']
                self.assertEqual(r, ['object', 'function'])

    def test_the_languages_page_puts_backend_text_in_as_text(self):
        # LuCI's E(tag, attrs, 'string') sets innerHTML; names, the release and the job's log come from the language
        # pack (perhaps an uploaded one), so every value that is not a literal or a _() message goes in as [ value ]
        src = (VIEWS / 'languages.js').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r"E\('\w+', \{[^}]*\}, (?!_\(|\[|')[A-Za-z][^\n]*", src), [])
        self.assertNotIn('innerHTML', src)

    def test_the_translate_shims_are_gone(self):
        # translate/localize/localizeMenu did the fork's partial matching; the pages have only _() now, and
        # common.js no longer has the no-op shims Task 13 left for them
        for name in VIEW_NAMES:
            with self.subTest(view=name):
                src = (VIEWS / f'{name}.js').read_text(encoding='utf-8')
                self.assertEqual(re.findall(r'\b(?:translate|localize|localizeMenu)\(|\bt\(_\(', src), [])
        r = self.run_view('home', None, "return [ 'translate', 'localize', 'localizeMenu' ].filter((k) => k in M);")
        self.assertEqual(r['result'], [])

    HOME = '''
const root = V.render();
await flush();
V.update({ info: { ts: 10, host: 'mu300', uptime: 3720, modem: { alive: true, atd: false },
                   wifi: { ssid: 'x', channel: 36, band: '5g', clients_n: 2, hidden: 1, up: 1 },
                   lan: { ip: '192.168.0.1', leases: 3, list: [ { host: 'a', ip: '1', mac: 'm', left: 7200 } ] },
                   temps: { soc: 50 }, mem: { total_kb: 1024, avail_kb: 512 }, power: { present: 1, capacity: 80,
                   status: 'Charging' }, conns: 7, cpu: { freqs: [ { cur: 1000, max: 2000 } ] } },
           cell: { ts: 5, cfun: 1, reg: { stat: 1, tac: 'AB' }, sig: { rsrp: -95, rsrq: -10, sinr: 15 },
                   lte: { band: 3, pci: 1, earfcn: 1850, sinr: 15 }, ident: { imsi: '460011234567890' } } });
return { html: root.innerHTML, op: text('op'), uptime: text('uptime'), reg: text('reg'), modem: text('modem'),
         wcl: text('wcl'), conntrack: text('conntrack'), ram: text('ram-sub'), cell: html('cellline'),
         freqs: html('freqs'), leases: html('leases') };'''

    def test_home_renders_in_each_language(self):
        want = {
            None: ('Link & traffic', 'China Unicom · Signal Good 7.8/10', 'Uptime 1 h 2 min', 'Registered · TAC AB',
                   'Online · AT adapter unavailable', '2 clients', '7 entries', 'Total 1.0 MB · free 512 KB',
                   'Anchor B3', 'Cluster 0', 'Recent DHCP leases', '2 h'),
            # tr's catalog is complete but holds the English msgids: only zh_Hans is translated, so tr renders English
            'tr': ('Link & traffic', 'China Unicom · Signal Good 7.8/10', 'Uptime 1 h 2 min', 'Registered · TAC AB',
                   'Online · AT adapter unavailable', '2 clients', '7 entries', 'Total 1.0 MB · free 512 KB',
                   'Anchor B3', 'Cluster 0', 'Recent DHCP leases', '2 h'),
            'zh_Hans': ('\u94fe\u8def\u4e0e\u6d41\u91cf',
                        '\u4e2d\u56fd\u8054\u901a \xb7 \u4fe1\u53f7 \u826f\u597d 7.8 \u5206',
                        '\u5df2\u8fd0\u884c 1 \u5c0f\u65f6 2 \u5206', '\u5df2\u6ce8\u518c \xb7 TAC AB',
                        '\u5728\u7ebf \xb7 AT \u9002\u914d\u5668\u4e0d\u53ef\u7528', '2 \u53f0', '7 \u6761',
                        '\u5171 1.0 MB \xb7 \u4f59 512 KB', '\u951a\u70b9 B3', '\u7c070',
                        '\u8fd1\u671f DHCP \u79df\u7ea6', '2 \u5c0f\u65f6'),
        }
        for lang, (heading, op, uptime, reg, modem, wcl, conns, ram, cell, cluster, leases, hours) in want.items():
            with self.subTest(lang=lang):
                r = self.run_view('home', lang, self.HOME)['result']
                self.assertIn(heading, r['html'])
                self.assertEqual(r['op'], op)
                self.assertEqual((r['uptime'], r['reg'], r['modem'], r['wcl'], r['conntrack']),
                                 (uptime, reg, modem, wcl, conns))
                self.assertEqual(r['ram'], ram)
                self.assertIn(cell, r['cell'])
                self.assertIn('>%s<' % cluster, r['freqs'])
                self.assertIn(leases, r['leases'])
                self.assertIn('>%s<' % hours, r['leases'])
                if lang != 'zh_Hans':
                    self.assertIsNone(CJK_RE.search(json.dumps(r, ensure_ascii=False)), r)

    LOCKS = '''
const root = V.render();
await flush();
V.lastLock = { mode: { label: 'auto' }, endc: '1', auto_apply: 1, cells: [ 'nr:627264,1' ],
               nr: { locked: '78' }, lte: { locked: '' } };
V.paint();
V.paintServing({ nr: { band: 78, pci: 1, arfcn: 627264 }, lte: { band: 3, pci: 2, earfcn: 1850 },
                 sig: { rsrp: -90 }, ident: { imsi: '460001234567890' } });
const out = { html: root.innerHTML, nr: text('lock-nrline'), lte: text('lock-lteline'), auto: text('lock-auto-apply'),
              cells: html('lockedcells'), srv: text('srv-rat'), lines: html('srv') };
// a confirmed apply-at-startup switch, on and then off: one whole message each
toasts.length = 0;
rpcReply = { auto_apply: 1 }; V.confirmToggle('auto_apply', 'on', null);
timers.splice(0).forEach((f) => f()); await flush();
rpcReply = { auto_apply: 0 }; V.confirmToggle('auto_apply', 'off', null);
timers.splice(0).forEach((f) => f()); await flush();
out.notes = notes();
return out;'''

    def test_locks_renders_in_each_language(self):
        want = {
            None: ('Band locking', '1 locked: n78', 'Automatic (9 supported)', 'Apply at startup ✓', 'Unlock NR',
                   '5G NSA · China Mobile', 'NR serving cell', ['Apply at startup is on', 'Apply at startup is off']),
            # tr's catalog is complete but holds the English msgids: only zh_Hans is translated, so tr renders English
            'tr': ('Band locking', '1 locked: n78', 'Automatic (9 supported)', 'Apply at startup ✓', 'Unlock NR',
                   '5G NSA · China Mobile', 'NR serving cell',
                   ['Apply at startup is on', 'Apply at startup is off']),
            'zh_Hans': ('\u9891\u6bb5\u9501\u5b9a', '\u5df2\u9501 1 \u4e2a\uff1an78',
                        '\u81ea\u52a8\uff08\u652f\u6301 9 \u4e2a\uff09', '\u5f00\u673a\u81ea\u52a8\u5e94\u7528 ✓',
                        '\u89e3\u9501 NR', '5G NSA \xb7 \u4e2d\u56fd\u79fb\u52a8', 'NR \u670d\u52a1\u5c0f\u533a',
                        ['\u5f00\u673a\u81ea\u52a8\u5e94\u7528\u5df2\u5f00\u542f',
                         '\u5f00\u673a\u81ea\u52a8\u5e94\u7528\u5df2\u5173\u95ed']),
        }
        for lang, (heading, nr, lte, auto, unlock, srv, line, notes) in want.items():
            with self.subTest(lang=lang):
                r = self.run_view('locks', lang, self.LOCKS)['result']
                self.assertIn(heading, r['html'])
                self.assertEqual((r['nr'], r['lte'], r['auto'], r['srv']), (nr, lte, auto, srv))
                self.assertIn('>%s</button>' % unlock, r['cells'])
                self.assertIn(line, r['lines'])
                self.assertEqual(r['notes'], notes)
                if lang != 'zh_Hans':
                    self.assertIsNone(CJK_RE.search(json.dumps(r, ensure_ascii=False)), r)

    SMS = '''
const root = V.render();
rpcReply = { pages: 1, total: 3, unread: 1, msgs: [ { id: '3', peer: '10086', dir: 'mo', preview: 'hi', time: 't3' },
    { id: '2', peer: '10086', dir: 'mt', preview: 'yo', time: 't2', status: 'unread' },
    { id: '1', peer: '+905551112233', dir: 'mt', preview: 'x', time: 't1' } ] };
await V.reload(); await flush();
const out = { html: root.innerHTML, stat: text('sms-stat'), convs: html('sms-convs') };
toasts.length = 0;
V.send();                                                   // no number, no text
get('mud-sms-num').value = '10086'; get('mud-sms-text').value = 'hello';
rpcReply = { ok: 0, busy: 1, error: 'The AT channel is busy; the command was not sent, try again' };
V.send(); await flush();
rpcReply = { ok: 0, error: 'Sending failed', detail: '+CMS ERROR: 500' }; V.send(); await flush();
out.notes = notes();
return out;'''

    def test_sms_renders_in_each_language(self):
        want = {
            None: ('Sync from SIM', '· 3 messages, 1 unread · 2 conversations', 'Me: hi',
                   ['Enter both a number and a message.', 'Sending…',
                    'The AT channel is busy; the command was not sent, try again', 'Sending…',
                    'Sending failed (+CMS ERROR: 500)']),
            # tr's catalog is complete but holds the English msgids: only zh_Hans is translated, so tr renders English
            'tr': ('Sync from SIM', '· 3 messages, 1 unread · 2 conversations', 'Me: hi',
                   ['Enter both a number and a message.', 'Sending…',
                    'The AT channel is busy; the command was not sent, try again', 'Sending…',
                    'Sending failed (+CMS ERROR: 500)']),
            'zh_Hans': ('\u4ece SIM \u540c\u6b65', '\xb7 3 \u6761\uff0c1 \u6761\u672a\u8bfb \xb7 2 \u4e2a\u4f1a\u8bdd',
                        '\u6211: hi',
                        ['\u53f7\u7801\u548c\u5185\u5bb9\u90fd\u8981\u586b\u3002', '\u53d1\u9001\u4e2d…',
                         'AT \u901a\u9053\u6b63\u5fd9\uff0c\u547d\u4ee4\u672a\u53d1\u51fa\uff0c\u8bf7\u91cd\u8bd5',
                         '\u53d1\u9001\u4e2d…', '\u53d1\u9001\u5931\u8d25 (+CMS ERROR: 500)']),
        }
        for lang, (button, stat, me, notes) in want.items():
            with self.subTest(lang=lang):
                r = self.run_view('sms', lang, self.SMS)['result']
                self.assertIn(button, r['html'])
                self.assertEqual(r['stat'], stat)
                self.assertIn('>%s<' % me, r['convs'])
                self.assertEqual(r['notes'], notes)

    AT = '''
const root = V.render();
const lines = [];
get('mud-at-out').appendChild = (s) => { lines.push(s.textContent); return s; };
get('mud-at-cmd').value = 'AT+CSQ';
rpcReply = { ok: 0, busy: 1, error: 'The AT channel is busy; the command was not sent, try again' };
V.send(); await flush();
get('mud-at-cmd').value = 'AT';
rpcReply = { ok: 1 }; V.send(); await flush();
return { html: root.innerHTML, lines: lines.filter((l) => !/^(> |\\u2014)/.test(l)), hist: html('at-hist') };'''

    def test_at_renders_in_each_language(self):
        want = {
            # the backend's sentence alone: it is a whole sentence already, an "Error: " in front doubled it (R31)
            None: ('Clear screen', ['The AT channel is busy; the command was not sent, try again\n',
                                    '(no output)\n'],
                   '(empty)'),
            # tr's catalog is complete but holds the English msgids: only zh_Hans is translated, so tr renders English
            'tr': ('Clear screen', ['The AT channel is busy; the command was not sent, try again\n',
                                    '(no output)\n'], '(empty)'),
            'zh_Hans': ('\u6e05\u5c4f',
                        ['AT \u901a\u9053\u6b63\u5fd9\uff0c\u547d\u4ee4\u672a\u53d1\u51fa\uff0c\u8bf7\u91cd\u8bd5\n',
                         '(\u65e0\u8f93\u51fa)\n'], '\uff08\u7a7a\uff09'),
        }
        for lang, (button, lines, empty) in want.items():
            with self.subTest(lang=lang):
                r = self.run_view('at', lang, self.AT)['result']
                self.assertIn(button, r['html'])
                self.assertEqual(r['lines'], lines)
                self.assertIn('>%s<' % empty, r['hist'])

    DEVICE = '''
const root = V.render({ ok: 1, role: 'host', host_supported: 1 });
await flush();
get('mud-usb-adapters').children = [];
rpcReply = { ok: 1, devices: [ { name: 'eth1', carrier: 1, in_lan: 1 }, { name: 'eth2', carrier: 0, in_lan: 0 } ] };
V.refreshAdapters(); await flush();
const texts = [], walk = (e) => { if (e.textContent) texts.push(e.textContent); e.children.forEach(walk); };
walk(get('mud-usb-adapters'));
// add eth2 to the LAN (confirmed): the toast says so in one message
M.confirmBox = () => Promise.resolve(true);
toasts.length = 0;
rpcReply = { ok: 1 };
get('mud-usb-adapters').children[1].children[1].on.click[0]();
await flush(); await flush();
return { html: root.innerHTML, role: text('usb-role-now'), note: text('usb-net-note'), adapters: texts, notes: notes() };'''

    def test_device_renders_in_each_language(self):
        # "Added to LAN" is one message (the fork's partial matching once made it half Chinese, half English)
        want = {
            None: ('USB adapters', 'Host mode', 'USB network mode is unavailable in host mode; host auto-start also '
                   'disables USB network auto-start.', ['eth1', 'Link connected', 'Added to LAN', 'eth2',
                                                        'No link; enable attempted', 'Add to LAN']),
            # tr's catalog is complete but holds the English msgids: only zh_Hans is translated, so tr renders English
            'tr': ('USB adapters', 'Host mode', 'USB network mode is unavailable in host mode; host auto-start also '
                   'disables USB network auto-start.', ['eth1', 'Link connected', 'Added to LAN', 'eth2',
                                                        'No link; enable attempted', 'Add to LAN']),
            'zh_Hans': ('USB \u7f51\u5361', '\u4e3b\u673a\u6a21\u5f0f', None,
                        ['eth1', None, '\u5df2\u6dfb\u52a0\u5230 LAN', 'eth2', None, '\u6dfb\u52a0\u5230 LAN']),
        }
        for lang, (heading, role, note, adapters) in want.items():
            with self.subTest(lang=lang):
                r = self.run_view('device', lang, self.DEVICE)['result']
                self.assertIn(heading, r['html'])
                self.assertEqual(r['role'], role)
                if note:
                    self.assertEqual(r['note'], note)
                self.assertEqual(len(r['adapters']), len(adapters), r['adapters'])
                for got, exp in zip(r['adapters'], adapters):
                    if exp is not None:
                        self.assertEqual(got, exp)
                self.assertEqual(r['notes'][-1], adapters[2])         # the toast after adding: the same message

    SETTINGS = '''
return V.render();'''

    # the Languages page without the pack (a failed install), with it (one running), and the replies of lang_set
    LANGUAGES = '''
V.render({ ok: 1, current: 'en', luci: [ { code: 'tr', name: 'T' } ], extra: { installed: 0 },
           job: { state: 'failed', log: 'no verified file' } });
V.paint({ ok: 1, current: 'de', luci: [], job: { state: 'running' }, extra: { installed: 1, release: 'v1',
          languages: [ { code: 'de', name: 'Deutsch (German)', enabled: 1, panel: 1 },
                       { code: 'ja', name: 'J', enabled: 0, panel: 0 } ] } });
rpcReply = { ok: 0, error: 'Invalid language code' }; await V.set(null, 'enable', 'de'); await flush();
rpcReply = { ok: 1, started: 1 }; await V.set(null, 'install', '', 'release'); await flush();
rpcReply = { ok: 1, job: { state: 'done' }, extra: {} }; timers.splice(0).forEach((f) => f()); await flush(); await flush();
rpcReply = { ok: 1 }; await V.set(null, 'disable', 'ja'); await flush();
return notes();'''

    TTL = '''
V.render({ ok: 1, enabled: 1, value: 64, backend: 'nft', offload: 0, iface: [] });
V.paint({ ok: 1, enabled: 0, value: null, backend: 'tc', offload: 1, iface: [ 'sipa_eth0' ] });
rpcReply = { ok: 0, error: 'Invalid TTL' }; await V.set(null, 64); await flush();
rpcReply = { ok: 1, enabled: 1, value: 65, backend: 'tc', offload: 1, iface: [ 'sipa_eth0' ] };
await V.set(null, 65); await flush(); await flush();
return notes();'''

    # a backend error on each page: (view, body returning what was shown, [(template, error, detail)]); the
    # page shows the error through the catalog, inside its template if any, and the detail after it as data
    BACKEND_ERRORS = [
        ('ttl', """V.render({}); toasts.length = 0;
rpcReply = { ok: 0, error: 'The TTL could not be set', detail: 'tc and nftables' };
await V.set(null, 64); await flush();
return [ notes().pop() ];""", [('Failed: %s', 'The TTL could not be set', 'tc and nftables')]),
        ('home', """V.render(); await flush(); toasts.length = 0;
rpcReply = { ok: 0, op: 'wifi on', error: 'Expected on or off' };
get('mud-btn-wifi').onclick.call(get('mud-btn-wifi')); await flush();
return [ notes().pop() ];""", [('Failed: %s', 'Expected on or off', None)]),
        ('locks', """V.render(); await flush();
V.lastLock = { error: 'Lock cache unavailable' }; V.paint();
V.paintServing({ error: 'Applying network locks: no live signal right now' });
return [ text('lock-nrline'), text('srv-rat') ];""",
         [(None, 'Lock cache unavailable', None), (None, 'Applying network locks: no live signal right now', None)]),
        ('sms', """V.render();
rpcReply = { error: 'mu300-sms is not available (the SMS service is not installed or not running)' };
await V.reload(); await flush();
const convs = html('sms-convs');
M.choiceBox = () => Promise.resolve('local'); toasts.length = 0;
rpcReply = { ok: 0, error: 'Delete failed', detail: 'no message 4' };
V.delMsg('4'); await flush(); await flush();
return [ convs.replace(/<[^>]*>/g, ''), notes().pop() ];""",
         [(None, 'mu300-sms is not available (the SMS service is not installed or not running)', None),
          (None, 'Delete failed', 'no message 4')]),
        # a message whose full text cannot be read says so, as send and delete do (R31: it used to stay silent)
        ('sms', """V.render();
rpcReply = { pages: 1, total: 1, msgs: [ { id: '9', peer: '10086', dir: 'mt', preview: 'x', time: 't9' } ] };
await V.reload(); await flush(); toasts.length = 0;
rpcReply = { ok: 0, error: 'Read failed', detail: 'mu300-sms: no message 9' };
V.open('10086'); await flush(); await flush();
return notes();""", [(None, 'Read failed', 'mu300-sms: no message 9')]),
        ('device', """V.render({ ok: 1, role: 'host', host_supported: 1 }); await flush();
get('mud-usb-adapters').children = [];
rpcReply = { ok: 1, devices: [ { name: 'eth2', carrier: 0, in_lan: 0 } ] };
V.refreshAdapters(); await flush();
M.confirmBox = () => Promise.resolve(true); toasts.length = 0;
rpcReply = { ok: 0, error: 'Not a USB network interface' };
get('mud-usb-adapters').children[0].children[1].on.click[0](); await flush(); await flush();
return [ notes().pop() ];""", [('Add failed: %s', 'Not a USB network interface', None)]),
    ]

    def test_backend_errors_are_shown_through_the_catalogs(self):
        for lang in (None, 'tr', 'zh_Hans'):
            cat = catalog(lang) if lang else {}
            for name, body, shown in self.BACKEND_ERRORS:
                with self.subTest(lang=lang, view=name):
                    want = []
                    for template, error, detail in shown:
                        self.assertIn(error, set(run('extract').stdout.splitlines()))
                        if lang:
                            self.assertIn(error, cat)
                        text = cat.get(error, error) + (' (%s)' % detail if detail else '')
                        want.append(cat.get(template, template).replace('%s', text) if template else text)
                    self.assertEqual(self.run_view(name, lang, body)['result'], want)

    def test_every_view_in_an_unknown_language_is_english_and_catalogued(self):
        # German has no catalog: everything a page shows is English, and every message it used is in both catalogs
        for name in VIEW_NAMES:
            with self.subTest(view=name):
                body = 'await (async function() { %s })(); return shown();' % getattr(self, name.upper())
                self.assert_english_and_catalogued(self.run_view(name, 'de', body))


if __name__ == '__main__':
    unittest.main()
