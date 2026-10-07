#!/usr/bin/env python3
"""Verify V50 outputs, matching kernel bytes, source overlays and generic ramdisk init."""
import argparse
import hashlib
import importlib.util
import json
import struct
import tarfile
from pathlib import Path

spec = importlib.util.spec_from_file_location('v50_release', Path(__file__).with_name('release.py'))
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def member_bytes(archive, name):
    matches = [m for m in archive if release.safe_name(m.name) == name]
    if len(matches) != 1 or not matches[0].isfile():
        raise ValueError(f'Missing or duplicated regular file: {name}')
    return archive.extractfile(matches[0]).read()


def ramdisk_init(data):
    import lz4.block
    raw = bytearray()
    pos = 0
    while pos < len(data):
        if data[pos:pos + 4] != b'\x02\x21\x4c\x18':
            raise ValueError('Invalid legacy LZ4 frame')
        pos += 4
        while pos + 4 <= len(data) and data[pos:pos + 4] != b'\x02\x21\x4c\x18':
            size = struct.unpack_from('<I', data, pos)[0]
            pos += 4
            raw.extend(lz4.block.decompress(data[pos:pos + size], uncompressed_size=8 << 20))
            pos += size
    pos = 0
    while pos + 110 <= len(raw):
        header = raw[pos:pos + 110]
        if header[:6] != b'070701':
            raise ValueError('Invalid newc archive')
        size, namesize = int(header[54:62], 16), int(header[94:102], 16)
        name = raw[pos + 110:pos + 110 + namesize - 1].decode()
        pos = (pos + 110 + namesize + 3) & ~3
        payload = raw[pos:pos + size]
        pos = (pos + size + 3) & ~3
        if name in ('init', './init'):
            return bytes(payload)
        if name == 'TRAILER!!!':
            break
    raise ValueError('Generic ramdisk has no init')


def verify(base, output):
    release.verified_inputs(base)
    manifest = json.loads((output / 'BUILD-MANIFEST.json').read_text(encoding='utf-8'))
    if b'\r' in (output / 'SHA256SUMS').read_bytes():
        raise ValueError('SHA256SUMS must use LF line endings for Linux sha256sum')
    for line in (output / 'SHA256SUMS').read_text(encoding='ascii').splitlines():
        digest, name = line.split()
        if '/' in name or '\\' in name or release.sha256(output / name) != digest:
            raise ValueError('Output checksum mismatch')
    expected_init = (release.TOP / 'boot/init').read_bytes().replace(b'\r\n', b'\n')
    for name in release.ASSETS[:2]:
        with tarfile.open(base / name, 'r:gz') as src, tarfile.open(output / name, 'r:gz') as dst:
            for m in dst:
                member = release.audit_member(m)
                if m.isfile() and member != 'ramdisk-generic.lz4':
                    if member_bytes(src, member) != dst.extractfile(m).read():
                        raise ValueError(f'Kernel bundle input changed: {member}')
            if ramdisk_init(member_bytes(dst, 'ramdisk-generic.lz4')) != expected_init:
                raise ValueError('Ramdisk init differs from source')
    with tarfile.open(output / release.ASSETS[2], 'r:gz') as root:
        for m in root:
            release.audit_member(m)
        for name, (source, _) in release.FILES.items():
            if member_bytes(root, name) != (release.TOP / source).read_bytes().replace(b'\r\n', b'\n'):
                raise ValueError(f'Overlay differs from source: {name}')
        if member_bytes(root, 'etc/mu300/image-version').decode().strip() != manifest['tag']:
            raise ValueError('Image tag mismatch')
        if member_bytes(root, 'etc/mu300/update.conf').decode().strip() != 'REPO=' + manifest['repository']:
            raise ValueError('Update repository mismatch')
        link = next(m for m in root if release.safe_name(m.name) == 'etc/rc.d/S19v50-led-off')
        if not link.issym() or link.linkname != '../init.d/v50-led-off':
            raise ValueError('LED startup link missing')
    print('Verified checksums, source overlays, LED startup, matching kernel/modules and both ramdisk init files.')
    print('Device boot and network operation are not verified by this check.')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    a = ap.parse_args()
    try:
        verify(a.base, a.output)
    except (OSError, ValueError, tarfile.TarError) as exc:
        ap.exit(1, f'Verification failed: {exc}\n')


if __name__ == '__main__':
    main()
