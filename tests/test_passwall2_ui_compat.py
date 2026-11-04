"""Detection must handle native built-ins/shared cores without masking missing support."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from helpers import TOP, shells

LIB = TOP / 'tools/passwall2-extra/module/lib'
COMPONENTS = '''---- Check the transparent proxy component
local handle = io.popen("lsmod")
local mods = ""
if handle then
    mods = handle:read("*a") or ""
    handle:close()
end
if mods:find("nft_tproxy") then return true end
'''
STATUS = '''function index_status()
    local e = {}
    e["global_status"] = luci.sys.call("/bin/busybox top -bn1 | grep '%s/bin/'" % api.TMP_PATH) == 0
    http_write_json(e)
end
'''


class UiCompatTests(unittest.TestCase):
    def patch(self, kind, text):
        return subprocess.run(['awk', '-v', 'kind=' + kind, '-f', str(LIB / 'ui-compat.awk')],
                              input=text, text=True, capture_output=True, check=False)

    def test_preserves_original_checks_and_is_idempotent(self):
        for kind, text in [('components', COMPONENTS), ('status', STATUS)]:
            with self.subTest(kind=kind):
                r = self.patch(kind, '-- custom extension stays\n' + text)
                self.assertEqual(r.returncode, 0, r.stderr)
                self.assertIn('-- custom extension stays', r.stdout)
                self.assertIn('luci.passwall2.mu300_compat', r.stdout)
                self.assertIn('lsmod' if kind == 'components' else 'top -bn1', r.stdout)
                again = self.patch(kind, r.stdout)
                self.assertEqual(again.returncode, 0, again.stderr)
                self.assertEqual(again.stdout, r.stdout)

    def test_unsupported_or_ambiguous_layout_is_refused(self):
        for kind, text in [('components', ''), ('status', 'return {}'),
                           ('components', COMPONENTS * 2), ('status', STATUS * 2)]:
            r = self.patch(kind, text)
            self.assertNotEqual(r.returncode, 0)
            self.assertEqual(r.stdout, '')

    def test_failure_leaves_all_original_files_untouched(self):
        for shell in shells():
            with self.subTest(shell=shell), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                paths = {
                    'usr/lib/lua/luci/model/cbi/passwall2/client/global.lua': COMPONENTS,
                    'usr/lib/lua/luci/model/cbi/passwall2/client/other.lua': 'unsupported layout\n',
                    'usr/lib/lua/luci/controller/passwall2.lua': STATUS,
                }
                for name, text in paths.items():
                    p = root / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_text(text)
                fakebin = root / 'bin'
                fakebin.mkdir()
                # Parsing is validated with real ARM64 Lua in the runtime test.
                (fakebin / 'lua').write_text('#!/bin/sh\nexit 0\n')
                (fakebin / 'lua').chmod(0o755)
                env = {**os.environ, 'PATH': str(fakebin) + ':' + os.environ['PATH'],
                       'EXTRA': str(LIB.parent), 'ROOT': str(root)}
                r = subprocess.run(shell + ['-c', 'd=$EXTRA; . "$d/lib/ui-compat.sh"; pw2_ui_install "$ROOT"'],
                                   env=env, capture_output=True, text=True)
                self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
                for name, text in paths.items():
                    self.assertEqual((root / name).read_text(), text)
                self.assertEqual(list(root.rglob('*.mu300-new')), [])


if __name__ == '__main__':
    unittest.main()
