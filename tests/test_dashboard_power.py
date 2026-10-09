"""The dashboard's power data: this device has no battery (it is powered over USB), so dashboard-info reports no
battery (present=0) whatever is in /sys/class/power_supply, and home.js has no battery tile."""
import json
import unittest

from helpers import ShellTest, TOP

APP = TOP / 'openwrt' / 'luci-app-mu300'
INFO = APP / 'root' / 'usr' / 'libexec' / 'unisoc-modem' / 'dashboard-info'


class Power(ShellTest):
    def setUp(self):
        super().setUp()
        self.stub('busybox', 'shift 4; exec "$@"')   # busybox timeout -s KILL N CMD...
        for name in ('ubus', 'ip', 'iw', 'uci'):
            self.stub(name, 'exit 1')
        self.psy = self.tmp / 'power_supply'
        self.psy.mkdir()

    def supply(self, name, **attrs):
        d = self.psy / name
        d.mkdir()
        for k, v in attrs.items():
            (d / k).write_text(v + '\n')

    def power(self):
        out = []
        for shell in self.each_shell():
            r = self.script(shell, INFO, MU300_POWER_SUPPLY_DIR=self.psy)
            out.append(json.loads(r.stdout)['power'])
        self.assertTrue(out)
        for p in out[1:]:
            self.assertEqual(p, out[0])
        return out[0]

    def test_no_supplies_at_all(self):
        p = self.power()
        self.assertEqual(p['present'], 0)
        self.assertIsNone(p['capacity'])

    def test_a_battery_supply_is_still_ignored(self):
        # a fuel gauge that reports a battery (a mainline F50's made-up one, or a U30 Air's) must not make a tile
        # appear: this device has none
        self.supply('sc27xx-fgu', type='Battery', present='1', capacity='64', status='Discharging',
                    voltage_now='3850000', current_now='-470000')
        self.supply('battery', type='Battery', present='1', capacity='87', status='Charging',
                    voltage_now='4123000', current_now='780000')
        self.supply('usb', type='USB', online='1', voltage_now='5012000', current_now='900000')
        p = self.power()
        self.assertEqual(p['present'], 0)
        self.assertIsNone(p['capacity'])
        self.assertIsNone(p['status'])
        self.assertIsNone(p['usb'])


if __name__ == '__main__':
    unittest.main()
