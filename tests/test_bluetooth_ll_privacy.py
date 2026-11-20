"""Bluetooth LE on Marlin3 (patches 0033 and 0034, FINDINGS 243): with the controller's address resolution on, the Marlin3
firmware reported a peer advertising with a private address as 00:00:00:00:00:00, so a connection through the
accept list never started. Patch 0034 clears LL Privacy from these controllers' LE features, for every mainline
series, and touches nothing else; 0033, mainline's 397464709a20, scans unfiltered for host-resolved peers, which a
controller without LL Privacy needs."""
import unittest
from pathlib import Path

TOP = Path(__file__).resolve().parent.parent
PATCH = TOP / 'upstream/patches/0034-bluetooth-marlin3-host-address-resolution.patch'
BACKPORT = TOP / 'upstream/patches/0033-bluetooth-hci-sync-scan-unfiltered-for-host-resolved-RPAs.patch'


class MarlinHostAddressResolution(unittest.TestCase):
    def test_ll_privacy_cleared_for_spreadtrum_only(self):
        p = PATCH.read_text()
        self.assertIn('+++ b/net/bluetooth/hci_event.c\n', p)
        hunk = p.split('+++ b/net/bluetooth/hci_event.c\n', 1)[1]
        self.assertIn('\n \tmemcpy(hdev->le_features, rp->features, 8);\n', hunk)
        self.assertIn('\n+\tif (hdev->manufacturer == 0x01ec)\n+\t\thdev->le_features[0] &= ~HCI_LE_LL_PRIVACY;\n', hunk)

    def test_only_hci_event_is_changed(self):
        files = [l for l in PATCH.read_text().splitlines() if l.startswith('+++ ')]
        self.assertEqual(['+++ b/net/bluetooth/hci_event.c'], files)

    def test_one_patch_with_its_number_for_every_series(self):
        # in patches/ itself, not in a series directory: 6.18 and 7.3 both get it
        names = [q.relative_to(TOP / 'upstream/patches').as_posix()
                 for q in (TOP / 'upstream/patches').rglob('0034-*.patch')]
        self.assertEqual([PATCH.name], names)

    def test_host_resolved_peers_scan_unfiltered_first(self):
        # without LL Privacy the accept list cannot match a bonded peer's private address: mainline 397464709a20
        p = BACKPORT.read_text()
        self.assertIn('397464709a204da9b8dc3b01d6ea42539d951cd2', p)
        self.assertIn('+\tif (!force_filter && !hdev->suspended && !ll_privacy_capable(hdev) &&\n', p)
        names = [q.relative_to(TOP / 'upstream/patches').as_posix()
                 for q in (TOP / 'upstream/patches').rglob('0033-*.patch')]
        self.assertEqual([BACKPORT.name], names)


if __name__ == '__main__':
    unittest.main()
