"""Making room on an encrypted Android by a reset, and the installation that resumes afterwards (EXPERIMENTAL;
tools/resume.py, tools/resume.sh, install.ps1's make-room path; docs/FINDINGS.md 112). Ported from kano's desktop
installer: the transaction and its checks first (the device, its slot, the partition geometry, the token, the
installer's tools), then install.sh as a whole against tests/fakeadb.py with real storage (tests/fakeemmc.py): the
backup, the partition table, the token and the request to recovery as they land on the fake eMMC; the reset; the
resumed run and every way it refuses. Nothing here runs on, or reaches, a real device."""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import fakeemmc
import fakegpt
from helpers import TOP, ShellTest
from test_answers import Device, events

sys.path.insert(0, str(TOP / 'tools'))
import resume  # noqa: E402

TOK = 'b' * 32


def record(**kw):
    r = {'format': 1, 'state': 'prepared', 'serial': 'SERIAL', 'slot': 'a', 'cid': 'c' * 32, 'node': 'mmcblk0p18',
         'start': 2000000, 'size': 120155008, 'disk': 122159104, 'target': 100000000, 'need': 20152320,
         'usable_end': 122155007, 'region_start': 102002688, 'region_end': 122155008, 'token': TOK, 'identity': 'i' * 64}
    r.update(kw)
    return r


class Transaction(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='mu300-resume-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / 'marker').write_bytes(resume.marker(TOK))
        (self.tmp / 'bcb').write_bytes(bytes(2048))

    def facts(self, **kw):
        r = record()
        f = {'serial': 'SERIAL', 'slot': 'a', 'cid': 'c' * 32, 'node': 'mmcblk0p18', 'start': 2000000, 'size': r['target'],
             'disk': r['disk'], 'gpt_first': 2000000, 'gpt_end': 2000000 + r['target'] - 1, 'usable_end': r['usable_end'],
             'region_start': r['region_start'], 'region_end': r['region_end'], 'marker': str(self.tmp / 'marker'),
             'bcb': str(self.tmp / 'bcb'), 'identity': 'i' * 64}
        f.update(kw)
        return f

    def test_the_prepared_device_passes(self):
        resume.check(record(), self.facts())
        # once installed, the token is not needed any more (kano: root_verified)
        (self.tmp / 'marker').write_bytes(bytes(4096))
        resume.check(record(state='installed'), self.facts())

    def test_wrong_device_slot_geometry_marker_or_tools_never_pass(self):
        # kano's test_resume_wrong_device_geometry_or_marker_never_pass, with this project's own checks beside it
        bad = {'serial': dict(serial='OTHER'), 'slot': dict(slot='b'), 'cid': dict(cid='d' * 32),
               'node': dict(node='mmcblk0p17'), 'start': dict(start=2000001), 'disk': dict(disk=61079552),
               'size': dict(size=100000000 - 4096), 'gpt_first': dict(gpt_first=2000001),
               'gpt_end': dict(gpt_end=2000000 + 100000000), 'usable_end': dict(usable_end=122155006),
               'region_start': dict(region_start=102002688 + 4096), 'region_end': dict(region_end=122155008 - 4096),
               'identity': dict(identity='j' * 64)}
        for why, kw in bad.items():
            with self.assertRaises(ValueError, msg=why):
                resume.check(record(), self.facts(**kw))
        (self.tmp / 'marker').write_bytes(resume.marker('c' * 32))
        with self.assertRaisesRegex(ValueError, 'token mismatch'):
            resume.check(record(), self.facts())
        (self.tmp / 'marker').write_bytes(b'')
        with self.assertRaisesRegex(ValueError, 'token mismatch'):
            resume.check(record(), self.facts())

    def test_a_reset_that_has_not_run(self):
        (self.tmp / 'bcb').write_bytes(resume.bcb())
        with self.assertRaisesRegex(ValueError, 'has not reset the device yet'):
            resume.check(record(), self.facts())

    def test_a_preparation_that_did_not_finish_is_not_resumed(self):
        with self.assertRaisesRegex(ValueError, 'did not finish'):
            resume.check(record(state='prepared-request'), self.facts())
        with self.assertRaises(ValueError):
            resume.check(record(state='cancelled'), self.facts())

    def test_a_record_that_does_not_add_up(self):
        with self.assertRaisesRegex(ValueError, 'does not add up'):
            resume.check(record(need=4096), self.facts())

    def test_the_bootloader_message(self):
        b = resume.bcb()
        self.assertEqual(len(b), 2048)
        self.assertEqual(b[:14], b'boot-recovery\0')
        n = len(b'recovery\n--wipe_data\n--reason=mu300-make-room\n')
        self.assertEqual(b[64:64 + n], b'recovery\n--wipe_data\n--reason=mu300-make-room\n')
        self.assertEqual(b[14:64], bytes(50))
        self.assertEqual(b[64 + n:], bytes(2048 - 64 - n))
        self.assertTrue(resume.bcb_pending(b))
        self.assertFalse(resume.bcb_pending(bytes(2048)))
        self.assertFalse(resume.bcb_pending(b'boot-recovery\0'.ljust(2048, b'\0')))      # somebody else's request

    def test_the_marker(self):
        m = resume.marker(TOK)
        self.assertEqual(len(m), 4096)
        self.assertTrue(m.startswith(b'MU300-PREPARED-V1 ' + TOK.encode() + b'\n'))
        for bad in ('x' * 32, 'b' * 31, 'B' * 32, ''):
            with self.assertRaises(ValueError):
                resume.marker(bad)
        self.assertEqual(len(resume.token()), 32)
        self.assertNotEqual(resume.token(), resume.token())

    def test_encryption_kanos_rule(self):
        # kano's test_fbe_with_plain_superblock_still_requires_format
        self.assertTrue(resume.encrypted('encrypted', 'file', '/dev/block/mmcblk0p40', '1020f5f2'))
        self.assertTrue(resume.encrypted('unencrypted', '', '/dev/block/dm-0', '53ef'))
        self.assertFalse(resume.encrypted('unencrypted', '', '/dev/block/mmcblk0p40', '53ef'))
        with self.assertRaises(ValueError):
            resume.encrypted('', '', '/dev/block/mmcblk0p40', '1020f5f2')
        out = subprocess.run([sys.executable, str(TOP / 'tools/resume.py'), 'encrypted', 'state=', 'type=', 'source=/dev/block/mmcblk0p40', 'magic='],
                             capture_output=True, text=True).stdout
        self.assertEqual(out, 'unknown\n')

    def test_the_identity_follows_the_tools_and_the_package_only(self):
        top = self.tmp / 'top'
        for name in resume.TOOLS + ('install.sh', 'README.md'):
            (top / name).parent.mkdir(parents=True, exist_ok=True)
            (top / name).write_text(name)
        before = resume.identity(top)
        (top / 'install.sh').write_text('a repaired prompt')
        (top / 'README.md').write_text('another text')
        self.assertEqual(resume.identity(top), before)                    # kano: prompts and texts may change
        for name in resume.TOOLS:
            saved = (top / name).read_text()
            (top / name).write_text(saved + 'changed')
            self.assertNotEqual(resume.identity(top), before, name)
            (top / name).write_text(saved)
        m = self.tmp / 'manifest'
        m.write_text('KERNEL_ASSET=k.tar.gz\nSHA256_KERNEL=%s\nROOTFS_ASSET=r.tar.gz\nSHA256_ROOTFS=%s\n' % ('1' * 64, '2' * 64))
        with_package = resume.identity(top, m)
        self.assertNotEqual(with_package, before)
        m.write_text(m.read_text().replace('2' * 64, '3' * 64))
        self.assertNotEqual(resume.identity(top, m), with_package)

    def test_saved_atomically_and_found_for_its_device(self):
        d = self.tmp / 'backups'
        for name, kw, age in (('old', {}, 300), ('new', {}, 100), ('other', dict(cid='d' * 32), 0),
                              ('done', dict(state='installed'), 0), ('broken', None, 0)):
            (d / name).mkdir(parents=True)
            p = d / name / 'transaction.json'
            if kw is None:
                p.write_text('{not json')
            else:
                resume.save(p, record(**kw))
            t = time.time() - age
            os.utime(p, (t, t))
        self.assertEqual(resume.find(d, 'SERIAL', 'c' * 32), d / 'new' / 'transaction.json')
        self.assertEqual(resume.find(d, 'SERIAL', 'd' * 32), d / 'other' / 'transaction.json')
        self.assertIsNone(resume.find(d, 'OTHER', 'c' * 32))
        self.assertEqual(resume.find(d), d / 'other' / 'transaction.json')          # any device: the newest
        self.assertFalse(list(d.rglob('*.tmp')))
        with self.assertRaises(ValueError):
            resume.new(self.tmp / 'x.json', {'serial': 'S'})                         # never half a transaction


def tables_equal_but_userdata(before, after):
    """[(name, first, last)] of two tables: the same partitions at the same places, userdata's end aside"""
    return [p for p in before if p[0] != 'userdata'] == [p for p in after if p[0] != 'userdata']


MAKE_ROOM = dict(MU300_ANS_MAKE_ROOM='yes', MU300_ANS_LINUX_GIB='4', MU300_ANS_ERASE_ANDROID='ERASE', MU300_ANS_REBOOT='yes')
INSTALL = dict(MU300_ANS_SYSTEMS='2', MU300_OPENWRT='plain', MU300_ANS_DEFAULT_LINUX='yes', MU300_ANS_BOOT_ATTEMPTS='5',
               MU300_ANS_HOTSPOT='yes', MU300_ANS_GPU='no', MU300_ANS_VPN='no', MU300_ANS_ADB='no', MU300_ANS_KERNEL='6.18',
               MU300_ANS_PASSWORD='hunter2secret', MU300_ANS_CONFIRM='INSTALL')


class ResetAndResume(Device):
    """install.sh's make-room path on the fake eMMC (tests/fakeemmc.py), the reset, and the run that resumes."""

    def setUp(self):
        super().setUp()
        self.emmc = fakeemmc.make(self.tmp / 'emmc')
        self.backups = self.tmp / 'home' / 'mu300-backups'

    def device(self, **keys):
        keys.setdefault('layout', 'vendor64')
        keys.setdefault('emmc', str(self.emmc))
        super().device(**keys)

    def inst(self, shell, answers, *args, **env):
        f = self.tmp / 'answers.txt'
        f.write_text(''.join(f'{k}={v}\n' for k, v in answers.items()))
        f.chmod(0o600)
        r = self.run_script(shell, 'install.sh', '--answers', str(f), *args, MU300_PROGRESS='1', **env)
        ev = events(r.stdout)
        return r, ev, {e['key']: e['value'] for e in ev if e['event'] == 'info'}

    def writes(self):
        return [c['cmd'] for c in self.calls('write')]

    def prepare(self, shell):
        self.device(pull=True)
        before = fakeemmc.table(self.emmc)
        misc_before = fakeemmc.bcb(self.emmc)
        r, ev, facts = self.inst(shell, MAKE_ROOM)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
        return r, ev, facts, before, misc_before

    def test_prepare_writes_the_table_the_token_and_the_request_and_saves_the_transaction(self):
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc')
            shutil.rmtree(self.backups, ignore_errors=True)
            r, ev, facts, before, misc_before = self.prepare(shell)
            self.assertEqual(ev[-1]['event'], 'done')
            self.assertEqual((ev[-1]['repartitioned'], ev[-1]['resume']), ('yes', 'pending'))
            self.assertEqual(facts['makeroom.crypto'], 'yes')
            tx = Path(ev[-1]['transaction'])
            self.assertTrue(tx.is_file() and tx.parent.parent == self.backups, tx)
            rec = json.loads(tx.read_text())
            self.assertEqual(rec['state'], 'prepared')
            self.assertEqual((rec['serial'], rec['slot'], rec['cid']), ('324950664950', 'a', fakeemmc.CID))
            after = fakeemmc.table(self.emmc)
            ud_before = [p for p in before if p[0] == 'userdata'][0]
            ud_after = [p for p in after if p[0] == 'userdata'][0]
            # only userdata's end moved, by the size asked for; every other partition is where it was
            self.assertTrue(tables_equal_but_userdata(before, after))
            self.assertEqual(ud_after[1], ud_before[1])
            self.assertEqual(rec['target'], ud_after[2] - ud_after[1] + 1)
            # the region by the installers' arithmetic is the size asked for, exactly; and the token at its start
            start = ((ud_after[2] + 1) // 4096 + 1) * 4096
            self.assertEqual(rec['region_start'], start)
            self.assertEqual(rec['region_end'] - rec['region_start'], 4 << 21)
            self.assertEqual(rec['need'], 4 << 21)
            self.assertEqual(fakeemmc.read(self.emmc, start, 8), resume.marker(rec['token']))
            # the request to recovery, and the A/B block behind it as it was
            misc = (self.emmc / 'dev/block/by-name/misc').read_bytes()
            self.assertEqual(misc[:2048], resume.bcb())
            self.assertEqual(misc[2048:2080], fakeemmc._misc()[2048:2080])
            # writes: the backup table first, then the primary, the token, the request - nothing else
            w = self.writes()
            targets = [('mmcblk0 tail' if 'seek=%d' % (fakegpt.DISK64 - 33) in c else
                        'mmcblk0 head' if 'of=/dev/block/mmcblk0 bs=512 conv' in c else
                        'token' if 'mu300-marker.bin' in c else 'misc' if 'of=/dev/block/by-name/misc' in c else c) for c in w
                       if 'of=/dev/block/' in c]
            self.assertEqual(targets, ['mmcblk0 tail', 'mmcblk0 head', 'token', 'misc'], w)
            self.assertEqual(self.calls('reboot')[0]['argv'], ['reboot'])
            # the backup on this computer: the table, misc, boot and the boot chain of both slots, all checked
            bd = Path(rec['backup'])
            names = sorted(l.split('  ')[1] for l in (bd / 'SHA256SUMS').read_text().splitlines())
            want = ['gpt.head', 'gpt.tail', 'misc-head.bin'] + sorted(f'{p}_{s}.img' for p in ('boot',) + fakeemmc.CHAIN for s in 'ab')
            self.assertEqual(names, sorted(want))
            for line in (bd / 'SHA256SUMS').read_text().splitlines():
                h, n = line.split('  ')
                self.assertEqual(hashlib.sha256((bd / n).read_bytes()).hexdigest(), h)
            self.assertEqual((bd / 'boot_b.img').read_bytes(), (self.emmc / 'dev/block/by-name/boot_b').read_bytes())
            # never an NV or calibration partition, not even read
            for c in self.calls():
                self.assertNotRegex(c['cmd'], r'by-name/(prodnv|miscdata|persist|ztecfg|ztepersist|calinv|isedata|\w*nv\w*)', c['cmd'])

    def test_the_smallest_size_leaves_a_region_openwrt_fits_and_the_figures_add_up(self):
        # the first device run (FINDINGS 112): userdata used to end that many sectors before the usable end, and the
        # region behind it came out 4 MiB or more short of the answer - 0.78125 GiB (OpenWrt's 800 MiB) gave 796 MiB,
        # which the resumed run would have refused after the reset. And the plan printed userdata's sectors as
        # bytes ("userdata now: 0.1 GiB"), and macOS's bash 3.2 broke on a case inside $(...).
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc')
            shutil.rmtree(self.backups, ignore_errors=True)
            self.device(pull=True)
            before = fakeemmc.table(self.emmc)
            ud = [p for p in before if p[0] == 'userdata'][0]
            r, ev, facts = self.inst(shell, dict(MAKE_ROOM, MU300_ANS_LINUX_GIB='0.78125'))
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
            rec = json.loads(Path(ev[-1]['transaction']).read_text())
            self.assertEqual(rec['region_end'] - rec['region_start'], 800 << 11)
            self.assertGreaterEqual((rec['region_end'] - rec['region_start']) * 512, int(facts['need.openwrt']))
            gib = '%.1f GiB' % ((ud[2] - ud[1] + 1) * 512 / 2**30)
            self.assertIn('userdata now:         %s (sectors' % gib, r.stdout)
            self.assertIn("Android's data:       encrypted (", r.stdout)
            self.assertNotIn('syntax error', r.stdout + r.stderr)
            # below it: refused, and the same answer twice stops the run with nothing written
            shutil.rmtree(self.backups, ignore_errors=True)
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc')
            self.device(pull=True)
            r, ev, facts = self.inst(shell, dict(MAKE_ROOM, MU300_ANS_LINUX_GIB='0.78'))
            self.assertNotEqual(r.returncode, 0)
            self.assertIn('too small: Linux needs at least 0.8 GiB', r.stdout)
            self.assertEqual(fakeemmc.table(self.emmc), before)
            self.assertEqual(self.writes(), [])

    def test_resumed_after_the_reset_and_refused_before_it(self):
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc')
            shutil.rmtree(self.backups, ignore_errors=True)
            r, ev, facts, *_ = self.prepare(shell)
            tx = ev[-1]['transaction']
            rec = json.loads(Path(tx).read_text())
            # before the reset: the kernel still has the old table and misc still asks recovery for the reset
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual(r.returncode, 1)
            self.assertIn('has not reset the device yet', ev[-1]['message'])
            self.assertEqual(self.writes(), [])
            # the reset: the kernel reads the table again, recovery formats userdata and clears the request
            fakeemmc.reset(self.emmc)
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual(facts['resume.transaction'], tx, r.stdout[-3000:])
            self.assertEqual(facts['resume.check'], 'RESUME-OK')
            self.assertEqual(facts['verdict.code'], 'resume')
            self.assertEqual(facts['storage'], 'internal')
            self.assertEqual(int(facts['region.offset']), rec['region_start'] * 512)
            asked = [e['id'] for e in ev if e['event'] == 'question']
            self.assertNotIn('MU300_ANS_OVERWRITE', asked)      # the region's old contents were erased by consent
            self.assertNotIn('MU300_ANS_MAKE_ROOM', asked)
            self.assertIn('MU300_ANS_SYSTEMS', asked)
            self.assertIn('could not read /dev/block/by-name/boot_a', ev[-1]['message'])     # (pulls refused: it ends here)
            self.assertEqual(self.writes(), [])
            # --check says the same, and writes nothing
            r, ev, facts = self.inst(shell, {}, '--check')
            self.assertEqual((facts['resume.check'], facts['verdict.code']), ('RESUME-OK', 'resume'))
            self.assertEqual(self.writes(), [])
            # --no-resume: as if nothing had been prepared - the region's contents are data to be asked about
            r, ev, facts = self.inst(shell, INSTALL, '--no-resume')
            self.assertNotIn('resume.transaction', facts)
            self.assertIn('set MU300_ANS_OVERWRITE', ev[-1]['message'])
            # what no longer matches stops it, before anything is written
            for why, change, word in (
                    ('another slot', lambda: self.device(pull='noboot', slot='b'), 'slot'),
                    ('a token overwritten', lambda: self.overwrite(rec['region_start']), 'token mismatch'),
                    ('the transaction edited', lambda: self.edit(tx, target=rec['target'] - 4096), 'geometry differs'),
                    ('other tools', lambda: self.edit(tx, identity='0' * 64), 'tools or the package differ')):
                self.device(pull='noboot')
                change()
                r, ev, facts = self.inst(shell, INSTALL)
                self.assertEqual(r.returncode, 1, why)
                self.assertIn(word, ev[-1]['message'], why)
                self.assertIn('Nothing was written', ev[-1]['message'], why)
                self.assertEqual(self.writes(), [], why)
                self.restore(tx, rec)
            # --resume with nothing saved for this device
            shutil.rmtree(self.backups)
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL, '--resume')
            self.assertIn('no saved transaction for this device', ev[-1]['message'])

    def overwrite(self, sector):
        with open(self.emmc / 'dev/block/mmcblk0', 'r+b') as f:
            f.seek(sector * 512)
            f.write(b'somebody else was here')

    def edit(self, tx, **kw):
        r = json.loads(Path(tx).read_text())
        r.update(kw)
        Path(tx).write_text(json.dumps(r))

    def restore(self, tx, rec):
        Path(tx).write_text(json.dumps(rec))
        with open(self.emmc / 'dev/block/mmcblk0', 'r+b') as f:
            f.seek(rec['region_start'] * 512)
            f.write(resume.marker(rec['token']))

    def test_an_encryption_state_that_cannot_be_told_changes_nothing(self):
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc', crypto=('', ''), source='/dev/block/mmcblk0p18')
            self.device(pull=True)
            r, ev, facts = self.inst(shell, MAKE_ROOM)
            self.assertEqual(r.returncode, 1)
            self.assertIn("encryption state is unknown", ev[-1]['message'])
            self.assertEqual(self.writes(), [])
            self.assertFalse(self.backups.exists())

    def test_kanos_rule_on_the_device(self):
        # what the device says decides (resume_facts): FBE is encrypted whatever its superblock; a plain F2FS with
        # "unencrypted" is not; --check reads it and writes nothing
        for crypto, source, want in ((('encrypted', 'file'), '/dev/block/dm-6', 'yes'),
                                     (('unencrypted', ''), '/dev/block/mmcblk0p18', 'no'),
                                     (('unencrypted', ''), '/dev/block/dm-2', 'yes')):
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc', crypto=crypto, source=source)
            for shell in self.each_shell():
                self.device(pull=True)
                r, ev, facts = self.inst(shell, {}, '--check')
                self.assertEqual(facts.get('makeroom.crypto'), want, (crypto, source, r.stdout[-2000:]))
                self.assertEqual(self.writes(), [])

    def test_nothing_is_written_without_every_word(self):
        for shell in self.each_shell():
            self.device(pull=True)
            for answers, word in ((dict(MAKE_ROOM, MU300_ANS_ERASE_ANDROID='erase'), 'nothing was changed.'),
                                  (dict(MAKE_ROOM, MU300_ANS_MAKE_ROOM='no'), 'nothing was changed.')):
                r, ev, facts = self.inst(shell, answers)
                self.assertEqual(ev[-1], {'event': 'error', 'message': word})
                self.assertEqual(self.writes(), [])
                self.assertFalse(self.backups.exists())

    def test_the_self_update_waits_while_a_transaction_does(self):
        self.backups.mkdir(parents=True)
        for shell in self.each_shell():
            code = (f'TOP="{TOP}"; HOME="{self.tmp}/home"; . "$TOP/tools/resume.sh"; '
                    'resume_pending && echo PENDING || echo NONE')
            self.assertIn('NONE', self.sh(shell, code).stdout)
            (self.backups / 'x').mkdir(exist_ok=True)
            resume.save(self.backups / 'x' / 'transaction.json', record())
            self.assertIn('PENDING', self.sh(shell, code).stdout)
            self.assertIn('NONE', self.sh(shell, code, MU300_RESUME='0').stdout)
            shutil.rmtree(self.backups / 'x')
        src = (TOP / 'install.sh').read_text()
        self.assertLess(src.index('if resume_pending; then'), src.index('self_update "$0" "$@"'))



class ResetAndResumeUfs(ResetAndResume):
    """The same on the 1 TB UFS U30 Air of issue #396 (fakeemmc's ufs1t): sda, 4096-byte logical blocks - the table
    in 48 sectors at the start and 40 at the end - and no CID, the UFS's string descriptors in its place."""

    def setUp(self):
        Device.setUp(self)
        self.emmc = fakeemmc.make(self.tmp / 'emmc', layout='ufs1t')
        self.backups = self.tmp / 'home' / 'mu300-backups'

    def device(self, **keys):
        keys.setdefault('layout', 'ufs1t')
        keys.setdefault('model', 'U30_Air')
        super().device(**keys)

    def test_prepare_and_resume_on_the_ufs(self):
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc', layout='ufs1t')
            shutil.rmtree(self.backups, ignore_errors=True)
            r, ev, facts, before, _ = self.prepare(shell)
            self.assertEqual((ev[-1]['repartitioned'], ev[-1]['resume']), ('yes', 'pending'), r.stdout[-3000:])
            rec = json.loads(Path(ev[-1]['transaction']).read_text())
            want_cid = hashlib.sha256(b'ufs:%s:%s' % tuple(x.encode() for x in fakeemmc.UFS_SERIAL)).hexdigest()[:32]
            self.assertEqual((rec['cid'], rec['node']), (want_cid, 'sda%d' % len(before)))
            after = fakeemmc.table(self.emmc)
            self.assertTrue(tables_equal_but_userdata(before, after))
            ud = [p for p in after if p[0] == 'userdata'][0]
            self.assertEqual((ud[2] + 1) % 8, 0)                      # on a 4096-byte block
            start = ((ud[2] + 1) // 4096 + 1) * 4096
            self.assertEqual((rec['region_start'], rec['region_end'] - rec['region_start']), (start, 4 << 21))
            self.assertEqual(fakeemmc.read(self.emmc, start, 8), resume.marker(rec['token']))
            targets = [('tail' if 'of=/dev/block/sda bs=512 seek=%d ' % (fakegpt.DISK1T - 40) in c else
                        'head' if 'of=/dev/block/sda bs=512 conv' in c else
                        'token' if 'mu300-marker.bin' in c else 'misc' if 'of=/dev/block/by-name/misc' in c else c)
                       for c in self.writes() if 'of=/dev/block/' in c]
            self.assertEqual(targets, ['tail', 'head', 'token', 'misc'])
            # nothing asked of an eMMC (the card's lookup, mmcblk1 and up, aside)
            self.assertFalse([c for c in self.calls() if 'mmcblk' in c['cmd'] and
                              not c['cmd'].startswith('for b in /sys/block/mmcblk[1-9];')])
            # after the reset the same unit is found again and the installation continues
            fakeemmc.reset(self.emmc)
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual(facts.get('resume.check'), 'RESUME-OK', r.stdout[-3000:])
            self.assertEqual(int(facts['region.offset']), rec['region_start'] * 512)

    # the eMMC's figures and messages are covered above; on this layout only the test of its own
    test_prepare_writes_the_table_the_token_and_the_request_and_saves_the_transaction = None
    test_the_smallest_size_leaves_a_region_openwrt_fits_and_the_figures_add_up = None
    test_resumed_after_the_reset_and_refused_before_it = None
    test_an_encryption_state_that_cannot_be_told_changes_nothing = None
    test_kanos_rule_on_the_device = None
    test_nothing_is_written_without_every_word = None
    test_the_self_update_waits_while_a_transaction_does = None


class FromAnUnpackedZip(ResetAndResume):
    """The two together (tools/package.sh, §111): room made from an unpacked Magisk zip's own installer, and the
    installation resumed by it after the reset. The transaction is bound to that zip's payload (kano's payload
    identity): the same zip continues it, another zip or a copy of the project does not."""

    @classmethod
    def setUpClass(cls):
        from test_magisk_zip import fake_release
        cls.zips = Path(tempfile.mkdtemp(prefix='mu300-resume-zips-'))
        fake_release(cls.zips / 'v2026.10.06')
        r = subprocess.run(['sh', str(TOP / 'tools/make-magisk-zips.sh'), str(cls.zips / 'v2026.10.06'), str(cls.zips / 'out')],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.zips, ignore_errors=True)

    def unpack(self, name):
        import zipfile
        d = self.tmp / 'unpacked' / name
        shutil.rmtree(d, ignore_errors=True)
        with zipfile.ZipFile(self.zips / 'out' / f'mu300-magisk-v2026.10.06-{name}.zip') as z:
            z.extractall(d)
        return d

    def pkg(self, shell, pkg, answers, *args):
        f = self.tmp / 'answers.txt'
        f.write_text(''.join(f'{k}={v}\n' for k, v in answers.items()))
        f.chmod(0o600)
        r = self.run_script(shell, str(pkg / 'computer/install.sh'), '--answers', str(f), *args, MU300_PROGRESS='1', MU300_RELEASE='')
        ev = events(r.stdout)
        return r, ev, {e['key']: e['value'] for e in ev if e['event'] == 'info'}

    def test_prepared_and_resumed_by_the_same_zip(self):
        zip_a = self.unpack('openwrt-k6.18')
        zip_b = self.unpack('ubuntu-24.04-k7.2')
        answers = {k: v for k, v in INSTALL.items() if k not in ('MU300_ANS_SYSTEMS', 'MU300_OPENWRT', 'MU300_ANS_KERNEL')}
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc')
            shutil.rmtree(self.backups, ignore_errors=True)
            self.device(pull=True)
            r, ev, facts = self.pkg(shell, zip_a, MAKE_ROOM)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
            self.assertEqual(facts['package.system'], 'openwrt')
            tx = ev[-1]['transaction']
            fakeemmc.reset(self.emmc)
            # another zip, or a copy of the project: not the payload the transaction was made with
            for run in (lambda: self.pkg(shell, zip_b, answers), lambda: self.inst(shell, INSTALL)):
                self.device(pull='noboot')
                r, ev, facts = run()
                self.assertEqual(r.returncode, 1)
                self.assertIn('tools or the package differ', ev[-1]['message'])
                self.assertEqual(self.writes(), [])
            # the same zip: found, checked, continued into the prepared region, as a package (no system question)
            self.device(pull='noboot')
            r, ev, facts = self.pkg(shell, zip_a, answers)
            self.assertEqual((facts['resume.transaction'], facts['resume.check'], facts['verdict.code']), (tx, 'RESUME-OK', 'resume'),
                             r.stdout[-3000:])
            self.assertEqual(facts['package.system'], 'openwrt')
            asked = [e['id'] for e in ev if e['event'] == 'question']
            for q in ('MU300_ANS_SYSTEMS', 'MU300_ANS_KERNEL', 'MU300_ANS_OVERWRITE', 'MU300_STORAGE'):
                self.assertNotIn(q, asked)
            self.assertIn('could not read /dev/block/by-name/boot_a', ev[-1]['message'])
            self.assertEqual(self.writes(), [])

    # (the tests of ResetAndResume run there, not again here)
    for _n in [n for n in dir(ResetAndResume) if n.startswith('test_')]:
        locals()[_n] = None
    del _n

KEEP = dict(MU300_ANS_MAKE_ROOM='yes', MU300_ANS_MAKE_ROOM_METHOD='keep', MU300_ANS_LINUX_GIB='4', MU300_ANS_SHRINK='yes',
            MU300_ANS_REBOOT='yes')


class OnlineShrink(ResetAndResume):
    """The online way (method keep): dikeckaan's method, kanoqwq's implementation. install.sh on the fake eMMC with
    tests/fakeonline.py in place of the device script: the transaction, the worker's table and F2FS, the token, the
    restart instead of a reset, the run that continues, and every interruption that the next run picks up. The
    device script and mu300-f2fs-online themselves run for real in tests/online-shrink-e2e.sh."""

    def setUp(self):
        super().setUp()
        self.wrapper = self.tmp / 'fake-online.sh'
        self.wrapper.write_text('#!/bin/sh\nexec "%s" "%s" "$@"\n' % (sys.executable, TOP / 'tests/fakeonline.py'))

    def inst(self, shell, answers, *args, **env):
        env.setdefault('MU300_ONLINE_SH', str(self.wrapper))
        env.setdefault('MU300_ONLINE_POLL', '0')
        env.setdefault('MU300_ONLINE_LOST_TRIES', '3')
        return super().inst(shell, answers, *args, **env)

    def knobs(self, **kw):
        (self.emmc / 'online.json').write_text(json.dumps(kw))

    def fresh(self):
        shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc')
        shutil.rmtree(self.backups, ignore_errors=True)

    def keep(self, shell, **answers):
        self.device(pull=True)
        before, misc = fakeemmc.table(self.emmc), fakeemmc.bcb(self.emmc)
        blocks = fakeemmc.f2fs_blocks(self.emmc)
        r, ev, facts = self.inst(shell, dict(KEEP, **answers))
        return r, ev, facts, before, misc, blocks

    def test_android_keeps_its_data_and_the_installation_continues_after_a_restart(self):
        for shell in self.each_shell():
            self.fresh()
            r, ev, facts, before, misc, blocks = self.keep(shell)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
            self.assertEqual((facts['makeroom.online'], facts['makeroom.method']), ('yes', 'keep'))
            self.assertEqual((ev[-1]['event'], ev[-1]['repartitioned'], ev[-1]['resume']), ('done', 'yes', 'pending'))
            asked = [e['id'] for e in ev if e['event'] == 'question']
            self.assertNotIn('MU300_ANS_ERASE_ANDROID', asked)
            rec = json.loads(Path(ev[-1]['transaction']).read_text())
            self.assertEqual((rec['state'], rec['method']), ('prepared', 'online'))
            # only userdata's end moved; the F2FS is at its target, a whole number of sections inside it, and more
            # than 2 GiB above what is used (kano's margin)
            after = fakeemmc.table(self.emmc)
            self.assertTrue(tables_equal_but_userdata(before, after))
            ud = [p for p in after if p[0] == 'userdata'][0]
            self.assertEqual(rec['target'], ud[2] - ud[1] + 1)
            self.assertEqual(fakeemmc.f2fs_blocks(self.emmc), rec['fs_target'])
            self.assertEqual(rec['fs_blocks'], blocks)
            self.assertEqual(rec['fs_target'] % 512, 0)
            self.assertLessEqual(rec['fs_target'] * 8, rec['target'])
            self.assertGreater(rec['fs_target'] * 4096, (1 << 30) + (2 << 30))
            # the token, and misc exactly as it was: no reset is asked for
            self.assertEqual(fakeemmc.read(self.emmc, rec['region_start'], 8), resume.marker(rec['token']))
            self.assertEqual(fakeemmc.bcb(self.emmc), misc)
            self.assertEqual(self.calls('reboot')[0]['argv'], ['reboot'])
            # the host wrote the token only (the worker wrote the table, checked against both tables it was given)
            self.assertEqual([c for c in self.writes() if 'of=/dev/block/' in c and 'mu300-marker.bin' not in c], [])
            # the backup: the tables before and after, with the rest
            bd = Path(rec['backup'])
            names = sorted(l.split('  ')[1] for l in (bd / 'SHA256SUMS').read_text().splitlines())
            self.assertIn('gpt-new.head', names); self.assertIn('boot_a.img', names)
            # Android has not restarted yet: the kernel still has the old table
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual(r.returncode, 1)
            self.assertIn('has not restarted since userdata was shrunk', ev[-1]['message'])
            self.assertEqual(self.writes(), [])
            # the restart: nothing is reset, the kernel reads the new table; the installation continues
            fakeemmc.reset(self.emmc, wipe=False)
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual((facts['resume.check'], facts['verdict.code'], facts['storage']), ('RESUME-OK', 'resume', 'internal'),
                             r.stdout[-3000:])
            self.assertIn('could not read /dev/block/by-name/boot_a', ev[-1]['message'])
            self.assertEqual(self.writes(), [])
            # an F2FS that is not the one shrunk, or not at its size, is not continued
            raw = bytearray((self.emmc / 'dev/block/dm-6').read_bytes()); raw[1024 + 108] ^= 1
            (self.emmc / 'dev/block/dm-6').write_bytes(bytes(raw))
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertIn('not the filesystem that was shrunk', ev[-1]['message'])
            self.assertEqual(self.writes(), [])

    def test_a_kernel_that_refuses_changes_nothing(self):
        for shell in self.each_shell():
            self.fresh()
            self.knobs(probe='refused')
            r, ev, facts, before, misc, blocks = self.keep(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn('does not shrink this F2FS while it is mounted (errno 95)', ev[-1]['message'])
            self.assertIn('answer reset', ev[-1]['message'])
            self.assertEqual((fakeemmc.table(self.emmc), fakeemmc.bcb(self.emmc), fakeemmc.f2fs_blocks(self.emmc)), (before, misc, blocks))
            self.assertEqual(self.writes(), [])
            tx = next(self.backups.glob('*/transaction.json'))
            self.assertEqual(json.loads(tx.read_text())['state'], 'declined')
            # a declined transaction is not one to continue: the next run plans anew
            self.knobs()
            self.device(pull=True)
            r, ev, facts = self.inst(shell, KEEP)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:])
            self.assertNotIn('resume.transaction', [k for k in facts if facts[k] == str(tx)])

    def test_an_interrupted_shrink_is_finished_by_the_next_run(self):
        for shell in self.each_shell():
            self.fresh()
            self.knobs(stop='shrunk')
            r, ev, facts, before, misc, blocks = self.keep(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn('Do not restart or power off the device', ev[-1]['message'])
            tx = next(self.backups.glob('*/transaction.json'))
            rec = json.loads(tx.read_text())
            self.assertEqual(rec['state'], 'prepared-request')
            self.assertEqual(fakeemmc.table(self.emmc), before)              # the table: not yet
            self.assertEqual(fakeemmc.f2fs_blocks(self.emmc), rec['fs_target'])
            # --check says so and writes nothing
            self.knobs()
            self.device(pull=True)
            r, ev, facts = self.inst(shell, {}, '--check')
            self.assertIn('did not finish', r.stdout)
            self.assertEqual(self.writes(), [])
            # the next run finds the shrunk F2FS behind the old table, commits the table and asks for the restart
            r, ev, facts = self.inst(shell, dict(INSTALL, MU300_ANS_REBOOT='yes'))
            self.assertEqual(r.returncode, 0, r.stdout[-3000:])
            self.assertEqual(facts['online.state'], 'STATE=shrunk')
            self.assertEqual(json.loads(tx.read_text())['state'], 'prepared')
            ud = [p for p in fakeemmc.table(self.emmc) if p[0] == 'userdata'][0]
            self.assertEqual(ud[2] - ud[1] + 1, rec['target'])
            self.assertEqual(fakeemmc.read(self.emmc, rec['region_start'], 8), resume.marker(rec['token']))
            fakeemmc.reset(self.emmc, wipe=False)
            self.device(pull='noboot')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual(facts['resume.check'], 'RESUME-OK', r.stdout[-3000:])

    def test_nothing_happened_yet_puts_the_transaction_aside(self):
        for shell in self.each_shell():
            self.fresh()
            self.knobs(lost=True, stop='shrunk')
            # the worker never ran (stop before anything: the F2FS put back) and the device stopped answering
            r, ev, facts, before, misc, blocks = self.keep(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn('does not answer', ev[-1]['message'])
            tx = next(self.backups.glob('*/transaction.json'))
            raw = bytearray((self.emmc / 'dev/block/dm-6').read_bytes())
            import struct
            struct.pack_into('<Q', raw, 1024 + 36, blocks); struct.pack_into('<Q', raw, 5120 + 36, blocks)
            (self.emmc / 'dev/block/dm-6').write_bytes(bytes(raw))
            self.knobs()
            self.device(pull=True)
            r, ev, facts = self.inst(shell, KEEP)
            self.assertEqual(facts['online.state'], 'STATE=unchanged', r.stdout[-3000:])
            self.assertEqual(json.loads(tx.read_text())['state'], 'declined')
            self.assertEqual(r.returncode, 0, r.stdout[-3000:])         # and room is made anew

    def test_android_data_that_would_not_fit_is_refused(self):
        for shell in self.each_shell():
            self.fresh()
            ud = [p for p in fakeemmc.table(self.emmc) if p[0] == 'userdata'][0]
            self.knobs(used=(ud[2] - ud[1] + 1) * 512 - (5 << 30))
            r, ev, facts, before, misc, blocks = self.keep(shell)
            self.assertEqual(r.returncode, 1)
            self.assertIn("too large: Android's data takes", r.stdout)
            self.assertIn('the answer in MU300_ANS_LINUX_GIB was not accepted', ev[-1]['message'])
            self.assertEqual((fakeemmc.table(self.emmc), self.writes()), (before, []))

    def test_on_a_ufs_of_4096_byte_blocks(self):
        # issue #396's 1 TB U30 Air (sda, 4096-byte blocks): the table is 48 and 40 sectors, the worker gets the
        # backup table's place at the disk's end - 40 sectors, and userdata's new end falls on a block
        for shell in self.each_shell():
            shutil.rmtree(self.emmc); self.emmc = fakeemmc.make(self.tmp / 'emmc', layout='ufs1t')
            shutil.rmtree(self.backups, ignore_errors=True)
            self.device(pull=True, layout='ufs1t')
            before = fakeemmc.table(self.emmc)
            r, ev, facts = self.inst(shell, KEEP)
            self.assertEqual(r.returncode, 0, r.stdout[-3000:] + r.stderr)
            self.assertEqual(facts['makeroom.method'], 'keep')
            rec = json.loads(Path(ev[-1]['transaction']).read_text())
            after = fakeemmc.table(self.emmc)
            self.assertTrue(tables_equal_but_userdata(before, after))
            ud = [p for p in after if p[0] == 'userdata'][0]
            self.assertEqual(((ud[2] + 1) % 8, ud[2] - ud[1] + 1), (0, rec['target']))
            self.assertIn('start %s ' % rec['token'], ' '.join(c['cmd'] for c in self.calls()))
            self.assertTrue(any(c['cmd'].endswith(' 40') and 'android-online-shrink.sh start' in c['cmd'] for c in self.calls()))
            self.assertEqual(fakeemmc.f2fs_blocks(self.emmc), rec['fs_target'])
            fakeemmc.reset(self.emmc, wipe=False)
            self.device(pull='noboot', layout='ufs1t')
            r, ev, facts = self.inst(shell, INSTALL)
            self.assertEqual(facts['resume.check'], 'RESUME-OK', r.stdout[-3000:])

    def test_without_the_helper_only_the_reset_is_offered(self):
        for shell in self.each_shell():
            self.fresh()
            self.device(pull=True)
            r, ev, facts = self.inst(shell, {}, '--check', MU300_F2FS_ONLINE=str(self.tmp / 'missing'))
            self.assertEqual(facts['makeroom.online'], 'no')
            self.assertIn('mu300-f2fs-online', facts['makeroom.online_reason'])
            r, ev, facts = self.inst(shell, MAKE_ROOM, MU300_F2FS_ONLINE=str(self.tmp / 'missing'))
            self.assertEqual(r.returncode, 0, r.stdout[-3000:])
            self.assertNotIn('MU300_ANS_MAKE_ROOM_METHOD', [e['id'] for e in ev if e['event'] == 'question'])
            self.assertEqual(json.loads(Path(ev[-1]['transaction']).read_text()).get('method'), None)

    for _n in [n for n in dir(ResetAndResume) if n.startswith('test_')]:
        locals()[_n] = None
    del _n


class Static(unittest.TestCase):
    def test_marked_installed_only_after_the_boot_image_and_misc(self):
        src = (TOP / 'install.sh').read_text()
        self.assertLess(src.index('write_linux_boot "$WORK/boot-linux-slot$LINUX_SLOT.img"\n'),
                        src.index('resume_py set "$RESUME_FILE" state=installed'))

    def test_the_old_clear_of_userdata_is_gone(self):
        # a filesystem cleared from outside is one an encrypted Android cannot mount: recovery formats it now
        for name in ('install.sh', 'install.ps1', 'tools/resume.sh'):
            self.assertNotIn('of=/dev/block/by-name/userdata', (TOP / name).read_text(), name)

    def test_experimental_and_credited(self):
        for name in ('tools/resume.sh', 'tools/resume.py'):
            text = (TOP / name).read_text()
            self.assertIn('EXPERIMENTAL', text)
            self.assertIn('f6b0668d', text)
            self.assertIn('kano', text)


if __name__ == '__main__':
    unittest.main()
