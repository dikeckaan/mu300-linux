#!/usr/bin/env python3
"""Patch the supported OpenClash check_mod guard; refuse unknown source layouts."""
import argparse
from pathlib import Path


def patch(text):
    # Only this guard may be relaxed, and only after the caller verifies real TUN operation.
    old = 'check_mod()\n{\n'
    guard = '   if [ "$1" = tun ] && [ -c /dev/net/tun ]; then\n      return 0\n   fi\n'
    new = old + guard
    if new in text and text.count(old) == 1:
        return text
    if text.count(old) != 1:
        raise ValueError('Unsupported OpenClash init script; inspect check_mod before patching')
    return text.replace(old, new, 1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path)
    a = ap.parse_args()
    if a.source.resolve() == a.output.resolve():
        ap.error('Use a separate output; keep the original for rollback')
    try:
        result = patch(a.source.read_text(encoding='utf-8'))
    except ValueError as exc:
        ap.error(str(exc))
    a.output.write_text(result, encoding='utf-8', newline='\n')


if __name__ == '__main__':
    main()
