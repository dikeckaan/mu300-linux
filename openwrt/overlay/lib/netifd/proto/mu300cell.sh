#!/bin/sh
# netifd protocol for the MU300 modem: attach with AT commands (mobile-data) and configure sipa_eth0.
# /etc/config/network:  config interface 'wan' / option proto 'mu300cell' / option apn 'internet'
# LuCI edits the same options through www/luci-static/resources/protocol/mu300cell.js.
#
# The bearer's kernel state is owned here, not by netifd: every update is sent
# address-external, so netifd tracks addresses, routes and DNS for display and
# firewall purposes but never installs or removes them. A mixed mode (netifd
# installing the v4 during setup, the monitor later reporting external) makes
# netifd delete the address it installed the moment the first external report
# arrives - the mobile-data watchdog then saw an address-less WAN and redialled
# every 60 s. mobile-data's netifd path leaves the interface alone; this script
# and mu300cell-v6.sh are the only writers.
[ -n "$INCLUDE_ONLY" ] || {
	. /lib/functions.sh
	. ../netifd-proto.sh
	init_proto "$@"
}

proto_mu300cell_init_config() {
	available=1
	no_device=1
	renew_handler=1
	proto_config_add_string "apn"
	proto_config_add_string "pdptype"
	proto_config_add_boolean "peerdns"
	proto_config_add_array "dns:list(ipaddr)"
}

proto_mu300cell_setup() {
	local config="$1"
	local apn pdptype peerdns out ifname ip prefix dns1 dns2 iid zone
	json_get_vars apn pdptype peerdns

	out=$(MU300_NETIFD=1 MU300_PDP_TYPE="${pdptype:-IP}" /opt/mu300/bin/mobile-data up $apn 2>/tmp/mu300cell.err)
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
		proto_setup_failed "$config"
		return 1
	fi
	ifname=$(echo "$out" | sed -n 's/^IFACE=//p')
	prefix=$(echo "$out" | sed -n 's/^PREFIX=//p')
	dns1=$(echo "$out" | sed -n 's/^DNS1=//p')
	dns2=$(echo "$out" | sed -n 's/^DNS2=//p')
	iid=$(echo "$out" | sed -n 's/^IID6=//p')

	ip link set "$ifname" up
	# This carrier's RAs give INFINITE address lifetimes: after a redial on a
	# new prefix the old SLAAC address never expires and prefixes stack up
	# (same for the default route a previous dial left behind). Clear the last
	# dial's v6 state; RS/RA re-establishes it within ~1 s. Also fine for
	# v4-only bearers - there is nothing to keep either way.
	ip -6 addr flush dev "$ifname" scope global 2>/dev/null
	ip -6 route flush dev "$ifname" 2>/dev/null
	# netifd treats this as a v4 protocol, so forwarding leaves accept_ra at 0. Enable
	# IPv6 and accept RAs before waiting for the carrier address. The monitor below
	# reports the initial RA and all later address/route lifetime refreshes.
	if [ "${pdptype:-IP}" != IP ]; then
		# The 1->0 cycle restarts addrconf entirely: the link-local on-link
		# route is rebuilt (a bare route flush leaves it missing and stops RA
		# processing) and a fresh router solicitation goes out, so the global
		# address returns about a second after the flush above.
		[ -w "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6" ] && {
			echo 1 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"
			echo 0 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"
		}
		[ -w "/proc/sys/net/ipv6/conf/$ifname/accept_ra" ] && {
			echo 0 > "/proc/sys/net/ipv6/conf/$ifname/accept_ra"
			echo 2 > "/proc/sys/net/ipv6/conf/$ifname/accept_ra"
		}
	fi
	# Install the bearer address ourselves (external updates are never applied by
	# netifd). Replace-first keeps an unchanged address continuous across
	# re-setups; anything else the carrier left behind is removed after it.
	ip -4 addr replace "$ip/${prefix:-32}" dev "$ifname" 2>/dev/null ||
		ip -4 addr add "$ip/${prefix:-32}" dev "$ifname"
	local a
	for a in $(ip -4 -o addr show dev "$ifname" scope global | awk '{print $4}'); do
		[ "$a" = "$ip/${prefix:-32}" ] || ip -4 addr del "$a" dev "$ifname" 2>/dev/null
	done
	ip -4 route replace default dev "$ifname"

	proto_init_update "$ifname" 1 1
	proto_add_ipv4_address "$ip" "${prefix:-32}"
	proto_add_ipv4_route "0.0.0.0" 0
	if [ "${peerdns:-1}" != 0 ]; then
		[ -n "$dns1" ] && proto_add_dns_server "$dns1"
		[ -n "$dns2" ] && proto_add_dns_server "$dns2"
	fi
	proto_send_update "$config"
	# The event-driven child is the protocol task netifd owns. It reports IPv6
	# netlink changes and CGEV-triggered IPv4/DNS changes without holding setup.
	[ "${pdptype:-IP}" != IP ] && proto_run_command "$config" \
		/lib/netifd/proto/mu300cell-v6.sh "$config" "$ifname" "$ip" \
		"${prefix:-32}" "$dns1" "$dns2" "${peerdns:-1}"
	[ "${pdptype:-IP}" = IP ] && [ -w "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6" ] &&
		echo 1 > "/proc/sys/net/ipv6/conf/$ifname/disable_ipv6"
	logger -t mu300cell "connected: $ip/${prefix:-32} on $ifname"
}

proto_mu300cell_renew() {
	# Standard netifd renew: ask the existing event monitor to re-read the
	# bearer. It updates in place; it does not cycle CGACT or restart the link.
	local sigusr1="$(kill -l SIGUSR1)"
	[ -n "$sigusr1" ] && proto_kill_command "$1" "$sigusr1"
}

proto_mu300cell_teardown() {
	local config="$1"
	proto_kill_command "$config"
	/opt/mu300/bin/mobile-data down >/dev/null 2>&1
	# External state is not removed by netifd on ifdown, so clean the bearer
	# ourselves - both families. v6 must go too: this carrier's RAs carry
	# INFINITE lifetimes, so an unflushed SLAAC address (and the default route
	# an earlier report installed) would survive every redial and stack up.
	# sipa_eth0 is the one bearer this hardware has (mobile-data assumes it too).
	ip -4 addr flush dev sipa_eth0 scope global 2>/dev/null
	ip -4 route del default dev sipa_eth0 2>/dev/null
	ip -6 addr flush dev sipa_eth0 scope global 2>/dev/null
	ip -6 route flush dev sipa_eth0 2>/dev/null
}

[ -n "$INCLUDE_ONLY" ] || add_protocol mu300cell
