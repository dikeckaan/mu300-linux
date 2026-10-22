// mu300.cellparse -- the cellular collector's readings, from the modem's answers to JSON (FINDINGS 206).
//
// Pure functions, no AT and no files: shared by the collector program (/usr/libexec/unisoc-modem/cell) and the modem
// daemon (/opt/mu300/bin/mu300-modemd), so both write the same sig.json and cell.json. They were the awk and sed
// fragments of the shell collector; each keeps that one's rules (comments below). busybox awk's 32-bit integers are
// no longer a concern (ucode's are 64-bit), but the cell ids stay strings, as the page expects them.
'use strict';

function safe_iface(name, dflt) {
	return (type(name) == 'string' && match(name, /^[A-Za-z0-9][A-Za-z0-9_.-]*$/) && length(name) <= 15) ? name : dflt;
}

function safe_state_dir(path, dflt) {
	if (type(path) != 'string' || !match(path, /^\/etc\/(unisoc-modem|mu300)(\/.*)?$/))
		return dflt;
	if (match(path, /\/\./) || index(path, '//') >= 0 || substr(path, -1) == '/' || match(path, /[^A-Za-z0-9_.\/-]/))
		return dflt;
	return path;
}

function data_cid(dev, slot) {
	let m = match(dev, /^sipa_eth([0-9]+)$/);
	if (!m)
		return null;
	let n = +m[1];
	if (slot == '0' && n <= 7 && length(m[1]) == 1) return n + 1;
	if (slot == '1' && ((n >= 8 && n <= 9 && length(m[1]) == 1) || (n >= 10 && n <= 15 && length(m[1]) == 2))) return n - 7;
	return null;
}

const FINAL = /(^|\n)(OK|ERROR|\+CME ERROR|\+CMS ERROR|CONNECT|NO CARRIER)/;

function lines(text) { let l = split(text ?? '', '\n'); return filter(l, (x, i) => !(i == length(l) - 1 && x == '')); }

function first_with(text, prefix) {
	for (let l in lines(text))
		if (substr(l, 0, length(prefix)) == prefix)
			return l;
	return '';
}

function after_prefix(text, prefix) {
	for (let l in lines(text))
		if (substr(l, 0, length(prefix)) == prefix)
			return ltrim(substr(l, length(prefix)), ' ');
	return '';
}

function eng_line(text) {
	for (let l in lines(text))
		if (substr(l, 0, 2) != 'AT' && index(l, '-') >= 0)
			return l;
	return '';
}

function n_or_null(s) { return match(s ?? '', /^[0-9]+$/) ? +s : null; }

// ---------------------------------------------------------------- awk's numbers
// x+0 as awk takes it: the leading number of the text, 0 for none
function anum(x) {
	let m = match('' + (x ?? ''), /^[ \t\n]*([-+]?([0-9]+\.?[0-9]*|\.[0-9]+)([eE][-+]?[0-9]+)?)/);
	return m ? +m[1] : 0;
}

function fmt1(v) { return +sprintf('%.1f', v); }

// ------------------------------------------------------------- identity
// ident_token REPLY ERE: the first line of an identity answer that is the value alone, after an optional
// "+CGSN: "-like prefix and quotes; an error line ("+CME ERROR: 10") is never a value
function ident_token(reply, re) {
	for (let l in lines(replace(replace(reply, /\r/g, ''), /"/g, ''))) {
		if (match(l, /error/i))
			continue;
		l = rtrim(ltrim(replace(l, /^[+^][A-Za-z]*: */, ''), ' '), ' ');   // (no replace() with a pattern that can match nothing: ucode repeats the text then)
		if (match(l, re))
			return l;
	}
	return '';
}

function iccid_value(v) {
	v = replace(v, /[abcdef]/g, (c) => uc(c));
	if (!match(v, /[^0-9F]/) && match(v, /[0-9]F$/)) {
		v = substr(v, 0, length(v) - 1);
		if (length(v) < 18)
			v = '';
	}
	return v;
}

// ------------------------------------------------------------- own number
// cnum_number: the first number of an AT+CNUM answer, +CNUM: "alpha","number",type[,...]: digits (spaces, dashes and
// brackets dropped), 3 to 15 of them (E.164), "+" put in front for type 145 (international)
function cnum_number(text) {
	for (let l in lines(text)) {
		if (!match(l, /^\+CNUM:/))
			continue;
		let f = split(l, '"');
		let n = replace(f[3] ?? '', /[ ()-]/g, '');
		if (!match(n, /^\+?[0-9][0-9]+[0-9]$/))
			continue;
		let d = replace(n, /^\+/, '');
		if (length(d) > 15)
			continue;
		if (match(f[4] ?? '', /^[ \t]*,[ \t]*145([ \t]*,|[ \t]*$)/) && !match(n, /^\+/))
			n = '+' + n;
		return n;
	}
	return '';
}

function ims_number(text) {
	let sip = '';
	for (let l in lines(text)) {
		if (!match(l, /^\+SPPAURI:/))
			continue;
		l = replace(l, /^\+SPPAURI:[ \t]*/, '');
		for (let uri in split(l, /[ \t",<>]+/)) {
			let lower = lc(uri);
			if (!match(lower, /^(tel|sips?):/))
				continue;
			let n = replace(replace(replace(uri, /^[^:]*:/, ''), /[@;?].*$/, ''), /[ ().-]/g, '');
			let d = replace(n, /^\+/, '');
			if (!match(d, /^[0-9]+$/) || length(d) < 3 || length(d) > 15)
				continue;
			if (match(lower, /^tel:/))
				return n;
			if (match(n, /^\+/) && sip == '')
				sip = n;
		}
	}
	return sip;
}

// ------------------------------------------------------------- SPENGMD decode
// Unisoc separates fields with "-" and writes negatives as "+<abs>":
// "1-300-211--11747--654" = band 1, EARFCN 300, PCI 211, RSRP -117.47, RSRQ -6.54.
// Normalize ",-" -> ",+" and "--" -> "-+" first, then split on "-". A token may
// carry a comma list (bandwidth codes, CA flags); the scalar is the first field.
// dB values are centi-units.
function norm(l) {
	let s = replace(l, /\r/g, '');
	s = replace(s, /,-/g, ',+');
	s = replace(s, /--/g, '-+');
	s = replace(s, /^-/, '+');
	return map(split(s, '-'), (x) => replace(x, / /g, ''));
}

function f(x) {
	let v = replace(replace(x ?? '', /,.*/, ''), /\+/g, '-');
	return (v == '' || v == 'NA' || v == 'N/A') ? '' : anum(v);
}

function nnum(x) { return (x === '') ? null : x; }

function c1(x) { return (x === '') ? null : fmt1(x / 100.0); }

function fs_(x) {
	let v = replace(x ?? '', /,.*/, '');
	if (substr(v, 0, 1) == '+')
		v = '' + (4294967296 - (+substr(v, 1) || 0));
	return (v == '' || v == 'NA' || v == 'N/A') ? null : v;
}

function d(x) { return (x === '') ? 0 : int(x); }

const LTE_BANDS = [ [1,0,599],[2,600,1199],[3,1200,1949],[4,1950,2399],[5,2400,2649],[7,2750,3449],[8,3450,3799],
	[12,5010,5179],[13,5180,5279],[14,5280,5379],[17,5730,5849],[18,5850,5999],[19,6000,6149],[20,6150,6449],
	[25,8040,8689],[26,8690,9039],[27,9040,9209],[28,9210,9659],[30,9770,9869],[31,9870,9919],[33,36000,36199],
	[34,36200,36349],[35,36350,36949],[36,36950,37549],[37,37550,37749],[38,37750,38249],[39,38250,38649],
	[40,38650,39649],[41,39650,41589],[42,41590,43589],[43,43590,45589],[44,45590,46589],[46,46790,54539],
	[47,54540,55239],[48,55240,56739],[49,56740,58239],[50,58240,59089],[51,59090,59139],[65,65536,66435],
	[66,66436,67335] ];

const NR_BANDS = [ [1,422000,434000],[3,361000,376000],[5,173800,178800],[8,185000,192000],[28,151600,160600],
	[40,460000,480000],[41,499200,537999],[78,620000,653333],[77,620000,680000],[79,693334,733333] ];

function band_of(table, fr) {
	for (let b in table)
		if (fr >= b[1] && fr <= b[2])
			return b[0];
	return 0;
}

function eq0(x) { return x !== '' && x == 0; }

function sp_lte(line, phy) {
	if (line == '')
		return null;
	let t = norm(line);
	let band = f(t[0]), earfcn = f(t[1]), pci = f(t[2]);
	if ((eq0(band) || band === '') && eq0(earfcn) && eq0(pci))
		return null;
	let bw = '';
	if (t[7] != null && t[7] != '')
		for (let c in split(t[7], ',')) {
			let v = anum(c);
			let w = (v == 0) ? '1.4' : (v == 1) ? '3' : (v == 2) ? '5' : (v == 3) ? '10' : (v == 4) ? '15' : (v == 5) ? '20' : null;
			if (w != null)
				bw += ((bw == '') ? '' : '+') + w + 'M';
		}
	let enb = f(t[11]), cidl = f(t[12]);
	let tac = f(t[28]);
	if (tac === '' || tac == 0)
		tac = f(t[29]);
	let ca = t[13] ?? '';
	// 0,0,6 carries the LTE PHY: token 2 = SINR (centi-dB), 3/4 = the UL/DL MCS histograms (the dominant index is
	// the live MCS), 5/6 = BLER. This device answers all zeros while camped on 5G SA (no LTE anchor), and an idle
	// histogram is all zeros too - both mean "no reading", not "0 dB".
	let psinr = null, pmcs = null, pumcs = null, publer = null, pdbler = null;
	if (phy != '') {
		let u = norm(phy);
		let s2 = f(u[2]);
		if (s2 !== '' && s2 >= -2000 && s2 <= 4000)
			psinr = fmt1(s2 / 100.0);
		publer = c1(f(u[5]));
		pdbler = c1(f(u[6]));
		for (let dir = 3; dir <= 4; dir++) {
			let h = split(u[dir] ?? '', ','), best = -1, bestn = 0, total = 0;
			if ((u[dir] ?? '') == '')
				h = [];
			for (let i = 0; i < length(h); i++) {
				let hv = anum(h[i]);
				total += hv;
				if (hv > bestn) { bestn = hv; best = i; }
			}
			if (total > 0 && best >= 0) {
				if (dir == 4) pmcs = best; else pumcs = best;
			}
		}
	}
	return { band: d(band), earfcn: d(earfcn), pci: d(pci), rsrp: c1(f(t[3])), rsrq: c1(f(t[4])), bw: bw,
		enb: nnum(enb), cid: nnum(cidl), tac: (tac === '') ? '' : sprintf('%x', tac), ca: (index(ca, 'DL_CA') >= 0) ? 'DL_CA' : '',
		sinr: psinr, dl_mcs: pmcs, ul_mcs: pumcs, dl_bler: pdbler, ul_bler: publer };
}

function sp_nr(line) {
	if (line == '')
		return null;
	let t = norm(line);
	let band = f(t[0]), arfcn = f(t[1]), pci = f(t[2]);
	if ((eq0(band) || band === '') && eq0(arfcn) && eq0(pci))
		return null;
	return { band: d(band), arfcn: d(arfcn), pci: d(pci), rsrp: c1(f(t[3])), rsrq: c1(f(t[4])), sinr: c1(f(t[15])),
		bw_mhz: nnum(f(t[7])), gnb: fs_(t[8]), cid: fs_(t[9]), ul_mcs: nnum(f(t[16])), dl_mcs: nnum(f(t[17])),
		ul_bler: c1(f(t[18])), dl_bler: c1(f(t[19])) };
}

// eight 12-field slots, the first four EARFCN/PCI/RSRP/RSRQ
function sp_ltenb(line) {
	if (line == '')
		return [];
	let t = norm(line), n = length(t), out = [];
	for (let s = 0; s < 8; s++) {
		let b = s * 12;
		if (b + 3 >= n)
			break;
		let earfcn = f(t[b]), pci = f(t[b + 1]);
		if (eq0(earfcn) && eq0(pci))
			continue;
		push(out, { rat: 'lte', band: band_of(LTE_BANDS, (earfcn === '') ? 0 : earfcn), arfcn: d(earfcn), pci: d(pci),
			rsrp: c1(f(t[b + 2])), rsrq: c1(f(t[b + 3])) });
	}
	return out;
}

// SPQ5GNCELLEX CSV: the serving 8-tuple, the count at index 8, then 8-tuples (arfcn, pci, rsrp, rsrq, sinr, ...)
function nr_neighbours(line) {
	if (line == '')
		return [];
	let a = split(line, ','), m = length(a), cnt = anum(a[8]), out = [];
	for (let i = 0; i < cnt && i < 8; i++) {
		let b = 9 + i * 8;   // awk's a[b+1] is a[b] here
		if (b + 5 > m)
			break;
		let fr = anum(a[b]), pci = anum(a[b + 1]);
		if (fr == 0 && pci == 0)
			continue;
		push(out, { rat: 'nr', band: band_of(NR_BANDS, fr), arfcn: int(fr), pci: int(pci),
			rsrp: fmt1(anum(a[b + 2]) / 100.0), rsrq: fmt1(anum(a[b + 3]) / 100.0), sinr: fmt1(anum(a[b + 4]) / 100.0) });
	}
	return out;
}

// registration line "+CEREG: 2,1,\"01F0\",\"0ABCD123\",13" -> stat/tac/cid/act
function reg_fragment(line) {
	if (line == '')
		return null;
	let f = split(replace(replace(line, /^\+C5*EREG: */, ''), /"/g, ''), ',');
	let rn = (x) => { x = replace(x ?? '', / /g, ''); return match(x, /^[0-9]+$/) ? +x : null; };
	let rs = (x) => (x == null || x == '') ? null : x;
	return { stat: rn(f[1]), tac: rs(f[2]), cid: rs(f[3]), act: rn(f[4]) };
}

// ---------------------------------------------------------------- operator
// cops_fragment COPS [NAMED CSCS] -> name/plmn/act. <format> 2 is the numeric PLMN, 0 and 1 a name. NAMED is the same
// answer in the long-name format (operator_name), CSCS the character set the modem said it uses. A name is read as
// UCS2 hex when the character set is UCS2, and then passed on as JSON \u escapes (valid UTF-16, no control
// character); under any other character set only a text that cannot reasonably be a name (issue #174) is read so.
function hexv(s) {
	let v = 0;
	for (let i = 0; i < length(s); i++)
		v = v * 16 + index('0123456789ABCDEF', substr(s, i, 1));
	return v;
}

function ucs2(s, strict) {
	if (length(s) % 4 || !match(s, /^[0-9A-Fa-f]+$/))
		return null;
	if (strict && (length(s) < 8 || match(s, /^[0-9]+$/)))
		return null;
	let out = '', hi = false, units = [];
	for (let i = 0; i < length(s); i += 4) {
		let u = uc(substr(s, i, 4)), v = hexv(u);
		if (v < 32 || (v >= 127 && v < 160))
			return null;
		if (strict && ((v >= 57344 && v <= 63743) || (v >= 64976 && v <= 65007) || v >= 65534))
			return null;
		if (v >= 55296 && v <= 56319) { if (hi) return null; hi = true; }
		else if (v >= 56320 && v <= 57343) { if (!hi) return null; hi = false; }
		else if (hi) return null;
		push(units, v);
	}
	if (hi)
		return null;
	// the code units as text (what the \u escapes of the shell version decode to)
	for (let i = 0; i < length(units); i++) {
		let v = units[i];
		if (v >= 55296 && v <= 56319) {
			v = 65536 + ((v - 55296) << 10) + (units[i + 1] - 56320);
			i++;
		}
		out += uchr(v);
	}
	return out;
}

function cops_parse(l) {
	let m = match(l ?? '', /^\+COPS: *[0-9]+ *, *([0-9]+) *, *"([^"]*)"(.*)$/);
	if (!m)
		return null;
	let a = replace(replace(m[3], /^ *, */, ''), /[^0-9].*$/, '');
	return { F: m[1], T: m[2], A: a };
}

function name_json(t, cscs) {
	if (t == '')
		return null;
	let u = ucs2(t, uc(cscs ?? '') != 'UCS2');
	return (u != null) ? u : t;
}

function cops_fragment(line, named, cscs) {
	if (line == '')
		return null;
	let p = cops_parse(line);
	if (!p)
		return null;
	let act = p.A, plmn = null, name = null;
	if (p.F == '2') {
		if (match(p.T, /^[0-9]{5,6}$/))
			plmn = p.T;
		let q = cops_parse(named);
		if (q && (q.F == '0' || q.F == '1'))
			name = name_json(q.T, cscs);
	}
	else
		name = name_json(p.T, cscs);
	return { name: name, plmn: plmn, act: (act == '') ? null : +act };
}

function cesq_fragment(line) {
	if (line == '')
		return null;
	let f = split(replace(line, /^\+CESQ: */, ''), ',');
	let f5 = f[4] ?? '', f6 = f[5] ?? '';
	let rsrp = (f6 != '' && anum(f6) != 255) ? anum(f6) - 140 : null;
	let rsrq = (f5 != '' && anum(f5) != 255) ? fmt1(-19.5 + anum(f5) * 0.5) : null;
	return { rsrp: rsrp, rsrq: rsrq };
}

function qos_fragment(line) {
	if (line == '')
		return null;
	let f = split(replace(replace(line, /OK$/, ''), /^\+CGEQOSRDP: */, ''), ',');
	if (!match(f[1] ?? '', /^ *[0-9]+ *$/))
		return null;
	let v7 = f[6] ?? '', v8 = f[7] ?? '';
	return { qci: int(anum(f[1])), dl: (v7 != '' && anum(v7) > 0) ? fmt1(anum(v7) / 1000.0) : null,
		ul: (v8 != '' && anum(v8) > 0) ? fmt1(anum(v8) / 1000.0) : null };
}

// Engineering reads, neighbours and bearer QoS have no useful answer while the
// modem is searching/no-service. Skipping them avoids a chain of AT timeouts.
function reg_stat(l) { return replace(split(replace(l, /"/g, ''), ',')[1] ?? '', / /g, ''); }


export { safe_iface, safe_state_dir, data_cid, lines, first_with, after_prefix, eng_line, n_or_null, anum, fmt1,
	ident_token, iccid_value, cnum_number, ims_number, norm, f, nnum, c1, fs_, d, band_of, eq0, sp_lte, sp_nr, sp_ltenb,
	nr_neighbours, reg_fragment, hexv, ucs2, cops_parse, name_json, cops_fragment, cesq_fragment, qos_fragment, reg_stat,
	LTE_BANDS, NR_BANDS, FINAL };
