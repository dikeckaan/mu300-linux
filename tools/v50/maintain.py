#!/usr/bin/env python3
"""V50 backup, configuration recovery and read-only checks using system OpenSSH."""
import argparse
import hashlib
import io
import json
import re
import shlex
import subprocess
import tarfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

TOP = Path(__file__).resolve().parents[2]
BACKUP_PATHS = (
    'etc/config', 'etc/mu300', 'etc/openclash', 'etc/init.d/openclash',
    'etc/init.d/v50-led-off', 'etc/apk/world', 'opt/mu300/bin/mu300-led',
    'opt/mu300/bin/mu300-v50-led-off',
)


def ssh_args(host):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.:-]+', host):
        raise ValueError('Use user@hostname (no SSH options in the host value)')
    return ['ssh', '-T', '-o', 'StrictHostKeyChecking=ask', host]


def remote(host, command, **kwargs):
    return subprocess.run(ssh_args(host) + [command], check=True, **kwargs)


def safe_name(name):
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError('Unsafe archive path')
    return p.as_posix().removeprefix('./')


def recovery_archive(backup):
    """Restore configuration only; packages, old libraries and init scripts stay out."""
    output = io.BytesIO()
    with tarfile.open(backup, 'r:gz') as src, tarfile.open(fileobj=output, mode='w:gz') as dst:
        for member in src:
            name = safe_name(member.name)
            allowed = (name == 'etc/config/openclash' or name.startswith('etc/openclash/')
                       or name in ('etc/mu300/led.conf', 'etc/mu300/profile'))
            if not allowed or not member.isfile() or name.startswith('etc/openclash/core/'):
                continue
            member.name = name
            member.uid = member.gid = 0
            member.uname = member.gname = 'root'
            member.mode = 0o600
            dst.addfile(member, src.extractfile(member))
    return output.getvalue()


def backup(host, directory):
    directory.mkdir(parents=True, exist_ok=False)
    archive = directory / 'device-config.tar.gz'
    # Missing optional components are omitted without printing their contents.
    paths = ' '.join(shlex.quote(p) for p in BACKUP_PATHS)
    command = f'cd / && set --; for p in {paths}; do [ ! -e "$p" ] || set -- "$@" "$p"; done; tar -czf - "$@"'
    with archive.open('xb') as stream:
        remote(host, command, stdout=stream)
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            safe_name(member.name)
    info = remote(host, 'uname -r; cat /etc/mu300/image-version; apk list --installed',
                  stdout=subprocess.PIPE).stdout.decode(errors='replace')
    (directory / 'packages.txt').write_text(info, encoding='utf-8')
    manifest = {'created_utc': datetime.now(timezone.utc).isoformat(),
                'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
                'contains_credentials': True, 'restore_scope': 'OpenClash settings and LED policy only'}
    (directory / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Private backup written to {directory}. Keep it outside public Git history.')


def restore(host, directory):
    archive = directory / 'device-config.tar.gz'
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != manifest['sha256']:
        raise ValueError('Backup checksum mismatch')
    data = recovery_archive(archive)
    # Caller reinstalls packages first. Do not restart proxying during recovery.
    command = ('test -f /etc/init.d/openclash && test -x /etc/openclash/core/clash_meta || exit 1; '
               '/etc/init.d/openclash stop; tar -xzf - -C / && '
               'uci set openclash.config.enable=0 && uci commit openclash && '
               '/etc/init.d/openclash disable')
    remote(host, command, input=data)
    print('Settings restored. OpenClash remains disabled; validate before enabling it.')


def check(host):
    remote(host, 'uname -r; cat /etc/mu300/image-version; '
           'test -x /opt/mu300/bin/mu300-v50-check || { echo "V50 helper not installed" >&2; exit 1; }; '
           '/opt/mu300/bin/mu300-v50-check')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--host', default='root@192.168.77.1')
    sub = ap.add_subparsers(dest='action', required=True)
    sub.add_parser('check')
    for action in ('backup', 'restore'):
        p = sub.add_parser(action)
        p.add_argument('--directory', type=Path, required=True,
                       help='Private directory; backup refuses to overwrite one')
    args = ap.parse_args()
    try:
        if args.action == 'check':
            check(args.host)
        else:
            directory = args.directory.resolve()
            if args.action == 'backup' and TOP in directory.parents and 'private' not in directory.relative_to(TOP).parts:
                raise ValueError('Inside the repository, put backups under an ignored private/ directory')
            (backup if args.action == 'backup' else restore)(args.host, directory)
    except (ValueError, OSError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        ap.exit(1, f'Maintenance failed: {exc}\n')


if __name__ == '__main__':
    main()
