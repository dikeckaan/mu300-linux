"""Compile the actual metadata parser from the hostapd patch, with malformed IE input."""
import random
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from helpers import TOP, ShellTest

PATCH = TOP / 'openwrt/patches/hostapd/990-u30-sae-offload.patch'


class SaeMetadata(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which('cc')
        if not cc:
            raise unittest.SkipTest('no native C compiler')
        cls.work = tempfile.TemporaryDirectory(prefix='u30-sae-parser-')
        work = Path(cls.work.name)
        patch = PATCH.read_text()
        added = patch[patch.index('+++ b/src/ap/u30_sae_offload.h'):].splitlines()[2:]
        lines = []
        for line in added:
            if line.startswith('--- '): break
            if line.startswith('+'): lines.append(line[1:])
        (work / 'u30_sae_offload.h').write_text('\n'.join(lines) + '\n')
        (work / 'check.c').write_text(r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
#define WLAN_EID_VENDOR_SPECIFIC 221
#define os_memcmp memcmp
#include "u30_sae_offload.h"
int main(void) {
    u8 bytes[4];
    if (u30_sae_get_key(NULL, 0)) return 2;
    while (fread(bytes, 1, 4, stdin) == 4) {
        size_t len = bytes[0] | ((uint32_t) bytes[1] << 8) |
            ((uint32_t) bytes[2] << 16) | ((uint32_t) bytes[3] << 24);
        u8 *buf;
        const u8 *key;
        if (len > 65535) return 3;
        buf = malloc(len ? len : 1);
        if (!buf || fread(buf, 1, len, stdin) != len) return 4;
        key = u30_sae_get_key(buf, len);
        printf("%ld\n", key ? (long) (key - buf) : -1L);
        free(buf);
    }
    return 0;
}
''')
        cls.exe = work / 'check'
        # Sanitizers are optional on desktop hosts whose compiler has no runtime library.
        # CI can require them with MU300_TEST_UBSAN=1.
        probe = subprocess.run([cc, '-fsanitize=undefined', '-x', 'c', '-', '-o', str(work / 'probe')],
                               input='int main(void) { return 0; }', capture_output=True, text=True)
        if os.environ.get('MU300_TEST_UBSAN') == '1' and probe.returncode:
            raise AssertionError('UBSan was required but its compiler/runtime is unavailable: ' + probe.stderr)
        flags = ['-fsanitize=undefined', '-fno-sanitize-recover=all'] if not probe.returncode else []
        r = subprocess.run([cc, '-std=c99', '-Wall', '-Wextra', '-Werror'] + flags + [
                            str(work / 'check.c'), '-o', str(cls.exe)], capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(r.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def parse(self, records):
        data = b''.join(struct.pack('<I', len(x)) + x for x in records)
        r = subprocess.run([str(self.exe)], input=data, capture_output=True, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        return [int(x) for x in r.stdout.splitlines()]

    def test_only_one_complete_trailing_private_element(self):
        key = bytes([221, 52]) + bytes.fromhex('4045da04') + bytes(range(48))
        prefix = bytes([0, 3]) + b'abc'
        records = [b'', b'\xdd', key, prefix + key, key[:-1], key + b'\x00',
                   key + prefix, key + key, key[:5] + b'\x05' + key[6:],
                   b'\x00\xff' + key, prefix]
        self.assertEqual(self.parse(records), [-1, -1, 6, 11, -1, -1, -1, -1, -1, -1, -1])

    def test_every_truncation_and_random_malformed_inputs(self):
        key = bytes([221, 52]) + bytes.fromhex('4045da04') + bytes(range(48))
        rng = random.Random(2355)
        records = [key[:n] for n in range(54)]
        records += [rng.randbytes(rng.randrange(0, 2048)) for _ in range(500)]
        self.assertEqual(self.parse(records), [-1] * len(records))

    def test_firmware_request_gates_and_vendor_contract(self):
        # Run the actual firmware helper with fake driver/crypto calls; all credentials are synthetic.
        added = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
        start = added.index('static int u30_sae_configure_fw(')
        helper = added[start:added.index('\n}\n', start) + 3]
        source = Path(self.work.name) / 'firmware.c'
        source.write_text(r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <assert.h>
typedef uint8_t u8;
#define WPA_KEY_MGMT_SAE 1024
#define MGMT_FRAME_PROTECTION_REQUIRED 2
#define WPA_DRIVER_FLAGS2_AP_SME 1
#define NESTED_ATTR_USED 1
#define MSG_INFO 3
#define MSG_ERROR 4
#define os_strlen strlen
#define os_memcmp_const memcmp
#define os_memcpy memcpy
#define os_memset memset
#define wpa_printf(...) ((void) 0)
struct conf {
    struct { const char *wpa_passphrase; } ssid;
    int u30_sae_offload, wpa_key_mgmt, ieee80211w, sae_pwe;
    void *sae_passwords;
};
struct iface { unsigned long drv_flags2; };
struct hostapd_data {
    struct conf *conf;
    struct iface *iface;
    int u30_sae_configured;
    u8 u30_sae_key_fingerprint[32];
};
static u8 saved[84];
static size_t saved_len;
static int calls, result;
static void put(u8 *p, uint32_t n, size_t len) {
    size_t i; for (i=0; i<len; i++) p[i] = n >> (8*i);
}
#define WPA_PUT_LE16(p,n) put((p),(n),2)
#define WPA_PUT_LE32(p,n) put((p),(n),4)
static void forced_memzero(void *p, size_t n) { memset(p, 0, n); }
static int sha256_vector(size_t n, const u8 **p, const size_t *len, u8 *out) {
    size_t i; (void) n; memset(out, 0, 32);
    for (i=0; i<len[0]; i++) out[i%32] ^= p[0][i];
    return 0;
}
static int hostapd_drv_vendor_cmd(struct hostapd_data *h, unsigned int oui,
    unsigned int cmd, u8 *data, size_t len, int nested, void *reply) {
    (void) h; (void) reply;
    assert(oui == 0x001374 && cmd == 43 && nested == 1);
    assert(len <= sizeof(saved));
    memcpy(saved, data, len); saved_len=len; calls++;
    return result;
}
''' + helper + r'''
int main(void) {
    struct conf c = {0}; struct iface i = {0};
    struct hostapd_data h = { .conf=&c, .iface=&i };
    size_t n, group;
    assert(u30_sae_configure_fw(&h) == 0 && calls == 0);
    c.u30_sae_offload=1; c.wpa_key_mgmt=WPA_KEY_MGMT_SAE;
    c.ieee80211w=2; c.ssid.wpa_passphrase="synthetic-test-password";
    assert(u30_sae_configure_fw(&h) == 0 && calls == 1 && h.u30_sae_configured);
    n=strlen(c.ssid.wpa_passphrase); group=(n+7)&~(size_t)3;
    assert(saved[0] == n+4 && saved[1] == 0 && saved[2] == 8 && saved[3] == 0);
    assert(memcmp(saved+4, c.ssid.wpa_passphrase, n) == 0);
    assert(saved[group] == 8 && saved[group+2] == 6 && saved[group+4] == 19);
    assert(saved[group+8] == 8 && saved[group+10] == 7);
    assert(memcmp(saved+group+12, "\xff\xff\xff\xff", 4) == 0 && saved_len == group+16);
    assert(u30_sae_configure_fw(&h) == 0 && calls == 1);
    c.sae_pwe=2; assert(u30_sae_configure_fw(&h) < 0 && calls == 1); c.sae_pwe=0;
    c.ieee80211w=1; assert(u30_sae_configure_fw(&h) < 0 && calls == 1); c.ieee80211w=2;
    c.wpa_key_mgmt |= 1; assert(u30_sae_configure_fw(&h) < 0 && calls == 1); c.wpa_key_mgmt=WPA_KEY_MGMT_SAE;
    i.drv_flags2=1; assert(u30_sae_configure_fw(&h) < 0 && calls == 1); i.drv_flags2=0;
    c.ssid.wpa_passphrase="short"; assert(u30_sae_configure_fw(&h) < 0 && calls == 1);
    c.ssid.wpa_passphrase="another-synthetic-password"; result=-1;
    assert(u30_sae_configure_fw(&h) < 0 && calls == 2 && !h.u30_sae_configured);
    result=0; assert(u30_sae_configure_fw(&h) == 0 && calls == 3 && h.u30_sae_configured);
    return 0;
}
''')
        exe = source.with_suffix('')
        r = subprocess.run([shutil.which('cc'), '-std=c99', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(exe)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = subprocess.run([str(exe)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class SaeSdkBuild(ShellTest):
    def setUp(self):
        super().setUp()
        self.sdk = self.tmp / 'sdk'
        self.package = self.sdk / 'package/network/services/hostapd'
        self.package.mkdir(parents=True)
        (self.package / 'Makefile').write_text(
            'PKG_SOURCE_VERSION:=ca266cc24d8705eb1a2a0857ad326e48b1408b20\nPKG_RELEASE:=5\n')
        self.stub('make', '''echo "$*" >> "$STUBLOG/calls"
case "$*" in *hostapd/compile*)
    mkdir -p bin/packages/aarch64_generic/base
    for name in hostapd-common wpad-basic-openssl; do
        echo fixture > "bin/packages/aarch64_generic/base/$name-fixture-r6.apk"
    done ;;
esac''')

    def build(self):
        return self.script(['sh'], TOP / 'openwrt/build-u30-sae.sh', self.sdk, self.tmp / 'out')

    def test_recipe_revision_and_matching_package_pair(self):
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('PKG_RELEASE:=6', (self.package / 'Makefile').read_text())
        self.assertEqual((self.package / 'patches' / PATCH.name).read_bytes(), PATCH.read_bytes())
        self.assertEqual(sorted(p.name for p in (self.tmp / 'out').glob('*.apk')),
                         ['hostapd-common-fixture-r6.apk', 'wpad-basic-openssl-fixture-r6.apk'])
        self.assertEqual((self.tmp / 'calls').read_text().splitlines(),
                         ['defconfig', 'package/network/services/hostapd/clean',
                          '-j4 package/network/services/hostapd/compile V=s'])
        self.assertEqual(self.build().returncode, 0)

    def test_different_source_is_rejected_before_mutation(self):
        recipe = self.package / 'Makefile'
        recipe.write_text('PKG_SOURCE_VERSION:=unsupported\nPKG_RELEASE:=5\n')
        self.assertNotEqual(self.build().returncode, 0)
        self.assertFalse((self.package / 'patches').exists())
        self.assertFalse((self.tmp / 'calls').exists())
        self.assertFalse((self.sdk / '.config').exists())

    def test_official_sdk_feed_layout_and_revision(self):
        feed = self.sdk / 'feeds/base/network/services/hostapd'
        feed.parent.mkdir(parents=True)
        self.package.rename(feed)
        recipe = feed / 'Makefile'
        recipe.write_text(recipe.read_text().replace('PKG_RELEASE:=5', 'PKG_RELEASE:=1'))
        link = self.sdk / 'package/feeds/base/hostapd'
        link.parent.mkdir(parents=True)
        link.symlink_to(feed, target_is_directory=True)
        r = self.build()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('PKG_RELEASE:=6', recipe.read_text())
        self.assertEqual((feed / 'patches' / PATCH.name).read_bytes(), PATCH.read_bytes())
        self.assertIn('package/feeds/base/hostapd/compile', (self.tmp / 'calls').read_text())

    def test_missing_feed_gives_setup_instructions_without_mutation(self):
        (self.package / 'Makefile').unlink()
        r = self.build()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('scripts/feeds install -p base hostapd', r.stderr)
        self.assertFalse((self.sdk / '.config').exists())
        self.assertFalse((self.tmp / 'calls').exists())

    def test_unrecorded_revision_is_rejected(self):
        recipe = self.package / 'Makefile'
        original = recipe.read_text().replace('PKG_RELEASE:=5', 'PKG_RELEASE:=2')
        recipe.write_text(original)
        self.assertNotEqual(self.build().returncode, 0)
        self.assertEqual(recipe.read_text(), original)
        self.assertFalse((self.sdk / '.config').exists())

    def test_conflicting_local_patch_is_not_overwritten(self):
        target = self.package / 'patches' / PATCH.name
        target.parent.mkdir()
        target.write_text('existing private changes')
        self.assertNotEqual(self.build().returncode, 0)
        self.assertEqual(target.read_text(), 'existing private changes')
        self.assertFalse((self.sdk / '.config').exists())


if __name__ == '__main__':
    unittest.main()
