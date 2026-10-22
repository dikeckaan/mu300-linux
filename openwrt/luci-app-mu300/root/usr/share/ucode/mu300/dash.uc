// mu300.dash -- the home page's data, without starting a process.
//
// The status snapshot (info) is what the shell dashboard-info used to print, field for field: the same keys, the same
// types, the same rules (each one is commented where it is computed). The shell version started 700 to 1000
// processes per snapshot (121 command substitutions, each a fork, most of them a cat, awk or sed besides): about
// 0.56 CPU seconds a call on the U30 Air, every 1.5 s while the home page was open, on top of the cellular collector
// it kicked each time. Here every file is read in the calling process, ubus, uci, the station table (nl80211) and the
// addresses (rtnl) are asked through ucode's own modules, and the few answers that still need a program (the SIM
// selector, the device name) are kept: the SIM selector's for a few seconds, the device name for good.
//
// Three users: the rpcd plugin /usr/share/rpcd/ucode/mu300status.uc (status, sysinfo and sms_head, in rpcd itself),
// /usr/libexec/unisoc-modem/dashboard-info (the same snapshot as a program, for mu300dash and the tests), and the
// tests, which put stand-ins for the ubus, uci, nl80211 and rtnl modules first on the module path. The environment
// overrides are the shell version's (MU300_POWER_SUPPLY_DIR, MU300_DHCP_LEASES, ...): rpcd sets none of them.
'use strict';

import { readfile, stat, lstat, lsdir, popen, access, glob, mkdir, chmod, rename, unlink } from 'fs';

function env(name, dflt) {
	let v = getenv(name);
	return (v != null && v != '') ? v : dflt;
}

// what $(cat FILE) gives: the content without its trailing newlines, '' when it cannot be read. (No regular
// expressions on the hot path: musl's matcher costs 50-100 us a match on the A55, and a snapshot reads ~30 files.)
function rd(path) {
	let s = readfile(path);
	if (s == null)
		return '';
	return rtrim(s, '\n');
}

// the first line of a file (or ''), at most LIMIT bytes read
function first_line(path, limit) {
	let s = readfile(path, limit);
	if (s == null)
		return '';
	let i = index(s, '\n');
	return (i >= 0) ? substr(s, 0, i) : s;
}

function is_file(path) { let s = stat(path); return s != null && s.type == 'file'; }
function is_dir(path) { let s = stat(path); return s != null && s.type == 'directory'; }
function exists(path) { return stat(path) != null || lstat(path) != null; }
function executable(path) { return is_file(path) && access(path, 'x') == true; }
function readable(path) { return access(path, 'r') == true; }

// json_num (lib.sh): TEXT when it is a JSON number - an optional minus, digits with at most one inner dot, no
// leading zero - as a number, else null
function num(text) {
	if (type(text) == 'int' || type(text) == 'double')
		return text;
	if (type(text) != 'string')
		return null;
	// the common case, a plain integer, without a regular expression
	let i = int(text);
	if (type(i) == 'int' && '' + i === text)
		return i;
	return match(text, /^-?(0|[1-9][0-9]*)(\.[0-9]+)?$/) ? +text : null;
}

// json_str_or_null (lib.sh): the text, or null for an empty one
function str(text) {
	return (text == null || text == '') ? null : '' + text;
}

// safe_iface (lib.sh): an interface, device or uci section name - at most 15 characters of letters, digits, "_", "."
// and "-", starting with a letter or a digit - else DEFAULT
function safe_iface(name, dflt) {
	if (type(name) != 'string' || !match(name, /^[A-Za-z0-9][A-Za-z0-9_.-]*$/) || length(name) > 15)
		return dflt;
	return name;
}

// safe_tty (lib.sh): /dev/stty<name> or /dev/tty<name>, else DEFAULT
function safe_tty(path, dflt) {
	return (type(path) == 'string' && match(path, /^\/dev\/(stty|tty)[A-Za-z0-9_]+$/)) ? path : dflt;
}

// safe_program (lib.sh): one of KNOWN, or a program directly inside the platform directory, else ''
function safe_program(path, known) {
	if (path == null || path == '')
		return '';
	for (let k in known ?? [])
		if (path == k)
			return path;
	let dir = env('MU300_PLATFORM_DIR', '/usr/libexec/unisoc-modem/platform') + '/';
	if (substr(path, 0, length(dir)) != dir)
		return '';
	let rest = substr(path, length(dir));
	if (rest == '' || substr(rest, 0, 1) == '.' || index(rest, '/') >= 0 || match(rest, /[^A-Za-z0-9_.-]/))
		return '';
	return path;
}

// safe_state_dir (lib.sh): a directory under /etc/unisoc-modem or /etc/mu300 (no dot component, no "//"), else DEFAULT
function safe_state_dir(path, dflt) {
	if (type(path) != 'string' || !match(path, /^\/etc\/(unisoc-modem|mu300)(\/.*)?$/))
		return dflt;
	if (match(path, /\/\./) || index(path, '//') >= 0 || substr(path, -1) == '/' || match(path, /[^A-Za-z0-9_.\/-]/))
		return dflt;
	return path;
}

// ------------------------------------------------------------------ modules
// Loaded when first needed and kept. A module that is not installed leaves its readouts empty (null), as a failed
// command did in the shell version; nothing else is held up by it.
let mods = {};
function mod(name) {
	if (!exists(mods, name)) {
		try { mods[name] = require(name); }
		catch (e) { mods[name] = null; }
	}
	return mods[name];
}

let bus = null;
function ubus_call(object, method, args) {
	let ubus = mod('ubus');
	if (!ubus)
		return null;
	for (let attempt = 0; attempt < 2; attempt++) {
		if (!bus)
			bus = ubus.connect(null, 3);
		if (!bus)
			return null;
		let r = bus.call(object, method, args ?? {});
		if (r != null)
			return r;
		// a connection that broke (ubusd restarted) answers nothing; a second try on a fresh one
		let err = ubus.error();
		if (err == null || !match('' + err, /connection|socket|ubus_connect|Not connected/i))
			return null;
		bus = null;
	}
	return null;
}

function uci_cursor() {
	let uci = mod('uci');
	return uci ? uci.cursor() : null;
}

// memo(opts, KEY, TTL, fn): fn()'s value, kept for TTL seconds in the plugin (opts.cache; rpcd keeps this module
// loaded), computed every time otherwise. For what changes slowly or is shown without hurry - the configuration, the
// file system, the temperatures, the battery - so that a 1.5 s poll reads only what moves: CPU, memory, counters,
// the WAN, the stations.
let memo_store = {};
function memo(opts, key, ttl, fn) {
	if (!opts?.cache)
		return fn();
	let now = time(), m = memo_store[key];
	if (m && now >= m.at && now - m.at < ttl)
		return m.v;
	let v = fn();
	memo_store[key] = { at: now, v: v };
	return v;
}
// a uci option as `uci -q get` prints it: a list joined by spaces, '' when unset
function uget(cur, conf, section, option) {
	if (!cur)
		return '';
	let v = cur.get(conf, section, option);
	if (type(v) == 'array')
		return join(' ', v);
	return (v == null) ? '' : '' + v;
}

// ------------------------------------------------------------ the SIM selector
// mu300-sim active and status --json: the selector's own account (its U30 backend reads the modem's state files and
// takes a lock: ~70 ms of CPU for the two on the U30 Air). The plugin keeps it while the files it is made of are
// unchanged - the boot's slot (/run/mu300/sim-slot), the saved choice (uci network, /etc/mu300/sim-slot, the old
// /etc/mu300-sim-slot, the V50's card under /etc/mu300) and the switch markers a SIM switch leaves in /run/mu300 -
// and SIM_MAXAGE seconds at most. The program keeps nothing (one run, as before).
const SIM_MAXAGE = 300;
const SIM_FILES = [ '/run/mu300/sim-slot', '/run/mu300', '/etc/config/network', '/etc/mu300/sim-slot', '/etc/mu300-sim-slot',
	'/etc/mu300' ];
let sim_cache = null;
function sim_signature() {
	return join(':', map(SIM_FILES, (p) => { let s = stat(p); return s ? s.mtime + '/' + s.size : '-'; }));
}

function run(cmd) {
	let p = popen(cmd, 'r');
	if (!p)
		return null;
	let out = p.read('all') ?? '';
	let rc = p.close();
	return { rc: rc, out: out };
}

function shq(s) {
	return "'" + replace('' + s, "'", "'\\''") + "'";
}

function sim_state(simbin, cache) {
	let now = time();
	let sig = cache ? sim_signature() : null;
	if (cache && sim_cache && sim_cache.bin == simbin && sim_cache.sig == sig && now - sim_cache.at < SIM_MAXAGE &&
	    now >= sim_cache.at)
		return sim_cache;
	let a = run(shq(simbin) + ' active 2>/dev/null');
	let st = { bin: simbin, at: now, sig: sig, ok: false, slot: null, status: '' };
	if (a && a.rc == 0) {
		st.ok = true;
		st.slot = replace(a.out, /\n+$/, '');
		let s = run(shq(simbin) + ' status --json 2>/dev/null');
		st.status = s ? s.out : '';
	}
	if (cache)
		sim_cache = st;
	return st;
}

// sim_n (dashboard-info): the digit after "KEY": in the selector's answer - the last such key on its line, as sed's
// greedy match took it
function sim_n(text, key) {
	let found = null, k = '"' + key + '":';
	for (let line in split(text, '\n')) {
		let i = rindex(line, k);
		if (i < 0)
			continue;
		let v = ltrim(substr(line, i + length(k)), ' ');
		let c = substr(v, 0, 1);
		if (c != '' && index('0123456789', c) >= 0)
			found = c;
	}
	return found;
}

// --------------------------------------------------------------- device name
// mu300-device (its own rules for the V50, which reports itself as an F50 in some boots); asked once
let device_cache = null;
function device_name() {
	if (device_cache == null) {
		let r = run('mu300-device 2>/dev/null');
		device_cache = r ? replace(r.out, /\n+$/, '') : '';
	}
	return device_cache;
}

// -------------------------------------------------------------- temperatures
function zone_temp(z) {
	let t = rd(z + '/temp');
	if (t == '')
		return null;
	return t;
}
// awk's printf "%.1f", v/1000 on what the zone said: a number with one decimal (junk reads as 0, as awk takes it)
function deci(t) {
	let m = match(t, /^[ \t]*([-+]?[0-9]*\.?[0-9]+([eE][-+]?[0-9]+)?)/);
	let v = m ? +m[1] : 0;
	return +sprintf('%.1f', v / 1000.0);
}
function temp_of(zones, label) {
	for (let z in zones) {
		if (!readable(z + '/type'))
			continue;
		if (rd(z + '/type') != label)
			continue;
		let t = zone_temp(z);
		return (t == null) ? null : deci(t);
	}
	return null;
}
function temp_hottest(zones) {
	let best = null, bestv = null;
	for (let z in zones) {
		let s = readfile(z + '/temp');
		if (s == null)
			continue;
		for (let line in split(replace(s, /\n$/, ''), '\n')) {
			let m = match(line, /^[ \t]*([-+]?[0-9]*\.?[0-9]+)/);
			let v = m ? +m[1] : 0;
			if (bestv == null || v >= bestv) { bestv = v; best = line; }
		}
	}
	return (best == null) ? null : deci(best);
}

// -------------------------------------------------------------------- power
function power_v(v) { return (v != null && match(v, /^-?[0-9]+$/) && +v > 0) ? +sprintf('%.2f', +v / 1000000.0) : null; }
function power_i(v) { return (v != null && match(v, /^-?[0-9]+$/)) ? +v : null; }
function power_w(v, i) {
	if (v == null || i == null || !match(v, /^-?[0-9]+$/) || !match(i, /^-?[0-9]+$/) || +v <= 0)
		return null;
	let w = (+v) * (+i) / 1e12;
	if (w < 0)
		w = -w;
	return +sprintf('%.2f', w);
}

function power_info(dev) {
	let psy = env('MU300_POWER_SUPPLY_DIR', '/sys/class/power_supply');
	let out = { present: 0, capacity: null, status: null, volt: null, ua: null, w: null, usb: null,
		in_volt: null, in_ua: null, in_w: null };
	// only the U30 Air has a battery (the F50 and the V50 have none): under mainline the F50's fuel gauge still
	// appears, with made-up values, so it reports no battery and the page hides the tile
	if (dev == 'f50' || dev == 'v50')
		return out;
	let all = glob(psy + '/*') ?? [];
	let dir = null;
	for (let d in [ psy + '/battery', psy + '/sc27xx-fgu', ...all ]) {
		if (!is_dir(d))
			continue;
		if (rd(d + '/present') == '0')
			continue;
		let base = replace(d, /.*\//, '');
		if (base == 'battery' || base == 'sc27xx-fgu') {
			if (!readable(d + '/capacity') && rd(d + '/type') != 'Battery')
				continue;
		}
		else if (rd(d + '/type') != 'Battery')
			continue;
		dir = d;
		break;
	}
	if (!dir)
		return out;
	out.present = 1;
	let cap = rd(dir + '/capacity');
	let status = rd(dir + '/status');
	let v = rd(dir + '/voltage_now'), i = rd(dir + '/current_now');
	let usb = null, in_v = '', in_i = '';
	// the first USB/Mains supply that is online, else whether any says 0
	for (let d in all) {
		let t = rd(d + '/type');
		if (!match(t, /^USB/) && t != 'Mains')
			continue;
		let o = rd(d + '/online');
		if (o == '0') { usb = 0; continue; }
		if (o != '1')
			continue;
		usb = 1;
		in_v = rd(d + '/voltage_now');
		in_i = rd(d + '/current_now');
		if (in_i == '')
			in_i = rd(d + '/input_current_now');
		break;
	}
	out.capacity = match(cap, /^[0-9]+$/) ? +cap : null;
	out.status = str(status);
	out.volt = power_v(v);
	out.ua = power_i(i);
	out.w = power_w(v, i);
	out.usb = usb;
	out.in_volt = power_v(in_v);
	out.in_ua = power_i(in_i);
	out.in_w = power_w(in_v, in_i);
	return out;
}

// --------------------------------------------------------- interface counters
function net_obj(iface) {
	// an interface name by safe_iface's rule, or nothing is read: the name becomes a /sys path
	if (iface == null || iface == '' || safe_iface(iface, '') != iface)
		return null;
	let d = '/sys/class/net/' + iface;
	if (!is_dir(d))
		return null;
	return { rx: num(rd(d + '/statistics/rx_bytes')), tx: num(rd(d + '/statistics/tx_bytes')),
		up: (rd(d + '/operstate') == 'up') ? 1 : 0 };
}

// ------------------------------------------------------------------ addresses
// the addresses of DEV of FAMILY ('inet' or 'inet6'), in the kernel's order (what `ip addr show DEV` lists), without
// their prefix length
function addresses(dev, family) {
	let rtnl = mod('rtnl');
	let res = [];
	if (!rtnl)
		return res;
	let af = (family == 'inet6') ? rtnl.const.AF_INET6 : rtnl.const.AF_INET;
	let all = rtnl.request(rtnl.const.RTM_GETADDR, rtnl.const.NLM_F_DUMP, { family: af });
	for (let a in all ?? []) {
		if (a.dev != dev || a.address == null)
			continue;
		push(res, replace(a.address, /\/.*/, ''));
	}
	return res;
}

// ------------------------------------------------------------------- stations
const MAC_RE = /^[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]$/;

// iw's "MBit/s" reading of a rate attribute (units of 100 kbit/s), as the page shows it
function rate(r) {
	if (type(r) != 'object')
		return '';
	let v = r.bitrate32 ?? r.bitrate;
	if (type(v) != 'int' || v <= 0)
		return '';
	return sprintf('%d.%d Mbit/s', v / 10, v % 10);
}

// one station's row: [mac, signal, tx, rx, connected] with '' for what the driver did not say. The SC2355 reports
// signal 0 and no tx rate for a client it has no metrics for: unknown, not 0 dBm.
function station_row(s) {
	let i = s.sta_info ?? {};
	let sig = (type(i.signal) == 'int' && i.signal != 0) ? i.signal : '';
	let ct = (type(i.connected_time) == 'int') ? sprintf('%d min', i.connected_time / 60) : '';
	return [ lc(s.mac ?? ''), sig, rate(i.tx_bitrate), rate(i.rx_bitrate), ct ];
}

// The station table: one row per associated client, a client without metrics included. The SC2355's dump lists each
// MAC alone; a "get" of that MAC can have the metrics, so a row without them asks once per client, at most 16.
function stations(dev) {
	let nl = mod('nl80211');
	let rows = [];
	if (!nl)
		return rows;
	let dump = nl.request(nl.const.NL80211_CMD_GET_STATION, nl.const.NLM_F_DUMP, { dev: dev });
	let seen = {}, asked = 0;
	for (let s in dump ?? []) {
		let row = station_row(s);
		if (!match(row[0], MAC_RE) || seen[row[0]])
			continue;
		seen[row[0]] = true;
		if ((row[1] == '' || row[2] == '' || row[3] == '' || row[4] == '') && asked < 16) {
			asked++;
			let g = nl.request(nl.const.NL80211_CMD_GET_STATION, 0, { dev: dev, mac: row[0] });
			if (type(g) == 'array')
				g = g[0];
			if (type(g) == 'object') {
				let r = station_row(g);
				if (r[0] == row[0])
					for (let k = 1; k <= 4; k++)
						if (row[k] == '')
							row[k] = r[k];
			}
		}
		push(rows, row);
	}
	return rows;
}

// the DHCP leases file: one [expiry, mac, ip, host] per line that ends in a newline (what `while read` takes)
function lease_lines(path) {
	let s = readfile(path);
	if (s == null)
		return [];
	let lines = split(s, '\n');
	pop(lines);   // the text after the last newline: `read` does not take an unterminated line
	let out = [];
	for (let l in lines) {
		let f = filter(split(trim(l), /[ \t]+/), x => x != '');
		push(out, f);
	}
	return out;
}

// --------------------------------------------------------------- AT adapter
// `at --available` (unisoc-modem/at): whether an AT backend is configured and present
function at_available(cur) {
	let backend = uget(cur, 'unisoc_modem', 'main', 'at_backend');
	if (backend == '')
		backend = 'auto';
	let port = safe_tty(uget(cur, 'unisoc_modem', 'main', 'at_port'), '/dev/stty_nr1');
	let custom = safe_program(uget(cur, 'unisoc_modem', 'main', 'at_command'));
	let mu300 = executable('/opt/mu300/bin/mu300-at') || executable('/usr/bin/mu300-at');
	let chardev = (stat(port)?.type == 'char');
	let atinout = false;
	for (let d in split(getenv('PATH') ?? '', ':'))
		if (d != '' && executable(d + '/atinout')) { atinout = true; break; }
	if (backend == 'auto') {
		if (mu300) return true;
		if (atinout && chardev) return true;
		return custom != '';   // a custom adapter is not checked further on this path, as the shell did not
	}
	if (backend == 'mu300') return mu300;
	if (backend == 'atinout') return chardev;
	if (backend == 'custom') return custom != '' && executable(custom);
	return false;
}

// -------------------------------------------------------------------- VPN
// vpn_conf_value (lib/vpn-orphan.sh): the last KEY= line's value, a trailing " # comment" dropped, quotes and blanks
// removed
function vpn_conf_value(path, key) {
	if (!readable(path))
		return '';
	let s = readfile(path) ?? '';
	let v = null;
	for (let l in split(s, '\n'))
		if (substr(l, 0, length(key) + 1) == key + '=')
			v = substr(l, length(key) + 1);
	if (v == null)
		return '';
	v = replace(v, /[ \t\n\r\f\v]#.*/, '');
	return replace(v, /["' ]/g, '');
}
function vpn_killswitch_wanted(root) {
	if (vpn_conf_value(root + '/etc/mu300/vpn.conf', 'ENABLE') != '1')
		return false;
	let ks;
	if (is_dir(root + '/etc/mu300/vpn/profiles') && readable(root + '/etc/mu300/vpn/settings'))
		ks = vpn_conf_value(root + '/etc/mu300/vpn/settings', 'KILL_SWITCH');
	else
		ks = vpn_conf_value(root + '/etc/mu300/vpn.conf', 'KILL_SWITCH');
	return ks != '0';
}

function link_exists(name) {
	return name != '' && match(name, /^[A-Za-z0-9_.-]+$/) && exists('/sys/class/net/' + name);
}

// ------------------------------------------------------------------- the snapshot
// info(opts) -> the snapshot, or { error } when the SIM selector cannot say which card is in use (the shell version
// printed nothing then, and the backend answered this error). opts.cache: keep the SIM selector's answer (the plugin).
function info(opts) {
	opts ??= {};
	// one uci cursor (it keeps what it parsed) for 10 s: a change made in the panel shows within that
	let cur = memo(opts, 'cursor', 10, uci_cursor);
	let cfg = (o) => uget(cur, 'unisoc_modem', 'main', o);
	let NOW = time();

	// --------------------------------------------------------------- WAN (ubus)
	let data_iface = safe_iface(cfg('data_interface'), 'wan');
	let data_iface6 = safe_iface(cfg('data_interface_v6'), 'wan6');
	let wan = ubus_call('network.interface.' + data_iface, 'status') ?? {};
	let wan6 = ubus_call('network.interface.' + data_iface6, 'status') ?? {};

	// The SIM selector's own account (issue #194): the card this boot uses, the one the configuration asks for, and
	// whether this device has the internal card at all. Local only (uci and a file under /run), no AT command.
	let simbin = env('MU300_SIM_BIN', '/opt/mu300/bin/mu300-sim');
	let sim_slot = 0, sim_json = null;
	if (executable(simbin)) {
		let st = sim_state(simbin, opts.cache);
		if (!st.ok)
			return { error: 'Dashboard info failed' };
		sim_slot = st.slot;
		let a = sim_n(st.status, 'active'), w = sim_n(st.status, 'default'), s1 = sim_n(st.status, 'slot1_supported');
		if (a != null && w != null && s1 != null && match(a + w + s1, /^[12][12][01]$/)) {
			sim_json = { slot: +a - 1, wanted: +w - 1, slot1_supported: +s1 };
			// the ZTE V50 (FINDINGS 204): slot 0 is built-in SIM 1 or the external SIM, slot 1 built-in SIM 2 or 3
			if (index(st.status, '"v50":{') >= 0)
				sim_json.v50 = 1;
		}
	}
	let slot_n = match('' + sim_slot, /^[0-9]+$/) ? +sim_slot : 0;

	// The mobile data device: netifd's live one first, the configured one while the WAN has none, the slot's CID 1
	// bearer last.
	let data_device = safe_iface(wan.l3_device, '');
	if (data_device == '')
		data_device = safe_iface(cfg('data_device'), '');
	if (data_device == '')
		data_device = 'sipa_eth' + (slot_n * 8);
	let lan_device = safe_iface(cfg('lan_device'), 'br-lan');
	let wifi_device = safe_iface(cfg('wifi_device'), 'wlan0');
	let usb_device = safe_iface(cfg('usb_device'), 'usb0');

	// the first "address" of netifd's status, in the order ubus prints it (IPv4 before IPv6, active before inactive)
	let wan_ip4 = null;
	for (let blk in [ wan, wan.inactive ?? {} ]) {
		for (let k in [ 'ipv4-address', 'ipv6-address', 'ipv6-prefix', 'ipv6-prefix-assignment' ]) {
			let l = blk[k];
			if (type(l) == 'array' && length(l) && l[0]?.address != null) { wan_ip4 = '' + l[0].address; break; }
		}
		if (wan_ip4 != null)
			break;
	}
	let wan6_ip = null;
	for (let a in memo(opts, 'inet6:' + data_device, 5, () => addresses(data_device, 'inet6')))
		if (match(a, /^[23]/)) { wan6_ip = a; break; }
	// the active DNS servers of both data interfaces (never inactive ones), each once
	let dns = [];
	for (let st in [ wan, wan6 ])
		for (let d in (type(st['dns-server']) == 'array') ? st['dns-server'] : [])
			if (d != null && d != '' && !(('' + d) in dns))
				push(dns, '' + d);
	// slot 1 (the F50's internal card) has its own APN and roaming options, see mu300cell.sh
	let apn = uget(cur, 'network', data_iface, (sim_slot == '1') ? 'apn_internal' : 'apn');
	if (apn == '')
		apn = '(SIM default)';
	let roam = uget(cur, 'network', data_iface, (sim_slot == '1') ? 'roaming_internal' : 'roaming');
	let roam_allowed = (roam in [ '0', 'off', 'no', 'false' ]) ? 0 : 1;
	let roam_held = exists(env('MU300_ROAM_HELD', '/run/mu300/data-roaming-held')) ? 1 : 0;

	// ------------------------------------------------------------------ system
	let uptime = +(split(rd('/proc/uptime'), ' ')[0] ?? '0');
	let host = uget(cur, 'system', '@system[0]', 'hostname');
	if (host == '')
		host = rd('/proc/sys/kernel/hostname');
	let ident = memo(opts, 'ident', 300, () => {
		let model = rd('/tmp/sysinfo/model');
		if (model == '')
			model = replace(rd('/proc/device-tree/model'), /\0/g, '');
		let fw = '';
		for (let l in split(readfile('/etc/openwrt_release') ?? '', '\n')) {
			let m = match(l, /^DISTRIB_DESCRIPTION='(.*)'$/);
			if (m) { fw = m[1]; break; }
		}
		let kernel = rd('/proc/sys/kernel/osrelease');
		if (fw == '')
			fw = 'Linux ' + kernel;
		return { model: model, fw: fw, kernel: kernel };
	});
	let model = ident.model, fw = ident.fw, kernel = ident.kernel;

	// /proc/stat's first line: busy is everything but idle and iowait; the page deltas two snapshots
	let cpuf = split(first_line('/proc/stat', 512), /[ \t]+/);
	let c = (i) => +(cpuf[i] ?? 0) || 0;
	let cpu_total = c(1) + c(2) + c(3) + c(4) + c(5) + c(6) + c(7) + c(8);
	let cpu_idle = c(4) + c(5);
	let cpun = memo(opts, 'cpun', 10, () => {
		let n = 0;
		for (let l in split(readfile('/proc/cpuinfo') ?? '', '\n'))
			if (substr(l, 0, 9) == 'processor')
				n++;
		return n;
	});
	// one frequency pair per policy (big.LITTLE has several)
	let freqs = [];
	let policies = memo(opts, 'policies', 30, () => glob('/sys/devices/system/cpu/cpufreq/policy*/scaling_cur_freq') ?? []);
	for (let p in policies) {
		let cur = readfile(p);
		if (cur == null)
			continue;
		let d = substr(p, 0, rindex(p, '/'));
		push(freqs, { cur: num(rtrim(cur, '\n')), max: memo(opts, 'max:' + d, 300, () => num(rd(d + '/cpuinfo_max_freq'))) });
	}

	// MemTotal and MemAvailable: the first lines of /proc/meminfo
	let mem_t = null, mem_a = null;
	for (let l in split(readfile('/proc/meminfo', 512) ?? '', '\n')) {
		let k = substr(l, 0, index(l, ':'));
		if (k != 'MemTotal' && k != 'MemAvailable')
			continue;
		let v = num(split(ltrim(substr(l, length(k) + 1), ' \t'), ' ')[0]);
		if (k == 'MemTotal' && mem_t == null) mem_t = v;
		if (k == 'MemAvailable' && mem_a == null) mem_a = v;
	}

	// the root file system (the ext4 mu300root loop device), as df -k reports it
	let storage = memo(opts, 'storage', 30, () => {
		let core = mod('luci.core');
		let vfs = core ? core.statvfs('/') : null;
		if (vfs && vfs.frsize)
			return { total_kb: vfs.blocks * vfs.frsize / 1024, used_kb: (vfs.blocks - vfs.bfree) * vfs.frsize / 1024,
				avail_kb: vfs.bavail * vfs.frsize / 1024 };
		let r = run('df -k / 2>/dev/null');
		let l = split(r?.out ?? '', '\n')[1];
		let f = l ? filter(split(l, /[ \t]+/), x => x != '') : [];
		return { total_kb: num(f[1]), used_kb: num(f[2]), avail_kb: num(f[3]) };
	});

	let temps = memo(opts, 'temps', 5, () => {
		let zones = glob('/sys/class/thermal/thermal_zone*') ?? [];
		return { soc: temp_of(zones, 'soc-thmzone'), cpu: temp_of(zones, 'apcpu0-thmzone'),
			modem: temp_of(zones, 'nr0-thmzone'), board: temp_of(zones, 'board-thmzone'), hottest: temp_hottest(zones) };
	});

	// (the fuel gauge's readings are ADC conversions in the kernel: every 3 s is plenty for the tile)
	let power = memo(opts, 'power', 3, () => power_info(device_name()));

	// ------------------------------------------------------------------- Wi-Fi
	// configuration truth is uci (the driver reports nothing useful); the first wifi-iface section's options
	let iface = null;
	if (cur)
		cur.foreach('wireless', 'wifi-iface', (s) => { if (iface == null) iface = s['.name']; });
	let wu = (sec, opt) => (sec == null) ? '' : uget(cur, 'wireless', sec, opt);
	let w_ssid = wu(iface, 'ssid');
	let w_ch = wu('radio0', 'channel');
	let w_band = wu('radio0', 'band');
	if (w_band == '')
		w_band = wu('radio0', 'hwmode');
	// HE80 / VHT40 / HT20 -> the number is the width (its first two digits, as before)
	let w_width = substr(replace(wu('radio0', 'htmode'), /[^0-9]/g, ''), 0, 2);
	if (w_width != '')
		w_width += ' MHz';
	let w_enc = wu(iface, 'encryption');
	if (w_enc == '')
		w_enc = 'none';
	let hapd = ubus_call('hostapd.' + wifi_device, 'get_status');
	let w_hostapd = (hapd?.status == 'ENABLED') ? 1 : 0;
	let w_up = (wu('radio0', 'disabled') == '1') ? 0 : 1;
	if (!is_dir('/sys/class/net/' + wifi_device) || !w_hostapd)
		w_up = 0;

	// clients: the station table, names and addresses from dnsmasq's leases (lower-case MACs, "*" for no name)
	let leases_file = env('MU300_DHCP_LEASES', '/tmp/dhcp.leases');
	let leases = lease_lines(leases_file);
	let clients = [];
	for (let row in stations(wifi_device)) {
		let ip = '', host_n = '';
		for (let f in leases)
			if (lc(f[1] ?? '') == row[0]) { ip = f[2] ?? ''; host_n = f[3] ?? ''; break; }
		if (host_n == '*')
			host_n = '';
		push(clients, { mac: str(row[0]), host: str(host_n), ip: str(ip), signal: num('' + row[1]),
			tx: str(row[2]), rx: str(row[3]), conn: str(row[4]) });
	}
	let leases_raw = readfile(leases_file);
	let lan_leases = (leases_raw == null) ? 0 : length(match(leases_raw, /\n/g) ?? []);
	// recent DHCP leases (shows devices that were here even when nobody is associated now)
	let lease_list = [];
	for (let f in leases) {
		if ((f[1] ?? '') == '')
			continue;
		let exp = f[0] ?? '';
		if (!match(exp, /^[0-9]+$/))
			exp = '' + NOW;
		let left = +exp - NOW;
		if (left < 0)
			left = 0;
		let h = f[3] ?? '';
		if (h == '*')
			h = '';
		push(lease_list, { host: str(h), ip: str(f[2] ?? ''), mac: str(f[1]), left: left });
	}
	let lan_ip = memo(opts, 'inet:' + lan_device, 5, () => addresses(lan_device, 'inet'))[0];

	// ---------------------------------------------------------------- modem/path
	// the liveness rule mu300-atd uses: the URC log on nr0 is written to as long as the modem runs
	let urclog = '/run/mu300-at/urc/stty_nr' + (slot_n * 3) + '.log';
	let ust = stat(urclog);
	let modem_alive = (ust && ust.type == 'file' && NOW - ust.mtime < 240) ? 1 : 0;
	let atd_ok = memo(opts, 'atd', 30, () => at_available(cur) ? 1 : 0);
	if (modem_alive != 1)
		modem_alive = atd_ok;
	let data_paused = exists('/run/mu300-mobile-data-down') ? 1 : 0;
	// tracked connections: the kernel's counter (mainline has no /proc/net/nf_conntrack), the table as fallback, null
	// when neither can be read
	let conns = null;
	let counter = env('MU300_CONNTRACK_COUNT', '/proc/sys/net/netfilter/nf_conntrack_count');
	let table = env('MU300_CONNTRACK_TABLE', '/proc/net/nf_conntrack');
	if (readable(counter) && match(rd(counter), /^[0-9]+$/))
		conns = +rd(counter);
	else if (readable(table)) {
		let t = readfile(table);
		if (t != null)
			conns = length(match(t, /\n/g) ?? []);
	}

	// --------------------------------------------------------------------- VPN
	// (the VPN's configuration and links, the boot lock: kept 10 s in the plugin)
	let vpn = memo(opts, 'vpn', 10, () => {
		let vpn_enabled = 0, vpn_engine = '', vpn_up = 0;
		if (readable('/etc/mu300/vpn.conf') && match(readfile('/etc/mu300/vpn.conf') ?? '', /(^|\n)ENABLE=1/))
			vpn_enabled = 1;
		let active = first_line('/etc/mu300/vpn/active', 64);
		if (active != '' && match(active, /^[a-z0-9-]+$/) && length(active) <= 32) {
			for (let l in split(readfile('/etc/mu300/vpn/profiles/' + active + '/meta') ?? '', '\n'))
				if (substr(l, 0, 5) == 'TYPE=')
					vpn_engine = replace(replace(substr(l, 5), /^'/, ''), /'$/, '');
		}
		if (vpn_engine == '')
			for (let l in split(readfile('/etc/mu300/vpn.conf') ?? '', '\n'))
				if (substr(l, 0, 7) == 'ENGINE=')
					vpn_engine = substr(l, 7);
		let vpn_if = first_line('/run/mu300-vpn/iface', 32);
		if (!match(vpn_if, /^[A-Za-z0-9_.-]+$/))
			vpn_if = '';
		if ((vpn_if != '' && link_exists(vpn_if)) || link_exists('xtun') || link_exists('sbtun'))
			vpn_up = 1;
		// the VPN is a module of its own (github.com/dikeckaan/mu300-linux-vpn): present when its hook linked it in
		let cap_vpn = (executable('/opt/mu300/bin/mu300-vpn') && executable('/etc/init.d/mu300-vpn')) ? 1 : 0;
		// orphaned: the VPN on with its kill switch and no module to enforce it (lib/vpn-orphan.sh)
		let vpn_orphaned = 0;
		if (readable(env('MU300_VPN_ORPHAN_LIB', '/opt/mu300/lib/vpn-orphan.sh')) &&
		    !executable(env('MU300_VPN_CMD', '/opt/mu300/bin/mu300-vpn')) && vpn_killswitch_wanted(getenv('MU300_SYSROOT') ?? ''))
			vpn_orphaned = 1;
		let cap_dualboot = executable('/opt/mu300/bin/mu300-next-boot') ? 1 : 0;
		let boot_lock = (is_file('/mnt/mu300-disk/.mu300/boot-lock') || is_file('/.mu300/boot-lock')) ? 1 : 0;
		return { enabled: vpn_enabled, engine: vpn_engine, up: vpn_up, orphaned: vpn_orphaned, cap_vpn: cap_vpn,
			cap_dualboot: cap_dualboot, boot_lock: boot_lock };
	});
	let vpn_enabled = vpn.enabled, vpn_engine = vpn.engine, vpn_up = vpn.up, vpn_orphaned = vpn.orphaned;
	let cap_vpn = vpn.cap_vpn, cap_dualboot = vpn.cap_dualboot, boot_lock = vpn.boot_lock;

	// a newer release: the note mu300-update keeps (only read here); its tag must be a release tag (FINDINGS 125)
	let notes = memo(opts, 'notes', 10, () => {
		let update_tag = '';
		for (let l in split(readfile(env('MU300_NOTICE', '/run/mu300/update-available')) ?? '', '\n')) {
			let m = match(l, /^mu300-linux (v[0-9.]*) is out /);
			if (m) { update_tag = m[1]; break; }
		}
		if (!match(update_tag, /^(v[0-9]{4}\.[0-9]{2}\.[0-9]{2}|v[0-9]{4}\.(0[1-9]|1[0-2])\.(0[1-9]|[12][0-9]|3[01])\.[1-9][0-9]?)$/))
			update_tag = '';

		// ------------------------------------------------------------- data usage
		// mu300-traffic's summary (RAM, once a minute): numbers and fixed words only
		let tsum = {};
		for (let l in split(readfile(env('MU300_TRAFFIC_SUMMARY', '/run/mu300/traffic/summary')) ?? '', '\n')) {
			let m = match(l, /^([a-z_]+)=(.*)$/);
			if (m && !exists(tsum, m[1]))
				tsum[m[1]] = m[2];
		}
		let tint = (k) => { let v = tsum[k] ?? ''; return (v == '' || match(v, /[^0-9]/) || match(v, /^0./)) ? 0 : +v; };
		let traffic = null;
		if ((tsum.level ?? '') in [ 'ok', 'warn', 'over', 'none' ])
			traffic = { level: tsum.level, today: tint('today_rx') + tint('today_tx'), used: tint('used'), cap: tint('cap'),
				warn: tint('warn'), clock: tint('clock') };
		return { update_tag: update_tag, traffic: traffic };
	});
	let update_tag = notes.update_tag, traffic = notes.traffic;

	return {
		ts: NOW, uptime: int(uptime), host: str(host), model: str(model), fw: str(fw), kernel: str(kernel),
		cpu: { n: cpun, total: cpu_total, idle: cpu_idle, freqs: freqs },
		mem: { total_kb: mem_t, avail_kb: mem_a },
		storage: storage,
		temps: temps,
		power: power,
		net: { mobile: net_obj(data_device), sipa_eth0: net_obj(data_device), brlan: net_obj(lan_device),
			wlan0: net_obj(wifi_device), usb0: net_obj(usb_device) },
		data_device: str(data_device),
		sim: sim_json,
		traffic: traffic,
		wan: { up: (wan.up === true) ? 1 : 0, uptime: num(wan.uptime), proto: str(wan.proto), apn: str(apn),
			ip4: str(wan_ip4), ip6: str(wan6_ip), dns: str(join(', ', dns)),
			roaming: { allowed: roam_allowed, held: roam_held } },
		wifi: { up: w_up, ssid: str(w_ssid), channel: str(w_ch), band: str(w_band), width: str(w_width),
			country: str(wu('radio0', 'country')), enc: str(w_enc), hidden: num(wu(iface, 'hidden')),
			hostapd: w_hostapd, clients: clients, clients_n: length(clients) },
		lan: { leases: lan_leases, ip: str(lan_ip), list: lease_list },
		modem: { alive: modem_alive, atd: atd_ok, data_paused: data_paused },
		capabilities: { vpn: cap_vpn, dualboot: cap_dualboot, bootlock: boot_lock },
		update: str(update_tag),
		conns: conns,
		vpn: { enabled: vpn_enabled, engine: str(vpn_engine), up: vpn_up, orphaned: vpn_orphaned }
	};
}

// ------------------------------------------------------------- the status call
// The runtime directory of the backend (lib.sh RUN_DIR, private_dir): root's, 0700, not a symlink
function run_dir() {
	let dir = env('MU300_DASH_DIR', '/var/run/unisoc-modem');
	if (!exists(dir)) {
		mkdir(replace(dir, /\/[^\/]*$/, ''));
		mkdir(dir, 0700);
	}
	let l = lstat(dir);
	let uid = +(match(rd('/proc/self/status'), /\nUid:[ \t]*([0-9]+)/)?.[1] ?? '0');
	if (!l || l.type != 'directory' || l.uid != uid)
		return null;
	if (l.perm?.group_write || l.perm?.other_write)
		return null;
	chmod(dir, 0700);
	return dir;
}

function age_of(path) {
	let s = stat(path);
	return (s && s.type == 'file' && s.size > 0) ? time() - s.mtime : -1;
}

function json_file(path) {
	let s = readfile(path);
	if (s == null || s == '')
		return null;
	try {
		let v = json(s);
		return (type(v) == 'object') ? v : null;
	}
	catch (e) {
		return null;
	}
}

// a collector that holds LOCK (its pid file names a live process running unisoc-modem/cell)
function collector_alive(lock) {
	let pid = rd(lock + '/pid');
	if (!match(pid, /^[0-9]+$/))
		return false;
	let cmd = readfile('/proc/' + pid + '/cmdline');
	if (cmd == null)
		return false;
	cmd = replace(cmd, /\0/g, ' ');
	// the collector program, or the modem daemon running a round of its own (FINDINGS 206)
	return index(cmd, '/unisoc-modem/cell') >= 0 || index(cmd, 'mu300-modemd') >= 0;
}

// The collector's command line (without its mode). In the plugin (opts.cache) it is the collector compiled once
// (ucode -c): compiling its source took ~15 ms of a fast round's ~50. The bytecode lives in the runtime directory
// (root's, 0700; its path keeps "/unisoc-modem/cell", which the collectors' lock checks look for) and is made again
// when the source or the interpreter is newer; when it cannot be made, the source runs. The SIM slot the plugin
// already knows is handed down (MU300_DASH_SIM_SLOT): asking the selector is another 13 ms on the U30 Air.
function collector(dash, dir, opts) {
	let src = dash + '/cell';
	let cmd = shq(src);
	if (opts.cache) {
		let ucb = dir + '/cell.ucb';
		let b = stat(ucb), s = stat(src), u = stat('/usr/bin/ucode');
		if (s && u) {
			if (!b || b.mtime < s.mtime || b.mtime < u.mtime) {
				unlink(ucb + '.part');
				if (system('ucode -c -s -o ' + shq(ucb + '.part') + ' ' + shq(src) + ' >/dev/null 2>&1') == 0 &&
				    rename(ucb + '.part', ucb))
					b = stat(ucb);
				else {
					unlink(ucb + '.part');
					b = null;
				}
			}
			if (b)
				cmd = 'ucode ' + shq(ucb);
		}
	}
	let slot = (opts.cache && sim_cache?.ok && match('' + sim_cache.slot, /^[01]$/)) ? 'MU300_DASH_SIM_SLOT=' + sim_cache.slot + ' ' : '';
	return slot + 'setsid ' + cmd;
}

// kick(dash, dir, opts, mode): a background round. The modem daemon runs it in its own process when it is there
// (ubus mu300.modem cell, FINDINGS 206: no process, no fork, the commands straight to its channels); else the
// collector program starts, detached, as before.
function kick(dash, dir, opts, mode) {
	let r = ubus_call('mu300.modem', 'cell', { mode: mode });
	if (r != null && (r.started || r.busy))
		return;
	system(collector(dash, dir, opts) + ((mode == 'fast') ? ' fast' : '') + ' </dev/null >/dev/null 2>&1 &');
}

// status(opts): the info snapshot and the two cellular caches with their ages. A stale cache starts a background
// refresh (setsid): the call itself never waits for the modem. opts.ttl / opts.ttl_fast: the two tiers' ages in
// seconds before a refresh is started.
function status(opts) {
	opts ??= {};
	let dir = run_dir();
	if (!dir)
		return { ok: 0, error: 'The runtime directory is not safe; nothing was run' };
	let dash = env('MU300_DASH_BIN', '/usr/libexec/unisoc-modem');
	let cell = dir + '/cell.json', sigf = dir + '/sig.json';
	let ttl = opts.ttl ?? 5, ttl_fast = opts.ttl_fast ?? 1;
	let inf = info(opts);
	let cage = age_of(cell), sage = age_of(sigf);
	let busy = 0, fbusy = 0;
	// during a lock apply or a SIM switch the modem answers garbage: nothing is started
	if (is_dir('/run/unisoc-modem-lock-apply') || exists('/run/mu300/sim-switching') || exists('/run/mu300/sim-active-unknown'))
		busy = fbusy = 1;
	if (collector_alive(dir + '/collect.lck'))
		busy = fbusy = 1;
	if (collector_alive(dir + '/fast.lck'))
		fbusy = 1;
	// a full round also writes sig.json: it is preferred when both tiers are stale
	if ((cage < 0 || cage > ttl) && !busy) {
		kick(dash, dir, opts, 'full');
		busy = fbusy = 1;
	}
	else if ((sage < 0 || sage > ttl_fast) && !fbusy) {
		kick(dash, dir, opts, 'fast');
		fbusy = 1;
	}
	return { info: inf, cell: json_file(cell), sig: json_file(sigf), cell_age: cage, sig_age: sage, refreshing: busy };
}

// sms_head(): what changes when a message is pooled or removed - the pool's next id and its message directory's
// count and time - for the pages' new-message watcher, which then asks for the list only when this changed
function sms_head() {
	let cur = uci_cursor();
	let pool = safe_state_dir(uget(cur, 'unisoc_modem', 'main', 'sms_pool'), '');
	if (match(pool, /^\/etc\/mu300\/sms(\/|$)/))
		pool = '';
	pool = env('MU300_SMS_POOL', (pool != '') ? pool : '/etc/mu300/sms-pool');
	let s = stat(pool + '/msg');
	let n = 0;
	for (let f in lsdir(pool + '/msg') ?? [])
		if (match(f, /^[0-9]+$/))
			n++;
	return { next_id: num(rd(pool + '/next_id')), count: n, mtime: s ? s.mtime : null };
}

export { info, status, sms_head };
