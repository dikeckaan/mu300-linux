"""A partition table for the tests of the make-room path (tools/resize-last-partition.py, install.ps1's
OfferRepartition): the first 34 sectors of a disk and its last 33, the two pieces the installers read from the eMMC.

    python fakegpt.py OUT LAYOUT      writes OUT.head and OUT.tail

The layouts are built from the figures the project has, not from a dump of a device:
  factory64   the 64 GB eMMC as FINDINGS #9 measured it: 122159104 sectors, last usable LBA 122155007, userdata
              20 GiB ending at sector 54218752, and the gap behind it
  vendor64    issue #32: the same eMMC after a vendor firmware flash replaced the table by one in which userdata
              fills the disk. The issue gives no sectors; this is factory64 with userdata extended to the last
              usable LBA, which is the layout that gives the "-4 MiB" it reports
  nvlast64    vendor64 with a partition behind userdata: not a table the make-room path may touch
  part64      factory64 with a 128 MiB partition named mu300root right behind userdata, 1 MiB aligned: the layout of
              kanoqwq's desktop installer (FINDINGS 179), small so that a test may erase it
  small64     vendor64 with userdata so small that there is nothing to split (4 GiB for Android + 800 MiB)
  ufs1t       the 1 TB UFS U30 Air of issue #396: 4096-byte logical blocks (the table in them: 6 blocks at the start,
              5 at the end, 48 and 40 sectors), 1999372288 sectors, userdata from sector 12275712 to the last usable
              one (LBA 249921023)
Only the names, the order and userdata's sectors matter here; the other partitions' sizes are made up.
"""
import binascii
import struct
import sys

SECTOR = 512
DISK64 = 122159104
DISK1T = 1999372288                          # sectors of 512 bytes; 249921536 blocks of 4096
USABLE_LAST1T = (249921023 + 1) * 8 - 1
USERDATA_FIRST1T = 1534464 * 8
USABLE_LAST64 = 122155007
USERDATA_FIRST = 54218752 - (20 << 21)       # 20 GiB that end at sector 54218752
# the partitions in front of userdata, NV and calibration among them: none of them may change
BEFORE = ['prodnv', 'miscdata', 'l_fixnv1_a', 'l_fixnv1_b', 'l_runtimenv1_a', 'l_runtimenv1_b', 'nvram', 'persist',
          'misc', 'uboot_a', 'uboot_b', 'boot_a', 'boot_b', 'super', 'metadata', 'blackbox', 'fulldumpdb']


def layout(name):
    """(disk sectors, last usable sector, [(name, first, last), ...]), in 512-byte sectors (block_size: the table's)"""
    if name == 'ufs1t':
        step = (USERDATA_FIRST1T - 2048) // len(BEFORE) // 8 * 8
        parts = [(n, 2048 + i * step, 2048 + (i + 1) * step - 1) for i, n in enumerate(BEFORE)]
        parts.append(('userdata', USERDATA_FIRST1T, USABLE_LAST1T))
        return DISK1T, USABLE_LAST1T, parts
    step = (USERDATA_FIRST - 2048) // len(BEFORE)
    parts = [(n, 2048 + i * step, 2048 + (i + 1) * step - 1) for i, n in enumerate(BEFORE)]
    if name == 'factory64':
        parts.append(('userdata', USERDATA_FIRST, 54218752 - 1))
    elif name == 'vendor64':
        parts.append(('userdata', USERDATA_FIRST, USABLE_LAST64))
    elif name == 'part64':
        parts.append(('userdata', USERDATA_FIRST, 54218752 - 1))
        parts.append(('mu300root', 54218752, 54218752 + (128 << 11) - 1))
    elif name == 'nvlast64':
        parts.append(('userdata', USERDATA_FIRST, USABLE_LAST64 - 2048))
        parts.append(('l_fixnv2_a', USABLE_LAST64 - 2047, USABLE_LAST64))
    elif name == 'small64':
        parts[-1] = ('fulldumpdb', parts[-1][1], USABLE_LAST64 - (4 << 21))
        parts.append(('userdata', USABLE_LAST64 - (4 << 21) + 1, USABLE_LAST64))
    else:
        raise SystemExit(f'no layout called {name}')
    return DISK64, USABLE_LAST64, parts


def block_size(name):
    """The logical block size of the disk of that layout."""
    return 4096 if name == 'ufs1t' else SECTOR


def make(disk, usable_last, parts, lbs=SECTOR, nents=128, esize=128):
    """(head, tail): LBA 0..33 and the last 33 LBAs of a disk with this table, every CRC right (with 4096-byte
    blocks: LBA 0..5 and the last 5). DISK, USABLE_LAST and PARTS in 512-byte sectors."""
    k = lbs // SECTOR
    disk, usable_last = disk // k, (usable_last + 1) // k - 1
    parts = [(n, first // k, (last + 1) // k - 1) for n, first, last in parts]
    entries = bytearray(nents * esize)
    for i, (name, first, last) in enumerate(parts):
        o = i * esize
        entries[o:o + 16] = bytes([0xa2, i + 1]) * 8                 # a type GUID: any non-zero one marks it used
        entries[o + 16:o + 32] = bytes([0x5c, i + 1]) * 8
        struct.pack_into('<QQ', entries, o + 32, first, last)
        entries[o + 56:o + 56 + 2 * len(name)] = name.encode('utf-16-le')
    ecrc = binascii.crc32(bytes(entries)) & 0xffffffff

    def header(cur, bak, entries_lba):
        h = bytearray(struct.pack('<8sIIII QQQQ16s QIII', b'EFI PART', 0x10000, 92, 0, 0, cur, bak, 2 + esectors,
                                  usable_last,
                                  b'\x77' * 16, entries_lba, nents, esize, ecrc))
        struct.pack_into('<I', h, 16, binascii.crc32(bytes(h)) & 0xffffffff)
        return bytes(h).ljust(lbs, b'\0')

    esectors = nents * esize // lbs
    head = b'\0' * lbs + header(1, disk - 1, 2) + bytes(entries)
    tail = bytes(entries) + header(disk - 1, 1, disk - 1 - esectors)
    assert len(head) == (2 + esectors) * lbs and len(tail) == (1 + esectors) * lbs
    return head, tail


def write(out, name):
    head, tail = make(*layout(name), lbs=block_size(name))
    with open(out + '.head', 'wb') as f:
        f.write(head)
    with open(out + '.tail', 'wb') as f:
        f.write(tail)


if __name__ == '__main__':
    write(sys.argv[1], sys.argv[2])
