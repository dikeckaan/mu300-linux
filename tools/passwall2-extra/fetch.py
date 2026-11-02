#!/usr/bin/env python3
"""Fetch the pinned package set. Direct verified HTTPS, TLS 1.2 only."""
import argparse
import hashlib
import json
from pathlib import Path
import ssl
import urllib.request
import zipfile


def fetch(url, target, sha):
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == sha:
        return
    if not url.startswith('https://'):
        raise ValueError('HTTPS is required')
    ctx = ssl.create_default_context()
    ctx.minimum_version = ctx.maximum_version = ssl.TLSVersion.TLSv1_2
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
    tmp = target.with_suffix(target.suffix + '.part')
    with op.open(url, timeout=60) as r, tmp.open('wb') as f:
        if not r.url.startswith('https://'):
            raise ValueError('insecure redirect')
        while chunk := r.read(1024 * 1024):
            f.write(chunk)
    if hashlib.sha256(tmp.read_bytes()).hexdigest() != sha:
        tmp.unlink()
        raise ValueError('SHA256 mismatch: ' + target.name)
    tmp.replace(target)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('cache', type=Path)
    a = p.parse_args()
    a.cache.mkdir(parents=True, exist_ok=True)
    lock = json.loads(Path(__file__).with_name('packages.lock.json').read_text())
    for e in lock['packages']:
        target = a.cache / e['file']
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == e['sha256']:
            print(e['file'], 'verified (cached)')
            continue
        if 'container' in e:
            c = e['container']
            z = a.cache / c['file']
            fetch(c['url'], z, c['sha256'])
            with zipfile.ZipFile(z) as archive:
                data = archive.read(e['member'])
            if hashlib.sha256(data).hexdigest() != e['sha256']:
                raise ValueError('ZIP member mismatch: ' + e['file'])
            target.write_bytes(data)
        else:
            fetch(e['url'], target, e['sha256'])
        print(e['file'], 'verified')
