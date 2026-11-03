/* kanoqwq's native test of mu300-f2fs-online.c (installer/device/test-f2fs-online.c): superblock decoding, target
 * checks and the GPT write/readback primitives on a temporary file. cc test-f2fs-online.c && ./a.out */
#define main device_tool_main
#include "mu300-f2fs-online.c"
#undef main
#include <assert.h>

static void put32(unsigned char *p, uint32_t n)
{
    for (int i = 0; i < 4; i++) p[i] = n >> (i * 8);
}

static void put64(unsigned char *p, uint64_t n)
{
    put32(p, n); put32(p + 4, n >> 32);
}

int main(void)
{
    unsigned char raw[8192] = {0}, saved[8192];
    unsigned char *a = raw + 1024;
    struct geometry g;
    put32(a, 0xf2f52010); put32(a + 16, 12); put32(a + 20, 9);
    put32(a + 24, 1); put64(a + 36, 29008896);
    memcpy(raw + 5120, a, SB_BYTES); memcpy(saved, raw, sizeof(raw));
    assert(!decode(raw, &g)); assert(g.blocks == 29008896 && g.section_blocks == 512);
    assert(!validate_target(&g, 29008896, 12231680, 4ULL << 30));
    assert(validate_target(&g, 29008895, 12231680, 0));
    assert(validate_target(&g, 29008896, 12231681, 0));
    assert(validate_target(&g, 29008896, 0, 0));
    assert(validate_target(&g, 29008896, 29008896, 0));
    assert(validate_target(&g, 29008896, 12231680, 50ULL << 30));
    assert(validate_target(&g, 29008896, 12231680, UINT64_MAX));
    uint64_t n;
    assert(!parse_count("12231680", &n) && n == 12231680);
    const char *bad[] = {"", "0", "0123", "-1", "+1", "1G", " 123", "18446744073709551616"};
    for (unsigned i = 0; i < sizeof(bad)/sizeof(*bad); i++) assert(parse_count(bad[i], &n));
    for (int copy = 0; copy < 2; copy++) {
        memcpy(raw, saved, sizeof(raw)); raw[(copy ? 5120 : 1024)] ^= 1;
        assert(decode(raw, &g));
    }
    for (uint32_t sections = 0; sections <= 65537; sections += 65537) {
        memcpy(raw, saved, sizeof(raw)); put32(raw + 1024 + 24, sections);
        memcpy(raw + 5120, raw + 1024, SB_BYTES); assert(decode(raw, &g));
    }
    /* The copies may differ in the kernel's version string and the crc that covers it, and in nothing else: every
     * byte of either copy changed alone is refused, but for those. */
    for (int copy = 0; copy < 2; copy++)
        for (unsigned i = 0; i < SB_BYTES; i++) {
            bool ignored = (i >= SB_VERSION && i < SB_VERSION + SB_VERSION_BYTES) || i >= SB_CRC;
            memcpy(raw, saved, sizeof(raw)); raw[(copy ? 5120 : 1024) + i] ^= 0x5a;
            assert(!decode(raw, &g) == ignored);
            if (ignored) assert(g.blocks == 29008896 && g.section_blocks == 512);
        }
    /* what a U30 Air had: the primary names the running kernel, the backup an older build (and, with sb_chksum, the
     * crcs differ); the geometry is the primary's and the same in both */
    memcpy(raw, saved, sizeof(raw));
    memcpy(raw + 1024 + SB_VERSION, "5.4.254-android12-9-g35e7b2480b7a", 33);
    memcpy(raw + 5120 + SB_VERSION, "5.4.254-android12-9-g7463324543ed", 33);
    put32(raw + 1024 + SB_CRC, 0x11111111); put32(raw + 5120 + SB_CRC, 0x22222222);
    assert(!decode(raw, &g)); assert(g.blocks == 29008896 && g.section_blocks == 512);
    memcpy(raw, saved, sizeof(raw)); put64(raw + 1024 + 36, 29008895);
    memcpy(raw + 5120, raw + 1024, SB_BYTES); assert(decode(raw, &g));
    /* Exercise the actual compare/write/fsync/readback primitives on an owned
     * temporary regular file. Never open a system block device in this test. */
    char temp[] = "/tmp/mu300-online-native-XXXXXX";
    int fd = mkstemp(temp); assert(fd >= 0);
    struct image old = { saved, sizeof(saved) }, next = { raw, sizeof(raw) };
    assert(commit_image(fd, &old, 0)); assert(matches(fd, &old, 0));
    assert(!matches(fd, &next, 0));
    assert(commit_image(fd, &next, 8192)); assert(matches(fd, &next, 8192));
    close(fd); fd = open(temp, O_RDONLY); assert(fd >= 0);
    assert(!commit_image(fd, &old, 8192)); assert(matches(fd, &next, 8192));
    close(fd); unlink(temp);
    puts("PASS: dual superblocks (equal but for the kernel version string and its crc), exact 64 GiB target, alignment, stale geometry, capacity and invalid arguments; no device ioctl");
    return 0;
}
