#!/usr/bin/env python3
"""Connection/session guard for the existing desktop installers' opt-in TCP adb mode.

Only connection checks and staging transfers retry. An unacknowledged shell command is never replayed. The
device installation is a detached job; reconnecting to status does not restart it or arm a boot slot.
"""
import argparse
import ipaddress
import json
import os
import posixpath
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid


class TransportError(RuntimeError):
    pass


class PeerError(RuntimeError):
    pass


def emit(data):
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout.buffer.write(data); sys.stdout.buffer.flush()
    else:
        sys.stdout.write(data.decode('utf-8', 'replace')); sys.stdout.flush()


def endpoint(value):
    try:
        host, port = value.rsplit(':', 1)
        ipaddress.IPv4Address(host)
        if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
            raise ValueError()
    except ValueError:
        raise argparse.ArgumentTypeError('use a literal IPv4 address and port, for example 192.168.0.1:5555') from None
    return value


def wifi_name():
    """Best effort; lack of an OS Wi-Fi utility is not evidence that Wi-Fi stayed unchanged."""
    try:
        if os.name == 'nt':
            r = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True, timeout=5)
            names = re.findall(r'^\s*SSID\s*:\s*(.+?)\s*$', r.stdout.decode('oem', 'replace'), re.M)
        elif shutil.which('nmcli'):
            r = subprocess.run(['nmcli', '-t', '-f', 'ACTIVE,SSID', 'device', 'wifi'], capture_output=True, timeout=5)
            names = [s[4:] for s in r.stdout.decode('utf-8', 'replace').splitlines() if s.startswith('yes:')]
        elif shutil.which('iwgetid'):
            r = subprocess.run(['iwgetid', '-r'], capture_output=True, timeout=5)
            names = r.stdout.decode('utf-8', 'replace').splitlines()
        else:
            return None
        return ' / '.join(sorted(set(names))) if names else None
    except (OSError, subprocess.SubprocessError):
        return None


def write_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('x', encoding='utf-8', newline='\n') as f:
        if os.name == 'posix':
            os.fchmod(f.fileno(), 0o600)
        json.dump(state, f, indent=2)
        f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)


def read_state(path):
    if path.is_symlink():
        raise RuntimeError('wireless state must not be a symlink')
    s = json.loads(path.read_text(encoding='utf-8'))
    if s.get('version') != 1 or not re.fullmatch(r'[0-9a-f]{32}', s.get('id', '')):
        raise RuntimeError('invalid wireless session file')
    if s.get('remote') != '/data/local/tmp/mu300-wireless-' + s['id']:
        raise RuntimeError('invalid wireless staging path')
    return s


FACTS = '''test ! -d /opt/mu300/bin || exit 42
test "$(id -u)" = 0 || exit 43
echo SERIAL=$(getprop ro.serialno)
echo CID=$(cat /sys/class/block/mmcblk0/device/cid)
echo SLOT=$(getprop ro.boot.slot_suffix)
echo MODEL=$(getprop ro.product.model)
echo PRODUCT=$(getprop ro.product.device)
echo COMPLETED=$(getprop sys.boot_completed)
echo BOOT=$(cat /proc/sys/kernel/random/boot_id)
echo BATTERY=$(cat /sys/class/power_supply/battery/capacity 2>/dev/null)
echo STATUS=$(cat /sys/class/power_supply/battery/status 2>/dev/null)
p=0; for f in /sys/class/power_supply/*/online; do test "$(cat "$f" 2>/dev/null)" != 1 || p=1; done
echo POWERED=$p'''


class Session:
    def __init__(self, adb, address, path, timeout=120):
        self.adb, self.address, self.path, self.timeout = adb, address, path, timeout
        self.state = read_state(path) if path.exists() else None
        self.last_notice = None

    def save(self):
        write_state(self.path, self.state)

    def note_wifi(self):
        current = wifi_name()
        previous = self.state.get('wifi') if self.state else None
        if current and previous and current != previous and current != self.last_notice:
            print('WARNING: Wi-Fi changed from ' + previous + ' to ' + current +
                  '. Check the device hotspot and TCP adb address; no new device will be selected automatically.', file=sys.stderr, flush=True)
            self.last_notice = current
            self.state['wifi_notice'] = {'from': previous, 'to': current}
        if self.state and current and current != previous:
            self.state['wifi'] = current
            self.save()

    def call(self, args, timeout=20):
        try:
            return subprocess.run([self.adb, *args], stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as e:
            raise TransportError('adb did not return: ' + type(e).__name__) from None

    def shell(self, command, root=True, timeout=120):
        token = 'MU300-NET-RC-' + uuid.uuid4().hex + ':'
        wrapped = 'sh -c ' + shlex.quote(command) + '; rc=$?; printf "\\n' + token + '%s\\n" "$rc"'
        remote = ('su -c ' if root else 'sh -c ') + shlex.quote(wrapped)
        r = self.call(['-s', self.address, 'shell', remote], timeout)
        data = r.stdout.replace(b'\r\n', b'\n')
        match = re.search(rb'\n' + token.encode('ascii') + rb'([0-9]+)\n?$', data)
        if not match:
            raise TransportError('adb reply was lost or incomplete; command completion is unknown')
        return data[:match.start()], int(match[1])

    def facts(self):
        raw, rc = self.shell(FACTS, timeout=15)
        if rc:
            raise PeerError('rooted Android is required; boot Android, authorize adb and allow su for Shell')
        f = dict(line.split('=', 1) for line in raw.decode('utf-8', 'strict').splitlines() if '=' in line)
        if f.get('COMPLETED') != '1':
            raise TransportError('Android has not finished starting')
        if not f.get('SERIAL') or not re.fullmatch(r'[0-9a-f]{32}', f.get('CID', '')) or f.get('SLOT') not in ('_a', '_b') or not f.get('BOOT'):
            raise PeerError('could not verify Android serial, eMMC identity and boot slot')
        return f

    def wait(self, pinned=True):
        deadline = time.monotonic() + self.timeout
        while True:
            self.note_wifi()
            try:
                self.call(['connect', self.address], timeout=10)
                r = self.call(['-s', self.address, 'get-state'], timeout=10)
                if r.returncode or r.stdout.strip() != b'device':
                    raise TransportError('the explicit endpoint is offline or unauthorized')
                f = self.facts()
                if pinned and self.state and any(f[k] != self.state['identity'][k] for k in ('SERIAL', 'CID', 'SLOT', 'MODEL', 'PRODUCT')):
                    raise PeerError('the address now answers as another device or Android slot; check Wi-Fi and the adb address')
                if self.state and self.state.get('endpoint') != self.address:
                    self.state['endpoint'] = self.address
                    self.save()
                return f
            except TransportError:
                if time.monotonic() >= deadline:
                    raise TransportError('TCP adb is unreachable. Check whether the computer joined a different Wi-Fi, '
                                         'rejoin the device hotspot or a valid route, and check the adb address. '
                                         'An existing device job may still be running: use --adb-status; do not restart writes.') from None
                time.sleep(2)

    def power_warning(self, f):
        capacity = f.get('BATTERY', '')
        powered = (f.get('POWERED') == '1' and f.get('STATUS') != 'Discharging') or f.get('STATUS') == 'Charging'
        if not powered:
            print('WARNING: wireless installation is using battery power (' + (capacity + '%' if capacity.isdecimal() else 'level unknown') +
                  '). Connect a stable charger and keep power connected during installation.', file=sys.stderr, flush=True)
        elif not self.state.get('power_notice'):
            print('Wireless installation: keep the charger connected; Wi-Fi alone does not supply power.', file=sys.stderr, flush=True)
        if capacity.isdecimal() and int(capacity) <= 30:
            print('WARNING: low battery (' + capacity + '%). Connect charging before continuing; do not power off an active device write.', file=sys.stderr, flush=True)
        self.state['power_notice'] = True
        self.save()

    def connect(self, restart=False):
        if self.state and self.state.get('phase') not in ('ready', 'complete'):
            f = self.wait()
            finished = self.job_result()[0] is not None if self.state.get('job') else False
            unknown_foreground = self.state['phase'] == 'uncertain'
            safe_transfer_failure = self.state['phase'] == 'blocked' and not self.state.get('job')
            same_boot = f['BOOT'] == self.state.get('boot')
            if not restart or (same_boot and (unknown_foreground or (not finished and not safe_transfer_failure))):
                raise RuntimeError('a previous wireless session needs review. Use --adb-status. '
                                   'After a finished job, or a manual Android reboot for an unknown foreground command, '
                                   '--adb-restart starts the normal installer again; it does not replay the old command.')
        f = self.wait()
        old = self.state
        sid = uuid.uuid4().hex
        self.state = {'version': 1, 'id': sid, 'remote': '/data/local/tmp/mu300-wireless-' + sid,
                      'identity': {k: f[k] for k in ('SERIAL', 'CID', 'SLOT', 'MODEL', 'PRODUCT')},
                      'endpoint': self.address, 'boot': f['BOOT'], 'wifi': wifi_name(), 'phase': 'ready'}
        if old:
            history = self.path.parent / 'wireless-history'
            history.mkdir(exist_ok=True)
            write_state(history / (old['id'] + '.json'), old)
        self.save()
        # The adb shell owns the staging directory, so the original push/pull and backup code still works.
        r = self.call(['-s', self.address, 'shell', 'umask 077; mkdir ' + self.state['remote']])
        if r.returncode:
            raise RuntimeError('could not create the private wireless staging directory')
        print('Connected to the specified rooted Android device over TCP adb.', flush=True)
        if not self.state['wifi']:
            print('Wi-Fi name is unavailable on this host. If disconnected, check the current Wi-Fi and adb address.', flush=True)
        self.power_warning(f)

    def guard(self):
        if not self.state:
            raise RuntimeError('connect a wireless installation session first')
        if self.state.get('phase') not in ('ready', 'installed', 'complete'):
            raise RuntimeError('wireless session is paused for review; use --adb-status, not another write')
        f = self.wait()
        if f['BOOT'] != self.state['boot']:
            raise PeerError('Android rebooted during this session; review --adb-status and start a fresh checked installation')
        return f

    def notices(self):
        # Also show queued changes at visible installer checkpoints. A quiet probe may redirect its stderr.
        notice = self.state.pop('wifi_notice', None)
        if notice:
            print('WARNING: the connected Wi-Fi changed from ' + notice['from'] + ' to ' + notice['to'] +
                  '. Check the device hotspot and adb address.', flush=True)
            self.save()

    def check(self):
        f = self.guard()
        self.notices()
        self.power_warning(f)

    def job_result(self):
        job = self.state.get('job')
        if not job:
            return None, b'No detached device installation has been started.\n'
        if not re.fullmatch(r'/data/adb/mu300-wireless-[0-9a-f]{32}', job):
            raise RuntimeError('invalid device job path')
        out, rc = self.shell('cd ' + shlex.quote(job) + ' || exit; '
                             'if test -f result; then printf "RESULT="; cat result; else echo RUNNING_OR_INTERRUPTED; fi; '
                             'test ! -f run.log || cat run.log')
        if rc:
            return None, b'Device job directory is unavailable. Inspect before restarting.\n'
        first, _, log = out.partition(b'\n')
        return (int(first[7:]) if re.fullmatch(rb'RESULT=[0-9]+', first) else None), log

    def install(self):
        self.guard()
        if self.state.get('job'):
            raise RuntimeError('a device job already exists; use --adb-status')
        job = '/data/adb/mu300-wireless-' + self.state['id']
        stage = self.state['remote']
        self.state.update(job=job, phase='installing')
        self.save()  # persist the job identity before dispatch; never replay after a lost launch reply
        setup = ('umask 077; mkdir ' + job + ' && cp ' + stage + '/android-install.sh ' + job + '/driver.sh && '
                 'test "$(sha256sum ' + stage + '/android-install.sh | cut -d \' \' -f 1)" = '
                 '"$(sha256sum ' + job + '/driver.sh | cut -d \' \' -f 1)"')
        _, rc = self.shell(setup)
        if rc:
            raise RuntimeError('device worker preparation failed; inspect --adb-status')
        # A per-boot name avoids racing another worker while trying to delete a stale lock after reboot.
        worker = ('cd ' + job + ' || exit; '
                  'lk=/data/adb/mu300-wireless-install-$(cat /proc/sys/kernel/random/boot_id).lock; '
                  'if mkdir "$lk"; then '
                  'MU300_ADB_WORK_T=' + stage + ' MU300_LOCK_DIR=/data/adb sh ./driver.sh; rc=$?; '
                  'rmdir "$lk"; else echo "Another wireless installer may be active"; rc=79; fi; '
                  'printf "%s\\n" "$rc" > result.tmp; mv result.tmp result; sync')
        launch = ('cd ' + job + ' || exit; mkdir started || exit; trap \'\' HUP; '
                  '(sh -c ' + shlex.quote(worker) + ' > run.log 2>&1 < /dev/null) >/dev/null 2>&1 < /dev/null &')
        try:
            _, rc = self.shell(launch)
            if rc:
                raise RuntimeError('device job launch was refused; inspect --adb-status')
        except TransportError:
            pass  # launch may have succeeded; poll this exact job instead of sending launch again
        self.poll()

    def poll(self):
        deadline = time.monotonic() + 3600
        power_notice = time.monotonic()
        while time.monotonic() < deadline:
            f = self.wait()
            if f['BOOT'] != self.state['boot']:
                raise RuntimeError('Android rebooted while the job was pending; inspect --adb-status before restarting')
            if time.monotonic() - power_notice >= 60:
                self.power_warning(f)
                power_notice = time.monotonic()
            try:
                rc, log = self.job_result()
            except TransportError:
                continue
            if rc is not None:
                self.state['phase'] = 'installed' if rc == 0 and b'MU300-INSTALL-OK' in log else 'failed'
                self.save()
                emit(log)
                if self.state['phase'] != 'installed':
                    raise RuntimeError('device installation failed; boot image/slot arming has not been run by the host')
                return
            time.sleep(2)
        raise RuntimeError('device job is still pending. Use --adb-status; no second worker was launched')

    def status(self):
        f = self.wait()
        self.notices()
        self.power_warning(f)
        rc, log = self.job_result()
        print('Session phase: ' + self.state['phase'] + '; device result: ' + (str(rc) if rc is not None else 'unknown/pending'), flush=True)
        if self.state['phase'] == 'uncertain':
            print('A foreground command lost its reply. Do not replay it. Review logs and reboot Android before an explicit restart.', flush=True)
        emit(log)

    def proxy(self, args):
        if args[:1] == ['-s']:
            if len(args) < 3 or args[1] != self.address:
                raise PeerError('the installer tried to select a different adb target')
            args = args[2:]
        if not args or args[0].startswith('-') or args[0] in ('tcpip', 'disconnect', 'kill-server'):
            raise RuntimeError('this adb operation is not part of the pinned wireless installation')
        try:
            self.guard()
        except (TransportError, PeerError):
            if self.state and self.state['phase'] in ('ready', 'installed'):
                self.state['phase'] = 'blocked'; self.save()
            raise
        if args[0] == 'shell':
            command = args[1] if len(args) == 2 else ' '.join(shlex.quote(a) for a in args[1:])
            parts = shlex.split(command)
            if parts == ['su', '-c', 'sh ' + self.state['remote'] + '/android-install.sh']:
                self.install(); return 0
            try:
                output, rc = self.shell(command, root=False, timeout=600)
            except TransportError:
                self.state['phase'] = 'uncertain'; self.save()
                raise
            if rc and re.search(r'\bof=/dev/block/', command):
                self.state['phase'] = 'blocked'; self.save()
                raise RuntimeError('device write returned failure; inspect the medium before another installation')
            emit(output)
            return rc
        if args[0] in ('push', 'pull'):
            if args[0] == 'push' and not posixpath.normpath(args[-1]).startswith('/data/local/tmp/'):
                raise RuntimeError('wireless push is restricted to staging files, never a block device')
            for attempt in range(3):
                try:
                    self.wait()
                    r = self.call(['-s', self.address, *args], timeout=600)
                    if not r.returncode:
                        emit(r.stdout)
                        return 0
                except TransportError:
                    pass
                time.sleep(1)
            self.state['phase'] = 'blocked'; self.save()
            raise RuntimeError('staging transfer failed. Check Wi-Fi and the adb address; no write command was replayed')
        try:
            r = self.call(['-s', self.address, *args], timeout=30)
        except TransportError:
            if args[0] == 'reboot' and self.state['phase'] == 'complete':
                print('WARNING: installation was written, but the reboot reply was lost. Check the device before rebooting manually; no reboot was retried.', flush=True)
                return 0
            raise
        emit(r.stdout)
        if args[0] == 'reboot':
            print('Rejoin the device Wi-Fi after reboot. Linux uses its SSH/LuCI address; Android TCP adb may use another address.', flush=True)
            if r.returncode and self.state['phase'] == 'complete':
                print('WARNING: reboot was not acknowledged. Check the device before rebooting manually; installation writes are complete.', flush=True)
                return 0
        return r.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--adb', required=True)
    p.add_argument('--address', type=endpoint)
    p.add_argument('--state', required=True, type=Path)
    p.add_argument('--timeout', type=int, default=120)
    p.add_argument('--restart', action='store_true')
    p.add_argument('action', choices=('connect', 'work', 'check', 'status', 'finish', 'proxy'))
    p.add_argument('args', nargs=argparse.REMAINDER)
    a = p.parse_args()
    if not 1 <= a.timeout <= 600:
        p.error('--timeout must be 1..600 seconds')
    old = read_state(a.state) if a.state.exists() else None
    if a.action != 'connect' and not old:
        raise RuntimeError('no saved wireless session exists in this work directory')
    address = a.address or (old or {}).get('endpoint')
    if not address:
        p.error('--address is required for a new session')
    session = Session(a.adb, address, a.state, a.timeout)
    if a.action == 'connect':
        session.connect(a.restart)
    elif a.action == 'work':
        print(read_state(a.state)['remote'])
    elif a.action == 'status':
        session.status()
    elif a.action == 'check':
        session.check()
    elif a.action == 'finish':
        session.check(); session.state['phase'] = 'complete'; session.save()
    else:
        args = a.args[1:] if a.args[:1] == ['--'] else a.args
        return session.proxy(args)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print('WIRELESS ADB: ' + str(error), file=sys.stderr)
        sys.exit(125)
