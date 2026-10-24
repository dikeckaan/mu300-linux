// Stand-in for ucode's rtnl module in the tests: an address dump runs the `ip -4|-6 addr show` the test stubbed on
// PATH and reads its "N: DEV: ..." and "inet[6] ADDR/LEN" lines (the one-line form "N: DEV inet ADDR/LEN" too).
import { popen } from 'fs';

const CONSTS = { RTM_GETADDR: 22, NLM_F_DUMP: 0x300, AF_INET: 2, AF_INET6: 10 };

function request(cmd, flags, args) {
	let fam = (args?.family == 10) ? '-6' : '-4';
	let p = popen('ip ' + fam + ' addr show 2>/dev/null', 'r');
	if (!p) return null;
	let out = p.read('all');
	if (p.close() != 0) return [];
	let list = [], dev = null;
	for (let l in split(out ?? '', '\n')) {
		let m = match(l, /^[0-9]+:[ \t]+([^:@ \t]+)[@:]?/);
		if (m) dev = m[1];
		m = match(l, /inet6?[ \t]+([0-9A-Fa-f.:]+\/[0-9]+)/);
		if (m && dev)
			push(list, { family: args?.family, dev: dev, address: m[1] });
	}
	return list;
}

return { const: CONSTS, request: request, error: () => null };
