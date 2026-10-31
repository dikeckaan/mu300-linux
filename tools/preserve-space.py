#!/usr/bin/env python3
"""Experimental TCP/USB adb preparation: preserve U30 Air/M3 data while making 4 GiB for Linux.

An explicit target is required. plan uploads a helper and saves recovery copies, but changes no partition or
filesystem size. apply runs independently of the adb connection; status never restarts it. verify is for after
a manual Android reboot. This is a separate preparation step before the normal desktop installer.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
GPT = runpy.run_path(str(ROOT / 'resize-last-partition.py'))['GPT']
DISK = 61079552
FIRST, OLD_LAST, NEW_LAST = 12275712, 61075455, 52678655
OLD_BLOCKS, NEW_BLOCKS = 6099968, 5050368
SUCCESS = 'BOTH_GPT_COPIES_FLUSHED_AND_VERIFIED_REBOOT_REQUIRED'
RECOVERY = ('boot_a', 'boot_b', 'trustos_a', 'trustos_b', 'metadata', 'misc')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def address(value):
    """Only a literal IPv4 address and port; never adb's wildcard/default target."""
    try:
        host, port = value.rsplit(':', 1)
        ipaddress.IPv4Address(host)
        if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError()
    except ValueError:
        raise argparse.ArgumentTypeError('use a literal IPv4 address and port, e.g. 192.168.0.1:5555') from None
    return value


class Adb:
    def __init__(self, binary, serial=None, endpoint=None):
        self.binary, self.target, self.endpoint = binary, endpoint or serial, endpoint

    def call(self, *args, timeout=40):
        r = subprocess.run([self.binary, *args], capture_output=True, timeout=timeout)
        if r.returncode:
            raise RuntimeError('adb command failed: ' + r.stderr.decode('utf-8', 'replace').strip())
        return r.stdout

    def connect(self):
        if self.endpoint:
            self.call('connect', self.endpoint, timeout=20)
        # adb connect can exit zero even when its message says "failed". Check this exact target.
        if self.call('-s', self.target, 'get-state').strip() != b'device':
            raise RuntimeError('the explicit adb target is not connected/authorized')
        if self.text('id -u').strip() != '0':
            raise RuntimeError('rooted Android adb is required')
        identity = self.text('getprop ro.product.model; getprop ro.product.device').splitlines()
        if identity not in (['MU5352', 'MU5352'], ['U30Air', 'U30Air'], ['U30_Air', 'U30Air'], ['U30 Air', 'U30Air']):
            raise RuntimeError('only the shared U30 Air/M3 profile is supported')

    def remote(self, command, timeout=40):
        # Text only. Some su implementations allocate a PTY even under exec-out; pull() handles binary data.
        return self.call('-s', self.target, 'exec-out', 'su -c ' + shlex.quote(command), timeout=timeout)

    def text(self, command, timeout=40):
        return self.remote(command, timeout).decode('utf-8', 'strict').replace('\r', '')

    def pull(self, command, local):
        # Same device-file + adb-pull approach as backup-device.sh/dev_pull: su cannot rewrite binary stdout.
        # Let the adb shell create its own private staging file, so adb pull can read it without chmod 644.
        temp = '/data/local/tmp/mu300-preserve-' + uuid.uuid4().hex
        self.call('-s', self.target, 'shell', 'umask 077; set -C; : > ' + shlex.quote(temp))
        try:
            self.text('(' + command + ') > ' + shlex.quote(temp), timeout=180)
            self.call('-s', self.target, 'pull', temp, str(local), timeout=180)
        finally:
            try:
                self.call('-s', self.target, 'shell', 'rm -f ' + shlex.quote(temp))
            except (RuntimeError, subprocess.SubprocessError):
                pass  # a lost wireless connection must not hide the primary error

    def read(self, command):
        with tempfile.TemporaryDirectory(prefix='mu300-preserve-') as directory:
            path = Path(directory) / 'read'
            self.pull(command, path)
            return path.read_bytes()

    def push_private(self, source, destination):
        temp = '/data/local/tmp/mu300-preserve-' + uuid.uuid4().hex
        self.call('-s', self.target, 'push', str(source), temp, timeout=180)
        sha = digest(Path(source).read_bytes())
        # Check the private copy, not the shell-writable upload, before using it.
        self.text('umask 077; cp ' + shlex.quote(temp) + ' ' + shlex.quote(destination) +
                  ' && test "$(sha256sum ' + shlex.quote(destination) +
                  ' | cut -d \' \' -f 1)" = ' + sha + '; r=$?; rm -f ' + shlex.quote(temp) + '; exit "$r"')


def facts(adb, remote):
    text = adb.text(shlex.quote(remote + '/helper') + ' inspect')
    out = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
    if not re.fullmatch(r'[0-9a-f]{32}', out.get('CID', '')):
        raise RuntimeError('helper did not return an eMMC identity')
    for key in ('FS_BLOCKS', 'DATA_SECTORS', 'GPT_LAST', 'AVAILABLE_BLOCKS', 'BATTERY'):
        out[key] = int(out[key])
    return out


def candidate(head, tail):
    """The native helper separately validates the stricter measured layout and constructs the same bytes."""
    g = GPT(head, tail, DISK)
    last = g.find_last()
    if last != {'index': 74, 'first': FIRST, 'last': OLD_LAST, 'name': 'userdata'}:
        raise RuntimeError('not the measured, unmodified last-userdata layout')
    if head[g.p_entries_off:g.p_entries_off + g.earray_bytes] != tail[g.b_entries_off:g.b_entries_off + g.earray_bytes]:
        raise RuntimeError('GPT entry arrays disagree')
    g.set_end(74, NEW_LAST)
    GPT(bytes(g.head), bytes(g.tail), DISK)
    return bytes(g.head), bytes(g.tail)


def save(path, data):
    with path.open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def plan(adb, state, helper):
    if helper.read_bytes()[:4] != b'\x7fELF':
        raise RuntimeError('--helper must be a compiled static aarch64 Linux executable')
    state.mkdir(mode=0o700, parents=True, exist_ok=False)
    remote = '/data/adb/mu300-preserve-' + uuid.uuid4().hex
    adb.text('umask 077; mkdir ' + shlex.quote(remote))
    adb.push_private(helper, remote + '/helper')
    adb.text('chmod 700 ' + shlex.quote(remote + '/helper'))
    f = facts(adb, remote)
    if f['GPT_LAST'] != OLD_LAST or f['DATA_SECTORS'] != OLD_LAST - FIRST + 1 or f['FS_BLOCKS'] != OLD_BLOCKS:
        raise RuntimeError('this device is already resized or has a different layout; nothing was resized')
    if not 80 <= f['BATTERY'] <= 100 or f['AVAILABLE_BLOCKS'] < OLD_BLOCKS - NEW_BLOCKS + 131072:
        raise RuntimeError('need battery >=80% and enough free F2FS blocks plus reserve')
    head = adb.read('dd if=/dev/block/mmcblk0 bs=512 count=34 2>/dev/null')
    tail = adb.read('dd if=/dev/block/mmcblk0 bs=512 skip=61079519 count=33 2>/dev/null')
    if len(head) != 34 * 512 or len(tail) != 33 * 512:
        raise RuntimeError('short GPT backup')
    nh, nt = candidate(head, tail)
    files = {'before.head': head, 'before.tail': tail, 'candidate.head': nh, 'candidate.tail': nt,
             'cid': f['CID'].encode('ascii')}
    for name, data in files.items():
        save(state / name, data)
        adb.push_private(state / name, remote + '/' + name)
    # These are recovery copies, not a full userdata backup. Never claim otherwise.
    for name in RECOVERY:
        size = int(adb.text('blockdev --getsize64 /dev/block/by-name/' + name).strip())
        if not 0 < size <= 128 * 1024**2 or size % 4096:
            raise RuntimeError('unexpected recovery partition size: ' + name)
        # Stage and pull like the existing backup path; no binary stream through a su PTY.
        path = state / (name + '.raw')
        adb.pull('cat /dev/block/by-name/' + name, path)
        if path.stat().st_size != size:
            raise RuntimeError('incomplete recovery backup: ' + name)
        data_hash = digest(path.read_bytes())
        live_hash = adb.text('sha256sum /dev/block/by-name/' + name).split()[0]
        if data_hash != live_hash:
            raise RuntimeError('recovery backup hash mismatch: ' + name)
    manifest = {p.name: digest(p.read_bytes()) for p in state.iterdir() if p.is_file()}
    manifest['helper-source'] = digest(helper.read_bytes())
    result = {'version': 1, 'profile': 'u30air-m3-f2fs-4gib', 'remote': remote, 'facts': f,
              'sha256': manifest, 'linux_bytes': 4 * 1024**3,
              'warning': 'Recovery copies are not a full backup of Android data. No resize has run.'}
    save(state / 'plan.json', (json.dumps(result, indent=2) + '\n').encode('utf-8'))
    print('Prepared 4 GiB plan and verified recovery copies. No resize or GPT write has run.')
    print('Private state: ' + str(state))


def load(state):
    p = json.loads((state / 'plan.json').read_text(encoding='utf-8'))
    if p.get('version') != 1 or p.get('profile') != 'u30air-m3-f2fs-4gib' or not re.fullmatch(
            r'/data/adb/mu300-preserve-[0-9a-f]{32}', p.get('remote', '')):
        raise RuntimeError('invalid preparation state')
    expected = {'before.head', 'before.tail', 'candidate.head', 'candidate.tail', 'cid'} | {n + '.raw' for n in RECOVERY}
    if set(p['sha256']) != expected | {'helper-source'}:
        raise RuntimeError('incomplete backup manifest')
    for name in expected:
        file = state / name
        if file.is_symlink() or digest(file.read_bytes()) != p['sha256'][name]:
            raise RuntimeError('local backup changed: ' + name)
    nh, nt = candidate((state / 'before.head').read_bytes(), (state / 'before.tail').read_bytes())
    if nh != (state / 'candidate.head').read_bytes() or nt != (state / 'candidate.tail').read_bytes():
        raise RuntimeError('candidate does not match independent host plan')
    if (state / 'cid').read_text() != p['facts']['CID']:
        raise RuntimeError('plan CID mismatch')
    return p


def apply(adb, state, backup_confirmed):
    if not backup_confirmed:
        raise RuntimeError('apply requires --backup-confirmed: an independent complete backup and recovery access')
    p = load(state)
    r = p['remote']
    current = facts(adb, r)
    if current['CID'] != p['facts']['CID']:
        raise RuntimeError('this plan belongs to another eMMC')
    # Rehash the executable and root-owned plan files immediately before launch too.
    for name, sha in p['sha256'].items():
        if name in {n + '.raw' for n in RECOVERY}:
            continue
        remote_name = 'helper' if name == 'helper-source' else name
        if adb.text('sha256sum ' + shlex.quote(r + '/' + remote_name)).split()[0] != sha:
            raise RuntimeError('prepared device file changed: ' + remote_name)
    # Atomic mkdir prevents retries after a dropped connection or an earlier failed attempt.
    # HUP is ignored before forking; neither nohup nor a live network connection is needed by the worker.
    worker = './helper apply; rc=$?; printf "%s\\n" "$rc" > result.tmp; mv result.tmp result'
    # Keep the whole launch conditional: failed mkdir must not spawn another worker.
    command = ('cd ' + shlex.quote(r) + ' || exit; mkdir started || exit; trap \'\' HUP; '
               '(sh -c ' + shlex.quote(worker) + ' > run.log 2>&1 < /dev/null) >/dev/null 2>&1 < /dev/null &')
    adb.text(command)
    print('Worker launched. A lost adb reply is not a failed shrink: use status; do not run apply again.')


def status(adb, state):
    p = load(state)
    # Do not run the full helper preflight here: after a partial GPT write it must still be possible to read logs.
    if adb.text('cat /sys/class/block/mmcblk0/device/cid').strip() != p['facts']['CID']:
        raise RuntimeError('status target is another eMMC')
    r = shlex.quote(p['remote'])
    print(adb.text('cd ' + r + ' || exit; if test -f result; then printf "EXIT="; cat result; '
                   'elif test -d started; then echo RUNNING_OR_INTERRUPTED; else echo NOT_STARTED; fi; '
                   'if test -f run.log; then cat run.log; fi'), end='')


def verify(adb, state):
    p = load(state)
    f = facts(adb, p['remote'])
    result = adb.text('cd ' + shlex.quote(p['remote']) + ' && cat result && cat run.log')
    if not result.startswith('0\n') or SUCCESS not in result:
        raise RuntimeError('worker did not record a successful commit; inspect status before recovery')
    if (f['CID'], f['FS_BLOCKS'], f['DATA_SECTORS'], f['GPT_LAST']) != (
            p['facts']['CID'], NEW_BLOCKS, NEW_LAST - FIRST + 1, NEW_LAST):
        raise RuntimeError('post-reboot geometry mismatch; do not install or format')
    for name in ('head', 'tail'):
        command = ('dd if=/dev/block/mmcblk0 bs=512 ' +
                   ('count=34' if name == 'head' else 'skip=61079519 count=33') + ' 2>/dev/null')
        if adb.read(command) != (state / ('candidate.' + name)).read_bytes():
            raise RuntimeError('post-reboot GPT differs from the committed plan')
    # metadata is live F2FS and may change normally; never demand a static post-boot hash for it.
    for name in ('boot_a', 'boot_b', 'trustos_a', 'trustos_b'):
        if adb.text('sha256sum /dev/block/by-name/' + name).split()[0] != p['sha256'][name + '.raw']:
            raise RuntimeError('boot/TrustOS partition changed: ' + name)
    print('Verified after Android reboot: root adb, same eMMC, smaller F2FS, both GPT copies, unchanged boot/TrustOS.')
    print('4 GiB is ready for the normal installer. Android data was not formatted by this tool.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--adb', default='adb', help='path to the host adb executable')
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--adb-address', type=address, help='already enabled rooted TCP adb endpoint')
    target.add_argument('--serial', help='explicit adb serial (USB or an already connected target)')
    parser.add_argument('--state', type=Path, required=True, help='private local plan and recovery-copy directory')
    sub = parser.add_subparsers(dest='action', required=True)
    prepare = sub.add_parser('plan', help='inspect, save recovery copies and prepare; no resizing')
    prepare.add_argument('--helper', type=Path, required=True)
    run = sub.add_parser('apply', help='start the detached shrink and verified GPT commit')
    run.add_argument('--backup-confirmed', action='store_true')
    sub.add_parser('status', help='reconnect and read the worker result; never restart it')
    sub.add_parser('verify', help='verify after manually rebooting back into Android')
    a = parser.parse_args()
    adb = Adb(a.adb, a.serial, a.adb_address)
    adb.connect()
    if a.action == 'plan':
        plan(adb, a.state.resolve(), a.helper.resolve())
    elif a.action == 'apply':
        apply(adb, a.state.resolve(), a.backup_confirmed)
    elif a.action == 'status':
        status(adb, a.state.resolve())
    else:
        verify(adb, a.state.resolve())


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        sys.exit('STOP: ' + str(error))
