#!/usr/bin/env python3
"""Check publishable Git paths and common credential formats, without printing secret values."""
import argparse
import re
import subprocess
from pathlib import Path

TOP = Path(__file__).resolve().parents[2]
SECRET_PATTERNS = (
    rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    rb'gh[pousr]_[A-Za-z0-9]{30,}', rb'github_pat_[A-Za-z0-9_]{40,}',
    rb'AKIA[0-9A-Z]{16}',
)


def inspect(path, data):
    parts = Path(path).parts
    problems = []
    if any(p in ('private', 'work', 'v50-backup', 'v50-openclash', 'v50-proxy', '__pycache__') for p in parts):
        problems.append('private or generated directory')
    if Path(path).name in ('.env', 'known_hosts', 'controller-secret.txt'):
        problems.append('local credentials or host identity')
    if path.endswith(('.pem', '.key', '.local.json', '.local.conf')):
        problems.append('private/local file extension')
    if any(re.search(pattern, data) for pattern in SECRET_PATTERNS):
        problems.append('credential pattern')
    return problems


def audit(root=TOP):
    result = subprocess.run(['git', '-C', str(root), 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
                            check=True, capture_output=True)
    paths = sorted(set(p.decode('utf-8') for p in result.stdout.split(b'\0') if p))
    errors = []
    for path in paths:
        file = root / path
        if file.is_file():
            for problem in inspect(path, file.read_bytes()):
                errors.append(f'{path}: {problem}')
    print(f'Audited {len(paths)} publishable paths; {len(errors)} findings.')
    for error in errors:
        print(error)
    print('Heuristic scan only. Review git diff --cached and release contents before publishing.')
    return bool(errors)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=TOP)
    args = ap.parse_args()
    raise SystemExit(audit(args.root.resolve()))


if __name__ == '__main__':
    main()
