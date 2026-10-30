"""upstream/check-parity.py: nothing the vendor 5.4 kernel has may be missing from mainline without a line in
upstream/parity-5.4.txt - the repository as it is, and the rule itself on small made-up kernels."""
import importlib.util
import io
import re
import tarfile
import tempfile
import unittest
from pathlib import Path

TOP = Path(__file__).resolve().parents[1]
UP = TOP / 'upstream'

spec = importlib.util.spec_from_file_location('check_parity', UP / 'check-parity.py')
cp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cp)


class Repository(unittest.TestCase):
    def test_every_5_4_item_is_on_mainline_or_said_why_not(self):
        entries, errors = cp.check_repo()
        self.assertEqual(errors, [])
        self.assertGreater(len(entries), 100)

    def test_the_builds_run_the_check(self):
        self.assertIn('python3 /work/check-parity.py --mainline $OUT', (UP / 'build-modules.sh').read_text())
        self.assertIn('check-parity.py" --mainline "$UO"', (UP / 'make-bundle.sh').read_text())
        self.assertIn('check-parity.py" --5.4 "$OUT"', (TOP / 'kernel/build-all.sh').read_text())

    def test_the_board_inventories_come_from_the_script(self):
        invs = cp.inventories()
        self.assertIn('5.4', invs['f50b'])
        self.assertTrue(any(k != '5.4' for k in invs['f50b']))
        for board, kernels in invs.items():
            for k, items in kernels.items():
                self.assertTrue(items, (board, k))
                for kind, name in items:
                    self.assertIn(kind, cp.DEVICE_KINDS, (board, k, kind, name))
        self.assertIn('driver $bus/', (UP / 'parity-inventory.sh').read_text())

    def test_missing_items_name_their_group_and_boards(self):
        entries, _ = cp.parse_parity()
        groups = {}
        for e in entries.values():
            if e.status == 'missing':
                groups.setdefault(e.field('group'), []).append(e.name)
        # groups nobody has ported yet (the porting list shrinks group by group)
        self.assertIn('display', groups)
        self.assertIn('debug', groups)


class Rule(unittest.TestCase):
    """a made-up repository: kernel/ inputs, upstream/parity/ and upstream/parity-5.4.txt in a temporary directory"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.top = Path(self.tmp.name)
        (self.top / 'kernel').mkdir()
        for f in cp.INPUTS54:
            (self.top / f).write_text('# %s\n' % f)
        (self.top / 'kernel/build-display.sh').write_text('cp $D/sprd-drm.ko out/\n')
        self.d = self.top / 'upstream/parity'
        self.d.mkdir(parents=True)
        self.parity = self.top / 'upstream/parity-5.4.txt'
        self.write54(['module zram', 'module sprd_trng', 'builtin unix', 'extra sprd_drm'])
        self.mainline({'6.18': ['ko zram', 'cfg UNIX'], '7.3': ['ko zram', 'cfg UNIX']})
        (self.d / 'f50b-5.4.inv').write_text('driver platform/sprd-rtc\ntz soc-thmzone\ntz board-thmzone\n')
        (self.d / 'f50b-7.3.inv').write_text('driver platform/sprd-rtc\ntz soc-thmzone\n')
        self.lines = ['module sprd_trng missing group:rng boards:f50 # no driver',
                      'builtin unix ok cfg:UNIX',
                      'extra sprd_drm missing group:display boards:f50 # display',
                      'tz board-thmzone missing group:thermal boards:f50 # generic-adc-thermal']

    def write54(self, items, digest=None):
        digest = digest or cp.inputs_hash(self.top)
        (self.d / '5.4-build.list').write_text('# inputs %s\n' % digest + ''.join(i + '\n' for i in items))

    def mainline(self, series):
        out = {}
        for s, names in series.items():
            for n in names:
                out.setdefault(n, []).append(s)
        (self.d / 'mainline.list').write_text(''.join('%s %s\n' % (n, ' '.join(ss)) for n, ss in out.items()))

    def check(self):
        self.parity.write_text('\n'.join(self.lines) + '\n')
        return cp.check_repo(self.top, self.d, self.parity)[1]

    def test_a_complete_file_passes(self):
        self.assertEqual(self.check(), [])

    def test_a_5_4_module_without_a_line_or_a_namesake_fails(self):
        self.lines.pop(0)
        errors = self.check()
        self.assertEqual(len(errors), 1)
        self.assertIn('module sprd_trng: 5.4 has it', errors[0])

    def test_a_namesake_must_be_in_every_mainline_series(self):
        self.mainline({'6.18': ['cfg UNIX'], '7.3': ['ko zram', 'cfg UNIX']})
        self.assertIn('module zram: 5.4 has it', self.check()[0])

    def test_a_board_item_the_mainline_inventory_lacks_needs_a_line(self):
        self.lines.pop()
        self.assertIn('tz board-thmzone: 5.4 has it', self.check()[0])

    def test_an_ok_line_needs_its_reference_in_every_series(self):
        self.lines[1] = 'builtin unix ok cfg:UNIX cfg:IPV6'
        errors = self.check()
        self.assertEqual(len(errors), 2)
        self.assertTrue(all('cfg:IPV6 is not in mainline' in e for e in errors))
        self.lines[1] = 'builtin unix ok cfg:IPV6|cfg:UNIX'
        self.assertEqual(self.check(), [])

    def test_an_ok_line_needs_something_a_build_can_check(self):
        self.lines[1] = 'builtin unix ok bind:platform/sprd-rtc'
        self.assertIn('needs a ko:, cfg: or =', self.check()[0])

    def test_run_time_proof_must_be_in_a_mainline_inventory(self):
        self.lines[1] = 'builtin unix ok cfg:UNIX bind:platform/sprd-rtc has:tz/soc-thmzone'
        self.assertEqual(self.check(), [])
        self.lines[1] = 'builtin unix ok cfg:UNIX bind:platform/sprd-unix'
        self.assertIn('bind:platform/sprd-unix is in no mainline inventory', self.check()[0])

    def test_missing_and_na_lines_say_why_and_for_whom(self):
        self.lines[0] = 'module sprd_trng missing boards:f50 # no driver'
        self.assertIn('name its group', self.check()[0])
        self.lines[0] = 'module sprd_trng missing group:rng # no driver'
        self.assertIn('name the boards', self.check()[0])
        self.lines[0] = 'module sprd_trng na'
        self.assertIn('say why', self.check()[0])
        self.lines[0] = 'module sprd_trng na boards:f40 # why'
        self.assertIn('boards: f40', self.check()[0])

    def test_a_line_for_nothing_5_4_has_fails(self):
        self.lines.append('module sprd_gone na # gone')
        self.assertIn('module sprd_gone is not an item', self.check()[0])

    def test_a_missing_item_that_mainline_has_now_must_say_so(self):
        self.mainline({'6.18': ['ko zram', 'ko sprd_trng', 'cfg UNIX'], '7.3': ['ko zram', 'ko sprd_trng', 'cfg UNIX']})
        self.assertIn('marked missing, but mainline has it', self.check()[0])

    def test_a_changed_5_4_build_needs_a_new_record(self):
        (self.top / 'kernel/mu300-linux.fragment').write_text('CONFIG_NEW=m\n')
        self.assertIn('other 5.4 build inputs', self.check()[0])

    def test_the_display_modules_are_part_of_the_record(self):
        (self.top / 'kernel/build-display.sh').write_text('cp $D/sprd-drm.ko $P/sc27xx_pd.ko out/\n')
        self.write54(['module zram', 'module sprd_trng', 'builtin unix', 'extra sprd_drm'])
        self.assertTrue(any('build-display.sh' in e for e in self.check()))

    def test_record_54_reads_a_5_4_build(self):
        out = self.top / 'out'
        for d in ('modules', 'modules-u30air'):
            (out / d).mkdir(parents=True)
        (out / 'modules/sprd-trng.ko').touch()
        (out / 'modules-u30air/zte_sar_stk.ko').touch()
        (out / 'modules.builtin').write_text('kernel/net/unix/unix.ko\n')
        cp.record_54(out, self.d / '5.4-build.list', self.top)
        items, digest = cp.read_build54(self.d / '5.4-build.list')
        self.assertEqual(items, {('module', 'sprd_trng'), ('module', 'zte_sar_stk'), ('builtin', 'unix'),
                                 ('extra', 'sprd_drm')})
        self.assertEqual(digest, cp.inputs_hash(self.top))


class MainlineBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.d = Path(self.tmp.name)

    def bundle(self, modules, builtin, config):
        path = self.d / 'mu300-kernel-7.3.tar.gz'
        with tarfile.open(path, 'w:gz') as t:
            for name, text in (('modules.list', '\n'.join(modules)), ('modules.builtin', builtin),
                               ('kernel.config', config)):
                data = text.encode()
                info = tarfile.TarInfo('./' + name)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        return path

    def test_a_bundle_keeps_module_names_that_differ_in_case_apart(self):
        b = self.bundle(['xt_HL.ko', 'xt_hl.ko'], 'kernel/net/unix/unix.ko\n',
                        '# Linux/arm64 7.3.0 Kernel Configuration\nCONFIG_UNIX=y\n# CONFIG_IPV6 is not set\n')
        have, series = cp.bundle_names(b)
        self.assertEqual(series, '7.3')
        self.assertEqual(have['ko'], {'xt_HL', 'xt_hl', 'unix'})
        self.assertEqual(have['cfg'], {'UNIX'})

    def test_a_build_fails_on_a_reference_or_namesake_it_does_not_have(self):
        entries = {('builtin', 'ipv6'): cp.Entry('builtin', 'ipv6', 'ok', ['cfg:IPV6'], '', 'x:1'),
                   ('builtin', 'ntfs'): cp.Entry('builtin', 'ntfs', 'ok', ['=|ko:ntfs3'], '', 'x:2'),
                   ('module', 'sprd_trng'): cp.Entry('module', 'sprd_trng', 'missing', ['group:rng'], 'r', 'x:3')}
        items = {('builtin', 'ipv6'), ('builtin', 'ntfs'), ('module', 'sprd_trng'), ('module', 'zram')}
        have = {'ko': {'zram', 'ntfs3'}, 'cfg': {'IPV6'}}
        self.assertEqual(cp.check_build(entries, items, have, '7.3'), [])
        errors = cp.check_build(entries, items, {'ko': {'ntfs3'}, 'cfg': set()}, '7.3')
        self.assertEqual(len(errors), 2)
        self.assertTrue(any(re.search(r'cfg:IPV6 is not in 7\.3', e) for e in errors))
        self.assertTrue(any('module zram of 5.4 is not in 7.3' in e for e in errors))

    def test_record_keeps_what_each_series_has(self):
        path = self.d / 'mainline.list'
        entries = {('builtin', 'ipv6'): cp.Entry('builtin', 'ipv6', 'ok', ['cfg:IPV6'], '', 'x:1')}
        items = {('module', 'zram'), ('builtin', 'ipv6')}
        cp.record_mainline({'ko': {'zram'}, 'cfg': {'IPV6'}}, '6.18', entries, items, path)
        cp.record_mainline({'ko': {'zram'}, 'cfg': set()}, '7.3', entries, items, path)
        got = cp.read_mainline(path)
        self.assertEqual(got['6.18'], {'ko': {'zram'}, 'cfg': {'IPV6'}})
        self.assertEqual(got['7.3'], {'ko': {'zram'}, 'cfg': set()})


if __name__ == '__main__':
    unittest.main()
