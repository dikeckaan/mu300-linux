"""USB device-management policy and host-only LAN attachment."""
import json
import time
import unittest
from helpers import ShellTest, TOP


USB = TOP / 'openwrt/luci-app-mu300/root/usr/libexec/unisoc-modem/device-usb'


class USBManagement(ShellTest):
    def setUp(self):
        super().setUp()
        self.role = self.tmp / 'role'
        self.role.write_text('device\n')
        self.boot_file = self.tmp / 'usb-boot.conf'
        self.applied = self.tmp / 'applied'
        self.net_class = self.tmp / 'net'
        self.net_class.mkdir()
        self.usb_bus = self.tmp / 'usb-bus'
        self.usb_bus.mkdir()
        self.rescan_marker = self.tmp / 'rescan-done'
        self.stub('uci', '''
cmd=$1; [ "$cmd" = -q ] && { shift; cmd=$1; }; shift
case "$cmd" in
  get)
    case "$1" in
      unisoc_modem.usb) echo device ;;
      unisoc_modem.usb.*) key=${1##*.}; [ -f "$STUBLOG/uci.$key" ] && cat "$STUBLOG/uci.$key" ;;
      unisoc_modem.main.lan_device) echo br-lan ;;
      network.*.ports) [ -f "$STUBLOG/ports" ] && cat "$STUBLOG/ports" ;;
    esac ;;
  set)
    key=${1%%=*}; val=${1#*=}; printf '%s' "$val" > "$STUBLOG/uci.${key##*.}" ;;
  show) [ "$1" = network ] && echo "network.@device[0].name='br-lan'" ;;
  add_list) printf '%s' "${1##*=}" > "$STUBLOG/ports" ;;
  commit) echo "$1" >> "$STUBLOG/commits" ;;
esac
''')
        helper = self.tmp / 'safe-role'
        helper.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > "$MU300_USB_ROLE_FILE"\n')
        helper.chmod(0o755)
        self.helper = helper
        reload_script = self.tmp / 'network'
        reload_script.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> "$STUBLOG/reloads"\n')
        reload_script.chmod(0o755)
        self.reload_script = reload_script
        self.stub('ip', 'printf "%s\\n" "$*" >> "$STUBLOG/ip-calls"')

    def call_usb(self, shell, *args):
        return self.script(shell, USB, *args,
                           MU300_USB_ROLE_FILE=self.role,
                           MU300_USB_BOOT_FILE=self.boot_file,
                           MU300_USB_APPLIED_FILE=self.applied,
                           MU300_USB_NET_CLASS=self.net_class,
                           MU300_USB_BUS=self.usb_bus,
                           MU300_USB_RESCAN_MARKER=self.rescan_marker,
                           MU300_USB_RESCAN_DELAY='0',
                           MU300_USB_ROLE_COMMAND=self.helper,
                           MU300_USB_NETWORK_SERVICE=self.reload_script,
                           MU300_USB_IP_BIN=self.stubs / 'ip')

    def wait_text(self, path, value):
        # Role application is intentionally detached until after the RPC
        # acknowledgement. CI runners can schedule that child later than a
        # lightly loaded developer machine, so wait for the state, not a
        # fixed sub-second deadline.
        for _ in range(200):
            if path.exists() and path.read_text().strip() == value:
                return
            time.sleep(0.02)
        self.assertEqual(path.read_text().strip() if path.exists() else None, value)

    def test_host_auto_disables_usb_network_auto_and_blocks_changes(self):
        for shell in self.each_shell():
            self.role.write_text('device\n')
            (self.tmp / 'uci.role_auto').write_text('0')
            self.call_usb(shell, 'set-net', 'ecm', 'permanent', '1')
            self.assertTrue(self.boot_file.exists())
            response = self.call_usb(shell, 'set-role', 'host', '1')
            self.assertEqual(json.loads(response.stdout)['ok'], 1, response.stderr)
            self.wait_text(self.role, 'host')
            self.assertEqual((self.tmp / 'uci.net_auto').read_text(), '0')
            self.assertFalse(self.boot_file.exists())
            denied = self.call_usb(shell, 'set-net', 'rndis', 'once', '1')
            self.assertEqual(json.loads(denied.stdout)['ok'], 0)

    def test_once_consumed_only_after_boot_marker(self):
        for shell in self.each_shell():
            self.role.write_text('device\n')
            (self.tmp / 'uci.role_auto').write_text('0')
            self.applied.unlink(missing_ok=True)
            self.call_usb(shell, 'set-net', 'rndis', 'once', '1')
            self.assertIn('mode=rndis', self.boot_file.read_text())
            self.call_usb(shell, 'boot')
            self.assertTrue(self.boot_file.exists())
            self.applied.touch()
            self.call_usb(shell, 'boot')
            self.assertFalse(self.boot_file.exists())
            self.assertEqual((self.tmp / 'uci.net_auto').read_text(), '0')

    def test_f50_host_uses_explicit_role_adapter(self):
        for shell in self.each_shell():
            self.role.write_text('device\n')
            result = self.script(shell, USB, 'set-role', 'host', '1',
                                 MU300_USB_ROLE_FILE=self.role,
                                 MU300_USB_DEVICE='f50',
                                 MU300_USB_ROLE_COMMAND=self.helper,
                                 MU300_USB_BOOT_FILE=self.boot_file,
                                 MU300_USB_NET_CLASS=self.net_class,
                                 MU300_USB_BUS=self.usb_bus,
                                 MU300_USB_RESCAN_MARKER=self.rescan_marker,
                                 MU300_USB_RESCAN_DELAY='0')
            self.assertEqual(json.loads(result.stdout)['ok'], 1)
            self.wait_text(self.role, 'host')
            status = self.script(shell, USB, 'get', MU300_USB_ROLE_FILE=self.role,
                                 MU300_USB_DEVICE='f50', MU300_USB_BOOT_FILE=self.boot_file)
            self.assertEqual(json.loads(status.stdout)['host_supported'], 1)
            self.role.write_text('device\n')
            raw = self.script(shell, USB, 'set-role', 'host', '0',
                              MU300_USB_ROLE_FILE=self.role,
                              MU300_USB_DEVICE='f50', MU300_USB_BOOT_FILE=self.boot_file)
            self.assertEqual(json.loads(raw.stdout)['ok'], 1)
            self.wait_text(self.role, 'host')

    def test_async_role_readback_is_pending_not_a_false_failure(self):
        slow = self.tmp / 'slow-role'
        slow.write_text('#!/bin/sh\nprintf "%s\\n" "$1" > "$STUBLOG/role-request"\n')
        slow.chmod(0o755)
        for shell in self.each_shell():
            self.role.write_text('device\n')
            result = self.script(shell, USB, 'set-role', 'host', '1',
                                 MU300_USB_ROLE_FILE=self.role,
                                 MU300_USB_ROLE_COMMAND=slow,
                                 MU300_USB_BOOT_FILE=self.boot_file,
                                 MU300_USB_NET_CLASS=self.net_class,
                                 MU300_USB_BUS=self.usb_bus,
                                 MU300_USB_RESCAN_MARKER=self.rescan_marker,
                                 MU300_USB_RESCAN_DELAY='0')
            self.assertEqual(json.loads(result.stdout), {'ok': 1, 'pending': 1})
            self.assertEqual((self.tmp / 'uci.role_auto').read_text(), '1')
            self.wait_text(self.tmp / 'role-request', 'host')

    def test_host_only_usb_adapter_list_and_idempotent_bridge_add(self):
        usbdev = self.tmp / 'usb1' / '1-1'
        usbdev.mkdir(parents=True)
        nic = self.net_class / 'eth0'
        nic.mkdir()
        (nic / 'device').symlink_to(usbdev, target_is_directory=True)
        (nic / 'carrier').write_text('1\n')
        other = self.net_class / 'sipa_eth0'
        other.mkdir()
        (other / 'carrier').write_text('1\n')
        gadget = self.net_class / 'rndis0'
        gadget.mkdir()
        gadget_parent = self.tmp / 'gadget.0'
        gadget_parent.mkdir()
        (gadget / 'device').symlink_to(gadget_parent, target_is_directory=True)
        gadget_bus = self.tmp / 'bus' / 'gadget'
        gadget_bus.mkdir(parents=True)
        (gadget_parent / 'subsystem').symlink_to(gadget_bus, target_is_directory=True)
        for shell in self.each_shell():
            (self.tmp / 'ports').unlink(missing_ok=True)
            (self.tmp / 'reloads').unlink(missing_ok=True)
            self.role.write_text('device\n')
            denied = self.call_usb(shell, 'net-add', 'eth0')
            self.assertEqual(json.loads(denied.stdout)['ok'], 0)
            self.role.write_text('host\n')
            listed = json.loads(self.call_usb(shell, 'net-list').stdout)
            self.assertEqual([d['name'] for d in listed['devices']], ['eth0'])
            self.assertEqual(listed['devices'][0]['carrier'], 1)
            added = self.call_usb(shell, 'net-add', 'eth0')
            self.assertEqual(json.loads(added.stdout)['ok'], 1,
                             added.stdout + added.stderr + (self.tmp / 'ip-calls').read_text())
            self.assertEqual(json.loads(self.call_usb(shell, 'net-add', 'eth0').stdout)['ok'], 1)
            self.assertEqual((self.tmp / 'reloads').read_text().splitlines(), ['reload'])
            self.assertEqual(json.loads(self.call_usb(shell, 'net-add', 'sipa_eth0').stdout)['ok'], 0)
            self.assertEqual(json.loads(self.call_usb(shell, 'net-add', 'rndis0').stdout)['ok'], 0)

    def test_selected_usb_nic_reattaches_without_network_reload(self):
        usbdev = self.tmp / 'usb1' / '1-1'
        usbdev.mkdir(parents=True)
        nic = self.net_class / 'eth0'
        nic.mkdir()
        (nic / 'device').symlink_to(usbdev, target_is_directory=True)
        (self.tmp / 'ports').write_text('usb0 eth0')
        for shell in self.each_shell():
            (self.tmp / 'ip-calls').unlink(missing_ok=True)
            (self.tmp / 'reloads').unlink(missing_ok=True)
            self.role.write_text('host\n')
            self.call_usb(shell, 'net-sync')
            calls = (self.tmp / 'ip-calls').read_text()
            self.assertIn('link set dev eth0 up', calls)
            self.assertIn('link set dev eth0 master br-lan', calls)
            self.assertFalse((self.tmp / 'reloads').exists())

    def test_missing_host_nic_triggers_one_hub_rescan(self):
        hub = self.usb_bus / '1-1'
        hub.mkdir()
        (hub / 'bDeviceClass').write_text('09\n')
        (hub / 'authorized').write_text('1\n')
        for shell in self.each_shell():
            self.role.write_text('host\n')
            self.rescan_marker.rmdir() if self.rescan_marker.exists() else None
            self.call_usb(shell, 'host-rescan')
            self.assertEqual((hub / 'authorized').read_text(), '1\n')
            self.assertTrue(self.rescan_marker.exists())
            (hub / 'authorized').write_text('sentinel\n')
            self.call_usb(shell, 'host-rescan')
            self.assertEqual((hub / 'authorized').read_text(), 'sentinel\n')


class USBIntegration(unittest.TestCase):
    def test_tf_early_policy_precedes_gadget_enumeration(self):
        init = (TOP / 'boot/init').read_text()
        self.assertLess(init.index('stage=sd-scan dev='),
                        init.index('[ "$root_mounted" = 1 ] && read_usb_boot_policy\nsetup_usb_gadget'))
        self.assertLess(init.index('stage=sd-root dev='),
                        init.index('[ "$root_mounted" = 1 ] && read_usb_boot_policy\nsetup_usb_gadget'))
        self.assertLess(init.index('[ "$root_mounted" = 1 ] && read_usb_boot_policy\nsetup_usb_gadget'),
                        init.index('if [ -z "$sd_root" ]; then'))
        self.assertIn('/disk/openwrt/etc/unisoc-modem/usb-boot.conf', init)
        self.assertIn('/run/unisoc-usb-net-applied', init)

    def test_rndis_is_single_configuration_with_own_revision_and_early_dhcp(self):
        init = (TOP / 'boot/init').read_text()
        self.assertIn('[ -z "$netfunc$rndis" ] && mkdir -p "$g/functions/$f.usb0"', init)
        self.assertNotIn('cdc=c.2', init)
        self.assertIn('echo 0x0302 > "$g/bcdDevice"', init)
        self.assertIn('early_net=rndis0', init)
        self.assertIn('interface $early_net', init)
        reset = (TOP / 'rootfs/overlay/opt/mu300/bin/mu300-usb-reset').read_text()
        self.assertIn('for nic in usb0 rndis0', reset)
        self.assertIn('ACTION=ifup INTERFACE=lan /etc/hotplug.d/iface/10-mu300-usb', reset)
        self.assertIn('/run/mu300-usb-rebind-done', reset)

    def test_rndis_enters_lan_on_firstboot_and_reload(self):
        first = (TOP / 'openwrt/overlay/etc/uci-defaults/90-mu300').read_text()
        hotplug = (TOP / 'openwrt/overlay/etc/hotplug.d/iface/10-mu300-usb').read_text()
        self.assertIn("uci add_list network.$dev.ports='rndis0'", first)
        self.assertIn('ip link set rndis0 master br-lan', hotplug)

    def test_host_boot_cannot_be_undone_by_gadget_rebind(self):
        ui = (TOP / 'openwrt/luci-app-mu300/root/etc/init.d/unisoc-modem-ui').read_text()
        post = (TOP / 'openwrt/overlay/etc/init.d/mu300-post').read_text()
        reset = (TOP / 'rootfs/overlay/opt/mu300/bin/mu300-usb-reset').read_text()
        self.assertIn('/usr/libexec/unisoc-modem/device-usb boot', ui)
        self.assertIn('!= host', post)
        self.assertIn('= host ] && exit 0', reset)

    def test_host_nic_hotplug_and_build_inventory(self):
        pkg = TOP / 'openwrt/luci-app-mu300/root/etc/hotplug.d'
        net = (pkg / 'net/90-unisoc-usb-host').read_text()
        iface = (pkg / 'iface/90-unisoc-usb-host').read_text()
        self.assertIn('device-usb net-sync', net)
        self.assertIn('device-usb net-sync', iface)
        for script in ('openwrt/build-rootfs.sh', 'tools/build-openwrt-tf-magisk.sh', 'tools/make-release.sh'):
            content = (TOP / script).read_text()
            self.assertIn('90-unisoc-usb-host', content)


if __name__ == '__main__':
    import unittest
    unittest.main()
