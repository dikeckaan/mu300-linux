// Stand-in for ucode's ubus module in the tests: a call runs the `ubus` command the test stubbed on PATH
// (`ubus call OBJECT METHOD [ARGS]`) and parses what it prints. Only what mu300.dash and the collector use.
import { popen } from 'fs';

let last_error = null;

function shq(s) { return "'" + replace('' + s, "'", "'\\''") + "'"; }

function call(object, method, args) {
	let a = (args && length(keys(args))) ? ' ' + shq(sprintf('%J', args)) : '';
	let p = popen('ubus call ' + shq(object) + ' ' + shq(method) + a + ' 2>/dev/null', 'r');
	if (!p) { last_error = 'popen failed'; return null; }
	let out = p.read('all');
	let rc = p.close();
	if (rc != 0 || out == null || out == '') { last_error = 'Not found'; return null; }
	try { return json(out); }
	catch (e) { last_error = 'Invalid argument'; return null; }
}

return {
	connect: (path, timeout) => ({ call: call, disconnect: () => true, error: () => last_error }),
	error: () => last_error
};
