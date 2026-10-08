#!/bin/sh
# netifd protocol for the MU300 modem: attach with AT commands (mobile-data) and configure sipa_eth0.
# /etc/config/network:  config interface 'wan' / option proto 'mu300cell' / option apn 'internet'
# LuCI edits the same options through www/luci-static/resources/protocol/mu300cell.js.
#
# The bearer's kernel state is owned here, not by netifd: every update is sent
# address-external, so netifd tracks addresses, routes and DNS for display and
# firewall purposes but never installs or removes them. A mixed mode (netifd
# installing the v4 during setup, a later update reporting external) makes
# netifd delete the address it installed the moment the first external report
# arrives - the mobile-data watchdog then saw an address-less WAN and redialled
# every 60 s. mobile-data's netifd path leaves the interface alone; this script
# (and in relay mode mu300cell-v6.sh) is the only writer.
#
# option ipv6: 'relay' (openwrt-luci, set by its first boot; K35-K37, spec D9) takes IPv6 the way kanoqwq's fork
# does: sipa_eth0 accepts the carrier's RA, odhcpd relays RA/DHCPv6 to the LAN, fw4 masquerades (NAT66), and the
# event monitor mu300cell-v6.sh (openwrt-luci's overlay) reports the RA's addresses and routes to netifd. It works on
# carriers that never fill in +CGCONTRDP's v6 address. Unset or 'extend' (plain OpenWrt): the RFC 7278 design
# below, which needs that address. Relay applies to a dual-stack context only (pdptype other than IP).
[ -n "$INCLUDE_ONLY" ] || {
	. /lib/functions.sh
	. ../netifd-proto.sh
	init_proto "$@"
}

mu300cell_slot() {
    if [ -x /opt/mu300/bin/mu300-sim ]; then /opt/mu300/bin/mu300-sim active
    else echo 0; fi
}

proto_mu300cell_init_config() {
	available=1
	no_device=1
	# renew (K35): SIGUSR1 to the protocol task, which is the relay monitor; with no monitor running it does nothing
	renew_handler=1
	proto_config_add_string "sim_slot"
	proto_config_add_string "apn_internal"
	proto_config_add_string "pdptype_internal"
	proto_config_add_string "apn"
	proto_config_add_string "pdptype"
	proto_config_add_string "ipv6"
	proto_config_add_boolean "peerdns"
	proto_config_add_array "dns:list(ipaddr)"
}

proto_mu300cell_setup() {
	local config="$1"
	local apn pdptype peerdns ipv6 out ifname ip prefix dns1 dns2 iid zone a relay=0
    local slot apn_internal pdptype_internal
    json_get_vars apn pdptype peerdns ipv6 apn_internal pdptype_internal
    slot=$(mu300cell_slot) || { proto_notify_error "$config" INVALID_SIM_SLOT; return 1; }
    # Selection is frozen for the boot, so Apply never mixes old AT channels with new IP settings.
    if [ "$slot" = 1 ]; then
        apn=$apn_internal
        pdptype=${pdptype_internal:-IPV4V6}
    fi
	[ "$ipv6" = relay ] && [ "${pdptype:-IP}" != IP ] && relay=1

	out=$(MU300_NETIFD=1 MU300_PDP_TYPE="${pdptype:-IP}" MU300_IPV6="$ipv6" \
		/opt/mu300/bin/mobile-data up "$apn" 2>/tmp/mu300cell.err)
	if [ $? = 3 ]; then
		logger -t mu300cell "$(cat /tmp/mu300cell.err)"
		proto_notify_error "$config" NO_MODEM
		proto_block_restart "$config"
		return 1
	fi
	ip=$(echo "$out" | sed -n 's/^IP=//p')
	if [ -z "$ip" ]; then
		logger -t mu300cell "attach failed: $(cat /tmp/mu300cell.err)"
		proto_notify_error "$config" ATTACH_FAILED
		sleep 20
		proto_setup_failed "$config"
		return 1
	fi
	ifname=$(echo "$out" | sed -n 's/^IFACE=//p')
	prefix=$(echo "$out" | sed -n 's/^PREFIX=//p')
	dns1=$(echo "$out" | sed -n 's/^DNS1=//p')
	dns2=$(echo "$out" | sed -n 's/^DNS2=//p')
	iid=$(echo "$out" | sed -n 's/^IID6=//p')

	ip link set "$ifname" up
	# This carrier's RAs give INFINITE address lifetimes: after a redial on a new prefix the old SLAAC
	# address never expires and prefixes stack up (same for a default route a previous dial left behind).
	# Clear the last dial's v6 state; RS/RA re-establishes it. Fine for v4-only bearers too.
	ip -6 addr flush dev "$ifname" scope global 2>/dev/null
	ip -6 route flush dev "$ifname" 2>/dev/null
	if [ "$relay" = 1 ]; then
		# Relay: netifd treats this as a v4 protocol, so with forwarding on accept_ra stays 0; take the RA before
		# waiting for the carrier's address. The disable_ipv6 1->0 cycle restarts addrconf entirely: the link-local
		# on-link route is rebuilt (a bare route flush leaves it missing and stops RA processing) and a fresh router
		# solicitation goes out, so the global address returns about a second after the flush above. accept_ra 2:
		# this is a router.
		[ -w "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6" ] && {
			echo 1 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"
			echo 0 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"
		}
		[ -w "/proc/sys/net/ipv6/conf/$ifname/accept_ra" ] && {
			echo 0 > "/proc/sys/net/ipv6/conf/$ifname/accept_ra"
			echo 2 > "/proc/sys/net/ipv6/conf/$ifname/accept_ra"
		}
	fi
	# Install the bearer address ourselves (external updates are never applied by netifd). Replace-first
	# keeps an unchanged address continuous across re-setups; anything else the carrier left is removed.
	ip -4 addr replace "$ip/${prefix:-32}" dev "$ifname" 2>/dev/null ||
		ip -4 addr add "$ip/${prefix:-32}" dev "$ifname"
	for a in $(ip -4 -o addr show dev "$ifname" scope global | awk '{print $4}'); do
		[ "$a" = "$ip/${prefix:-32}" ] || ip -4 addr del "$a" dev "$ifname" 2>/dev/null
	done
	# Once more: a leftover primary in the new address's subnet made the new one its secondary, and deleting the
	# primary took the secondary with it (no promote_secondaries). Unchanged otherwise.
	ip -4 addr replace "$ip/${prefix:-32}" dev "$ifname" 2>/dev/null ||
		ip -4 addr add "$ip/${prefix:-32}" dev "$ifname" 2>/dev/null
	ip -4 route replace default dev "$ifname"

	proto_init_update "$ifname" 1 1
	proto_add_ipv4_address "$ip" "${prefix:-32}"
	proto_add_ipv4_route "0.0.0.0" 0
	if [ "${peerdns:-1}" != 0 ]; then
		[ -n "$dns1" ] && proto_add_dns_server "$dns1"
		[ -n "$dns2" ] && proto_add_dns_server "$dns2"
	fi
	proto_send_update "$config"
	if [ "$relay" = 1 ]; then
		# The event monitor is the protocol task netifd owns (killed on teardown, SIGUSR1 on renew). It reports the
		# RA's addresses and routes from netlink, and the bearer's IPv4 and DNS again after a +CGEV, without
		# holding setup. odhcpd relays the RA to the LAN (dhcp.wan master); ndp-learn routes the /64 to br-lan.
		proto_run_command "$config" /lib/netifd/proto/mu300cell-v6.sh "$config" "$ifname" "$ip" \
			"${prefix:-32}" "$dns1" "$dns2" "${peerdns:-1}"
	elif [ -n "$iid" ]; then
		# The network assigned IPv6. Link-local from its interface identifier, as 3GPP has the UE do, then
		# odhcp6c learns the /64 from the router advertisement; extendprefix hands that single /64 to the LAN,
		# where odhcpd advertises it (lan ip6assign 64) - the same as uqmi does for QMI modems.
		ip -6 addr add "fe80::$iid/64" dev "$ifname" 2>/dev/null
		zone=$(fw4 -q network "$config" 2>/dev/null)
		json_init
		json_add_string name "${config}_6"
		json_add_string ifname "@$config"
		json_add_string proto dhcpv6
		json_add_string reqaddress none
		json_add_string reqprefix no
		json_add_boolean extendprefix 1
		[ -n "$zone" ] && json_add_string zone "$zone"
		proto_add_dynamic_defaults
		json_close_object
		ubus call network add_dynamic "$(json_dump)"
	else
		# After proto_send_update, not before: netifd turns IPv6 back on as it configures the interface,
		# so mobile-data setting this itself has no effect on OpenWrt. The bearer is IPv4-only, and an
		# interface left with a link-local address sends router solicitations and multicast into it for
		# nothing. See docs/FINDINGS.md 13f.
		[ -w "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6" ] &&
			echo 1 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"
	fi
	# (the LED: mobile-data up has set it, blue on 4G and white on 5G; "data on" here turned 5G blue)
	logger -t mu300cell "connected: $ip/${prefix:-32} on $ifname"
}

proto_mu300cell_renew() {
	# Standard netifd renew: the monitor re-reads the bearer and updates in place; no CGACT cycle, no link restart.
	local sigusr1
	sigusr1=$(kill -l SIGUSR1 2>/dev/null)
	if [ -n "$sigusr1" ]; then proto_kill_command "$1" "$sigusr1"; fi
}

proto_mu300cell_teardown() {
	local config="$1" slot ifname
	slot=$(mu300cell_slot) || return 1
	ifname=sipa_eth$((slot * 8))
	proto_kill_command "$config"
	/opt/mu300/bin/mobile-data down >/dev/null 2>&1
	# External state is not removed by netifd on ifdown, so clean the bearer ourselves, both families:
	# an unflushed SLAAC address (infinite RA lifetimes) would survive every redial and stack up.
	# Tear down the active boot slot even if the next-boot selection has changed.
	ip -4 addr flush dev "$ifname" scope global 2>/dev/null
	ip -4 route del default dev "$ifname" 2>/dev/null
	ip -6 addr flush dev "$ifname" scope global 2>/dev/null
	ip -6 route flush dev "$ifname" 2>/dev/null
}

[ -n "$INCLUDE_ONLY" ] || add_protocol mu300cell
