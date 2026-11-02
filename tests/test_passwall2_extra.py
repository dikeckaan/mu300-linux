"""Optional Passwall2 extra: archive format and core ownership, without network or APK payloads."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest

from helpers import TOP, shells
from test_extra import ExtrasBase

MODULE = TOP / 'tools/passwall2-extra'
spec = importlib.util.spec_from_file_location('passwall2_builder', MODULE / 'build.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class PackagingTests(ExtrasBase):
    def setUp(self):
        super().setUp()
        self.source = self.tmp / 'source'
        self.source.mkdir()
        shutil.copytree(MODULE / 'module', self.source / 'module')
        shutil.copyfile(MODULE / 'LICENSE', self.source / 'LICENSE')
        self.cache = self.tmp / 'cache'
        self.cache.mkdir()
        self.lock = []
        # Opaque APK fixtures: the fake tool only models extract/mkpkg. Real ARM64
        # APK solving/postinsts are recorded separately in the manual validation.
        for name, version, language in [('luci-app-passwall2', '26.10.29-r1', None),
            ('sing-box', '1.14.4-r1', None), ('xray-core', '26.10.21-r1', None),
            ('luci-i18n-passwall2-zh-cn', '26.10.29', 'zh-cn'),
            ('luci-i18n-passwall2-ru', '26.10.29', 'ru')]:
            files = {'usr/lib/lua/luci/passwall2/api.lua': 'local function check_path(app_name)\nend\n'}
            if name in ('sing-box', 'xray-core'):
                core = 'xray' if name == 'xray-core' else name
                files = {'usr/bin/' + core: '#!/bin/sh\necho fixture-core\n'}
            apk = self.cache / (name + '.apk')
            apk.write_text(json.dumps(files))
            entry = {'name': name, 'version': version, 'file': apk.name,
                     'sha256': hashlib.sha256(apk.read_bytes()).hexdigest()}
            if language:
                entry['language'] = language
            self.lock.append(entry)
        (self.source / 'packages.lock.json').write_text(json.dumps({'packages': self.lock}))
        self.config = self.tmp / 'config'
        self.config.write_text(''.join(key + '=y\n' for symbols in builder.CAPS.values() for key, _ in symbols))
        self.tool = self.tmp / 'fake-apk'
        self.tool.write_text('''#!/usr/bin/env python3
import json, pathlib, sys
a = sys.argv[1:]
if 'extract' in a:
    for name, content in json.loads(pathlib.Path(a[-1]).read_text()).items():
        p = pathlib.Path.cwd() / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
elif 'mkpkg' in a:
    pathlib.Path(a[a.index('--output')+1]).write_bytes(b'opaque native metadata fixture')
else:
    raise SystemExit(2)
''')
        self.tool.chmod(0o755)

    def build(self, mode='shared', languages='all'):
        out = self.tmp / (mode + '.tar.gz')
        original = builder.TOP
        try:
            builder.TOP = self.source
            builder.build(self.cache, out, self.tool, self.config, 'dev', languages, mode)
        finally:
            builder.TOP = original
        return out

    def test_both_modes_manifest_and_real_extra_unpack(self):
        for mode in ('shared', 'bundled'):
            path = self.build(mode)
            with tarfile.open(path) as t:
                names = t.getnames()
                self.assertNotIn('./apks/sing-box.apk', names)
                self.assertNotIn('./apks/xray-core.apk', names)
                self.assertEqual('./engines/xray' in names, mode == 'bundled')
                self.assertEqual(t.getmember('./libexec/xray').mode, 0o755)
                self.assertEqual(t.getmember('./libexec/sing-box').mode, 0o755)
                manifest = t.extractfile('./manifest').read().decode().splitlines()
                for line in manifest:
                    sha, name = line.split('  ')
                    self.assertEqual(sha, hashlib.sha256(t.extractfile(name).read()).hexdigest())
                self.assertEqual({line.split('  ')[1] for line in manifest}, set(names) - {'./manifest'})
                self.assertTrue(all(m.uid == m.gid == 0 and m.isfile() for m in t.getmembers()))
            for shell in self.each_shell():
                r = self.up(shell, 'extra_unpack passwall2 "$INPUT" v2026.11.02.99', INPUT=path)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        sums = (self.tmp / 'SHA256SUMS').read_text()
        self.assertIn('  shared.tar.gz\n', sums)
        self.assertIn('  bundled.tar.gz\n', sums)

    def test_language_selection_and_bad_input(self):
        path = self.build(languages='en,zh-cn')
        with tarfile.open(path) as t:
            self.assertEqual(t.extractfile('./languages').read(), b'en\nzh-cn\n')
            self.assertNotIn('./apks/luci-i18n-passwall2-ru.apk', t.getnames())
        with self.assertRaises(ValueError):
            self.build(languages='unsupported')
        (self.cache / 'sing-box.apk').write_bytes(b'changed')
        with self.assertRaises(ValueError):
            self.build()

    def test_packaged_cli_catalog_and_english_fallback(self):
        path = self.build()
        extracted = self.tmp / 'extracted'
        with tarfile.open(path) as t:
            t.extractall(extracted)
        for shell in self.each_shell():
            for lang, expected in [('en', 'run as root'), ('zh_cn', '\u8bf7\u4ee5 root \u8eab\u4efd\u8fd0\u884c')]:
                with self.subTest(shell=shell, lang=lang):
                    r = self.sh(shell, 'd=$EXTRA; . "$d/lib/messages.sh"; '
                                'pw2_msg "run as root"; pw2_msg "unknown message"; '
                                'pw2_zh "Simplified Chinese"',
                                EXTRA=extracted, MU300_PASSWALL2_LANG=lang)
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(r.stdout, expected + '\nunknown message\n'
                                     '\u7b80\u4f53\u4e2d\u6587 (Simplified Chinese)\n')

    def test_inactive_system_hooks_do_not_run_live_apk_and_refuse_orphans(self):
        inactive = self.tmp / 'inactive'
        (inactive / 'etc/config').mkdir(parents=True)
        (inactive / 'etc/openwrt_release').touch()
        d = '/mnt/mu300-disk/extra/passwall2'
        for shell in self.each_shell():
            r = self.script(shell, MODULE / 'module/hooks/link', inactive, MU300_EXTRA_DIR=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            (inactive / 'etc/config/passwall2').write_text("option xray_file '" + d + "/libexec/xray'\n")
            r = self.script(shell, MODULE / 'module/hooks/unlink', inactive, MU300_EXTRA_DIR=d)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('inactive OpenWrt', r.stderr)
            (inactive / 'etc/config/passwall2').write_text("option xray_file '/usr/bin/xray'\n")
            r = self.script(shell, MODULE / 'module/hooks/unlink', inactive, MU300_EXTRA_DIR=d)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.stub('grep', 'exit 2')
            r = self.script(shell, MODULE / 'module/hooks/unlink', inactive, MU300_EXTRA_DIR=d)
            self.assertNotEqual(r.returncode, 0, 'an unreadable inactive config must not be treated as detached')
            (self.stubs / 'grep').unlink()

class SharedCoreTests(unittest.TestCase):
    def setUp(self):
        self.shell = shells()[0]
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.extra = self.root / 'disk/extra/passwall2'
        (self.extra / 'libexec').mkdir(parents=True)
        (self.extra / 'engines').mkdir()
        (self.extra / 'core-versions').write_text('xray 26.10.21\nsing-box 1.14.4\n')
        (self.root / 'bin').mkdir()
        uci = self.root / 'bin/uci'
        uci.write_text('#!/bin/sh\nprintf "%s" "${CUSTOM_CORE:-}"\n')
        uci.chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.root / 'bin') + ':/usr/bin:/bin',
            'MU300_DISK': str(self.root / 'disk'), 'CORE_LIB': str(MODULE / 'module/lib/cores.sh'),
            'D': str(self.extra)}

    def tearDown(self):
        self.tmp.cleanup()

    def core(self, path, name='xray', version=None, tags=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        output = ('Xray ' + (version or '26.10.21') + ' test' if name == 'xray' else
                  'sing-box version ' + (version or '1.14.4') + '\nTags: ' +
                  ('with_quic,with_utls,with_wireguard' if tags else 'with_quic'))
        path.write_text('#!/bin/sh\ncat <<\'CORE\'\n' + output + '\nCORE\n')
        path.chmod(0o755)
        return path

    def pick(self, name='xray', custom=''):
        return subprocess.run(self.shell + ['-c', 'd=$D; . "$CORE_LIB"; pw2_pick "$CORE"'],
            env={**self.env, 'CORE': name, 'CUSTOM_CORE': str(custom)}, capture_output=True, text=True)

    def test_shared_module_preferred_over_bundled_fallback(self):
        shared = self.core(self.root / 'disk/extra/vpn-xray/bin/xray')
        self.core(self.extra / 'engines/xray')
        self.assertEqual(self.pick().stdout.strip(), str(shared))

    def test_legacy_module_and_existing_custom_path(self):
        legacy = self.core(self.root / 'disk/extra/vpn/bin/xray')
        self.assertEqual(self.pick().stdout.strip(), str(legacy))
        custom = self.core(self.root / 'custom/xray')
        self.assertEqual(self.pick(custom=custom).stdout.strip(), str(custom))

    def test_incompatible_shared_core_uses_private_fallback(self):
        self.core(self.root / 'disk/extra/vpn-xray/bin/xray', version='26.9.1')
        fallback = self.core(self.extra / 'engines/xray')
        self.assertEqual(self.pick().stdout.strip(), str(fallback))

    def test_missing_core_fails_without_installing_or_removing_anything(self):
        self.assertNotEqual(self.pick().returncode, 0)

    def test_singbox_version_and_tags_must_match(self):
        shared = self.root / 'disk/extra/vpn-singbox/bin/sing-box'
        self.core(shared, 'sing-box', '1.14.40')
        self.assertNotEqual(self.pick('sing-box').returncode, 0)
        self.core(shared, 'sing-box', tags=False)
        self.assertNotEqual(self.pick('sing-box').returncode, 0)
        self.core(shared, 'sing-box')
        self.assertEqual(self.pick('sing-box').stdout.strip(), str(shared))

    def test_provider_upgrade_is_rechecked_on_each_launch(self):
        shared = self.core(self.root / 'disk/extra/vpn-xray/bin/xray')
        self.assertEqual(self.pick().returncode, 0)
        self.core(shared, version='27.1.1')
        self.assertNotEqual(self.pick().returncode, 0)
