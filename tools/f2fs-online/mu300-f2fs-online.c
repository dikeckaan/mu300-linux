/* mu300-f2fs-online: shrink Android's mounted userdata F2FS in place, and commit the smaller partition table.
 * By kanoqwq (kanoqwq/mu300-linux, installer/device/f2fs-online.c, fe52afe3..e567f09e); the method, shrinking
 * userdata online instead of resetting Android, is dikeckaan's. Runs on the device in Android, as root, from a
 * directory in /dev (never from the userdata it resizes); tools/android-online-shrink.sh drives it.
 *
 *   mu300-f2fs-online inspect MOUNT DEV       geometry of the F2FS mounted at MOUNT from DEV (read only)
 *   mu300-f2fs-online probe MOUNT DEV         the kernel's F2FS_IOC_RESIZE_FS at the current size: a no-op that
 *                                             shows the kernel takes the ioctl at all (not a dry run of a shrink)
 *   mu300-f2fs-online lock-status             busy=1 while a worker runs
 *   mu300-f2fs-online start MOUNT DEV OLD_BLOCKS TARGET_BLOCKS DISK TAIL_BYTE DISK_BYTES UUID WORKDIR
 *       a detached worker (adb may drop): checks both GPT copies against WORKDIR's old-first/old-last (or the
 *       new-first/new-last of a commit that was interrupted), shrinks the F2FS to TARGET_BLOCKS, then writes the new
 *       backup GPT at TAIL_BYTE and the new primary at 0, each read back. WORKDIR/status says how far it got:
 *       shrinking, unchanged (the kernel refused, nothing changed), committing, complete, recovery, failed.
 * Built by tools/f2fs-online/build.sh (static, musl); the binary next to this file is that build.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/fs.h>
#include <linux/magic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/file.h>
#include <sys/wait.h>
#include <signal.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <unistd.h>

#define F2FS_RESIZE _IOW(0xf5, 16, uint64_t)
#define SB_BYTES 3072

struct geometry {
    uint64_t blocks, section_blocks;
    unsigned char uuid[16];
};

static uint32_t le32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static uint64_t le64(const unsigned char *p)
{
    return le32(p) | (uint64_t)le32(p + 4) << 32;
}

static int decode(const unsigned char *raw, struct geometry *g)
{
    const unsigned char *a = raw + 1024, *b = raw + 5120;
    if (le32(a) != 0xf2f52010 || le32(b) != 0xf2f52010 ||
        memcmp(a, b, SB_BYTES) || le32(a + 16) != 12 ||
        le32(a + 20) != 9 || !le32(a + 24) || le32(a + 24) > 65536) {
        errno = EINVAL;
        return -1;
    }
    g->blocks = le64(a + 36);
    g->section_blocks = 512ULL * le32(a + 24);
    memcpy(g->uuid, a + 108, 16);
    if (!g->blocks || g->blocks % g->section_blocks) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

static int read_geometry(int fd, struct geometry *g)
{
    void *buffer = NULL;
    int error = posix_memalign(&buffer, 4096, 8192);
    if (error) { errno = error; return -1; }
    ssize_t n = pread(fd, buffer, 8192, 0);
    int rc = n == 8192 ? decode(buffer, g) : -1;
    if (n >= 0 && n != 8192) errno = EIO;
    free(buffer);
    return rc;
}

static int parse_count(const char *s, uint64_t *result)
{
    if (!*s || *s == '0') return -1;
    for (const char *p = s; *p; p++) if (*p < '0' || *p > '9') return -1;
    errno = 0;
    unsigned long long n = strtoull(s, NULL, 10);
    if (errno || !n || n > UINT64_MAX / 4096) return -1;
    *result = n;
    return 0;
}

static int validate_target(const struct geometry *g, uint64_t expected,
                           uint64_t target, uint64_t used)
{
    if (expected != g->blocks || !target || target >= expected ||
        target % g->section_blocks || target > UINT64_MAX / 4096 ||
        used > UINT64_MAX - (1ULL << 30) || target * 4096 <= used + (1ULL << 30)) {
        errno = EINVAL;
        return -1;
    }
    return 0;
}

static int failure(const char *stage)
{
    fprintf(stderr, "FAILED stage=%s errno=%d message=%s\n", stage, errno, strerror(errno));
    return 1;
}

/* One detached worker owns resize + GPT commit. All payloads live in /dev,
 * not the mounted userdata being resized. Disconnecting ADB does not kill it.
 * The host supplies verified original/candidate GPT copies; the worker compares
 * both immediately before mutation and never accepts unrelated disk bytes. */
struct image { unsigned char *p; size_t n; };

static struct image load_image(const char *name)
{
    struct image out = {0};
    int fd = open(name, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    struct stat st;
    if (fd < 0 || fstat(fd, &st) || !S_ISREG(st.st_mode) ||
        st.st_size < 512 || st.st_size > (2 << 20) || st.st_size % 512) goto done;
    out.n = st.st_size; out.p = malloc(out.n);
    if (!out.p || read(fd, out.p, out.n) != (ssize_t)out.n) {
        free(out.p); out.p = NULL; out.n = 0;
    }
done:
    if (fd >= 0) close(fd);
    return out;
}

static int matches(int fd, const struct image *image, uint64_t at)
{
    unsigned char *p = malloc(image->n);
    if (!p) return 0;
    int ok = pread(fd, p, image->n, at) == (ssize_t)image->n && !memcmp(p, image->p, image->n);
    free(p); return ok;
}

static int commit_image(int fd, const struct image *image, uint64_t at)
{
    return pwrite(fd, image->p, image->n, at) == (ssize_t)image->n &&
        !fsync(fd) && matches(fd, image, at);
}

static void receipt(const char *phase, int error)
{
    int fd = open("status.new", O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW, 0600);
    if (fd < 0) return;
    dprintf(fd, "phase=%s\nerrno=%d\npid=%ld\n", phase, error, (long)getpid());
    fsync(fd); close(fd); rename("status.new", "status");
}

static int worker_command(int argc, char **argv)
{
    /* start MOUNT DECRYPTED OLD TARGET DISK TAIL_BYTE DISK_BYTES UUID WORK */
    if (argc != 11) { errno = EINVAL; return failure("worker-arguments"); }
    uint64_t expected, target, tail, disk_bytes;
    if (parse_count(argv[4], &expected) || parse_count(argv[5], &target) ||
        parse_count(argv[7], &tail) || parse_count(argv[8], &disk_bytes) ||
        strlen(argv[9]) != 32 || strncmp(argv[10], "/dev/mu300-online-", 18)) {
        errno = EINVAL; return failure("worker-values");
    }
    int lock = open("/dev/mu300-f2fs-online.lock", O_CREAT | O_RDWR | O_NOFOLLOW, 0600);
    if (lock < 0 || flock(lock, LOCK_EX | LOCK_NB)) return failure("worker-lock");
    if (chdir(argv[10])) return failure("worker-directory");
    struct image old_first = load_image("old-first"), old_last = load_image("old-last"),
                 new_first = load_image("new-first"), new_last = load_image("new-last");
    if (!old_first.p || !old_last.p || !new_first.p || !new_last.p ||
        old_first.n != new_first.n || old_last.n != new_last.n ||
        tail >= disk_bytes || tail + old_last.n != disk_bytes || old_first.n >= tail) {
        errno = EINVAL; return failure("worker-gpt-inputs");
    }
    int mount_fd = open(argv[2], O_RDONLY | O_DIRECTORY | O_CLOEXEC),
        raw_fd = open(argv[3], O_RDONLY | O_DIRECT | O_CLOEXEC),
        disk_fd = open(argv[6], O_RDWR | O_CLOEXEC);
    struct stat ms, rs, ds;
    struct statfs fs;
    struct statvfs volume;
    struct geometry g;
    uint64_t actual_bytes, mapped_bytes;
    char uuid[33];
    if (mount_fd < 0 || raw_fd < 0 || disk_fd < 0 ||
        fstat(mount_fd, &ms) || fstat(raw_fd, &rs) || fstat(disk_fd, &ds) ||
        !S_ISBLK(rs.st_mode) || !S_ISBLK(ds.st_mode) || ms.st_dev != rs.st_rdev ||
        fstatfs(mount_fd, &fs) || fs.f_type != F2FS_SUPER_MAGIC ||
        fstatvfs(mount_fd, &volume) || (volume.f_flag & ST_RDONLY) ||
        ioctl(disk_fd, BLKGETSIZE64, &actual_bytes) || actual_bytes != disk_bytes ||
        ioctl(raw_fd, BLKGETSIZE64, &mapped_bytes) || read_geometry(raw_fd, &g) ||
        g.blocks > mapped_bytes / 4096 || target >= expected || target % g.section_blocks)
        return failure("worker-identity");
    for (int i=0; i<16; i++) snprintf(uuid+i*2, 3, "%02x", g.uuid[i]);
    if (strcmp(uuid, argv[9]) || (g.blocks != expected && g.blocks != target) ||
        !(matches(disk_fd, &old_first, 0) || matches(disk_fd, &new_first, 0)) ||
        !(matches(disk_fd, &old_last, tail) || matches(disk_fd, &new_last, tail))) {
        errno = EINVAL; return failure("worker-stale-state");
    }
    if (g.blocks == expected && (!matches(disk_fd, &old_first, 0) || !matches(disk_fd, &old_last, tail) ||
        !volume.f_frsize || volume.f_blocks < volume.f_bfree ||
        (volume.f_blocks-volume.f_bfree) > UINT64_MAX/volume.f_frsize ||
        validate_target(&g, expected, target, (volume.f_blocks-volume.f_bfree)*volume.f_frsize))) {
        errno = EINVAL; return failure("worker-target");
    }
    /* Inherit ignored SIGHUP before fork: adb may close the shell immediately
     * after the parent returns, before the child gets scheduled for setsid. */
    signal(SIGHUP, SIG_IGN); signal(SIGPIPE, SIG_IGN);
    pid_t child = fork();
    if (child < 0) return failure("worker-fork");
    if (child) { printf("worker_started=%ld\n", (long)child); return 0; }
    setsid(); signal(SIGHUP, SIG_IGN); signal(SIGPIPE, SIG_IGN);
    int log = open("worker.log", O_CREAT | O_WRONLY | O_APPEND | O_NOFOLLOW, 0600);
    int nil = open("/dev/null", O_RDONLY);
    if (log < 0 || nil < 0) _exit(1);
    dup2(nil, 0); dup2(log, 1); dup2(log, 2); close(nil); close(log);
    if (g.blocks == expected) {
        receipt("shrinking", 0);
        if (syncfs(mount_fd)) { receipt("failed", errno); _exit(1); }
        int rc = ioctl(mount_fd, F2FS_RESIZE, &target), error = errno;
        /* Some errors can occur after mutation. Read back before deciding. */
        if (read_geometry(raw_fd, &g)) { receipt("recovery", errno); _exit(1); }
        if (g.blocks == expected && rc) { receipt("unchanged", error); _exit(1); }
        if (g.blocks != target) { receipt("recovery", EIO); _exit(1); }
    }
    receipt("committing", 0);
    if (syncfs(mount_fd) || !commit_image(disk_fd, &new_last, tail) ||
        !commit_image(disk_fd, &new_first, 0)) { receipt("recovery", EIO); _exit(1); }
    receipt("complete", 0);
    close(disk_fd); close(raw_fd); close(mount_fd); close(lock); _exit(0);
}


int main(int argc, char **argv)
{
    if (argc == 2 && !strcmp(argv[1], "lock-status")) {
        int fd = open("/dev/mu300-f2fs-online.lock", O_CREAT | O_RDWR | O_NOFOLLOW, 0600);
        if (fd < 0) return failure("worker-lock-status");
        puts(flock(fd, LOCK_EX | LOCK_NB) ? "busy=1" : "busy=0");
        close(fd); return 0;
    }
    if (argc > 1 && !strcmp(argv[1], "start")) return worker_command(argc, argv);
    if (argc < 4 || (strcmp(argv[1], "inspect") && strcmp(argv[1], "probe") &&
                     strcmp(argv[1], "shrink")) ||
        (!strcmp(argv[1], "shrink") ? argc != 6 : argc != 4)) {
        fprintf(stderr, "usage: %s inspect|probe MOUNT BLOCKDEV; shrink MOUNT BLOCKDEV EXPECTED_BLOCKS TARGET_BLOCKS\n", argv[0]);
        return 2;
    }
    int mount_fd = open(argv[2], O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (mount_fd < 0) return failure("open-mount");
    int raw_fd = open(argv[3], O_RDONLY | O_DIRECT | O_CLOEXEC);
    if (raw_fd < 0) return failure("open-decrypted-device");
    struct stat mount_stat, device_stat;
    struct statfs fs;
    struct statvfs volume;
    struct geometry before, after;
    uint64_t mapped_bytes;
    if (fstat(mount_fd, &mount_stat) || fstat(raw_fd, &device_stat) ||
        fstatfs(mount_fd, &fs) || fstatvfs(mount_fd, &volume)) return failure("stat");
    if (!S_ISBLK(device_stat.st_mode) || mount_stat.st_dev != device_stat.st_rdev ||
        fs.f_type != F2FS_SUPER_MAGIC || volume.f_flag & ST_RDONLY) {
        errno = EINVAL; return failure("mount-device-identity");
    }
    if (ioctl(raw_fd, BLKGETSIZE64, &mapped_bytes) ||
        read_geometry(raw_fd, &before)) return failure("read-superblocks");
    if (!volume.f_frsize || before.blocks > mapped_bytes / 4096 || volume.f_blocks < volume.f_bfree ||
        (volume.f_blocks - volume.f_bfree) > UINT64_MAX / volume.f_frsize) {
        errno = EINVAL; return failure("geometry");
    }
    uint64_t used = (volume.f_blocks - volume.f_bfree) * volume.f_frsize;
    printf("blocks=%" PRIu64 "\nblock_size=4096\nsection_blocks=%" PRIu64
           "\nmapped_bytes=%" PRIu64 "\nused_bytes=%" PRIu64 "\n",
           before.blocks, before.section_blocks, mapped_bytes, used);
    printf("uuid="); for (int i=0; i<16; i++) printf("%02x", before.uuid[i]); puts("");
    fflush(stdout);
    if (!strcmp(argv[1], "inspect")) return 0;
    if (!strcmp(argv[1], "probe")) {
        /* Exact current size is a supported no-op, not a shrink dry run. */
        uint64_t same = before.blocks;
        if (ioctl(mount_fd, F2FS_RESIZE, &same)) return failure("same-size-probe");
        if (read_geometry(raw_fd, &after) || before.blocks != after.blocks ||
            before.section_blocks != after.section_blocks || memcmp(before.uuid, after.uuid, 16)) {
            errno = EIO; return failure("probe-readback");
        }
        puts("same_size_probe=OK");
        return 0;
    }
    uint64_t expected, target;
    if (parse_count(argv[4], &expected) || parse_count(argv[5], &target) ||
        validate_target(&before, expected, target, used)) {
        errno = EINVAL; return failure("target");
    }
    if (syncfs(mount_fd)) return failure("pre-sync");
    if (read_geometry(raw_fd, &after) || after.blocks != expected ||
        memcmp(before.uuid, after.uuid, sizeof(before.uuid))) {
        errno = EIO; return failure("pre-write-identity");
    }
    printf("ioctl_begin expected=%" PRIu64 " target=%" PRIu64 "\n", expected, target);
    fflush(stdout);
    if (ioctl(mount_fd, F2FS_RESIZE, &target)) return failure("resize-ioctl");
    if (syncfs(mount_fd)) return failure("post-sync");
    if (read_geometry(raw_fd, &after) || after.blocks != target ||
        memcmp(before.uuid, after.uuid, sizeof(before.uuid))) {
        errno = EIO; return failure("resize-readback");
    }
    printf("resize_verified=OK\nblocks=%" PRIu64 "\n", after.blocks);
    close(raw_fd); close(mount_fd);
    return 0;
}
