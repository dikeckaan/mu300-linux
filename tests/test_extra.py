"""Extras: optional components (the VPN engines) that are not part of the images and live on the Linux partition
(MU300_DISK/extra/<name>). mu300-update installs and updates them (sourced with MU300_LIB=1 against a fake partition),
mu300-extra is the command, and both systems' boot runs `mu300-extra link`."""
import hashlib
import io
import json
import os
import shutil
import tarfile
import unittest

from helpers import BIN, ShellTest

ENGINES = ('xray', 'hev-socks5-tunnel', 'sing-box')


def extra_tarball(path, name='vpn', release='v2026.10.10', bins=ENGINES, components='xray 26.3.27\n'):
    with tarfile.open(path, 'w:gz') as t:
        def add(fn, data, mode=0o644):
            ti = tarfile.TarInfo(fn)
            ti.size, ti.mode = len(data), mode
            t.addfile(ti, io.BytesIO(data))
        if name is not None:
            add('./name', (name + '\n').encode())
        add('./release', (release + '\n').encode())
        add('./components', components.encode())
        for b in bins:
            add(f'./bin/{b}', f'#!/bin/sh\necho {b} {release}\n'.encode(), 0o755)
    return path


class ExtrasBase(ShellTest):
    def setUp(self):
        super().setUp()
        self.disk = self.tmp / 'disk'
        for os_ in ('ubuntu', 'openwrt'):
            (self.disk / os_ / 'etc/mu300').mkdir(parents=True)
        self.root = self.tmp / 'root'
        (self.root / 'run/mu300').mkdir(parents=True)
        (self.root / 'run/mu300/device').write_text('f50\n')
        self.links = self.tmp / 'links'
        self.links.mkdir()
        self.stub('id', 'echo 0')

    def up(self, shell, code, **env):
        return self.sh(shell, f'. "{BIN}/mu300-update"; {code}', MU300_LIB=1, MU300_DISK=self.disk, MU300_BIN=BIN,
                       MU300_SYSROOT=self.root, **env)

    def ex(self, shell, *args, **env):
        e = dict(MU300_DISK=self.disk, MU300_BIN=BIN, MU300_SYSROOT=self.root, MU300_LINKDIR=self.links,
                 MU300_OPT=BIN.parent, MU300_FETCH_DELAY=0)
        e.update(env)
        return self.script(shell, BIN / 'mu300-extra', *args, **e)

    def baked(self, os_, enabled):
        """an installed system from before extras: engines in its image, and vpn.conf ENABLE=1 or 0"""
        b = self.disk / os_ / 'opt/mu300/bin'
        b.mkdir(parents=True, exist_ok=True)
        for e in ENGINES:
            (b / e).write_text(f'#!/bin/sh\necho baked {e}\n')
            (b / e).chmod(0o755)
        (self.disk / os_ / 'etc/mu300/vpn.conf').write_text(f'ENABLE={enabled}\nVLESS_URI="vless://x@y"\n')
        (self.disk / os_ / 'etc/mu300/image-version').write_text('v2026.10.06\n')

    def vpn(self):
        return self.disk / 'extra' / 'vpn'


class Extras(ExtrasBase):
    # ---- mu300-update: the core -----------------------------------------------------------------------------
    def test_unpack_installs_and_replaces(self):
        for shell in self.each_shell():
            old = extra_tarball(self.tmp / 'old.tar.gz', release='v2026.10.01')
            new = extra_tarball(self.tmp / 'new.tar.gz', release='v2026.10.10')
            r = self.up(shell, f'extra_unpack vpn "{old}" && extra_release vpn && extra_installed')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ['v2026.10.01', 'vpn'])
            r = self.up(shell, f'extra_unpack vpn "{new}" && extra_release vpn')
            self.assertEqual(r.stdout.split(), ['v2026.10.10'])
            self.assertTrue(os.access(self.vpn() / 'bin/xray', os.X_OK))
            # nothing half-done is left next to it
            self.assertEqual(sorted(p.name for p in (self.disk / 'extra').iterdir()), ['vpn'])

    def test_unpack_refuses_the_wrong_payload_and_keeps_the_old(self):
        for shell in self.each_shell():
            good = extra_tarball(self.tmp / 'good.tar.gz', release='v1')
            self.up(shell, f'extra_unpack vpn "{good}"')
            for bad in (extra_tarball(self.tmp / 'other.tar.gz', name='other'),
                        extra_tarball(self.tmp / 'noname.tar.gz', name=None),
                        extra_tarball(self.tmp / 'nobin.tar.gz', bins=())):
                r = self.up(shell, f'extra_unpack vpn "{bad}"; echo "rc=$?"')
                self.assertIn('rc=1', r.stdout, bad.name)
                self.assertEqual((self.vpn() / 'release').read_text().strip(), 'v1', bad.name)
            junk = self.tmp / 'junk.tar.gz'
            junk.write_bytes(b'not a tarball')
            r = self.up(shell, f'extra_unpack vpn "{junk}"; echo "rc=$?"')
            self.assertIn('rc=1', r.stdout)
            r = self.up(shell, f'extra_unpack ../x "{good}"; echo "rc=$?"')
            self.assertIn('rc=1', r.stdout)
            self.assertEqual(sorted(p.name for p in (self.disk / 'extra').iterdir()), ['vpn'])

    def test_adopt_takes_the_engines_of_an_older_image(self):
        for shell in self.each_shell():
            self.baked('ubuntu', 1)
            r = self.up(shell, f'extra_adopt vpn "{self.disk}/ubuntu"; echo "rc=$?"; extra_release vpn')
            self.assertEqual(r.stdout.split()[-2:], ['rc=0', 'v2026.10.06'], r.stderr)
            for e in ENGINES:
                self.assertTrue(os.access(self.vpn() / 'bin' / e, os.X_OK), e)
            # a root without engines has nothing to give
            r = self.up(shell, f'rm -rf "{self.disk}/extra"; extra_adopt vpn "{self.disk}/openwrt"; echo "rc=$?"')
            self.assertIn('rc=1', r.stdout)
            self.assertFalse(self.vpn().exists())

    def test_which_extras_an_update_fetches(self):
        cases = [
            # (installed release or None, ubuntu ENABLE, systems updated, wanted)
            (None, None, 'ubuntu', []),
            (None, 0, 'ubuntu', []),
            (None, 1, 'ubuntu', ['vpn']),             # uses the VPN with the engines of its image
            (None, 1, 'openwrt', []),                 # the system that uses it is not being updated
            ('v2026.10.01', None, 'ubuntu', ['vpn']),  # installed: follows the release
            ('v2026.10.10', 1, 'ubuntu', []),          # already this release's
        ]
        for shell in self.each_shell():
            for inst, enable, todo, want in cases:
                (self.disk / 'ubuntu/etc/mu300/vpn.conf').unlink(missing_ok=True)
                if enable is not None:
                    (self.disk / 'ubuntu/etc/mu300/vpn.conf').write_text(f'ENABLE={enable}\n')
                self.up(shell, f'rm -rf "{self.disk}/extra"')
                if inst:
                    self.up(shell, f'extra_unpack vpn "{extra_tarball(self.tmp / "i.tar.gz", release=inst)}"')
                r = self.up(shell, f'extras_to_fetch v2026.10.10 "{todo}"')
                self.assertEqual(r.stdout.split(), want, (inst, enable, todo, r.stderr))

    def test_update_keeps_a_configured_vpn_working(self):
        # the system was updated to an image without engines; the release's extra goes in, and when that fails the
        # engines of the image it replaced are taken over
        for shell in self.each_shell():
            for fetched in (True, False):
                self.up(shell, f'rm -rf "{self.disk}/extra" "{self.disk}/ubuntu.old"')
                self.baked('ubuntu', 1)
                os.rename(self.disk / 'ubuntu', self.disk / 'ubuntu.old')
                (self.disk / 'ubuntu/etc/mu300').mkdir(parents=True)
                (self.disk / 'ubuntu/etc/mu300/vpn.conf').write_text('ENABLE=1\n')
                stage = self.disk / '.mu300-update'
                stage.mkdir(exist_ok=True)
                if fetched:
                    extra_tarball(stage / 'mu300-extra-vpn.tar.gz', release='v2026.10.10')
                got = 'vpn' if fetched else ''
                r = self.up(shell, f'extras_install v2026.10.10 "ubuntu" "{got}"; echo "rc=$?"; extra_release vpn')
                self.assertEqual(r.stdout.split()[-2:], ['rc=0', 'v2026.10.10' if fetched else 'v2026.10.06'],
                                 (fetched, r.stdout, r.stderr))
                self.assertTrue(os.access(self.vpn() / 'bin/xray', os.X_OK))
                self.assertFalse((stage / 'mu300-extra-vpn.tar.gz').exists())

    def test_fetch_verified_takes_another_server(self):
        self.stub('curl', 'for a; do last=$a; done; echo "$last" >> "$STUBLOG/urls"; '
                          'case $last in */SHA256SUMS) echo "0000  x" ;; esac; exit 0')
        for shell in self.each_shell():
            (self.tmp / 'urls').unlink(missing_ok=True)
            self.up(shell, 'fetch_verified v1 x >/dev/null 2>&1', MU300_RELEASE_URL='http://10.0.0.2:8000/rel')
            urls = (self.tmp / 'urls').read_text().split()
            self.assertEqual(urls[0], 'http://10.0.0.2:8000/rel/SHA256SUMS')

    # ---- mu300-extra ---------------------------------------------------------------------------------------
    def serve(self, release='v2026.10.10', assets=None):
        """a release on a 'server': a directory curl (stubbed) reads from, with its SHA256SUMS"""
        d = self.tmp / 'server' / release
        d.mkdir(parents=True, exist_ok=True)
        if assets is None:
            assets = {'mu300-extra-vpn.tar.gz': extra_tarball(self.tmp / 'payload.tar.gz', release=release)}
        sums = []
        for name, src in assets.items():
            data = src.read_bytes()
            (d / name).write_bytes(data)
            sums.append(f'{hashlib.sha256(data).hexdigest()}  {name}')
        (d / 'SHA256SUMS').write_text('\n'.join(sums) + '\n')
        # curl -o OUT URL or curl URL (stdout); the URL's last two parts name the release and the file
        self.stub('curl', f'out=; url=; while [ $# -gt 0 ]; do case $1 in -o) out=$2; shift ;; -*) ;; *) url=$1 ;; esac; '
                          f'shift; done; echo "$url" >> "$STUBLOG/urls"; f=${{url##*/}}; r=${{url%/*}}; r=${{r##*/}}; '
                          f'case $url in */releases/latest) echo \'"tag_name": "v2026.10.10"\'; exit 0 ;; esac; '
                          f'src="{self.tmp}/server/$r/$f"; [ -f "$src" ] || exit 22; '
                          f'if [ -n "$out" ]; then cat "$src" > "$out"; else cat "$src"; fi')
        return d

    def test_install_from_the_release_of_the_system(self):
        self.serve('v2026.10.10')
        for shell in self.each_shell():
            self.up(shell, f'rm -rf "{self.disk}/extra"')
            for os_ in ('ubuntu', 'openwrt'):
                (self.disk / os_ / 'etc/mu300/image-version').write_text('v2026.10.10\n')
            (self.root / 'etc/mu300').mkdir(parents=True, exist_ok=True)
            (self.root / 'etc/mu300/image-version').write_text('v2026.10.10\n')
            r = self.ex(shell, 'install', 'vpn')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((self.vpn() / 'release').read_text().strip(), 'v2026.10.10')
            self.assertIn('/v2026.10.10/mu300-extra-vpn.tar.gz', (self.tmp / 'urls').read_text())
            # the commands are on the PATH
            self.assertEqual(os.readlink(self.links / 'xray'), str(self.vpn() / 'bin/xray'))
            st = self.ex(shell, 'status')
            self.assertIn('vpn', st.stdout)
            self.assertIn('v2026.10.10', st.stdout)
            # the download is not left behind
            self.assertFalse((self.disk / '.mu300-extra').exists())

    def test_install_falls_back_to_the_newest_release(self):
        # a system from before extras (v2026.10.06 has no mu300-extra-vpn.tar.gz) takes the newest release's
        other = self.tmp / 'other'
        other.write_text('x')
        self.serve('v2026.10.06', assets={'mu300-update': other})
        self.serve('v2026.10.10')
        (self.root / 'etc/mu300').mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/mu300/image-version').write_text('v2026.10.06\n')
        for shell in self.each_shell():
            self.up(shell, f'rm -rf "{self.disk}/extra"')
            r = self.ex(shell, 'install', 'vpn')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((self.vpn() / 'release').read_text().strip(), 'v2026.10.10')

    def test_install_refuses_a_bad_checksum(self):
        d = self.serve('v2026.10.10')
        (d / 'mu300-extra-vpn.tar.gz').write_bytes(b'tampered')
        (self.root / 'etc/mu300').mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/mu300/image-version').write_text('v2026.10.10\n')
        for shell in self.each_shell():
            r = self.ex(shell, 'install', 'vpn', MU300_RELEASE='v2026.10.10')
            self.assertNotEqual(r.returncode, 0)
            self.assertFalse(self.vpn().exists())

    def test_install_from_a_local_file_and_remove(self):
        f = extra_tarball(self.tmp / 'local.tar.gz', release='dev')
        for shell in self.each_shell():
            r = self.ex(shell, 'install', 'vpn', MU300_EXTRA_FILE=f)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.path.islink(self.links / 'sing-box'))
            # a file of the user's own with the same name is never replaced
            (self.links / 'hev-socks5-tunnel').unlink()
            (self.links / 'hev-socks5-tunnel').write_text('mine')
            r = self.ex(shell, 'remove', 'vpn')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(self.vpn().exists())
            self.assertFalse(os.path.lexists(self.links / 'sing-box'))
            self.assertEqual((self.links / 'hev-socks5-tunnel').read_text(), 'mine')
            (self.links / 'hev-socks5-tunnel').unlink()

    def test_install_on_a_disk_with_only_openwrt_luci(self):
        # the third system alone is a mounted Linux partition too
        f = extra_tarball(self.tmp / 'local.tar.gz', release='dev')
        for os_ in ('ubuntu', 'openwrt'):
            shutil.rmtree(self.disk / os_)
        (self.disk / 'openwrt-luci/etc/mu300').mkdir(parents=True)
        for shell in self.each_shell():
            r = self.ex(shell, 'install', 'vpn', MU300_EXTRA_FILE=f)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_remove_refuses_while_the_vpn_is_on(self):
        f = extra_tarball(self.tmp / 'local.tar.gz', release='dev')
        (self.root / 'etc/mu300').mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/mu300/vpn.conf').write_text('ENABLE=1\n')
        for shell in self.each_shell():
            r = self.ex(shell, 'install', 'vpn', MU300_EXTRA_FILE=f)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = self.ex(shell, 'remove', 'vpn')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('--force', r.stderr)
            self.assertTrue(self.vpn().exists())
            r = self.ex(shell, 'remove', 'vpn', '--force')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(self.vpn().exists())

    def test_a_swap_cut_off_between_its_renames_is_recovered(self):
        f = extra_tarball(self.tmp / 'local.tar.gz', release='dev')
        for shell in self.each_shell():
            r = self.up(shell, f'extra_unpack vpn "{f}"')
            self.assertEqual(r.returncode, 0, r.stderr)
            # cut off after "vpn -> .vpn.old": the next swap (here one that fails) must not throw the old one away
            os.rename(self.vpn(), self.vpn().parent / '.vpn.old')
            r = self.up(shell, f'extra_put vpn "{self.tmp}/nosuch"')
            self.assertNotEqual(r.returncode, 0)
            self.assertTrue((self.vpn() / 'bin/xray').exists(), shell)
            shutil.rmtree(self.vpn())

    def test_unknown_and_usage(self):
        for shell in self.each_shell():
            r = self.ex(shell, 'install', 'nosuch')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('nosuch', r.stderr)
            r = self.ex(shell, 'frobnicate')
            self.assertEqual(r.returncode, 2)
            r = self.ex(shell, 'list')
            self.assertEqual(r.returncode, 0)
            self.assertIn('vpn', r.stdout)
            self.assertIn('not installed', r.stdout)

    def test_link_puts_the_system_commands_on_the_path(self):
        for shell in self.each_shell():
            for p in self.links.iterdir():
                p.unlink()
            # a link left by an extra that is gone, and one of the user's that points somewhere else
            os.symlink(self.disk / 'extra/gone/bin/tool', self.links / 'tool')
            os.symlink('/somewhere/else', self.links / 'mine')
            r = self.ex(shell, 'link')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(os.readlink(self.links / 'mu300-ussd'), str(BIN / 'mu300-ussd'))
            self.assertEqual(os.readlink(self.links / 'mu300-extra'), str(BIN / 'mu300-extra'))
            self.assertFalse(os.path.lexists(self.links / 'tool'))
            self.assertTrue(os.path.lexists(self.links / 'mine'))

    def test_adopt_command(self):
        for shell in self.each_shell():
            self.up(shell, f'rm -rf "{self.disk}/extra" "{self.disk}/ubuntu.old"')
            self.baked('ubuntu', 1)
            os.rename(self.disk / 'ubuntu', self.disk / 'ubuntu.old')
            (self.disk / 'ubuntu/etc/mu300').mkdir(parents=True)
            r = self.ex(shell, 'adopt', 'vpn', MU300_RUNNING_OS='ubuntu')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertTrue(os.access(self.vpn() / 'bin/xray', os.X_OK))
            # nothing to take: fails, quietly enough for mu300-vpn to try the download next
            self.up(shell, f'rm -rf "{self.disk}/extra" "{self.disk}/ubuntu.old"')
            r = self.ex(shell, 'adopt', 'vpn', MU300_RUNNING_OS='ubuntu')
            self.assertNotEqual(r.returncode, 0)
            import shutil
            shutil.rmtree(self.disk / 'ubuntu')
            (self.disk / 'ubuntu/etc/mu300').mkdir(parents=True)



LANGS = {'de': 'Deutsch (German)', 'pt_br': 'Português do Brasil (Brazilian Portuguese)', 'ja': '日本語 (Japanese)'}
LMOS = ('base.de.lmo', 'firewall.de.lmo', 'mu300.de.lmo', 'base.pt-br.lmo', 'base.ja.lmo', 'mu300.ja.lmo')


def lang_tarball(path, release='v2026.10.10', langs=None, lmos=LMOS, extra=(), lines=None, manifest=True,
                 tamper=None):
    """the lang extra: ./name ./release ./components ./languages ./manifest ./i18n/*.lmo; EXTRA: (name, data, type)
    more; TAMPER: a file whose bytes differ from what the manifest says"""
    langs = LANGS if langs is None else langs
    text = lines if lines is not None else ''.join(f'{k}\t{v}\n' for k, v in langs.items())
    files = {'./name': b'lang\n', './release': (release + '\n').encode(), './components': b'luci-i18n-base-de 26.275\n',
             './languages': text.encode()}
    files.update({f'./i18n/{n}': f'lmo {n} {release}'.encode() for n in lmos})
    man = ''.join(f'{hashlib.sha256(d).hexdigest()}  {n}\n' for n, d in sorted(files.items()))
    if tamper:
        files[tamper] = b'other bytes'
    with tarfile.open(path, 'w:gz') as t:
        def add(fn, data=b'', typ=tarfile.REGTYPE, link=''):
            ti = tarfile.TarInfo(fn)
            ti.type, ti.linkname = typ, link
            ti.size = len(data) if typ == tarfile.REGTYPE else 0
            ti.mode = 0o755 if typ == tarfile.DIRTYPE else 0o644
            t.addfile(ti, io.BytesIO(data) if typ == tarfile.REGTYPE else None)
        for n in ('./name', './release', './components', './languages'):
            add(n, files[n])
        if manifest:
            add('./manifest', man.encode())
        add('./i18n', typ=tarfile.DIRTYPE)
        for n in lmos:
            add(f'./i18n/{n}', files[f'./i18n/{n}'])
        for e in extra:
            add(*e)
    return path


# uci as far as mu300-extra uses it, on a JSON file of "config.section[.option]" -> value
UCI = r"""
import json, os, sys
db = os.environ['UCI_DB']
d = json.load(open(db)) if os.path.exists(db) else {}
a = [x for x in sys.argv[1:] if x != '-q']
if a[:1] == ['-c']:
    a = a[2:]
with open(os.environ['STUBLOG'] + '/uci.log', 'a') as log:
    log.write(' '.join(a) + '\n')
cmd, rest = a[0], a[1:]
if cmd == 'get':
    if rest[0] not in d:
        sys.exit(1)
    print(d[rest[0]])
elif cmd == 'set':
    k, v = rest[0].split('=', 1)
    if k.count('.') == 2 and k.rsplit('.', 1)[0] not in d:
        sys.exit(1)
    d[k] = v
elif cmd == 'delete':
    d = {k: v for k, v in d.items() if k != rest[0] and not k.startswith(rest[0] + '.')}
elif cmd == 'show':
    for k, v in sorted(d.items()):
        if k == rest[0] or k.startswith(rest[0] + '.'):
            print(f"{k}='{v}'" if k.count('.') == 2 else f'{k}={v}')
elif cmd == 'commit':
    open(os.environ['STUBLOG'] + '/commits', 'a').write(rest[0] + '\n')
json.dump(d, open(db, 'w'))
"""


class LangExtra(ExtrasBase):
    """the lang extra: LuCI's and the panel's catalogs in many languages, linked into LuCI and registered in
    luci.languages by mu300-extra (install, link at boot, lang enable/disable, remove)"""

    def setUp(self):
        super().setUp()
        (self.root / 'etc/openwrt_release').parent.mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/openwrt_release').write_text("DISTRIB_ID='OpenWrt'\n")
        self.i18n = self.root / 'usr/lib/lua/luci/i18n'
        self.i18n.mkdir(parents=True)
        for n in ('base.tr.lmo', 'mu300.tr.lmo', 'base.zh-cn.lmo'):
            (self.i18n / n).write_text('image')
        (self.stubs / 'uci.py').write_text(UCI)
        self.stub('uci', f'exec python3 "{self.stubs}/uci.py" "$@"')
        self.reset_uci()
        self.file = lang_tarball(self.tmp / 'mu300-extra-lang.tar.gz')
        self.secret = self.tmp / 'secret'
        self.secret.write_text('root:x:0')

    def reset_uci(self, lang='en'):
        (self.tmp / 'uci.json').write_text(json.dumps({
            'luci.main': 'core', 'luci.main.lang': lang, 'luci.languages': 'internal',
            'luci.languages.tr': 'Türkçe (Turkish)', 'luci.languages.zh_cn': 'Chinese'}))

    def ex(self, shell, *args, **env):
        return super().ex(shell, *args, UCI_DB=self.tmp / 'uci.json', **env)

    def uci(self):
        d = json.loads((self.tmp / 'uci.json').read_text())
        return {k.split('.')[-1]: v for k, v in d.items() if k.startswith('luci.languages.')}, d.get('luci.main.lang')

    def lang(self):
        return self.disk / 'extra' / 'lang'

    def clean(self, shell):
        self.up(shell, f'rm -rf "{self.disk}/extra"')
        (self.root / 'etc/mu300/languages').unlink(missing_ok=True)
        for p in self.i18n.iterdir():
            if p.is_symlink():
                p.unlink()
        self.reset_uci()

    def test_unpack_takes_a_lang_extra_and_nothing_else(self):
        bad = [
            ('link', dict(extra=[('./i18n/base.fr.lmo', b'', tarfile.SYMTYPE, '/etc/shadow')])),
            ('outside', dict(extra=[('./i18n/../../x.lmo', b'x')])),
            ('program', dict(extra=[('./bin/sh', b'#!/bin/sh\n')])),
            ('odd name', dict(extra=[('./i18n/base.de.lmo.sh', b'x')])),
            ('no catalogs', dict(lmos=())),
            ('quote in a name', dict(lines="de\tDeutsch' (German)\n")),
            ('bad code', dict(lines='de;rm\tDeutsch (German)\n')),
            ('no list', dict(lines='')),
            ('absolute', dict(extra=[('/etc/cron.d/x', b'x')])),
            ('hard link', dict(extra=[('./i18n/base.fr.lmo', b'', tarfile.LNKTYPE, './name')])),
            ('device', dict(extra=[('./i18n/base.fr.lmo', b'', tarfile.CHRTYPE)])),
            ('dir link', dict(extra=[('./i18n/x', b'', tarfile.SYMTYPE, '/etc')])),
            ('hard link outside', dict(extra=[('./i18n/base.fr.lmo', b'', tarfile.LNKTYPE, str(self.secret))])),
            ('newline name', dict(extra=[('./i18n/base.fr.lmo\n./i18n/base.it.lmo', b'x')])),
            ('dotdot inside', dict(extra=[('./i18n/../../escaped.lmo', b'x')])),
            ('fifo', dict(extra=[('./i18n/base.fr.lmo', b'', tarfile.FIFOTYPE)])),
            ('markup in a name', dict(lines='de\t<img src=x onerror=alert(1)>\n')),
            ('ampersand in a name', dict(lines='de\tA &amp; B\n')),
            ('markup as the release', dict(release='<img src=x onerror=alert(1)>')),
            ('a catalog that is a directory', dict(extra=[('./i18n/base.fr.lmo', b'', tarfile.DIRTYPE)])),
            ('a catalog the manifest does not list', dict(extra=[('./i18n/base.fr.lmo', b'x')])),
            ('a catalog with other bytes than the manifest says', dict(tamper='./i18n/mu300.de.lmo')),
            ('no manifest', dict(manifest=False)),
        ]
        for shell in self.each_shell():
            self.clean(shell)
            (self.tmp / 'outside').mkdir(exist_ok=True)
            r = self.up(shell, f'extra_unpack lang "{self.file}" && extra_release lang && extra_installed')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.split(), ['v2026.10.10', 'lang'])
            for what, kw in bad:
                f = lang_tarball(self.tmp / 'bad.tar.gz', **dict(dict(release='v9'), **kw))
                r = self.up(shell, f'extra_unpack lang "{f}"; echo "rc=$?"')
                self.assertIn('rc=1', r.stdout, (shell, what))
                self.assertEqual((self.lang() / 'release').read_text().strip(), 'v2026.10.10', (shell, what))
            self.assertEqual(sorted(p.name for p in (self.disk / 'extra').iterdir()), ['lang'])
            # nothing was written outside the extra, and the secret has one name
            self.assertEqual(list((self.tmp / 'outside').iterdir()), [], shell)
            self.assertEqual(os.stat(self.secret).st_nlink, 1, shell)
            self.assertFalse((self.disk / 'escaped.lmo').exists())

    def test_a_directory_swapped_for_a_link_writes_nothing_outside(self):
        # ./i18n as a link to a directory outside, then a catalog written "into" it: refused before unpacking, and
        # nothing lands outside (a link and a file in the vpn extra, the same)
        for shell in self.each_shell():
            self.clean(shell)
            out = self.tmp / 'outside'
            out.mkdir(exist_ok=True)
            for name in ('lang', 'vpn'):
                f = self.tmp / f'swap-{name}.tar.gz'
                with tarfile.open(f, 'w:gz') as t:
                    for fn, data, typ, link in (('./name', name.encode() + b'\n', tarfile.REGTYPE, ''),
                                                ('./release', b'v9\n', tarfile.REGTYPE, ''),
                                                ('./i18n' if name == 'lang' else './bin', b'', tarfile.SYMTYPE, str(out)),
                                                ('./i18n/base.de.lmo' if name == 'lang' else './bin/xray', b'x',
                                                 tarfile.REGTYPE, '')):
                        ti = tarfile.TarInfo(fn)
                        ti.type, ti.linkname, ti.size, ti.mode = typ, link, len(data) if typ == tarfile.REGTYPE else 0, 0o755
                        t.addfile(ti, io.BytesIO(data) if typ == tarfile.REGTYPE else None)
                r = self.up(shell, f'extra_unpack {name} "{f}"; echo "rc=$?"')
                self.assertIn('rc=1', r.stdout, (shell, name))
                self.assertEqual(list(out.iterdir()), [], (shell, name))
                self.assertFalse((self.disk / 'extra' / name).exists(), (shell, name))

    def test_a_vpn_extra_with_a_manifest_is_held_to_it(self):
        # the vpn extra's manifest (tools/make-extra.sh writes one) is checked as well; one without (older releases)
        # is still taken
        for shell in self.each_shell():
            self.clean(shell)
            for manifest, ok in (('good', True), ('bad', False), (None, True)):
                f = self.tmp / 'vpn.tar.gz'
                files = {'./name': b'vpn\n', './release': b'v1\n', './bin/xray': b'#!/bin/sh\n'}
                with tarfile.open(f, 'w:gz') as t:
                    for n, d in list(files.items()) + ([('./manifest', ''.join(
                            f'{hashlib.sha256(d if manifest == "good" else b"x").hexdigest()}  {n}\n'
                            for n, d in sorted(files.items())).encode())] if manifest else []):
                        ti = tarfile.TarInfo(n)
                        ti.size, ti.mode = len(d), 0o755
                        t.addfile(ti, io.BytesIO(d))
                self.up(shell, f'rm -rf "{self.disk}/extra/vpn"')
                r = self.up(shell, f'extra_unpack vpn "{f}"; echo "rc=$?"')
                self.assertIn('rc=0' if ok else 'rc=1', r.stdout, (shell, manifest, r.stderr))
                self.assertEqual((self.disk / 'extra' / 'vpn').exists(), ok, (shell, manifest))

    def test_a_pack_that_unpacks_too_large_is_refused(self):
        # 40 MB of zeros compress to about 40 kB: refused before anything is unpacked
        for shell in self.each_shell():
            self.clean(shell)
            f = lang_tarball(self.tmp / 'bomb.tar.gz', extra=[('./i18n/base.xx.lmo', bytes(40 << 20))])
            self.assertLess(f.stat().st_size, 1 << 20)
            r = self.up(shell, f'extra_unpack lang "{f}"; echo "rc=$?"')
            self.assertIn('rc=1', r.stdout, shell)
            self.assertIn('too large', r.stderr)
            self.assertFalse((self.disk / 'extra' / '.lang.new').exists())

    def test_modes_from_the_archive_are_not_kept(self):
        # a set-id bit or a file anyone may write would be one on a disk Ubuntu's users share: catalogs come out
        # 644, directories 755, whatever the archive says
        for shell in self.each_shell():
            self.clean(shell)
            f = self.tmp / 'modes.tar.gz'
            with tarfile.open(f, 'w:gz') as t:
                members = [('./name', b'lang\n', 0o666), ('./release', b'v1\n', 0o644),
                           ('./languages', b'de\tDeutsch (German)\n', 0o666), ('./i18n', None, 0o777),
                           ('./i18n/base.de.lmo', b'x', 0o4777)]
                man = ''.join(f'{hashlib.sha256(d).hexdigest()}  {n}\n' for n, d, _ in members if d is not None)
                for fn, data, mode in members + [('./manifest', man.encode(), 0o666)]:
                    ti = tarfile.TarInfo(fn)
                    ti.mode = mode
                    if data is None:
                        ti.type = tarfile.DIRTYPE
                    else:
                        ti.size = len(data)
                    t.addfile(ti, io.BytesIO(data) if data is not None else None)
            r = self.up(shell, f'extra_unpack lang "{f}"; echo "rc=$?"')
            self.assertIn('rc=0', r.stdout, (shell, r.stderr))
            for rel, want in (('name', 0o644), ('languages', 0o644), ('manifest', 0o644), ('i18n', 0o755),
                              ('i18n/base.de.lmo', 0o644)):
                self.assertEqual(oct((self.lang() / rel).stat().st_mode & 0o7777), oct(want), (shell, rel))

    def test_the_tarball_is_read_once(self):
        # checked and unpacked from one private copy: a tarball that can be read only once (a FIFO: what a file
        # swapped between the check and the unpacking would look like to a second read) still installs
        import threading
        for shell in self.each_shell():
            self.clean(shell)
            fifo = self.tmp / 'once.tar.gz'
            fifo.unlink(missing_ok=True)
            os.mkfifo(fifo)
            data = self.file.read_bytes()

            def feed():
                with open(fifo, 'wb') as f:
                    f.write(data)
            t = threading.Thread(target=feed, daemon=True)
            t.start()
            r = self.up(shell, f'extra_unpack lang "{fifo}"; echo "rc=$?"')
            t.join(5)
            self.assertIn('rc=0', r.stdout, (shell, r.stderr))
            self.assertEqual((self.lang() / 'release').read_text().strip(), 'v2026.10.10')
            # and nothing of the copy is left
            self.assertEqual(sorted(p.name for p in (self.disk / 'extra').iterdir()), ['lang'])

    def test_install_links_and_registers_every_language(self):
        for shell in self.each_shell():
            self.clean(shell)
            # a catalog of the user's own (an apk-installed luci-i18n-base-ja) is never replaced
            (self.i18n / 'base.ja.lmo').write_text('mine')
            r = self.ex(shell, 'install', 'lang', MU300_EXTRA_FILE=self.file)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for n in LMOS:
                if n != 'base.ja.lmo':
                    self.assertEqual(os.readlink(self.i18n / n), str(self.lang() / 'i18n' / n), (shell, n))
            self.assertEqual((self.i18n / 'base.ja.lmo').read_text(), 'mine')
            langs, cur = self.uci()
            self.assertEqual(langs, {'tr': 'Türkçe (Turkish)', 'zh_cn': 'Chinese', **LANGS}, shell)
            self.assertEqual(cur, 'en')
            self.assertIn('luci', (self.tmp / 'commits').read_text())
            r = self.ex(shell, 'lang')
            self.assertEqual(r.stdout.splitlines(), [f'{k}\tenabled\t{v}' for k, v in LANGS.items()], shell)
            st = self.ex(shell, 'status')
            self.assertIn('languages 3, offered here: de pt_br ja', st.stdout, shell)
            (self.i18n / 'base.ja.lmo').unlink()

    def test_enable_and_disable(self):
        for shell in self.each_shell():
            self.clean(shell)
            self.ex(shell, 'install', 'lang', MU300_EXTRA_FILE=self.file)
            self.reset_uci('de')                                      # LuCI set to German
            self.ex(shell, 'link')
            r = self.ex(shell, 'lang', 'disable', 'de', 'ja')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual((self.root / 'etc/mu300/languages').read_text(), 'pt_br\n')
            self.assertFalse(os.path.lexists(self.i18n / 'base.de.lmo'))
            self.assertFalse(os.path.lexists(self.i18n / 'mu300.ja.lmo'))
            self.assertTrue(os.path.islink(self.i18n / 'base.pt-br.lmo'))
            langs, cur = self.uci()
            self.assertEqual(sorted(langs), ['pt_br', 'tr', 'zh_cn'], shell)
            self.assertEqual(cur, 'en', 'the language LuCI was set to is gone: back to English')
            r = self.ex(shell, 'lang', 'enable', 'ja')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(sorted(self.uci()[0]), ['ja', 'pt_br', 'tr', 'zh_cn'])
            r = self.ex(shell, 'lang', 'disable', 'all')
            self.assertEqual(sorted(self.uci()[0]), ['tr', 'zh_cn'], shell)
            self.assertEqual([p.name for p in self.i18n.iterdir() if p.is_symlink()], [])
            r = self.ex(shell, 'lang', 'enable', 'all')
            self.assertFalse((self.root / 'etc/mu300/languages').exists())
            self.assertEqual(sorted(self.uci()[0]), ['de', 'ja', 'pt_br', 'tr', 'zh_cn'], shell)
            # only codes of the extra, one argument each
            for bad in ('fr', 'de;reboot', '../de', '-x', 'all de'):
                r = self.ex(shell, 'lang', 'enable', *bad.split(' '))
                self.assertNotEqual(r.returncode, 0, (shell, bad))
            self.assertFalse((self.root / 'etc/mu300/languages').exists())

    def test_link_at_boot_after_an_update(self):
        # a new system image has none of the links; its first boot (mu300-post: mu300-extra link) brings back the
        # languages this system offered, from the kept /etc/mu300/languages
        for shell in self.each_shell():
            self.clean(shell)
            self.ex(shell, 'install', 'lang', MU300_EXTRA_FILE=self.file)
            self.ex(shell, 'lang', 'disable', 'pt_br')
            for p in self.i18n.iterdir():
                if p.is_symlink():
                    p.unlink()
            self.reset_uci()
            r = self.ex(shell, 'link')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(self.uci()[0]), ['de', 'ja', 'tr', 'zh_cn'], shell)
            self.assertTrue(os.path.islink(self.i18n / 'mu300.de.lmo'))
            self.assertFalse(os.path.lexists(self.i18n / 'base.pt-br.lmo'))
            # nothing changed: nothing committed
            (self.tmp / 'commits').unlink()
            self.ex(shell, 'link')
            self.assertFalse((self.tmp / 'commits').exists(), shell)

    def test_remove_takes_every_language_of_the_extra_away(self):
        for shell in self.each_shell():
            self.clean(shell)
            (self.i18n / 'base.de.lmo').write_text('mine')            # German stays: a catalog of its own
            self.ex(shell, 'install', 'lang', MU300_EXTRA_FILE=self.file)
            self.ex(shell, 'lang', 'disable', 'ja')
            r = self.ex(shell, 'remove', 'lang')
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertFalse(self.lang().exists())
            self.assertFalse((self.root / 'etc/mu300/languages').exists())
            self.assertEqual([p.name for p in self.i18n.iterdir() if p.is_symlink()], [], shell)
            self.assertEqual(sorted(self.uci()[0]), ['de', 'tr', 'zh_cn'], shell)
            (self.i18n / 'base.de.lmo').unlink()
            r = self.ex(shell, 'lang')
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('install lang', r.stderr)

    def test_ubuntu_has_no_luci(self):
        (self.root / 'etc/openwrt_release').unlink()
        for shell in self.each_shell():
            self.clean(shell)
            r = self.ex(shell, 'install', 'lang', MU300_EXTRA_FILE=self.file)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('OpenWrt only', r.stderr)
            self.assertFalse(self.lang().exists())
            r = self.ex(shell, 'list')
            self.assertRegex(r.stdout, r'lang +not installed - for OpenWrt only')
            # installed from OpenWrt, the shared copy is left alone by Ubuntu's link
            self.up(shell, f'extra_unpack lang "{self.file}"')
            r = self.ex(shell, 'link')
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((self.tmp / 'uci.log').exists() and 'set' in (self.tmp / 'uci.log').read_text())

    def test_an_update_brings_the_lang_extra_along(self):
        for shell in self.each_shell():
            self.clean(shell)
            self.up(shell, f'extra_unpack lang "{lang_tarball(self.tmp / "old.tar.gz", release="v2026.10.01")}"')
            r = self.up(shell, 'extras_to_fetch v2026.10.10 "openwrt"')
            self.assertEqual(r.stdout.split(), ['lang'], shell)
            r = self.up(shell, 'extras_to_fetch v2026.10.01 "openwrt"')
            self.assertEqual(r.stdout.split(), [], shell)


if __name__ == '__main__':
    unittest.main()
