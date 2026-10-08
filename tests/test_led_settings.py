"""The System > LED Configuration lamps: led-status brightness, persistence and validation, and the page's controls."""
import json
import shutil
import subprocess
import unittest
from pathlib import Path

from helpers import ShellTest, TOP

LED = TOP / 'rootfs/overlay/opt/mu300/bin/led-status'
UI = TOP / 'openwrt/overlay/www/luci-static/resources/view/system/leds.js'
DEFAULTS = TOP / 'openwrt/overlay/etc/uci-defaults/90-mu300'


class LedSettings(ShellTest):
    def leds(self, max_wifi='255'):
        leds = self.tmp / 'leds'
        for name in ('sc27xx:red', 'sc27xx:green', 'sc27xx:blue', 'keyboard-backlight'):
            led = leds / name
            led.mkdir(parents=True)
            (led / 'brightness').write_text('0\n')
            (led / 'trigger').write_text('none\n')
            (led / 'max_brightness').write_text(max_wifi if name == 'keyboard-backlight' else '255')
        self.stub('uci', '''case "$3" in
  system.mu300_leds.signal) echo "${TEST_SIGNAL_ENABLED:-1}" ;;
  system.mu300_leds.wifi) echo "${TEST_WIFI_ENABLED:-1}" ;;
  system.mu300_leds.signal_brightness) echo "${TEST_SIGNAL_BRIGHTNESS:-255}" ;;
  system.mu300_leds.wifi_brightness) echo "${TEST_WIFI_BRIGHTNESS:-127}" ;;
esac
''')
        self.stub('mu300-device', 'echo f50')
        return leds

    def level(self, leds, name):
        return (leds / name / 'brightness').read_text().strip()

    def test_signal_and_wifi_brightness_are_independent_and_persistent(self):
        for shell in self.each_shell():
            leds = self.leds()
            run = self.tmp / 'run'
            run.mkdir(exist_ok=True)
            base = dict(MU300_LED_SYSFS_ROOT=str(leds), MU300_LED_RUN_DIR=str(run),
                        TEST_SIGNAL_BRIGHTNESS='64', TEST_WIFI_BRIGHTNESS='32')

            def apply(state, **extra):
                env = dict(base)
                env.update(extra)
                r = self.script(shell, LED, state, **env)
                self.assertEqual(r.returncode, 0, r.stderr)

            def rgb():
                return tuple(self.level(leds, 'sc27xx:' + c) for c in ('red', 'green', 'blue'))

            apply('online-4g')
            self.assertEqual(rgb(), ('0', '0', '64'))
            apply('wifi-on')
            self.assertEqual(self.level(leds, 'keyboard-backlight'), '32')
            apply('online-5g')
            self.assertEqual(rgb(), ('0', '64', '0'))
            self.assertEqual(self.level(leds, 'keyboard-backlight'), '32')
            apply('refresh', TEST_SIGNAL_BRIGHTNESS='96', TEST_WIFI_BRIGHTNESS='48')
            self.assertEqual(self.level(leds, 'sc27xx:green'), '96')
            self.assertEqual(self.level(leds, 'keyboard-backlight'), '48')
            apply('refresh', TEST_SIGNAL_ENABLED='0', TEST_WIFI_ENABLED='0')
            self.assertEqual(rgb(), ('0', '0', '0'))
            self.assertEqual(self.level(leds, 'keyboard-backlight'), '0')
            (leds / 'keyboard-backlight' / 'max_brightness').write_text('100\n')
            apply('refresh', TEST_SIGNAL_ENABLED='1', TEST_WIFI_ENABLED='1',
                  TEST_SIGNAL_BRIGHTNESS='0', TEST_WIFI_BRIGHTNESS='255')
            self.assertEqual(self.level(leds, 'sc27xx:green'), '0')
            self.assertEqual(self.level(leds, 'keyboard-backlight'), '100')
            (leds / 'keyboard-backlight' / 'max_brightness').write_text('255\n')
            apply('refresh', TEST_SIGNAL_BRIGHTNESS='bad', TEST_WIFI_BRIGHTNESS='999')
            self.assertEqual(self.level(leds, 'sc27xx:green'), '255')
            self.assertEqual(self.level(leds, 'keyboard-backlight'), '127')

    def test_led_disabled_keeps_the_lamps_dark(self):
        # V50: LED_DISABLED=1 in led.conf (the profile's /etc/mu300/led.conf) squelches both lamps at any state
        for shell in self.each_shell():
            leds = self.leds()
            run = self.tmp / 'run'
            run.mkdir(exist_ok=True)
            conf = self.tmp / 'led.conf'
            conf.write_text('LED_DISABLED=1\n')
            r = self.script(shell, LED, 'online-5g', MU300_LED_SYSFS_ROOT=str(leds), MU300_LED_RUN_DIR=str(run),
                            MU300_LED_CONF=str(conf))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(tuple(self.level(leds, 'sc27xx:' + c) for c in ('red', 'green', 'blue')),
                             ('0', '0', '0'))

    def test_defaults_and_animations_use_brightness(self):
        defaults = DEFAULTS.read_text(encoding='utf-8')
        script = LED.read_text(encoding='utf-8')
        self.assertIn("set system.mu300_leds.signal_brightness='255'", defaults)
        self.assertIn("set system.mu300_leds.wifi_brightness='127'", defaults)
        self.assertIn('set_rgb "$_r" "$_w" "$_b"', script)
        self.assertIn('set_rgb 255 0 0; pause_us 120000', script)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for LuCI JS smoke tests')
    def test_page_labels_are_english_source_and_controls_are_validated(self):
        # the page is English _() (translated through the panel catalogs); the two lamps' brightness controls
        # carry their own range, bounded by the hardware maximum, and the defaults match led-status
        harness = r'''
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const used = [];
const _ = (s) => { used.push(s); return s; };
const form = { NamedSection: {}, GridSection: {}, Flag: {}, Value: {}, ListValue: {} };
form.Map = function() {
    const map = { sections: [], section(_type, name, _id, title) {
        const section = { name, title, options: [], option(_type, key, label, description) {
            const option = { key, label, description }; this.options.push(option); return option;
        } }; this.sections.push(section); return section;
    }, render() { return this; } };
    return map;
};
const page = new Function('view', 'uci', 'rpc', 'form', 'fs', 'L', 'document', '_', src)(
    { extend: o => o }, {}, { declare: () => () => ({}) }, form, {}, { env: {} }, { documentElement: {} }, _);
const map = page.render([{}, []]);
const opts = map.sections[0].options;
const sig = opts.find(o => o.key === 'signal_brightness');
const wf = opts.find(o => o.key === 'wifi_brightness');
if (sig.label !== 'Signal lamp brightness' || wf.label !== 'Wi-Fi lamp brightness') throw Error('labels');
if (sig.datatype !== 'range(0,255)' || sig.default !== '255') throw Error('signal control');
const real = page.render([{ 'keyboard-backlight': { max_brightness: 127, triggers: [] } }, []]);
const rw = real.sections[0].options.find(o => o.key === 'wifi_brightness');
if (rw.datatype !== 'range(0,127)' || rw.default !== '127') throw Error('hardware maximum');
if (!used.includes('LED Configuration') || !used.includes('Physical status lamps')) throw Error('not _()');
'''
        r = subprocess.run(['node', '-', str(UI)], input=harness, capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == '__main__':
    unittest.main()
