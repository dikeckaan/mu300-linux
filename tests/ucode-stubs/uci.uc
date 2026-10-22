// Stand-in for ucode's uci module in the tests: get() runs the `uci -q get CONF.SECTION.OPTION` the test stubbed on
// PATH (the very command the shell versions ran), foreach() parses `uci -q show CONF`.
import { popen } from 'fs';

function shq(s) { return "'" + replace('' + s, "'", "'\\''") + "'"; }

function run(cmd) {
	let p = popen(cmd + ' 2>/dev/null', 'r');
	if (!p) return null;
	let out = p.read('all');
	return (p.close() == 0) ? (out ?? '') : null;
}

// `uci show` lines: CONF.SECTION=TYPE and CONF.SECTION.OPTION='value'
function sections(conf) {
	let out = run('uci -q show ' + shq(conf));
	let list = [], by = {};
	for (let l in split(out ?? '', '\n')) {
		let m = match(l, /^[^.]+\.([^.=]+)=([^']*)$/);
		if (m) {
			by[m[1]] = { '.name': m[1], '.type': m[2] };
			push(list, by[m[1]]);
			continue;
		}
		m = match(l, /^[^.]+\.([^.=]+)\.([^.=]+)='(.*)'$/);
		if (m && by[m[1]])
			by[m[1]][m[2]] = m[3];
	}
	return list;
}

// the option as `uci -q get` prints it; a test that stubbed only `uci show CONF` (the shell dashboard read the Wi-Fi
// that way) is answered from that
function get(conf, section, option) {
	let out = run('uci -q get ' + shq(conf + '.' + section + ((option != null) ? '.' + option : '')));
	if (out != null)
		return replace(out, /\n+$/, '');
	if (option == null || substr(section, 0, 1) == '@')
		return null;
	for (let s in sections(conf))
		if (s['.name'] == section)
			return s[option];
	return null;
}

function foreach(conf, type, cb) {
	for (let s in sections(conf))
		if (type == null || s['.type'] == type)
			if (cb(s) === false)
				break;
	return true;
}

return {
	cursor: () => ({ get: get, foreach: foreach, get_all: (conf, sec) => null, unload: () => true })
};
