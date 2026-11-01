"""Not a test: tools/android-online-shrink.sh as the fake eMMC of tests/fakeemmc.py would answer it, for the tests of
the installers' online way (tests/test_resume.py OnlineShrink). The installers push it in place of the real script
(MU300_ONLINE_SH, a two-line wrapper that runs this file); tests/fakeadb.py runs it against the directory
($FAKE_EMMC). The real script and mu300-f2fs-online are tested for real by tests/online-shrink-e2e.sh.

The F2FS is the superblock in FAKE_EMMC/dev/block/dm-6 (fakeemmc.f2fs_super). The worker does at once what the real
one does: checks both copies of the table against the old (or new) ones it was given, sets the F2FS to its target,
writes the backup table, then the primary. FAKE_EMMC/online.json changes that:
    {"probe": "refused"}       the kernel refuses the same-size probe: nothing changes
    {"stop": "shrunk"}         the worker stops after the shrink, before the table (status: recovery)
    {"lost": true}             status answers nothing (adb lost)
    {"used": BYTES}            what inspect says is used (default 1 GiB)
"""
import hashlib
import json
import os
import struct
import sys
from pathlib import Path

D = Path(os.environ['FAKE_EMMC'])
FILES = ('mu300-f2fs-online', 'old-first', 'old-last', 'new-first', 'new-last')


def knobs():
    try:
        return json.loads((D / 'online.json').read_text())
    except OSError:
        return {}


def disk():
    return D / 'dev/block' / ('sda' if (D / 'dev/block/sda').exists() else 'mmcblk0')


def sb():
    return D / 'dev/block/dm-6'


def blocks():
    return struct.unpack_from('<Q', sb().read_bytes(), 1024 + 36)[0]


def set_blocks(n):
    raw = bytearray(sb().read_bytes())
    struct.pack_into('<Q', raw, 1024 + 36, n)
    struct.pack_into('<Q', raw, 5120 + 36, n)
    sb().write_bytes(bytes(raw))


def read(at, n):
    with open(disk(), 'rb') as f:
        f.seek(at)
        return f.read(n)


def write(at, data):
    with open(disk(), 'r+b') as f:
        f.seek(at)
        f.write(data)


def work(tok):
    return D / ('online-' + tok)


def main(argv):
    cmd = argv[0]
    if cmd == 'inspect':
        raw = sb().read_bytes()
        print('ONLINE=yes\nSOURCE=/dev/block/dm-6\nNODE=userdata\nMAPPED=0')
        print('BLOCKS=%d\nBLOCK_SIZE=4096\nSECTION_BLOCKS=512\nMAPPED_BYTES=0\nUSED_BYTES=%d\nUUID=%s'
              % (blocks(), knobs().get('used', 1 << 30), raw[1024 + 108:1024 + 124].hex()))
    elif cmd == 'stage':
        src, tok = Path(argv[1]), argv[2]
        work(tok).mkdir(exist_ok=True)
        for f in FILES:
            (work(tok) / f).write_bytes((src / f).read_bytes())
            print('SHA_%s=%s' % (f.upper().replace('-', '_'), hashlib.sha256((src / f).read_bytes()).hexdigest()))
        print('STAGE=ok')
    elif cmd == 'start':
        tok, old, target, uuid, n = argv[1], int(argv[2]), int(argv[3]), argv[4], int(argv[5])
        tail_sectors = int(argv[6]) if len(argv) > 6 else 33
        w = work(tok)
        if knobs().get('probe') == 'refused' and blocks() == old:
            print('PROBE=refused\nERRNO=95')
            return 0
        img = {f: (w / f).read_bytes() for f in FILES[1:]}
        tail = (n - tail_sectors) * 512
        first, last = read(0, len(img['old-first'])), read(tail, len(img['old-last']))
        if first not in (img['old-first'], img['new-first']) or last not in (img['old-last'], img['new-last']) or \
                blocks() not in (old, target):
            print('LAUNCH=failed\nSTAGE=worker-stale-state\nERRNO=22')
            return 0
        print('LAUNCH=ok')
        set_blocks(target)
        if knobs().get('stop') == 'shrunk':
            (w / 'status').write_text('phase=recovery\nerrno=5\n')
            return 0
        write(tail, img['new-last'])
        write(0, img['new-first'])
        (w / 'status').write_text('phase=complete\nerrno=0\n')
    elif cmd == 'status':
        if knobs().get('lost'):
            return 0
        w = work(argv[1])
        if not w.is_dir():
            print('PHASE=gone\nBUSY=0')
            return 0
        for line in (w / 'status').read_text().splitlines() if (w / 'status').exists() else []:
            k, _, v = line.partition('=')
            print('%s=%s' % (k.upper(), v))
        print('BUSY=0')
    elif cmd == 'cleanup':
        w = work(argv[1])
        for f in w.glob('*'):
            f.unlink()
        if w.is_dir():
            w.rmdir()
        print('CLEANUP=ok')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
