#!/bin/sh
# Keep netifd's complete view of a cellular bearer current without polling.
#
# IPv6 is supplied by RA, so address and route netlink notifications are the
# authoritative source (including lifetime refreshes). IPv4 and peer DNS are
# supplied by CGCONTRDP; nr0 announces PDP changes with +CGEV, at which point a
# single read refreshes them. This process is owned by netifd via
# proto_run_command and also implements the standard WAN renew signal (USR1).
#
# Every update is sent address-external (matching the setup in mu300cell.sh):
# the kernel state belongs to RA and to this monitor, netifd only tracks it. A
# report that flips the flag makes netifd delete the address it previously
# installed, so the monitor never manages what setup did not also send external.
#
# netifd scans every executable *.sh in this directory as a protocol provider
# and probes each one with an EMPTY proto name: argv is '<script> "" dump'
# (a direct '<script> dump' from a shell also happens). This helper is not a
# protocol, so every such probe must terminate at once - anything slower blocks
# netifd's scan, and falling through would start a monitor with no config that
# sits on a fifo forever. Real invocations pass 'wan sipa_eth0 ...'.
case "${1:-}-${2:-}" in
	*-dump|dump-*) exit 0 ;;
esac

. /lib/functions.sh
. /lib/netifd/netifd-proto.sh

export PATH="$PATH:/opt/mu300/bin:/opt/mu300/busybox-bin:/usr/sbin:/sbin"

config=$1
ifname=$2
ip4=$3
prefix4=$4
dns1=$5
dns2=$6
peerdns=$7
urclog=${MU300_URC_LOG:-/run/mu300-at/urc/stty_nr0.log}
logtag=mu300cell-renew

mask2prefix() {
	local m=$1 bits=0 o IFS=.
	for o in $m; do
		case $o in
			255) bits=$((bits + 8)) ;; 254) bits=$((bits + 7)) ;;
			252) bits=$((bits + 6)) ;; 248) bits=$((bits + 5)) ;;
			240) bits=$((bits + 4)) ;; 224) bits=$((bits + 3)) ;;
			192) bits=$((bits + 2)) ;; 128) bits=$((bits + 1)) ;;
			0) ;; *) echo 32; return ;;
		esac
	done
	echo "$bits"
}

# One record per address: CIDR|preferred seconds|valid seconds. Including the
# lifetimes in the snapshot means an RA refresh of an unchanged address is
# still forwarded to netifd instead of being mistaken for a duplicate event.
# (The program ends right at the rule's closing brace: an extra one to "end"
# the program is a syntax error - the cause of empty v6 reports before.)
current_v6() {
	ip -6 addr show dev "$ifname" scope global 2>/dev/null |
		awk '
			/^[[:space:]]*inet6 / { cidr=$2; next }
			/^[[:space:]]*valid_lft / && cidr!="" {
				valid=$2; preferred=$4
				gsub(/sec$/, "", preferred); gsub(/sec$/, "", valid)
				if (preferred=="forever") preferred=""
				if (valid=="forever") valid=""
				print cidr "|" preferred "|" valid
				cidr=""
			}' | sort
}

# gateway|remaining lifetime. The route is refreshed from RTM_NEWROUTE just as
# the address is refreshed from RTM_NEWADDR, so netifd never turns an expiring
# RA default into a permanent route.
current_v6_route() {
	ip -6 route show dev "$ifname" default proto ra 2>/dev/null |
		awk 'NR==1 {
			gw=""; valid=""
			for (i=1; i<=NF; i++) {
				if ($i=="via") gw=$(i+1)
				if ($i=="expires") valid=$(i+1)
			}
			gsub(/sec$/, "", valid)
			print gw "|" valid
		}'
}

v6_snapshot() {
	printf '%s\n--route--\n%s\n' "$(current_v6)" "$(current_v6_route)"
}

report() {
	local v6 route cidr addr prefix preferred valid gw
	v6=$(current_v6)
	route=$(current_v6_route)
	# The kernel owns SLAAC/RA lifetimes, and this monitor owns bearer IPv4.
	# Mark the report external so netifd records it without replacing a finite
	# SLAAC lifetime with a permanent static address or route.
	proto_init_update "$ifname" 1 1
	[ -n "$ip4" ] && {
		proto_add_ipv4_address "$ip4" "${prefix4:-32}"
		proto_add_ipv4_route "0.0.0.0" 0
	}
	if [ -n "$v6" ]; then
		while IFS='|' read -r cidr preferred valid; do
			[ -n "$cidr" ] || continue
			addr=${cidr%/*}; prefix=${cidr#*/}
			proto_add_ipv6_address "$addr" "${prefix:-64}" "$preferred" "$valid"
		done <<-EOF
		$v6
		EOF
	fi
	if [ -n "$route" ]; then
		gw=${route%%|*}; valid=${route#*|}
		proto_add_ipv6_route "::" 0 "$gw" 4096 "$valid"
	fi
	if [ "${peerdns:-1}" != 0 ]; then
		[ -n "$dns1" ] && proto_add_dns_server "$dns1"
		[ -n "$dns2" ] && proto_add_dns_server "$dns2"
	fi
	proto_send_update "$config"
}

read_bearer() {
	local d out line addrmask mask new_ip4 new_prefix new_dns1 new_dns2
	for d in /run/mu300-at6 /run/mu300-at7 /run/mu300-at; do
		[ -p "$d/cmd" ] || continue
		out=$(MU300_AT_LOCK_WAIT=0 MU300_AT_DIR="$d" mu300-at -t 3 'AT+CGCONTRDP=1' 2>/dev/null) || continue
		line=$(printf '%s\n' "$out" | awk -F, '/^\+CGCONTRDP:/ {
			a=$4; gsub(/"/, "", a); n=split(a, x, ".")
			if (n==8 && x[1]+0>0) { print; exit }
		}')
		[ -n "$line" ] && break
	done
	[ -n "$line" ] || return 1
	addrmask=$(printf '%s\n' "$line" | cut -d, -f4 | tr -d '"')
	new_ip4=$(printf '%s\n' "$addrmask" | cut -d. -f1-4)
	mask=$(printf '%s\n' "$addrmask" | cut -d. -f5-8)
	new_prefix=$(mask2prefix "$mask")
	new_dns1=$(printf '%s\n' "$line" | cut -d, -f6 | tr -d '"')
	new_dns2=$(printf '%s\n' "$line" | cut -d, -f7 | tr -d '"')
	[ -n "$new_ip4" ] || return 1
	BEARER_IP4=$new_ip4
	BEARER_PREFIX4=$new_prefix
	BEARER_DNS1=$new_dns1
	BEARER_DNS2=$new_dns2
}

refresh_bearer() {
	local reason=$1 old old_ip4 old_prefix4
	old="$ip4/$prefix4 $dns1 $dns2"
	old_ip4=$ip4; old_prefix4=$prefix4
	if ! read_bearer; then
		logger -t "$logtag" "$reason: PDP active address is not available; keeping the last netifd state"
		return 1
	fi
	ip4=$BEARER_IP4; prefix4=$BEARER_PREFIX4
	dns1=$BEARER_DNS1; dns2=$BEARER_DNS2
	if [ "$old" != "$ip4/$prefix4 $dns1 $dns2" ]; then
		# Add the replacement before deleting the old address. There is no
		# ifdown, CGACT cycle or USB event, so an address handover only loses
		# packets during the carrier's own transition.
		if [ "$old_ip4/$old_prefix4" != "$ip4/$prefix4" ]; then
			ip -4 addr add "$ip4/$prefix4" dev "$ifname" 2>/dev/null ||
				ip -4 addr replace "$ip4/$prefix4" dev "$ifname"
			[ -n "$old_ip4" ] && ip -4 addr del "$old_ip4/${old_prefix4:-32}" dev "$ifname" 2>/dev/null || true
			ip -4 route replace default dev "$ifname"
		fi
		report
		logger -t "$logtag" "$reason: bearer updated to $ip4/$prefix4"
	else
		logger -t "$logtag" "$reason: bearer unchanged"
	fi
}

last_v6=$(v6_snapshot)
report
[ "${8:-}" = --once ] && exit 0

# Kill processes a previous monitor left behind (never in --once test mode:
# that must not disturb the running instance). netifd's teardown signal does
# not reach pipeline members, so every re-setup that missed the kill left an
# event farm behind. The ps snapshot goes through a file: an environment
# prefix does not cross a pipe, and awk -v would otherwise match the awk line
# in a piped ps.
reap() {
	local pat=$1 pids pid
	ps w > /tmp/mu300cell-reap.ps
	pids=$(awk -v pat="$pat" 'NR>1 && index($0, pat) { print $1 }' /tmp/mu300cell-reap.ps)
	rm -f /tmp/mu300cell-reap.ps
	for pid in $pids; do
		[ "$pid" != "$$" ] && kill "$pid" 2>/dev/null
	done
}
reap "mu300cell-v6.sh $config $ifname"
reap "ip -6 monitor address dev $ifname"
reap "ip -6 monitor route dev $ifname"
reap "tail -n 0 -F $urclog"

events=/run/mu300cell-${config}.events
rm -f "$events"
mkfifo -m 600 "$events" || exit 1
exec 3<>"$events"

# Each producer blocks while idle. There is no periodic AT or netlink polling.
( ip -6 monitor address dev "$ifname" 2>/dev/null |
	while IFS= read -r _; do printf 'v6\n'; done > "$events" ) & addrmon=$!
( ip -6 monitor route dev "$ifname" 2>/dev/null |
	while IFS= read -r _; do printf 'v6\n'; done > "$events" ) & routemon=$!
( while [ ! -f "$urclog" ]; do sleep 0.2; done
	tail -n 0 -F "$urclog" 2>/dev/null |
	while IFS= read -r line; do
		case $line in
			*+CGEV:*PDN*|*+CGEV:*MODIFY*) printf 'pdp\n' ;;
		esac
	done > "$events" ) & urcmon=$!

renew_pending=0
cleanup() {
	trap - INT TERM EXIT USR1
	kill "$addrmon" "$routemon" "$urcmon" 2>/dev/null
	# Killing a subshell does not kill the pipeline it feeds; reap the
	# monitor and tail processes by command line so nothing survives us.
	reap "ip -6 monitor address dev $ifname"
	reap "ip -6 monitor route dev $ifname"
	reap "tail -n 0 -F $urclog"
	exec 3>&-
	rm -f "$events"
	exit 0
}
trap cleanup INT TERM EXIT
trap 'renew_pending=1' USR1

last_pdp=0
while :; do
	if [ "$renew_pending" = 1 ]; then
		renew_pending=0
		refresh_bearer manual-renew || true
		last_pdp=$(date +%s)
	fi
	event=
	# A USR1 (renew) interrupts the read builtin: it returns an error without
	# consuming fifo data. Continue, not break - leaving the loop would kill
	# the protocol task and netifd would tear the interface down. This fd is
	# an O_RDWR fifo, so a real EOF cannot occur.
	IFS= read -r event <&3 || continue
	case $event in
		v6)
			now=$(v6_snapshot)
			[ "$now" = "$last_v6" ] && continue
			last_v6=$now
			report
			logger -t "$logtag" "IPv6 RA address/route state refreshed"
			;;
		pdp)
			now=$(date +%s)
			[ $((now - last_pdp)) -lt 2 ] && continue
			# Networks commonly emit DEACT plus several ACT notifications as one
			# transition. Let the burst settle, then perform exactly one AT read.
			sleep 1
			refresh_bearer cgev || true
			last_pdp=$(date +%s)
			;;
	esac
done
