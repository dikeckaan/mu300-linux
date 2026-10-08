"""Forwarding localizes generated text without modifying received SMS data."""
from email.header import decode_header
import shutil

from helpers import ShellTest, TOP


FORWARD = TOP / 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/sms-forward'


class ForwardTemplates(ShellTest):
    def setUp(self):
        super().setUp()
        source = FORWARD.read_text(encoding='utf-8')
        self.code = "NL='\n'\n" + source[source.index('template_strings() {'):source.index('sms_units() {')]

    def test_sms_body_and_sender_are_preserved_in_every_language(self):
        body = '验证码 123456\nİstanbul şifre: 654321\n$(reboot); "quoted" \\path'
        sender = '+8613800000000'
        prefixes = {'zh': '短信来自', 'en': 'SMS from', 'tr': 'SMS gönderen:'}
        for shell in self.each_shell():
            for lang, prefix in prefixes.items():
                result = self.sh(shell, self.code + '\nformat_message sms "$SENDER" "$BODY"\nprintf "%s" "$_content"',
                                 template_language=lang, SENDER=sender, BODY=body)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f'{prefix} {sender}\n{body}')

    def test_test_message_and_rfc2047_subject_round_trip(self):
        if not shutil.which('openssl'):
            self.skipTest('openssl is needed for encoded email headers')
        expected = {
            'zh': ('MU300 转发测试', 'MU300 短信转发测试'),
            'en': ('MU300 forwarding test', 'MU300 SMS forwarding test'),
            'tr': ('MU300 yönlendirme testi', 'MU300 SMS yönlendirme testi'),
        }
        for shell in self.each_shell():
            for lang, (subject, body) in expected.items():
                result = self.sh(shell, self.code + '\nformat_message test NMS ""\n'
                                 'mime_subject "$_subject"\nprintf "\\n%s" "$_content"', template_language=lang)
                self.assertEqual(result.returncode, 0, result.stderr)
                header, text = result.stdout.split('\n', 1)
                self.assertTrue(header.isascii())
                self.assertLessEqual(len(header), 75)
                decoded, charset = decode_header(header)[0]
                self.assertEqual(decoded.decode(charset), subject)
                self.assertEqual(text, body)

    def test_power_states_and_device_labels_are_localized(self):
        # Shell functions also override ash's built-in applet lookup.
        telemetry = '\ncat() { printf "%s" F50; }\ncut() { printf "%s" 1234; }\nsed() { printf "%s" OpenWrt; }\n'
        expected = {
            'zh': ('充电状态', '当前电量', '电量提醒', '设备', '固件', '运行时间', '秒',
                   ['充电中', '放电中', '未充电', '已充满']),
            'en': ('Charging status', 'Battery level', 'Battery alert', 'Device', 'Firmware', 'Uptime', 'seconds',
                   ['Charging', 'Discharging', 'Not charging', 'Full']),
            'tr': ('Şarj durumu', 'Pil seviyesi', 'Pil uyarısı', 'Cihaz', 'Yazılım', 'Çalışma süresi', 'saniye',
                   ['Şarj oluyor', 'Pil kullanılıyor', 'Şarj olmuyor', 'Dolu']),
        }
        for shell in self.each_shell():
            for lang, words in expected.items():
                charge, level, threshold, device, firmware, uptime, seconds, states = words
                for status, translated in zip(['Charging', 'Discharging', 'Not charging', 'Full'], states):
                    result = self.sh(shell, self.code + '\npower_message "$STATUS" 40 40 "$STATUS"',
                                     template_language=lang, STATUS=status)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, f'{threshold}: 40%\n{level}: 40%\n{charge}: {translated}')
                result = self.sh(shell, self.code + telemetry + '\ntemplate_strings\ndevice_info',
                                 template_language=lang, nickname='我的设备 / İstanbul')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, f'{device}: F50 (我的设备 / İstanbul)\n'
                                 f'{firmware}: OpenWrt\n{uptime}: 1234 {seconds}')
