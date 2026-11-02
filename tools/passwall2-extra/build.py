#!/usr/bin/env python3
"""Build a mu300-extra custom module, from hash-pinned offline APKs."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile

TOP = Path(__file__).resolve().parent
CAPS = {
    'kmod-nf-conntrack-netlink': [('CONFIG_NF_CT_NETLINK', ''), ('CONFIG_NF_CONNTRACK', ''), ('CONFIG_NETFILTER_NETLINK', '')],
    'kmod-tun': [('CONFIG_TUN', 'tun')],
    'kmod-inet-diag': [('CONFIG_INET_DIAG', 'inet_diag')],
    'kmod-netlink-diag': [('CONFIG_NETLINK_DIAG', 'netlink_diag')],
    'kmod-nft-socket': [('CONFIG_NFT_SOCKET', ''), ('CONFIG_NF_SOCKET_IPV4', ''), ('CONFIG_NF_SOCKET_IPV6', '')],
    'kmod-nft-tproxy': [('CONFIG_NFT_TPROXY', ''), ('CONFIG_NF_TPROXY_IPV4', ''), ('CONFIG_NF_TPROXY_IPV6', '')],
}


def digest(p):
    with p.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def providers(apk, dest, config, work):
    ids = work / 'ids'
    (ids / 'etc').mkdir(parents=True)
    passwd = 'root:x:0:0:root:/:/bin/sh\n'
    group = 'root:x:0:\n'
    if os.getuid():
        passwd += f'root:x:{os.getuid()}:{os.getgid()}:root:/:/bin/sh\n'
    if os.getgid():
        group += f'root:x:{os.getgid()}:\n'
    (ids / 'etc/passwd').write_text(passwd)
    (ids / 'etc/group').write_text(group)
    lines = set(config.read_text().splitlines())
    for name, symbols in CAPS.items():
        for key, module in symbols:
            if key + '=y' not in lines and not (module and key + '=m' in lines):
                raise ValueError(f'{config}: missing native capability {key}')
        stage = work / name
        marker = Path('usr/share/mu300/passwall2-native') / name
        (stage / marker).parent.mkdir(parents=True)
        (stage / marker).write_text('Native kernel capability; no .ko in this package.\n')
        filelist = stage / 'lib/apk/packages' / (name + '.list')
        filelist.parent.mkdir(parents=True)
        filelist.write_text('/' + marker.as_posix() + '\n')
        guard = work / (name + '.pre-install')
        guard.write_text((TOP / 'module/lib/native-check.sh').read_text() +
                         '\nnative_check ' + name + '\n')
        for p in [stage, *stage.rglob('*')]:
            p.chmod(0o755 if p.is_dir() else 0o644)
        guard.chmod(0o755)
        subprocess.run([str(apk), '--root', str(ids), 'mkpkg', '--no-xattrs',
            '--info', 'name:' + name, '--info', 'version:2026.11.02-r2',
            '--info', 'arch:aarch64_generic', '--info', 'license:GPL-2.0-only',
            '--info', 'origin:mu300-passwall2-native',
            '--info', 'description:Verified native kernel capability (no foreign module)',
            '--script', 'pre-install:' + str(guard), '--files', str(stage),
            '--output', str(dest / (name + '.apk'))],
            check=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})


def build(cache, output, apk, config, release, languages='all', engines='shared'):
    if not re.fullmatch(r'[A-Za-z0-9._-]{1,40}', release):
        raise ValueError('invalid release')
    lock = json.loads((TOP / 'packages.lock.json').read_text())
    available = {'en'} | {e['language'] for e in lock['packages'] if 'language' in e}
    selected = available if languages == 'all' else set(languages.split(','))
    if not selected <= available or not selected:
        raise ValueError('unsupported languages; choose all or ' + ','.join(sorted(available)))
    with tempfile.TemporaryDirectory(prefix='mu300-passwall2-') as temp:
        work = Path(temp)
        files = {}
        for p in sorted((TOP / 'module').rglob('*')):
            if p.is_symlink():
                raise ValueError(f'symlink in module: {p}')
            if p.is_file():
                files[p.relative_to(TOP / 'module').as_posix()] = (p.read_bytes(), 0o755 if p.parent.name in ('bin', 'hooks', 'libexec') else 0o644)
        names = []
        versions = []
        for entry in lock['packages']:
            if 'language' in entry and entry['language'] not in selected:
                continue
            p = cache / entry['file']
            if digest(p) != entry['sha256']:
                raise ValueError(f'{p}: SHA256 mismatch')
            if entry['name'] in ('sing-box', 'xray-core'):
                core = 'xray' if entry['name'] == 'xray-core' else 'sing-box'
                versions.append(core + ' ' + entry['version'].split('-r')[0])
                if engines == 'bundled':
                    extracted = work / core
                    extracted.mkdir()
                    subprocess.run([str(apk), '--allow-untrusted', 'extract', str(p)], cwd=extracted,
                                   check=True, stdout=subprocess.DEVNULL)
                    files['engines/' + core] = ((extracted / 'usr/bin' / core).read_bytes(), 0o755)
                continue
            if entry['name'] == 'luci-app-passwall2':
                extracted = work / 'luci'
                extracted.mkdir()
                subprocess.run([str(apk), '--allow-untrusted', 'extract', str(p)], cwd=extracted,
                               check=True, stdout=subprocess.DEVNULL)
                api = extracted / 'usr/lib/lua/luci/passwall2/api.lua'
                files['api-original.sha256'] = ((digest(api) + '\n').encode(), 0o644)
            # Own extras allow plain path components, not OpenWrt's '~' versions.
            # Preserve the upstream filename/version/hash in the lock file instead.
            files['apks/' + entry['name'] + '.apk'] = (p.read_bytes(), 0o644)
            names.append(entry['name'])
        dest = work / 'providers'
        dest.mkdir()
        providers(apk, dest, config, work)
        for p in sorted(dest.iterdir()):
            files['providers/' + p.name] = (p.read_bytes(), 0o644)
        files['packages'] = ((''.join(n + '\n' for n in names)).encode(), 0o644)
        files['core-versions'] = (('\n'.join(sorted(versions)) + '\n').encode(), 0o644)
        files['engine-mode'] = ((engines + '\n').encode(), 0o644)
        files['languages'] = (('\n'.join(sorted(selected | {'en'})) + '\n').encode(), 0o644)
        files['packages.lock.json'] = ((TOP / 'packages.lock.json').read_bytes(), 0o644)
        files['LICENSE'] = ((TOP / 'LICENSE').read_bytes(), 0o644)
        files['name'] = (b'passwall2\n', 0o644)
        files['release'] = ((release + '\n').encode(), 0o644)
        files['components'] = (('Passwall2 offline extra ' + release + '\n' + ''.join(
            e['name'] + ' ' + e['version'] + '\n' for e in lock['packages'] if e['name'] in names)).encode(), 0o644)
        files['manifest'] = (''.join(hashlib.sha256(data).hexdigest() + '  ./' + name + '\n'
            for name, (data, _) in sorted(files.items())).encode(), 0o644)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Fixed gzip header and tar metadata make repeated builds byte-identical.
        with output.open('wb') as raw, gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w', format=tarfile.GNU_FORMAT) as archive:
                for name, (data, mode) in sorted(files.items()):
                    ti = tarfile.TarInfo('./' + name)
                    ti.size, ti.mode, ti.uid, ti.gid, ti.mtime = len(data), mode, 0, 0, 0
                    ti.uname = ti.gname = 'root'
                    archive.addfile(ti, io.BytesIO(data))
    sums = output.with_name('SHA256SUMS')
    entries = {}
    if sums.exists():
        for line in sums.read_text().splitlines():
            match = re.fullmatch(r'([0-9a-f]{64})  ([^/\r\n]+)', line)
            if match:
                entries[match[2]] = match[1]
    entries[output.name] = digest(output)
    sums.write_text(''.join(sha + '  ' + name + '\n' for name, sha in sorted(entries.items())))
    print(output, digest(output))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--apk', type=Path, required=True, help='host apk-tools v3 with mkpkg')
    p.add_argument('--config', type=Path, required=True, help='target native kernel configuration')
    p.add_argument('--release', default='v2026.11.02.2')
    p.add_argument('--engines', choices=['shared', 'bundled'], default='shared', help='reuse compatible installed cores; bundled adds one-copy offline fallback binaries')
    p.add_argument('--languages', default='all', help='all (default), or comma-separated en,zh-cn,zh-tw,ru,fa')
    a = p.parse_args()
    build(a.cache.resolve(), a.output.resolve(), a.apk.resolve(), a.config, a.release, a.languages, a.engines)
