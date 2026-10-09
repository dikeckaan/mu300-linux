'use strict';
'require view';
'require dom';
'require rpc';
'require poll';
'require mu300.common as M';

return view.extend({
	load: function() { return L.resolveDefault(M.callSimGet(), {}); },
	render: function(st) {
		var self = this;
		M.injectCss();
		this.root = E('div', { 'class': 'mud' });
		this.paint(st);
		poll.add(function() { return M.callSimGet().then(function(s) { self.paint(s); }); }, 3);
		return this.root;
	},
	set: function(op, value) {
		var self = this;
		return M.callSimSet(op, String(value)).then(function(r) {
			if (!r || r.ok !== 1) M.toast(M.errText(r), { type: 'error', timeout: 6000 });
			else if (r.started) M.toast(_('Switching SIM. Mobile data will disconnect briefly.'));
			return M.callSimGet().then(function(s) { self.paint(s); });
		});
	},
	paint: function(st) {
		var self = this;
		var results = {
			failed: _('SIM switch failed; check SIM readiness and hot switching.'),
			idle: _('Ready'), switching: _('Switching SIM'), switched: _('SIM switched; saved as boot default'),
			rolled_back: _('Switch failed; previous SIM restored'),
			reboot_required: _('Radio state unknown; reboot required')
		};
		var card = E('section', { 'class': 'mud-card' }, [
			E('h3', {}, [ _('Dual SIM') ]),
			E('p', {}, [ _('A successful switch also saves that SIM as the next cold-boot default. A SIM without service can switch successfully but cannot provide internet.') ]),
			E('p', {}, [ _('Active SIM') + ': ' + (st.active ? 'SIM' + st.active : _('Unknown')) ]),
			E('p', {}, [ _('Cold-boot default') + ': ' + (st.default ? 'SIM' + st.default : _('Unknown')) ]),
			E('p', {}, [ results[st.result] || _('SIM control unavailable') ])
		]);
		var hot = E('input', { 'type': 'checkbox', 'checked': st.hot ? '' : null, 'disabled': st.busy ? '' : null });
		hot.addEventListener('change', function() { self.set('hot', hot.checked ? 1 : 0); });
		card.appendChild(E('label', {}, [ hot, ' ', _('Enable hot switching') ]));
		if (!st.available)
			card.appendChild(E('p', {}, [ _('Reboot after enabling hot switching to prepare both SIM channels.') ]));
		[ 1, 2 ].forEach(function(n) {
			var row = E('div', { 'style': 'display:flex;gap:8px;margin:12px 0' });
			var b = E('button', { 'class': 'mud-btn',
				'disabled': (!st.hot || !st.available || st.busy || !st.active || st.active === n) ? '' : null },
				[ _('Switch to SIM%d').format(n) ]);
			b.addEventListener('click', function() { self.set('switch', n); });
			var d = E('button', { 'class': 'mud-btn', 'disabled': st.busy || st.default === n ? '' : null },
				[ _('Use SIM%d at next boot').format(n) ]);
			d.addEventListener('click', function() { self.set('default', n); });
			row.appendChild(b); row.appendChild(d); card.appendChild(row);
		});
		dom.content(this.root, card);
	},
	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
