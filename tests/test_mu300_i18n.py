"""The standalone dashboard follows LuCI's locale and theme tokens."""
import shutil
import subprocess
import unittest
import json
import re
import tempfile
from pathlib import Path

from helpers import TOP


COMMON = TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js'
HOME = TOP / 'openwrt/luci-app-mu300/htdocs/luci-static/resources/view/mu300/home.js'
PACKAGE = TOP / 'openwrt/luci-app-mu300'


@unittest.skipUnless(shutil.which('node'), 'Node.js is needed for LuCI JS smoke tests')
class DashboardI18n(unittest.TestCase):
    def test_package_installs_frontend_and_boot_worker(self):
        makefile = (PACKAGE / 'Makefile').read_text()
        self.assertIn('$(CP) ./htdocs/. $(1)/www/', makefile)
        self.assertIn('$(CP) ./root/. $(1)/', makefile)
        self.assertIn('$(CP) ./lmo/. $(1)/usr/lib/lua/luci/i18n/', makefile)
        self.assertNotIn('uci set luci.languages.zh_cn', makefile)
        self.assertIn('/etc/init.d/unisoc-modem-ui enable', makefile)
        for name in ('home', 'at', 'locks', 'sms', 'settings'):
            self.assertTrue((PACKAGE / f'htdocs/luci-static/resources/view/mu300/{name}.js').is_file())

    def test_global_menu_catalogs_are_complete(self):
        menu = json.loads((PACKAGE / 'root/usr/share/luci/menu.d/luci-app-mu300.json').read_text(encoding='utf-8'))
        titles = {item['title'] for item in menu.values()}
        for lang in ('en', 'tr'):
            po = (PACKAGE / f'po/{lang}/mu300.po').read_text(encoding='utf-8')
            translated = dict(re.findall(r'msgid "([^"]+)"\s+msgstr "([^"]+)"', po))
            self.assertEqual(set(translated), titles)
            self.assertTrue(all(translated.values()))
            self.assertTrue((PACKAGE / f'lmo/mu300.{lang}.lmo').is_file())

    @unittest.skipUnless(shutil.which('po2lmo'), 'po2lmo is needed to verify bundled catalogs')
    def test_global_menu_catalogs_match_po_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lang in ('en', 'tr'):
                output = f'{tmp}/mu300.{lang}.lmo'
                subprocess.run(['po2lmo', str(PACKAGE / f'po/{lang}/mu300.po'), output], check=True)
                self.assertEqual(Path(output).read_bytes(), (PACKAGE / f'lmo/mu300.{lang}.lmo').read_bytes())

    def run_js(self, body):
        harness = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
let lang = 'en', aurora = '', official = 'hsl(0,0%,100%)', selected;
const root = { classList: { remove: () => {}, toggle: (name, value) => { selected = value; } } };
const document = { documentElement: root, body: {}, getElementById: () => ({}), head: { appendChild: () => {} } };
const style = (el) => ({ getPropertyValue: (key) =>
    key === '--surface' ? aurora : key === '--background-color-high' ? official : '' });
const M = new Function('rpc', 'baseclass', 'L', 'document', 'navigator', 'getComputedStyle', src)(
    { declare: () => () => {} }, { extend: (obj) => obj }, { env: { get lang() { return lang; } } },
    document, { language: 'en-US' }, style);
''' + body
        # Pass Unicode source on stdin; Windows node -e can mangle non-ASCII
        # command-line arguments under the active console code page.
        result = subprocess.run(['node', '-', str(COMMON)], input=harness, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_three_dashboard_languages(self):
        self.run_js("""
lang = 'en';
if (M.translate('链路与流量 · 无应答') !== 'Link & traffic · No response') throw Error('English');
lang = 'tr_TR';
if (M.translate('链路与流量 · 无应答') !== 'Bağlantı ve trafik · Yanıt yok') throw Error('Turkish');
lang = 'zh_Hans';
if (M.translate('链路与流量 · 无应答') !== '链路与流量 · 无应答') throw Error('Chinese');
""")

    def test_carrier_names_follow_locale(self):
        self.run_js("""
lang = 'en';
if (M.carrierName({name: '中国联通'}) !== 'China Unicom') throw Error('English carrier name');
if (M.carrierName({plmn: '46001'}) !== 'China Unicom') throw Error('English PLMN fallback');
lang = 'tr';
if (M.carrierName({name: '中国联通'}) !== 'China Unicom') throw Error('Turkish carrier name');
lang = 'zh';
if (M.carrierName({name: '中国联通'}) !== '中国联通') throw Error('Chinese carrier name');
""")

    def test_official_theme_bridge_keeps_aurora_intact(self):
        self.run_js("""
aurora = ''; M.injectCss();
if (selected !== true) throw Error('Bootstrap bridge missing');
M.injectCss();
if (selected !== true) throw Error('Bootstrap bridge lost on next page');
aurora = '#fff'; M.injectCss();
if (selected !== false) throw Error('Aurora must retain its own variables');
""")

    def test_dashboard_static_labels_have_english_and_turkish(self):
        self.run_js("""
const homeSrc = fs.readFileSync(process.argv[2], 'utf8');
const home = new Function('view', 'poll', 'M', homeSrc)(
    { extend: (obj) => obj }, {}, M);
for (const locale of ['en', 'tr']) {
    lang = locale;
    if (/[㐀-鿿]/.test(M.translate('正在后台应用')))
        throw Error('phrase translation failed: ' + M.translate('正在后台应用'));
    const visible = M.translate(home.html().replace(/<[^>]+>/g, ' '));
    if (/[\u3400-\u9fff]/.test(visible)) throw Error(locale + ': untranslated static label: ' + visible.match(/[\u3400-\u9fff]+/)[0]);
}
""".replace('process.argv[2]', repr(str(HOME))))

    def test_menu_dialog_toast_and_each_view_vocabulary(self):
        self.run_js(r"""
const labels = [
    '状态看板', '蜂窝', '网络锁定', '短信', 'AT 终端', '适配设置',
    '应用「网络模式：仅 4G」？', '正在后台应用 NR 频段锁定：n78（SFUN 重启 + 重新驻网，约半分钟）',
    '回读超时，请点「刷新锁定状态」', '开机自动应用已开启',
    '会话历史（点击复用）', '错误：AT 通道正忙，命令未发出',
    '清空本地短信池', '只删本地文件，SIM 上的不动。',
    '删除这条短信', '本地 + SIM', '发送失败：未知错误',
    '收件人：号码，如 10086 或 +86...', '蜂窝逻辑接口',
    '等待 AT 就绪上限（秒）', '留空则从 netifd 自动获取'
];
for (const locale of ['en', 'tr']) {
    lang = locale;
    for (const label of labels) {
        const translated = M.translate(label);
        if (/[㐀-鿿]/.test(translated))
            throw Error(locale + ': untranslated: ' + label + ' -> ' + translated);
    }
}
lang = 'zh';
if (M.translate('删除这条短信') !== '删除这条短信') throw Error('Chinese must remain unchanged');
""")

    def test_other_views_call_localization_without_translating_user_data(self):
        for name in ('at', 'locks', 'sms'):
            source = (PACKAGE / f'htdocs/luci-static/resources/view/mu300/{name}.js').read_text(encoding='utf-8')
            self.assertIn('M.localize(root)', source, name)
        sms = (PACKAGE / 'htdocs/luci-static/resources/view/mu300/sms.js').read_text(encoding='utf-8')
        self.assertIn("(last.preview || '')", sms)
        self.assertIn('bd.textContent = body', sms)
        at = (PACKAGE / 'htdocs/luci-static/resources/view/mu300/at.js').read_text(encoding='utf-8')
        self.assertIn("line('ln-data', l)", at)
        settings = (PACKAGE / 'htdocs/luci-static/resources/view/mu300/settings.js').read_text(encoding='utf-8')
        self.assertIn('M.localizeMenu()', settings)
        self.assertIn("t('适配设置')", settings)

    def test_visible_chinese_literals_have_translations(self):
        literals = []
        for name in ('home', 'at', 'locks', 'sms', 'settings'):
            source = (PACKAGE / f'htdocs/luci-static/resources/view/mu300/{name}.js').read_text(encoding='utf-8')
            for line in source.splitlines():
                stripped = line.lstrip()
                if stripped.startswith(('/*', '*', '//', '<!--')):
                    continue
                code = line.split('/*', 1)[0].split('//', 1)[0]
                literals += re.findall(r"'([^'\\\n]*(?:\\.[^'\\\n]*)*)'", code)
        literals = sorted({s for s in literals if re.search(r'[\u3400-\u9fff]', s)})
        self.run_js(r'''
const literals = %s;
for (const locale of ['en', 'tr']) {
    lang = locale;
    const missing = literals.filter(s => /[\u3400-\u9fff]/.test(M.translate(s)));
    if (missing.length) throw Error(locale + ': ' + JSON.stringify(missing).replace(/[^\x00-\x7f]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0')));
}
''' % json.dumps(literals, ensure_ascii=True))


if __name__ == '__main__':
    unittest.main()
