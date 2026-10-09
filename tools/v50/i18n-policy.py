#!/usr/bin/env python3
"""The V50 translation policy for the control panel's catalogs: only zh_Hans is translated, every other catalog
carries the English msgid.

    python3 tools/v50/i18n-policy.py            make every catalog obey the policy (the usual command)
    python3 tools/v50/i18n-policy.py check      report the catalogs that do not; exit 1 if there is any
    python3 tools/v50/i18n-policy.py --root DIR work on another copy of the app (the tests use it)

One command keeps po/*/mu300.po in step with the messages the app uses, so an upstream merge never leaves the
catalogs to be resolved by hand:

  1. the stale msgids go, the missing ones arrive, the entries are ordered by first use, with the same escaping
     and layout tools/luci-i18n.py update writes;
  2. zh_Hans keeps its translations; a message it does not have yet stays empty and is printed as one that needs
     a translator;
  3. every other catalog (tr, zh_Hant, ...) gets msgstr = msgid, so LuCI shows the English message.

An English msgstr is the msgid itself, so the %s/%d/%% placeholders tools/luci-i18n.py checks match by
construction; check therefore only compares each catalog with what apply would write. apply exits 1 when a
zh_Hans message still needs a translator (check reports it too), so a merge is never called done by accident.
"""
import argparse
import importlib.util
import sys
from pathlib import Path

TOP = Path(__file__).resolve().parents[2]
TRANSLATED = 'zh_Hans'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


luci = load('luci_i18n', TOP / 'tools' / 'luci-i18n.py')


def read(root, lang):
    """(header lines, entries) of po/<lang>/mu300.po, or the header of a new catalog and no entries."""
    path = luci.po_path(root, lang)
    if path.is_file():
        return luci.read_po(path)
    return (['msgid ""', 'msgstr ""', '"Content-Type: text/plain; charset=UTF-8\\n"',
             f'"Language: {lang}\\n"'], [])


def desired(root, lang, messages):
    """The exact text the policy wants for po/<lang>/mu300.po, or nothing to change."""
    header, entries = read(root, lang)
    have = {e['msgid']: e for e in entries}
    out = header[:]
    for message in messages:
        entry = have.get(message)
        out += [''] + (entry['comments'] if entry else []) + [f'msgid "{luci.po_escape(message)}"']
        if lang == TRANSLATED:
            raw = entry['raw_msgstr'] if entry and entry['msgstr'] else ['""']
        else:
            raw = [f'"{luci.po_escape(message)}"']
        out += ['msgstr ' + raw[0]] + raw[1:]
    return '\n'.join(out) + '\n'


def messages_of(root):
    """Every message the app uses, once, in order of first use (what luci-i18n.py update orders by)."""
    return list(luci.extract(root).where)


def untranslated(root, messages):
    entries = {e['msgid']: e for e in read(root, TRANSLATED)[1]}
    return [m for m in messages if not (entries.get(m) or {}).get('msgstr')]


def deviations(root, lang, messages):
    """Why po/<lang>/mu300.po is not what the policy wants, for a readable report (empty when it is)."""
    _, entries = read(root, lang)
    have = {e['msgid']: e for e in entries}
    reasons = []
    for message in messages:
        entry = have.get(message)
        if entry is None:
            reasons.append(f'missing "{message}"')
        elif lang == TRANSLATED:
            if not entry['msgstr']:
                reasons.append(f'untranslated "{message}"')
        elif entry['msgstr'] != message:
            reasons.append(f'msgstr is not the English msgid for "{message}"')
    reasons += [f'stale "{e["msgid"]}"' for e in entries if e['msgid'] and e['msgid'] not in messages]
    return reasons


def rel(root, path):
    return path.relative_to(root).as_posix()


def apply(root):
    messages = messages_of(root)
    written = 0
    for lang in luci.langs(root):
        path = luci.po_path(root, lang)
        text = desired(root, lang, messages)
        if not path.is_file() or path.read_text(encoding='utf-8') != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding='utf-8')
            written += 1
    todo = untranslated(root, messages)
    print(f'{written} catalog(s) written; {len(todo)} {TRANSLATED} message(s) still need a translation.')
    for message in todo:
        print(f'  translate: {message}')
    return bool(todo)


def check(root):
    messages = messages_of(root)
    problems = []
    for lang in luci.langs(root):
        path = luci.po_path(root, lang)
        if not path.is_file():
            problems.append(f'{rel(root, path)}: no catalog')
            continue
        if path.read_text(encoding='utf-8') == desired(root, lang, messages):
            continue
        reasons = deviations(root, lang, messages)
        shown = '; '.join(reasons[:8]) if reasons else 'the entry order or the escaping differs from apply'
        more = f'; ... and {len(reasons) - 8} more' if len(reasons) > 8 else ''
        problems.append(f'{rel(root, path)}: {shown}{more}')
    return problems


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('action', nargs='?', choices=('apply', 'check'), default='apply',
                    help='apply (default): write the catalogs; check: report and exit 1 when they differ')
    ap.add_argument('--root', type=Path, help='the app directory (default: openwrt/luci-app-mu300)')
    args = ap.parse_args(argv)
    root = (args.root or luci.APP).resolve()
    try:
        if args.action == 'apply':
            return 1 if apply(root) else 0
        problems = check(root)
    except (ValueError, OSError) as exc:
        ap.exit(1, f'i18n-policy failed: {exc}\n')
    for problem in problems:
        print(problem)
    if problems:
        print(f'{len(problems)} catalog(s) do not obey the policy', file=sys.stderr)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

