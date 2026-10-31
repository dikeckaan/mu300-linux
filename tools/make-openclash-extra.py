#!/usr/bin/env python3
"""Build the openclash extra - the same archive tools/make-openclash-extra.sh builds, for a computer without a POSIX
shell (install.ps1) and for the tests that hold the two to one layout.
   tools/make-openclash-extra.py APK OUT.tar.gz [TAG]
The extra: the luci-app-openclash .apk, the hooks that install it into the running OpenWrt system, and the command
that does the same by hand. ./name ./release ./manifest as the other extras, root-owned, bin/ and hooks/ executable.
"""
import hashlib
import os
import shutil
import sys
import tarfile
import tempfile

TAG_OK = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-')


def main():
    if len(sys.argv) < 3 or len(sys.argv) > 4:
        sys.exit('usage: tools/make-openclash-extra.py APK OUT.tar.gz [TAG]')
    apk, out = sys.argv[1], sys.argv[2]
    tag = sys.argv[3] if len(sys.argv) == 4 else 'dev'
    if not os.path.isfile(apk) or os.path.getsize(apk) == 0:
        sys.exit(f'make-openclash-extra: {apk} not found')
    if not tag or len(tag) > 40 or not set(tag) <= TAG_OK:
        sys.exit(f"make-openclash-extra: bad tag '{tag}'")
    top = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(top, 'tools', 'openclash-extra')
    tmp = tempfile.mkdtemp(prefix='mu300-openclash-extra.')
    try:
        x = os.path.join(tmp, 'x')
        os.makedirs(os.path.join(x, 'hooks'))
        os.makedirs(os.path.join(x, 'bin'))
        shutil.copyfile(apk, os.path.join(x, 'openclash.apk'))
        for f in ('hooks/link', 'hooks/unlink', 'bin/mu300-openclash'):
            dst = os.path.join(x, f)
            shutil.copyfile(os.path.join(src, f), dst)
            os.chmod(dst, 0o755)
        with open(os.path.join(x, 'name'), 'w', encoding='utf-8') as f:
            f.write('openclash\n')
        with open(os.path.join(x, 'release'), 'w', encoding='utf-8') as f:
            f.write(tag + '\n')
        lines = []
        for d, _, fs in os.walk(x):
            for f in fs:
                path = os.path.join(d, f)
                rel = './' + os.path.relpath(path, x).replace(os.sep, '/')
                if rel == './manifest':
                    continue
                with open(path, 'rb') as h:
                    lines.append((rel, hashlib.sha256(h.read()).hexdigest()))
        with open(os.path.join(x, 'manifest'), 'w', encoding='utf-8') as f:
            for rel, h in sorted(lines):
                f.write('%s  %s\n' % (h, rel))

        def root(ti):
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = 'root'
            return ti
        with tarfile.open(out, 'w:gz', format=tarfile.GNU_FORMAT) as t:
            for name in ('name', 'release', 'manifest', 'openclash.apk', 'hooks', 'bin'):
                t.add(os.path.join(x, name), arcname='./' + name, filter=root)
        print(f'openclash extra ({tag}): {out}', file=sys.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
