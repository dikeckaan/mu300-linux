'use strict';
'require view';
'require dom';
'require mu300.common as M';

/* Every value from the backend goes into E() inside an array: LuCI's E() takes a lone string as HTML, an array's
 * strings as text. */
/* System > CPU: the CPU performance profile. The backend is mu300dash cpu_get/cpu_set (unisoc-modem/cpu, mu300-cpu):
 * a profile is a governor and a per-cluster scaling_min/max inside the hardware frequency table. It never changes
 * voltage and never touches the kernel thermal trips, so the device still throttles at its limit in every profile. */
return view.extend({
	load: function() { return L.resolveDefault(M.callCpuGet(), {}); },

	render: function(state) {
		M.injectCss();
		this.root = E('div', { 'class': 'mud' });
		this.paint(state || {});
		return this.root;
	},

	reload: function() {
		var self = this;
		return L.resolveDefault(M.callCpuGet(), {}).then(function(st) { self.paint(st || {}); return st; });
	},

	/* apply a profile and show the result */
	set: function(btn, name) {
		var self = this;
		M.busy(btn, true);
		return M.callCpuSet(String(name)).then(function(r) {
			M.busy(btn, false);
			if (!r || r.ok !== 1) {
				M.toast(_('Failed: %s').format(M.errText(r)), { type: 'error', timeout: 6000 });
				return;
			}
			M.toast(_('Saved'), { type: 'success' });
			return self.paint(r);
		}, function() {
			M.busy(btn, false);
			M.toast(_('Management connection lost'), { type: 'error', timeout: 6000 });
		});
	},

	paint: function(st) {
		var self = this;
		if (!st.profile || !Array.isArray(st.policies)) {
			dom.content(this.root, [ E('section', { 'class': 'mud-card', 'id': 'mud-cpu-unavailable' }, [
				E('h3', {}, _('CPU')),
				E('div', { 'class': 'mud-note' }, [ _('CPU profile unavailable') + (st.error ? ': ' + M.errText(st) : '') ])
			]) ]);
			return;
		}
		var names = { saving: _('Power saving'), balanced: _('Balanced'), performance: _('Performance') };
		var descs = {
			saving: _('Cores capped at about 60 %% of their maximum (cooler, less power).'),
			balanced: _('Schedutil across the full hardware range (the stock behaviour).'),
			performance: _('Every cluster pinned at its hardware maximum.')
		};

		/* 1. the profile buttons */
		var card = E('section', { 'class': 'mud-card', 'id': 'mud-cpu-profile' }, [ E('h3', {}, _('CPU profile')) ]);
		card.appendChild(E('div', { 'class': 'mud-note' },
			_('A profile sets the CPU governor and the per-cluster frequency limits. It stays within the hardware frequency table and never changes the voltage, so it cannot overclock this SoC. The kernel keeps throttling at its thermal limit in every profile.')));
		var actions = E('div', { 'style': 'display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:10px 0' });
		[ 'saving', 'balanced', 'performance' ].forEach(function(p) {
			var b = E('button', {
				'class': p === st.profile ? 'mud-btn cbi-button-positive' : 'mud-btn',
				'id': 'mud-cpu-' + p
			}, [ names[p] ]);
			b.addEventListener('click', function() { self.set(b, p); });
			actions.appendChild(b);
		});
		card.appendChild(actions);
		card.appendChild(E('div', { 'class': 'mud-note', 'id': 'mud-cpu-saved' },
			[ _('Saved profile: %s').format(names[st.profile] || String(st.profile)) ]));
		card.appendChild(E('div', { 'class': 'mud-note', 'id': 'mud-cpu-desc' }, [ descs[st.profile] || '' ]));
		if (st.throttling)
			card.appendChild(E('div', { 'class': 'mud-note', 'id': 'mud-cpu-throttle' },
				[ _('Thermal throttling is active right now: the frequencies below are below the profile ceiling.') ]));

		/* 2. the clusters */
		var num = function(x) { return typeof x === 'number' ? x : null; };
		var mhz = function(x) { return num(x) == null ? '--' : String(x); };
		var rows = st.policies.map(function(p) {
			return E('tr', {}, [
				E('td', {}, [ 'cpu' + String(p.cpus || '') ]),
				E('td', {}, [ String(p.governor || '--') ]),
				E('td', {}, [ mhz(p.cur) ]),
				E('td', {}, [ mhz(p.min) ]),
				E('td', {}, [ mhz(p.max) ]),
				E('td', {}, [ mhz(p.hwmax) ])
			]);
		});
		var table = E('section', { 'class': 'mud-card', 'style': 'margin-top:14px', 'id': 'mud-cpu-clusters' }, [
			E('h3', {}, _('Clusters')),
			E('table', { 'class': 'mud-table', 'id': 'mud-cpu-table' }, [
				E('tr', {}, [
					E('th', {}, _('Cores')), E('th', {}, _('Governor')), E('th', {}, _('Now')),
					E('th', {}, _('Min')), E('th', {}, _('Max')), E('th', {}, _('Hardware max'))
				])
			].concat(rows)),
			E('div', { 'class': 'mud-note' }, _('Frequencies in MHz.'))
		]);

		dom.content(this.root, [ card, table ]);
	}
});
