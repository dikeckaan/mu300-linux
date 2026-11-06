// Run on OpenWrt with ucode-mod-uloop. "baseline" reproduces the old call;
// no argument tests the workaround. Each run uses its own process, not rpcd.
import * as uloop from 'uloop';
import { glob } from 'fs';

uloop.init();
let worker, timer, completed = 0;
const baseline = ARGV[0] == 'baseline';
const before = length(glob('/proc/self/fd/*'));
const watchdog = uloop.timer(10000, () => die('task test timed out\n'));

timer = uloop.timer(1, () => {
	if (worker) {
		if (!worker.finished()) {
			timer.set(10);
			return;
		}
		worker = null;
		completed++;
	}
	if (completed == 100) {
		uloop.end();
		return;
	}
	worker = baseline
		? uloop.task(() => 1, () => {})
		: uloop.task(() => 1, () => {}, () => null);
	timer.set(10);
});

uloop.run();
watchdog.cancel();
const after = length(glob('/proc/self/fd/*'));
printf('%s: %d tasks, descriptors %d -> %d\n', baseline ? 'baseline' : 'workaround', completed, before, after);
if (after > before)
	die('task pipe descriptors leaked\n');
