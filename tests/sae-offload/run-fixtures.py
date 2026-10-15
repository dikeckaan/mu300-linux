#!/usr/bin/env python3
"""Compile and run fixtures extracted from the actual hostapd patch."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def run(command: list[str], expected: int = 0) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode != expected:
        raise RuntimeError(f"command returned {result.returncode}, expected {expected}: {command}\n{result.stdout}")
    return result


def main() -> None:
    compiler = shutil.which("cc") or shutil.which("gcc") or shutil.which("clang")
    if not compiler:
        raise RuntimeError("a C compiler is required for the actual-patch SAE fixtures")
    tests = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix="u30air-sae-fixtures-") as temporary:
        work = Path(temporary)
        for generator in ("check-sae-result-parser.py", "check-sae-bridge-state.py"):
            run([sys.executable, str(tests / generator), str(work)])
        pairs = (
            ("sae-result-parser-check.c", "sae-result-parser-check", True),
            ("sae-bridge-state-check.c", "sae-bridge-state-check", True),
            ("sae-bridge-state-old-guard.c", "sae-bridge-state-old-guard", False),
        )
        for source_name, binary_name, positive in pairs:
            source, binary = work / source_name, work / binary_name
            run([compiler, "-std=c11", "-D_GNU_SOURCE", "-Wall", "-Wextra", "-Werror",
                 "-fsanitize=address,undefined", "-fno-omit-frame-pointer", "-g",
                 str(source), "-o", str(binary)])
            result = run([str(binary)], expected=0 if positive else 1)
            if positive and "PASS:" not in result.stdout:
                raise RuntimeError(f"fixture did not report success: {source_name}\n{result.stdout}")
            if not positive and "FAIL: PSK accepts residual PWE2" not in result.stdout:
                raise RuntimeError(f"old-guard negative control failed for another reason:\n{result.stdout}")
            print(result.stdout.strip())
        print("PASS: old unconditional PWE guard is detected by the negative control")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"run-sae-offload-fixtures: {exc}", file=sys.stderr)
        raise SystemExit(1)
