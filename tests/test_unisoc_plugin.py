"""Portable adapter boundary of luci-app-mu300."""
import threading
from helpers import ShellTest, TOP


APP = TOP / 'openwrt' / 'luci-app-mu300' / 'root'
AT = APP / 'usr' / 'libexec' / 'unisoc-modem' / 'at'
REPLAY = APP / 'usr' / 'libexec' / 'unisoc-modem' / 'boot-replay'
LOCK = APP / 'usr' / 'libexec' / 'unisoc-modem' / 'lock'


class Adapter(ShellTest):
    def test_custom_at_contract(self):
        custom = self.tmp / 'platform-at'
        custom.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$STUBLOG/adapter.args"\nprintf "AT\\nOK\\n"\n')
        custom.chmod(0o755)
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.at_backend) echo custom ;;
unisoc_modem.main.at_command) echo "{custom}" ;;
esac''')
        for shell in self.each_shell():
            result = self.script(shell, AT, '-t', '3', 'AT+CFUN?')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('OK', result.stdout)
            self.assertEqual((self.tmp / 'adapter.args').read_text().strip(), '3 AT+CFUN?')

    def test_available_does_not_send_at(self):
        custom = self.tmp / 'platform-at'
        custom.write_text('#!/bin/sh\ntouch "$STUBLOG/was-called"\n')
        custom.chmod(0o755)
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.at_backend) echo custom ;;
unisoc_modem.main.at_command) echo "{custom}" ;;
esac''')
        for shell in self.each_shell():
            result = self.script(shell, AT, '--available')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((self.tmp / 'was-called').exists())

    def test_disabled_replay_has_zero_at_traffic(self):
        state = self.tmp / 'state'
        state.mkdir()
        (state / 'auto_apply').write_text('off')
        (state / 'mode').write_text('4g')
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.state_dir) echo "{state}" ;;
esac''')
        self.stub('grep', 'touch "$STUBLOG/at-was-probed"; exit 1')
        for shell in self.each_shell():
            result = self.script(shell, REPLAY)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((self.tmp / 'at-was-probed').exists())

    def test_ready_at_replays_saved_locks_immediately(self):
        state = self.tmp / 'state'
        state.mkdir()
        (state / 'auto_apply').write_text('on')
        (state / 'mode').write_text('4g')
        at = self.tmp / 'at'
        at.write_text('#!/bin/sh\nprintf "AT\\nOK\\n"\n')
        at.chmod(0o755)
        lock = self.tmp / 'lock'
        lock.write_text('#!/bin/sh\nprintf "%s\\n" "$*" > "$STUBLOG/replay.args"\n')
        lock.chmod(0o755)
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.state_dir) echo "{state}" ;;
unisoc_modem.main.replay_phase) echo early ;; # obsolete values must not weaken the generic fallback
unisoc_modem.main.replay_timeout) echo 10 ;;
esac''')
        for shell in self.each_shell():
            result = self.script(shell, REPLAY, UNISOC_AT_BIN=at, UNISOC_LOCK_BIN=lock)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.tmp / 'replay.args').read_text().strip(), 'replay late')

    def test_platform_early_window_suppresses_probe_and_late_replay(self):
        state = self.tmp / 'state'
        state.mkdir()
        (state / 'mode').write_text('4g')
        marker = self.tmp / 'replayed'
        pending = self.tmp / 'pending'
        at = self.tmp / 'at'
        at.write_text('#!/bin/sh\ntouch "$STUBLOG/at-probed"\necho OK\n')
        at.chmod(0o755)
        lock = self.tmp / 'lock'
        lock.write_text('#!/bin/sh\ntouch "$STUBLOG/late-called"\n')
        lock.chmod(0o755)
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.state_dir) echo "{state}" ;;
unisoc_modem.main.replay_timeout) echo 10 ;;
esac''')
        for shell in self.each_shell():
            marker.unlink(missing_ok=True)
            pending.touch()
            def finish_early():
                pending.unlink(missing_ok=True)
                marker.touch()
            timer = threading.Timer(0.1, finish_early)
            timer.start()
            try:
                result = self.script(shell, REPLAY, UNISOC_AT_BIN=at, UNISOC_LOCK_BIN=lock,
                                     UNISOC_EARLY_PENDING=pending, UNISOC_REPLAY_MARKER=marker)
            finally:
                timer.join()
            self.assertEqual(result.returncode, 0,
                             f'{result.stderr}; pending={pending.exists()} marker={marker.exists()}')
            self.assertFalse((self.tmp / 'at-probed').exists())
            self.assertFalse((self.tmp / 'late-called').exists())

    def test_early_replay_restores_every_saved_lock_without_sfun(self):
        state = self.tmp / 'state'
        state.mkdir()
        (state / 'auto_apply').write_text('on')
        (state / 'mode').write_text('nsa')
        (state / 'endc').write_text('on')
        (state / 'lte').write_text('1,3,5')
        (state / 'nr').write_text('41,78')
        (state / 'cell').write_text('lte:1650,211\nnr:627264,393\n')
        at = self.tmp / 'at'
        at.write_text('''#!/bin/sh
printf "%s\\n" "$*" >> "$STUBLOG/at.commands"
case "$*" in
  *'AT+SPTESTMODE?'*) printf '+SPTESTMODE: 131,134,0\\nOK\\n' ;;
  *'AT+SP5GRAN?'*) printf '+SP5GRAN: 0\\nOK\\n' ;;
  *'AT+SPENDC?'*) printf '+ENDC: 1\\nOK\\n' ;;
  *'AT+SPLBAND=0'*) printf '+SPLBAND: 0,0,0,21,0\\nOK\\n' ;;
  *'AT+SPLBAND=3'*) printf '+SPLBAND: 0,0,272\\nOK\\n' ;;
  *'AT+SPFORCEFRQ=12,3'*) printf '+SPFORCEFRQ: 12,3,1650,211\\nOK\\n' ;;
  *'AT+SPFORCEFRQ=16,3'*) printf '+SPFORCEFRQ: 16,3,627264,393\\nOK\\n' ;;
  *) printf 'OK\\n' ;;
esac
''')
        at.chmod(0o755)
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.state_dir) echo "{state}" ;;
unisoc_modem.main.data_interface) echo cellular ;;
esac''')
        # Band masks use POSIX awk arithmetic, so the host awk must work too.
        apply_dir = self.tmp / 'apply'
        marker = self.tmp / 'replayed'
        for shell in self.each_shell():
            (self.tmp / 'at.commands').unlink(missing_ok=True)
            marker.unlink(missing_ok=True)
            result = self.script(shell, LOCK, 'replay', 'early', MU300_AT=at,
                                 UNISOC_APPLY_DIR=apply_dir, UNISOC_REPLAY_MARKER=marker)
            self.assertEqual(result.returncode, 0, result.stderr)
            commands = (self.tmp / 'at.commands').read_text()
            self.assertIn('AT+SP5GRAN=0', commands)
            self.assertIn('AT+SPTESTMODE=131,134,0', commands)
            self.assertIn('AT+SPENDC=1', commands)
            self.assertIn('AT+SPLBAND=1,0,0,0,21,0', commands, result.stderr)
            self.assertIn('AT+SPLBAND=2,0,0,272,0', commands)
            self.assertIn('AT+SPFORCEFRQ=12,6,1650,211', commands)
            self.assertIn('AT+SPFORCEFRQ=16,6,627264,393', commands)
            self.assertNotIn('AT+SFUN=', commands)
            self.assertTrue(marker.exists())

    def test_early_replay_readback_failure_keeps_late_fallback(self):
        state = self.tmp / 'state'
        state.mkdir()
        (state / 'mode').write_text('4g')
        at = self.tmp / 'at'
        at.write_text('#!/bin/sh\ncase "$*" in *"AT+SPTESTMODE?"*) echo "+SPTESTMODE: 134,134,0" ;; esac\n')
        at.chmod(0o755)
        self.stub('uci', f'''case "$3" in
unisoc_modem.main.state_dir) echo "{state}" ;;
esac''')
        marker = self.tmp / 'replayed'
        for shell in self.each_shell():
            result = self.script(shell, LOCK, 'replay', 'early', MU300_AT=at,
                                 UNISOC_APPLY_DIR=self.tmp / 'apply', UNISOC_REPLAY_MARKER=marker)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    import unittest
    unittest.main()
