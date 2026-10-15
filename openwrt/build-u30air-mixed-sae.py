#!/usr/bin/env python3
"""Rebuild and pin the U30 Air r6 hostapd packages from the reviewed SDK inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
INPUTS = REPO_ROOT / "openwrt/sae-offload/inputs.json"
PATCH_LIST = REPO_ROOT / "openwrt/sae-offload/sdk-patches.sha256"
PATCH = REPO_ROOT / "openwrt/sae-offload/999-unisoc-sae-offload.patch"
PACKAGE_DIR = Path("package/network/services/hostapd")
MAKEFILE = PACKAGE_DIR / "Makefile"
INIT = PACKAGE_DIR / "files/wpad.init"
CUSTOM_PATCH = PACKAGE_DIR / "patches/999-unisoc-sae-offload.patch"
WIFI_ENV = b"        procd_set_param env U30AIR_SAE_OFFLOAD=pmk-first-v1\n"
HOSTAPD_COMMAND = b"\t\tprocd_set_param command /usr/sbin/hostapd -s -g /var/run/hostapd/global\n"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(feed: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(feed), *args], text=True).strip()


def run_logged(command: list[str], sdk: Path, log_path: Path) -> None:
    with log_path.open("a", encoding="utf-8") as log:
        log.write("$ " + " ".join(command) + "\n")
        result = subprocess.run(command, cwd=sdk, stdout=log, stderr=subprocess.STDOUT,
                                env={**os.environ, "LC_ALL": "C"})
    if result.returncode:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-5000:]
        raise RuntimeError(f"SDK command failed ({result.returncode}): {' '.join(command)}\n{tail}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--sdk-archive", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True,
                        help="new directory for two APKs and build provenance")
    parser.add_argument("--jobs", type=int, default=8)
    args = parser.parse_args()
    sdk, archive, output = args.sdk_root.resolve(), args.sdk_archive.resolve(), args.out.resolve()
    inputs = json.loads(INPUTS.read_text(encoding="utf-8"))
    if output.exists():
        raise RuntimeError(f"output directory already exists: {output}")
    if not sdk.is_dir() or not archive.is_file():
        raise RuntimeError("SDK directory and official SDK archive must both exist")
    if sha256(archive) != inputs["sdk_archive_sha256"]:
        raise RuntimeError("official SDK archive SHA-256 mismatch")
    config = sdk / ".config"
    if not config.is_file() or sha256(config) != inputs["sdk_config_sha256"]:
        raise RuntimeError("SDK .config differs from the reviewed package selection")

    feed = sdk / "feeds/base_root"
    if git(feed, "rev-parse", "HEAD") != inputs["sdk_feed_commit"]:
        raise RuntimeError("OpenWrt base feed commit differs from the reviewed package source")
    if git(feed, "status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("hostapd feed checkout must be clean before applying the release patch")
    original_makefile = subprocess.check_output(
        ["git", "-C", str(feed), "show", f"HEAD:{MAKEFILE.as_posix()}"])
    original_init = subprocess.check_output(
        ["git", "-C", str(feed), "show", f"HEAD:{INIT.as_posix()}"])
    if hashlib.sha256(original_makefile).hexdigest() != inputs["sdk_recipe_sha256"]:
        raise RuntimeError("base hostapd recipe hash differs from the official feed pin")
    if hashlib.sha256(original_init).hexdigest() != inputs["sdk_init_sha256"]:
        raise RuntimeError("base wpad init hash differs from the official feed pin")
    recipe_path, init_path, patch_path = feed / MAKEFILE, feed / INIT, feed / CUSTOM_PATCH
    if recipe_path.read_bytes() != original_makefile or init_path.read_bytes() != original_init:
        raise RuntimeError("hostapd recipe/init files do not match the clean feed commit")
    if patch_path.exists():
        raise RuntimeError("custom SAE patch already exists in the SDK; start from a clean SDK feed")
    if sha256(PATCH) != inputs["sae_result_patch_sha256"]:
        raise RuntimeError("SAE hostapd patch differs from its reviewed source pin")

    patch_root = feed / PACKAGE_DIR / "patches"
    declared = []
    for row in PATCH_LIST.read_text(encoding="ascii").splitlines():
        digest, rel = row.split(None, 1)
        rel = rel.strip()
        path = patch_root / rel
        if Path(rel).name != rel or not path.is_file() or sha256(path) != digest:
            raise RuntimeError(f"original OpenWrt patch is missing or changed: {rel}")
        declared.append(rel)
    if len(declared) != 63 or len(set(declared)) != 63:
        raise RuntimeError("the release must pin exactly 63 original hostapd patches")

    marker = b"PKG_RELEASE:=1\n"
    if original_makefile.count(marker) != 1:
        raise RuntimeError("expected exactly one original PKG_RELEASE:=1 field")
    patched_makefile = original_makefile.replace(marker, b"PKG_RELEASE:=6\n", 1)
    if original_init.count(HOSTAPD_COMMAND) != 1 or WIFI_ENV in original_init:
        raise RuntimeError("original wpad init does not match the reviewed hostapd service boundary")
    patched_init = original_init.replace(HOSTAPD_COMMAND, HOSTAPD_COMMAND + WIFI_ENV, 1)
    if patched_init.count(WIFI_ENV) != 1 or patched_init.index(WIFI_ENV) < patched_init.index(HOSTAPD_COMMAND):
        raise RuntimeError("could not scope the result opt-in to the hostapd service instance")

    output.mkdir(parents=True)
    log_path = output / "sdk-build.log"
    log_path.write_text("U30 Air WPA2/WPA3 mixed-mode hostapd package build\n", encoding="utf-8")
    try:
        recipe_path.write_bytes(patched_makefile)
        init_path.write_bytes(patched_init)
        shutil.copy2(PATCH, patch_path)
        run_logged(["make", "package/hostapd/clean", "V=s"], sdk, log_path)
        run_logged(["make", "package/hostapd/compile", "V=s", f"-j{args.jobs}"], sdk, log_path)
        package_dir = sdk / "bin/packages/aarch64_generic/base"
        wpad_name = "wpad-basic-mbedtls-2025.08.26~ca266cc2-r6.apk"
        common_name = "hostapd-common-2025.08.26~ca266cc2-r6.apk"
        wpad, common = package_dir / wpad_name, package_dir / common_name
        for path, key in ((wpad, "wpad_apk_sha256"), (common, "hostapd_common_apk_sha256")):
            if not path.is_file() or sha256(path) != inputs[key]:
                raise RuntimeError(f"built package does not match reviewed hash: {path.name}")
        # .pkgdir retains debug information. The pinned SDK package recipe
        # applies sstrip -z to its APK payload; the rootfs assembler checks
        # that installed payload separately against inputs["wpad_sha256"].
        build_tree = sdk / "build_dir"
        matching_binaries = [p for p in build_tree.rglob("wpad")
                             if p.is_file() and sha256(p) == inputs["wpad_sdk_binary_sha256"]]
        if not matching_binaries:
            raise RuntimeError("clean SDK build did not produce the reviewed wpad binary")
        shutil.copy2(wpad, output / wpad_name)
        shutil.copy2(common, output / common_name)
        shutil.copy2(PATCH, output / PATCH.name)
        shutil.copy2(REPO_ROOT / "openwrt/sae-offload/sdk.config", output / "sdk.config")
        shutil.copy2(PATCH_LIST, output / "sdk-patches.sha256")
        provenance = {
            "schema": 1,
            "official_sdk_archive_sha256": sha256(archive),
            "sdk_feed_commit": inputs["sdk_feed_commit"],
            "sdk_config_sha256": sha256(config),
            "base_hostapd_recipe_sha256": hashlib.sha256(original_makefile).hexdigest(),
            "patched_hostapd_recipe_sha256": hashlib.sha256(patched_makefile).hexdigest(),
            "base_wpad_init_sha256": hashlib.sha256(original_init).hexdigest(),
            "patched_wpad_init_sha256": hashlib.sha256(patched_init).hexdigest(),
            "hostapd_patch_sha256": sha256(PATCH),
            "original_hostapd_patch_count": len(declared),
            "wpad_binary_sha256": inputs["wpad_sdk_binary_sha256"],
            "wpad_apk": {"name": wpad_name, "sha256": sha256(wpad)},
            "hostapd_common_apk": {"name": common_name, "sha256": sha256(common)},
            "sdk_build_log_sha256": sha256(log_path),
        }
        (output / "wifi-build-provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wpad APK: {output / wpad_name}")
        print(f"hostapd-common APK: {output / common_name}")
        print(f"SDK debug wpad binary SHA-256: {inputs['wpad_sdk_binary_sha256']}")
        print(f"build evidence: {output}")
    finally:
        recipe_path.write_bytes(original_makefile)
        init_path.write_bytes(original_init)
        patch_path.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError,
            KeyError, ValueError) as exc:
        print(f"build-u30air-mixed-sae: {exc}", file=sys.stderr)
        raise SystemExit(1)
