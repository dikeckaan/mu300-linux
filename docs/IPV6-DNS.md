# IPv6 DNS on an OpenWrt relay bearer

A downstream router can receive a public IPv6 address and a default route but
still show an empty IPv6 DNS list. Some cellular bearers put no RDNSS option in
their router advertisements and have no responding DHCPv6 server. Relaying those
protocols cannot supply the missing DNS information.

The modem can nevertheless supply IPv6 DNS through `AT+CGCONTRDP=1`: it returns a
separate IPv6 record, with each DNS address encoded as sixteen decimal octets.
`mu300cell-v6.sh` now reads both DNS columns of all records, validates and converts
the IPv6 addresses, and includes them in netifd's peer DNS. It reads once at
monitor startup and again on the existing bearer events or a WAN renew. A failed
read keeps the last known state; a valid IPv4-only answer removes old IPv6 DNS.

For fresh `openwrt-luci` installations, RA relay and NAT66 still provide addresses
and routing. A local, stateless DHCPv6 server supplies DNS without assigning
addresses or delegating prefixes. `network.wan.dns6_publish='lan'` explicitly lets
the monitor manage the downstream section's advertised DNS list. The list is
committed and odhcpd reloaded only when the learned DNS changes. Existing pending
DHCP edits are left alone. With no carrier IPv6 DNS, odhcpd uses its local DNS
service instead. `peerdns='0'` prevents both peer DNS reporting and publication.

Existing installations keep their settings on update. To opt a relay bearer into
this arrangement (this gives the monitor ownership of `dhcp.lan.dns`):

```sh
uci set network.wan.dns6_publish='lan'
uci set dhcp.lan.dhcpv6='server'
uci set dhcp.lan.dhcpv6_na='0'
uci set dhcp.lan.dhcpv6_pd='0'
uci set dhcp.lan.dns_service='1'
uci commit network
uci commit dhcp
/etc/init.d/odhcpd reload
ubus call network.interface.wan renew
```

After installing the updated script, an already running monitor must first be
restarted (for example, during the next normal WAN reconnect or reboot). Renew
then re-reads the bearer without cycling the cellular connection. A downstream
router may also need a DHCPv6 renew to refresh its DNS list. It can continue to
use NAT6 and automatic DNS; no carrier DNS address is hard-coded in the fix.

For a manually maintained advertised DNS list, remove
`network.wan.dns6_publish` before setting `dhcp.lan.dns` yourself. Plain OpenWrt's
`extend` mode and existing users' RA/DHCPv6 choices are unchanged.

This arrangement was verified on a MU300 running OpenWrt 25.12.6 / kernel 7.3.1,
with a GL-MT3600BE downstream over USB: both carrier IPv6 DNS servers appeared
automatically in `network.interface.tethering6` and the resolver file, answered
queries, and IPv4/IPv6 connectivity remained working. A WAN renew retained the
DNS list without rewriting the unchanged DHCP configuration. A full device
reboot was not part of that validation.
