// Stand-in for ucode's nl80211 module in the tests: GET_STATION runs the `iw dev DEV station dump` (or `station get
// MAC`) the test stubbed on PATH and turns iw's text into the module's objects: signal in dBm, the rates as
// bitrate32 (units of 100 kbit/s), connected_time in seconds; what iw printed as "(unknown)" is left out.
import { popen } from 'fs';

const CONSTS = { NL80211_CMD_GET_STATION: 17, NLM_F_DUMP: 0x300 };

function shq(s) { return "'" + replace('' + s, "'", "'\\''") + "'"; }

function parse(text, dev) {
	let list = [], cur = null;
	for (let l in split(text ?? '', '\n')) {
		let m = match(l, /^Station[ \t]+([^ \t]+)/);
		if (m) { cur = { dev: dev, mac: lc(m[1]), sta_info: {} }; push(list, cur); continue; }
		if (!cur) continue;
		m = match(l, /^[ \t]+signal:[ \t]*(-?[0-9]+)/);
		if (m) { cur.sta_info.signal = +m[1]; continue; }
		m = match(l, /^[ \t]+(tx|rx) bitrate:[ \t]*([0-9]+)(\.([0-9]))?/);
		if (m) { cur.sta_info[m[1] + '_bitrate'] = { bitrate32: +m[2] * 10 + +(m[4] ?? 0) }; continue; }
		m = match(l, /^[ \t]+connected time:[ \t]*([0-9]+)/);
		if (m) { cur.sta_info.connected_time = +m[1]; continue; }
	}
	return list;
}

function request(cmd, flags, args) {
	let dump = (flags & 0x300) == 0x300;
	let c = 'iw dev ' + shq(args.dev) + ' station ' + (dump ? 'dump' : 'get ' + shq(args.mac));
	let p = popen(c + ' 2>/dev/null', 'r');
	if (!p) return null;
	let out = p.read('all');
	if (p.close() != 0) return null;
	let list = parse(out, args.dev);
	return dump ? list : list[0];
}

return { const: CONSTS, request: request, error: () => null };
