"""The F50 platform offers the standalone plugin an optional pre-radio hook."""
from pathlib import Path
import unittest


TOP = Path(__file__).resolve().parents[1]
RADIO = TOP / 'rootfs/overlay/opt/mu300/bin/mobile-data'
ATD = TOP / 'openwrt/overlay/etc/init.d/mu300-atd'


class EarlyReplayHook(unittest.TestCase):
    def test_hook_is_after_handshake_and_radio_off_check(self):
        radio = RADIO.read_text(encoding='utf-8')
        start = radio.index('radio_on_locked()')
        end = radio.index('\nradio_on() {', start)
        body = radio[start:end]
        self.assertLess(body.index("'AT+SMMSWAP=0'"), body.index("out=$(at 'AT+CFUN?'"))
        self.assertLess(body.index("out=$(at 'AT+CFUN?'"), body.index('lock replay early'))
        self.assertLess(body.index('lock replay early'), body.index("at 'AT+SFUN=4'"))
        self.assertIn('[ -x /usr/libexec/unisoc-modem/lock ]', body)
        self.assertIn('early lock replay unverified; late fallback remains armed', body)

    def test_pending_marker_brackets_platform_radio_on(self):
        atd = ATD.read_text(encoding='utf-8')
        radio = RADIO.read_text(encoding='utf-8')
        self.assertLess(atd.index('unisoc-modem-early-hook-pending'), atd.index('radio-warmup'))
        self.assertIn('[ "$rc" = 0 ] && rm -f /run/unisoc-modem-early-hook-pending', radio)


if __name__ == '__main__':
    unittest.main()
