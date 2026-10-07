#!/usr/bin/env python3
"""Build a V50 release from checksum-verified generic upstream release assets.

This repacks the rootfs and rebuilds generic boot ramdisks from this checkout.
The verified kernel Image and matching modules are reused, not recompiled.
"""
import argparse
import copy
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

TOP = Path(__file__).resolve().parents[2]
ASSETS = ('mu300-kernel.tar.gz', 'mu300-kernel-6.18.tar.gz', 'mu300-openwrt-luci-rootfs.tar.gz')
FILES = {
    'opt/mu300/bin/mu300-led': ('rootfs/overlay/opt/mu300/bin/mu300-led', 0o755),
    'opt/mu300/bin/mu300-v50-led-off': ('rootfs/overlay/opt/mu300/bin/mu300-v50-led-off', 0o755),
    'opt/mu300/bin/mu300-v50-check': ('rootfs/overlay/opt/mu300/bin/mu300-v50-check', 0o755),
    'opt/mu300/bin/mu300-update': ('rootfs/overlay/opt/mu300/bin/mu300-update', 0o755),
    'etc/init.d/v50-led-off': ('openwrt/overlay/etc/init.d/v50-led-off', 0o755),
    'etc/mu300/profile': ('profiles/v50/overlay/etc/mu300/profile', 0o644),
    'etc/mu300/led.conf': ('profiles/v50/overlay/etc/mu300/led.conf', 0o644),
}


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError('Unsafe archive path')
    return p.as_posix().removeprefix('./')


def audit_member(member):
    name = safe_name(member.name)
    parts = PurePosixPath(name).parts
    forbidden = ('private', 'v50-backup', 'dev-properties', '__properties__')
    if any(p in forbidden for p in parts) and not (name == 'etc/ssl/private' and member.isdir()):
        raise ValueError(f'Private device content: {name}')
    if name.startswith('opt/mu300/android/') and name not in (
            'opt/mu300/android/system', 'opt/mu300/android/system/bin', 'opt/mu300/android/system/bin/cltest'):
        raise ValueError(f'Proprietary Android content: {name}')
    if re.search(r'(^|/)(libmali|libOpenCL|libGLES|libEGL|libvulkan)[^/]*\.so', name):
        raise ValueError(f'Proprietary GPU library: {name}')
    if any(p in name for p in ('wcnmodem', 'gnssmodem', 'wifi_board_config', 'bt_configure', 'ssh_host_', 'dropbear_rsa_host_key', 'dropbear_ed25519_host_key')):
        raise ValueError(f'Device firmware or host key: {name}')
    if name.startswith('etc/openclash/') or name in (
            'etc/config/openclash', 'etc/mu300/hotspot.conf', 'etc/mu300/vpn.conf', 'etc/mu300/toolkit.conf'):
        raise ValueError(f'Personal configuration: {name}')
    if member.isdev() or member.isfifo():
        raise ValueError(f'Special file in release: {name}')
    return name


def verified_inputs(directory):
    sums = {}
    for line in (directory / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        fields = line.split()
        if len(fields) == 2 and re.fullmatch('[0-9a-f]{64}', fields[0]):
            name = fields[1].removeprefix('*')
            if name in sums:
                raise ValueError(f'Duplicate checksum: {name}')
            sums[name] = fields[0]
    for name in ASSETS:
        if name not in sums or sha256(directory / name) != sums[name]:
            raise ValueError(f'Input checksum mismatch: {name}')
    return {name: sums[name] for name in ASSETS}


def rewrite(source, target, replacements, links=None):
    links = links or {}
    seen = set()
    with tarfile.open(source, 'r:gz') as src, tarfile.open(target, 'w:gz', format=tarfile.GNU_FORMAT) as dst:
        for m in src:
            name = audit_member(m)
            if name in seen:
                raise ValueError(f'Duplicate archive path: {name}')
            seen.add(name)
            if name in replacements or name in links:
                continue
            m = copy.copy(m)
            m.name = './' + name
            if m.isfile() and name in ('etc/machine-id', 'var/lib/dbus/machine-id') and m.size:
                raise ValueError('Release contains a populated machine-id')
            dst.addfile(m, src.extractfile(m) if m.isfile() else None)
        for name, (data, mode) in sorted(replacements.items()):
            m = tarfile.TarInfo('./' + name)
            m.mode, m.size, m.uid, m.gid = mode, len(data), 0, 0
            m.uname = m.gname = 'root'
            dst.addfile(m, io.BytesIO(data))
        for name, link in sorted(links.items()):
            m = tarfile.TarInfo('./' + name)
            m.type, m.linkname, m.mode = tarfile.SYMTYPE, link, 0o777
            dst.addfile(m)


def extract_helpers(bundle, directory):
    """Extract only regular helper/module files needed for the generic ramdisk builder."""
    directory.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle, 'r:gz') as tar:
        for m in tar:
            name = audit_member(m)
            if not m.isfile() or not (name in ('busybox', 'logdw', 'kernel.release') or
                                     re.fullmatch(r'modules(?:-u30air)?/[A-Za-z0-9_.-]+\.ko', name)):
                continue
            p = directory / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(tar.extractfile(m).read())


def rebuild_ramdisk(kernel, helpers, directory, mainline):
    modules = directory / ('mainline' if mainline else 'vendor')
    extract_helpers(kernel, modules)
    out = modules / 'ramdisk-generic.lz4'
    args = [sys.executable, str(TOP / 'boot/build-boot-image.py'), '--generic-ramdisk',
            '--modules', str(modules / 'modules'), '--busybox', str(helpers / 'busybox'),
            '--logdw', str(helpers / 'logdw'), '--ueventd-perms', str(TOP / 'android-vendor/ueventd-perms.sh'),
            '--out', str(out)]
    if mainline:
        args += ['--module-order', str(TOP / 'upstream/module-order.txt')]
    else:
        args += ['--device-modules', 'u30air=' + str(helpers / 'modules-u30air')]
    subprocess.run(args, check=True)
    return out.read_bytes()


def build(base, output, tag, repo, base_tag=None):
    if not re.fullmatch(r'v\d{4}\.\d{2}\.\d{2}-v50[.A-Za-z0-9-]*', tag):
        raise ValueError('Use a tag such as v2026.10.07-v50.1')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repo) or repo == 'dikeckaan/mu300-linux':
        raise ValueError('Provide your V50 release repository as owner/repository')
    hashes = verified_inputs(base)
    base_tag = base_tag or base.name
    if not re.fullmatch(r'v\d{4}\.\d{2}\.\d{2}', base_tag):
        raise ValueError('Provide the upstream input release tag with --base-tag vYYYY.MM.DD')
    with tarfile.open(base / ASSETS[1], 'r:gz') as tar:
        kernel = next(m for m in tar if safe_name(m.name) == 'kernel.release')
        krel = tar.extractfile(kernel).read().decode().strip()
    if not krel.startswith('6.18.'):
        raise ValueError('V50 profile requires a 6.18 kernel input')
    # A complete public input audit precedes all output creation.
    for name in ASSETS:
        with tarfile.open(base / name, 'r:gz') as tar:
            for m in tar:
                audit_member(m)
    output.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='mu300-v50-') as temp:
        stage = Path(temp)
        helpers = stage / 'helpers'
        extract_helpers(base / ASSETS[0], helpers)
        for name in ASSETS[:2]:
            ramdisk = rebuild_ramdisk(base / name, helpers, stage, name == ASSETS[1])
            # Keep Image and matching modules intact. Only this checkout's generic init is replaced.
            rewrite(base / name, output / name, {'ramdisk-generic.lz4': (ramdisk, 0o644)})
        replacements = {name: ((TOP / source).read_bytes().replace(b'\r\n', b'\n'), mode)
                        for name, (source, mode) in FILES.items()}
        replacements['etc/mu300/image-version'] = ((tag + '\n').encode(), 0o644)
        replacements['etc/mu300/update.conf'] = ((f'REPO={repo}\n').encode(), 0o644)
        rewrite(base / ASSETS[2], output / ASSETS[2], replacements,
                {'etc/rc.d/S19v50-led-off': '../init.d/v50-led-off'})
    updater = (TOP / 'rootfs/overlay/opt/mu300/bin/mu300-update').read_bytes().replace(b'\r\n', b'\n')
    (output / 'mu300-update').write_bytes(updater)
    commit = subprocess.run(['git', '-C', str(TOP), 'rev-parse', 'HEAD'],
                            check=True, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(['git', '-C', str(TOP), 'status', '--porcelain'],
                                check=True, capture_output=True, text=True).stdout.strip())
    manifest = {'profile': 'v50', 'tag': tag, 'repository': repo, 'source_commit': commit,
                'input_release': f'https://github.com/dikeckaan/mu300-linux/releases/tag/{base_tag}',
                'source_dirty': dirty, 'input_sha256': hashes, 'kernel': krel,
                'kernel_recompiled': False, 'packages_rebuilt': False,
                'device_tested': False, 'optional_components': [],
                'build_method': 'verified generic assets + source overlays + rebuilt generic ramdisks'}
    (output / 'BUILD-MANIFEST.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8', newline='\n')
    names = (*ASSETS, 'mu300-update', 'BUILD-MANIFEST.json')
    (output / 'SHA256SUMS').write_text(''.join(f'{sha256(output / n)}  {n}\n' for n in names), encoding='ascii', newline='\n')
    print(f'Prepared {output}; kernel reused: {krel}; device testing still required.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True, help='Generic upstream assets and trusted SHA256SUMS')
    ap.add_argument('--base-tag', help='Upstream release tag (default: input directory name)')
    ap.add_argument('--output', type=Path, required=True, help='New directory; never overwritten')
    ap.add_argument('--tag', required=True)
    ap.add_argument('--repo', required=True)
    a = ap.parse_args()
    try:
        build(a.base.resolve(), a.output.resolve(), a.tag, a.repo, a.base_tag)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as exc:
        ap.exit(1, f'Release preparation failed: {exc}\n')


if __name__ == '__main__':
    main()
