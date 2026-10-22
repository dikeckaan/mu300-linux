// The home page's status in rpcd itself (rpcd-mod-ucode, FINDINGS 206): the snapshot mu300.dash builds from files,
// ubus, uci, nl80211 and rtnl, without a process (the shell backend started ~700 per snapshot, every 1.5 s while the
// page was open), and the two cellular caches the collector (unisoc-modem/cell) writes. A stale cache starts the
// collector in the background and the call returns at once, as mu300dash's status always did.
//
//   status     { info, cell, sig, cell_age, sig_age, refreshing }: mu300dash status's reply
//   sysinfo    the snapshot alone (mu300dash sysinfo)
//   sms_head   { next_id, count, mtime } of the SMS pool: the pages' new-message watcher asks for the list
//              (mu300dash sms_list) only when this changed
//
// The cellular tiers' ages before a refresh starts: the serving cell (fast tier, sig.json) after TTL_FAST seconds -
// so with the page's 1.5 s poll a fast round every ~4.5 s - and neighbours/operator/QoS/identity (full tier,
// cell.json) after TTL. unisoc_modem.main.cell_ttl_fast / cell_ttl override them (whole seconds, read every 10 s).
// The shell backend used 1 and 5: a round on every poll, ~60 % of a core while the page was open.
'use strict';

import { info, status, sms_head } from 'mu300.dash';
import { cursor } from 'uci';

const TTL_FAST = 3;
const TTL = 30;

let ttls = null;
function ttl_opts() {
	if (ttls == null || time() - ttls.at >= 10 || time() < ttls.at) {
		let c = cursor();
		let get = (option, dflt) => {
			let v = c.get('unisoc_modem', 'main', option);
			return (v != null && match('' + v, /^[0-9]{1,4}$/) && +v >= 1) ? +v : dflt;
		};
		ttls = { at: time(), ttl: get('cell_ttl', TTL), ttl_fast: get('cell_ttl_fast', TTL_FAST) };
	}
	return ttls;
}

function guarded(fn) {
	try {
		return fn();
	}
	catch (e) {
		warn(sprintf('mu300status: %s\n', e));
		return { error: 'Dashboard info failed' };
	}
}

return {
	mu300status: {
		status: {
			call: function() {
				let t = ttl_opts();
				return guarded(() => status({ cache: true, ttl: t.ttl, ttl_fast: t.ttl_fast }));
			}
		},
		sysinfo: {
			call: function() {
				return guarded(() => info({ cache: true }));
			}
		},
		sms_head: {
			call: function() {
				return guarded(() => sms_head());
			}
		}
	}
};
