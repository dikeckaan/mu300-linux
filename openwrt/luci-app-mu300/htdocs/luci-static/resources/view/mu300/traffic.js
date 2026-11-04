'use strict';
'require view';
'require dom';
'require mu300.common as M';

/* Every value from the backend goes into E() inside an array: LuCI's E() takes a lone string as HTML, an array's
 * strings as text. */
/* Cellular > Data usage: mobile data per day and per billing cycle, the cap and its warning, and a yearly plan of its
 * own, from mu300dash traffic_get/traffic_set (unisoc-modem/traffic, mu300-traffic: the same count as the
 * mu300-traffic command, shared by every system on the Linux disk). What is left of a cap is the page's first number:
 * with a monthly and a yearly cap both set it shows one of them, the more urgent one, behind a [Month | Year] switch,
 * and the other keeps a small line of its own. Sizes are binary (1 GB = 1024 MB), as everywhere on the panel. The daily
 * quota, the count mode (both ways, downloads or uploads only) and the plan's name are kanoqwq's traffic plans. */

var GB = 1073741824;
var DAYS = 31;

/* the caps' levels, the worse first: over > warn > ok/none. The page opens on the cap closer to its limit */
var LEVEL_RANK = { over: 3, warn: 2, ok: 1, none: 0 };

/* the date d (YYYY-MM-DD) moved by n days, in UTC so that no time zone or DST shifts it */
function addDays(d, n) {
	var t = new Date(Date.UTC(+d.substring(0, 4), +d.substring(5, 7) - 1, +d.substring(8, 10)) + n * 86400000);
	return t.toISOString().substring(0, 10);
}

/* a size in GB as the user types it (comma or point), as whole bytes; null when it is not one */
function gbBytes(text) {
	var v = String(text).trim().replace(',', '.');
	if (!/^[0-9]+(\.[0-9]+)?$/.test(v) || +v > 1000000) return null;
	return String(Math.round(+v * GB));
}

return view.extend({
	load: function() { return L.resolveDefault(M.callTrafficGet(), {}); },

	render: function(st) {
		M.injectCss();
		this.root = E('div', { 'class': 'mud' });
		this.paint(st || {});
		var self = this;
		/* a minute is the service's own pace; the page follows it */
		this._timer = setTimeout(function again() {
			if (!document.documentElement.contains(self.root)) return;
			self.reload().finally(function() { self._timer = setTimeout(again, 30000); });
		}, 30000);
		return this.root;
	},

	unload: function() { clearTimeout(this._timer); },

	/* nothing here goes through LuCI's Save & Apply */
	handleSaveApply: null, handleSave: null, handleReset: null,

	reload: function() {
		var self = this;
		return L.resolveDefault(M.callTrafficGet(), {}).then(function(st) { self.paint(st || {}); return st; });
	},

	/* run a traffic_set and show its result */
	set: function(btn, op, value, done) {
		var self = this;
		M.busy(btn, true);
		return L.resolveDefault(M.callTrafficSet(op, String(value)), null).then(function(r) {
			M.busy(btn, false);
			if (!r || r.ok !== 1) {
				M.toast(r ? _('Failed: %s').format(M.errText(r)) : _('Management connection lost'), { type: 'error', timeout: 6000 });
				return;
			}
			M.toast(_('Saved'), { type: 'success' });
			if (done) done();
			return self.reload();
		});
	},

	row: function(k, v, id) {
		return E('div', { 'class': 'mud-r' }, [ E('span', { 'class': 'mud-k' }, [ k ]),
			E('span', { 'class': 'mud-v', 'id': id || null }, [ v ]) ]);
	},

	paint: function(st) {
		this._st = st;
		if (st.ok === 0 || !st.cycle) {
			dom.content(this.root, E('section', { 'class': 'mud-card', 'id': 'mud-traffic' }, [
				E('h3', {}, _('Data usage')),
				E('div', { 'class': 'mud-note', 'id': 'mud-traffic-error' }, [ st.error ? M.errText(st) : _('The data usage could not be read') ])
			]));
			return;
		}
		/* the switch's pick wins; otherwise the more urgent period is the one shown */
		this.period = this.picked || this.auto(st) || 'month';
		dom.content(this.root, [ this.summary(st), this.days(st), this.cycles(st), this.settings(st) ]);
	},

	/* the period the page opens on: the cap that is closer to its limit (over > warn > ok); a tie goes to the year,
	 * the longer commitment. null when no cap is set. */
	auto: function(st) {
		var cap = st.cap || {}, capB = cap.bytes > 0 ? cap.bytes : 0;
		var y = st.yearly, yB = y && y.bytes > 0 ? y.bytes : 0;
		if (!capB) return yB ? 'year' : null;
		if (!yB) return 'month';
		return (LEVEL_RANK[cap.level] || 0) > (LEVEL_RANK[y.level] || 0) ? 'month' : 'year';
	},

	/* the [Month | Year] switch: a pick stays until the page is left (a repaint keeps it) */
	pick: function(period) {
		this.picked = period;
		if (this._st) this.paint(this._st);
	},

	summary: function(st) {
		var self = this;
		var c = st.cycle, cap = st.cap || {}, today = st.today || {}, pend = st.pending || {}, daily = st.daily || {};
		/* an older mu300-traffic writes no remaining and no yearly object: the rest of the cycle falls back to cap -
		 * used, and the yearly plan stays out of the page */
		var capB = cap.bytes > 0 ? cap.bytes : 0;
		var left = Math.max(0, cap.remaining != null ? cap.remaining : capB - c.used);
		var y = st.yearly, yB = y && y.bytes > 0 ? y.bytes : 0;
		var yleft = yB ? Math.max(0, y.remaining != null ? y.remaining : yB - y.used) : 0;
		var mpct = capB ? Math.min(100, Math.round(c.used * 100 / capB)) : 0;
		var ypct = yB ? Math.min(100, Math.round(y.used * 100 / yB)) : 0;
		var col = cap.level === 'over' ? 'var(--danger,#E25555)' : cap.level === 'warn' ? 'var(--warning,#f59e0b)' :
			'var(--brand,var(--primary,#3b82f6))';
		var ycol = y && y.level === 'over' ? 'var(--danger,#E25555)' : y && y.level === 'warn' ? 'var(--warning,#f59e0b)' :
			'var(--brand,var(--primary,#3b82f6))';
		/* one period at a time: the numbers beside today are the shown period's; the other cap keeps only one small line
		 * and its own warn/over note, so nothing urgent is hidden by the switch */
		var year = this.period === 'year' && yB > 0;
		var used = year ? y.used : c.used, sel = year ? yB : capB;
		var slev = year ? y.level : cap.level, scol = year ? ycol : col;
		var spct = year ? ypct : mpct;
		var dates = year ? (y.start && y.last ? y.start + ' – ' + y.last : '') :
			(c.start && c.last ? c.start + ' – ' + c.last : '');
		var days = year ? y.days_left : c.days_left;
		var pick = function(period, on) {
			var b = E('button', { 'class': 'mud-btn' + (on ? ' on' : ''), 'id': 'mud-traffic-' + period,
				'style': 'padding:2px 10px;font-size:.72rem' }, period === 'year' ? _('Year') : _('Month'));
			b.addEventListener('click', function() { self.pick(period); });
			return b;
		};
		var kpis = E('div', { 'class': 'mud-kpis' }, [
			E('div', { 'class': 'mud-kpi' }, [ E('b', { 'id': 'mud-traffic-today' }, [ M.fmtBytes(today.rx + today.tx) ]),
				E('span', {}, [ _('Today') + ' · ↓ ' + M.fmtBytes(today.rx) + ' ↑ ' + M.fmtBytes(today.tx) ]) ]),
			/* what is left of the shown period, the page's first number; no cap, no number */
			(capB || yB) ? E('div', { 'class': 'mud-kpi' }, [
				E('b', { 'id': 'mud-traffic-remaining', 'style': slev === 'ok' || slev === 'none' ? '' : 'color:' + scol },
					[ M.fmtBytes(year ? yleft : left) ]),
				E('span', {}, [ year ? _('Remaining this year') : _('Remaining this cycle') ]),
				(capB && yB) ? E('div', { 'style': 'display:flex;gap:4px;margin-top:5px' },
					[ pick('month', !year), pick('year', year) ]) : '' ]) : '',
			E('div', { 'class': 'mud-kpi' }, [
				E('b', { 'id': 'mud-traffic-used', 'style': slev === 'ok' || slev === 'none' ? '' : 'color:' + scol },
					[ sel ? _('%s of %s').format(M.fmtBytes(used), M.fmtBytes(sel)) : M.fmtBytes(used) ]),
				E('span', {}, [ _('Used') + (dates ? ' · ' + dates : '') ]),
				sel ? E('div', { 'class': 'mud-meter' }, [ E('i', { 'style': 'width:' + spct + '%;background:' + scol }) ]) : '' ])
		]);
		var other = [];
		if (capB && yB) {
			var o = year ? { label: _('Remaining this cycle'), left: left, used: c.used, cap: capB } :
				{ label: _('Remaining this year'), left: yleft, used: y.used, cap: yB };
			var opct = o.cap ? +(o.used * 100 / o.cap).toFixed(1) : 0;
			other.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-other' }, [
				o.label + ' ' + M.fmtBytes(o.left) + ' · ' + _('Used') + ' ' + opct + '%' ]));
		}
		var rows = [];
		if (days != null)
			rows.push(this.row(year ? _('Days left this year') : _('Days left in this cycle'), String(days), 'mud-traffic-left'));
		rows.push(this.row(_('Received'), M.fmtBytes(c.rx)));
		rows.push(this.row(_('Sent'), M.fmtBytes(c.tx)));
		if (c.adj) rows.push(this.row(_('Corrected by'), (c.adj < 0 ? '−' : '+') + M.fmtBytes(Math.abs(c.adj))));
		rows.push(this.row(_('Monthly cap'), capB ? _('%s, warning at %d%%').format(M.fmtBytes(capB), cap.warn) : _('None'), 'mud-traffic-cap'));
		if (y) rows.push(this.row(_('Yearly cap'), yB ? _('%s, warning at %d%%').format(M.fmtBytes(yB), cap.warn) : _('None'),
			'mud-traffic-yearly-cap'));
		if (daily.bytes > 0)
			rows.push(this.row(_('Daily quota'), _('%s of %s').format(M.fmtBytes(daily.used), M.fmtBytes(daily.bytes)), 'mud-traffic-daily'));
		var notes = [];
		if (cap.level === 'over')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-alert', 'style': 'color:' + col }, [
				cap.cut_active ? _('The monthly cap is reached: mobile data was turned off. It comes back on when the next cycle starts.')
					: _('The monthly cap is reached') ]));
		else if (cap.level === 'warn')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-alert', 'style': 'color:' + col }, [
				_('%d%% of the monthly cap is used').format(mpct) ]));
		if (yB && y.level === 'over')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-yalert', 'style': 'color:' + ycol }, [
				y.cut_active ? _('The yearly cap is reached: mobile data was turned off. It comes back on when the next year starts.')
					: _('The yearly cap is reached') ]));
		else if (yB && y.level === 'warn')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-yalert', 'style': 'color:' + ycol }, [
				_('%d%% of the yearly cap is used').format(ypct) ]));
		var dcol = daily.level === 'over' ? 'var(--danger,#E25555)' : 'var(--warning,#f59e0b)';
		if (daily.level === 'over')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-dalert', 'style': 'color:' + dcol }, [
				daily.cut_active ? _('The daily quota is reached: mobile data was turned off. It comes back on at midnight.')
					: _('The daily quota is reached') ]));
		else if (daily.level === 'warn')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-dalert', 'style': 'color:' + dcol }, [
				_('%d%% of the daily quota is used').format(Math.min(100, Math.round(daily.used * 100 / daily.bytes))) ]));
		if (st.count === 'rx' || st.count === 'tx')
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-count' }, [ st.count === 'rx' ?
				_('The cap and the daily quota count downloads only.') : _('The cap and the daily quota count uploads only.') ]));
		if (pend.rx + pend.tx > 0)
			notes.push(E('div', { 'class': 'mud-note', 'id': 'mud-traffic-pending' }, [
				_('%s waits for the clock: it has not been set over the network yet. It already counts towards this cycle and goes to its day once the clock is set.').format(M.fmtBytes(pend.rx + pend.tx)) ]));
		if (!st.available)
			notes.push(E('div', { 'class': 'mud-note' }, [ _('The interface %s is not there right now: nothing is counted until it comes back.').format(st.device) ]));
		notes.push(E('div', { 'class': 'mud-note' }, [
			_('Counted on %s, both ways, as the operator counts it (a VPN\'s overhead included).').format(st.device) + ' ' +
			_('The count is kept in memory and written to the disk every 30 minutes and at shutdown: a power cut loses at most the last half hour.') +
			(st.since ? ' ' + _('Counting since %s.').format(new Date(st.since * 1000).toISOString().substring(0, 10)) : '') ]));
		return E('section', { 'class': 'mud-card', 'id': 'mud-traffic' }, [
			E('h3', {}, [ _('Data usage') + (st.plan ? ' · ' + st.plan : '') ]), kpis ].concat(other, rows, notes));
	},

	/* the last DAYS days to today (none before counting started), a day without traffic as zero, each with a bar of
	 * its share of the busiest */
	days: function(st) {
		var by = {}, list = [], peak = 1, first = null;
		(st.days || []).forEach(function(d) { by[d.date] = d; if (!first || d.date < first) first = d.date; });
		if (st.since) {
			var s = new Date((st.since + 0) * 1000).toISOString().substring(0, 10);
			if (!first || s < first) first = s;
		}
		for (var i = 0; i < DAYS; i++) {
			var date = addDays(st.today.date, -i), d = by[date] || { rx: 0, tx: 0 };
			if (i > 0 && (!first || date < first)) break;
			list.push({ date: date, rx: d.rx, tx: d.tx });
			peak = Math.max(peak, d.rx + d.tx);
		}
		var body = list.map(function(d) {
			var w = Math.round((d.rx + d.tx) * 100 / peak);
			return E('tr', {}, [ E('td', {}, [ d.date ]),
				E('td', { 'style': 'width:35%;min-width:40px' }, [ E('div', { 'class': 'mud-meter', 'style': 'margin:0' },
					[ E('i', { 'style': 'width:' + w + '%;background:var(--brand,var(--primary,#3b82f6))' }) ]) ]),
				E('td', {}, [ M.fmtBytes(d.rx) ]), E('td', {}, [ M.fmtBytes(d.tx) ]), E('td', {}, [ M.fmtBytes(d.rx + d.tx) ]) ]);
		});
		return E('section', { 'class': 'mud-card', 'style': 'margin-top:10px' }, [ E('h3', {}, _('Per day')),
			E('div', { 'class': 'mud-scroll', 'style': 'max-height:340px' }, [ E('table', { 'class': 'mud-table', 'id': 'mud-traffic-days', 'style': 'white-space:nowrap' }, [
				E('thead', {}, [ E('tr', {}, [ E('th', {}, _('Date')), E('th', {}, ''), E('th', {}, _('Received')),
					E('th', {}, _('Sent')), E('th', {}, _('Total')) ]) ]),
				E('tbody', {}, body) ]) ]) ]);
	},

	cycles: function(st) {
		/* the last column: what the cap counts (both ways, or one way with count rx/tx), the correction included */
		var body = (st.cycles || []).map(function(c) {
			var u = c.used != null ? c.used : c.rx + c.tx + (c.adj || 0);
			return E('tr', {}, [ E('td', {}, [ c.start + ' – ' + c.last ]), E('td', {}, [ M.fmtBytes(c.rx) ]),
				E('td', {}, [ M.fmtBytes(c.tx) ]), E('td', {}, [ M.fmtBytes(Math.max(0, u)) ]) ]);
		});
		var oneWay = st.count === 'rx' || st.count === 'tx';
		return E('section', { 'class': 'mud-card', 'style': 'margin-top:10px' }, [ E('h3', {}, _('Per billing cycle')),
			E('table', { 'class': 'mud-table', 'id': 'mud-traffic-cycles', 'style': 'white-space:nowrap' }, [
				E('thead', {}, [ E('tr', {}, [ E('th', {}, _('Billing cycle')), E('th', {}, _('Received')),
					E('th', {}, _('Sent')), E('th', {}, oneWay ? _('Counted') : _('Total')) ]) ]),
				E('tbody', {}, body) ]) ]);
	},

	settings: function(st) {
		var self = this, cap = st.cap || {}, daily = st.daily || {}, y = st.yearly || null;
		var field = function(label, input, btn, note) {
			return E('div', { 'style': 'margin:8px 0' }, [
				E('div', { 'style': 'display:flex;gap:8px;flex-wrap:wrap;align-items:center' },
					[ E('span', { 'class': 'mud-k', 'style': 'flex:1 1 220px' }, [ label ]), input, btn ]),
				note ? E('div', { 'class': 'mud-note', 'style': 'margin-top:3px' }, [ note ]) : '' ]);
		};
		var input = function(id, value, width) {
			return E('input', { 'type': 'text', 'inputmode': 'decimal', 'class': 'cbi-input-text', 'id': id,
				'style': 'width:' + (width || '7em'), 'value': value });
		};

		var day = E('select', { 'class': 'cbi-input-select', 'id': 'mud-traffic-reset' });
		for (var d = 1; d <= 31; d++)
			day.appendChild(E('option', { 'value': String(d), 'selected': d === st.reset_day ? '' : null }, [ String(d) ]));
		var dayBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
		dayBtn.addEventListener('click', function() { self.set(dayBtn, 'reset_day', day.value); });

		var capIn = input('mud-traffic-capin', cap.bytes > 0 ? String(+(cap.bytes / GB).toFixed(2)) : '0');
		var capBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
		capBtn.addEventListener('click', function() {
			var b = gbBytes(capIn.value);
			if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
			self.set(capBtn, 'cap', b);
		});

		var warnIn = input('mud-traffic-warn', String(cap.warn || 90), '5em');
		var warnBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
		warnBtn.addEventListener('click', function() {
			var v = String(warnIn.value).trim();
			if (!/^[1-9][0-9]?$|^100$/.test(v)) { M.toast(_('Enter a percentage from 1 to 100'), { type: 'error' }); return; }
			self.set(warnBtn, 'warn', v);
		});

		var cutBtn = E('button', { 'class': 'mud-btn' + (cap.cut ? ' on' : ''), 'id': 'mud-traffic-cut' },
			cap.cut ? _('On') : _('Off'));
		cutBtn.addEventListener('click', function() {
			if (cap.cut) { self.set(cutBtn, 'cut', 'off'); return; }
			M.confirmBox(_('Turn mobile data off at the cap'),
				_('When this cycle reaches the cap, mobile data is turned off: no internet through the operator until the next cycle starts, the cap is raised or this is turned off again. Turning mobile data back on by hand keeps it on until the next reboot.'),
				{ danger: true, okText: _('On') }).then(function(go) { if (go) self.set(cutBtn, 'cut', 'on'); });
		});

		var dailyIn = input('mud-traffic-dailyin', daily.bytes > 0 ? String(+(daily.bytes / GB).toFixed(2)) : '0');
		var dailyBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
		dailyBtn.addEventListener('click', function() {
			var b = gbBytes(dailyIn.value);
			if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
			self.set(dailyBtn, 'daily', b);
		});

		var dcutBtn = E('button', { 'class': 'mud-btn' + (daily.cut ? ' on' : ''), 'id': 'mud-traffic-dcut' },
			daily.cut ? _('On') : _('Off'));
		dcutBtn.addEventListener('click', function() {
			if (daily.cut) { self.set(dcutBtn, 'daily_cut', 'off'); return; }
			M.confirmBox(_('Turn mobile data off at the daily quota'),
				_('When today reaches the daily quota, mobile data is turned off until midnight, the quota is raised or this is turned off again. Turning mobile data back on by hand keeps it on until the next reboot.'),
				{ danger: true, okText: _('On') }).then(function(go) { if (go) self.set(dcutBtn, 'daily_cut', 'on'); });
		});

		/* the yearly plan; an older mu300-traffic (no yearly object) has neither its settings nor its operations, so
		 * none of it is offered */
		var yearlyIn, yearlyBtn, ystartIn, ystartBtn, ycutBtn, yusedIn, yusedBtn, leftIn, leftBtn, yleftIn, yleftBtn;
		var leftNote;
		if (y) {
			leftNote = _('What the operator shows as left is used: the count is corrected to the cap minus it.');
			yearlyIn = input('mud-traffic-yearlyin', y.bytes > 0 ? String(+(y.bytes / GB).toFixed(2)) : '0');
			yearlyBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
			yearlyBtn.addEventListener('click', function() {
				var b = gbBytes(yearlyIn.value);
				if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
				self.set(yearlyBtn, 'yearly', b);
			});

			ystartIn = E('input', { 'type': 'text', 'class': 'cbi-input-text', 'id': 'mud-traffic-yearlystart',
				'style': 'width:6em', 'value': y.start_day || '01-01' });
			ystartBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
			ystartBtn.addEventListener('click', function() {
				self.set(ystartBtn, 'yearly_start', String(ystartIn.value).trim());
			});

			ycutBtn = E('button', { 'class': 'mud-btn' + (y.cut ? ' on' : ''), 'id': 'mud-traffic-ycut' },
				y.cut ? _('On') : _('Off'));
			ycutBtn.addEventListener('click', function() {
				if (y.cut) { self.set(ycutBtn, 'yearly_cut', 'off'); return; }
				M.confirmBox(_('Turn mobile data off at the yearly cap'),
					_('When this year reaches the yearly cap, mobile data is turned off: no internet through the operator until the next year starts, the yearly cap is raised or this is turned off again. Turning mobile data back on by hand keeps it on until the next reboot.'),
					{ danger: true, okText: _('On') }).then(function(go) { if (go) self.set(ycutBtn, 'yearly_cut', 'on'); });
			});
		}

		var count = E('select', { 'class': 'cbi-input-select', 'id': 'mud-traffic-count' });
		[ [ 'total', _('Both ways') ], [ 'rx', _('Downloads only') ], [ 'tx', _('Uploads only') ] ].forEach(function(o) {
			count.appendChild(E('option', { 'value': o[0], 'selected': (st.count || 'total') === o[0] ? '' : null }, [ o[1] ]));
		});
		var countBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
		countBtn.addEventListener('click', function() { self.set(countBtn, 'count', count.value); });

		var planIn = E('input', { 'type': 'text', 'class': 'cbi-input-text', 'id': 'mud-traffic-plan', 'maxlength': '32',
			'style': 'width:14em', 'value': st.plan || '' });
		var planBtn = E('button', { 'class': 'mud-btn' }, _('Save'));
		planBtn.addEventListener('click', function() { self.set(planBtn, 'plan', String(planIn.value).trim()); });

		var usedIn = input('mud-traffic-usedin', '');
		var usedBtn = E('button', { 'class': 'mud-btn' }, _('Set'));
		usedBtn.addEventListener('click', function() {
			var b = gbBytes(usedIn.value);
			if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
			self.set(usedBtn, 'used', b, function() { usedIn.value = ''; });
		});

		/* the corrections by what is used this year or seems left, which only the new mu300-traffic takes */
		if (y) {
			yusedIn = input('mud-traffic-yearlyusedin', '');
			yusedBtn = E('button', { 'class': 'mud-btn' }, _('Set'));
			yusedBtn.addEventListener('click', function() {
				var b = gbBytes(yusedIn.value);
				if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
				self.set(yusedBtn, 'yearly_used', b, function() { yusedIn.value = ''; });
			});

			leftIn = input('mud-traffic-usedremainingin', '');
			leftBtn = E('button', { 'class': 'mud-btn' }, _('Set'));
			leftBtn.addEventListener('click', function() {
				var b = gbBytes(leftIn.value);
				if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
				self.set(leftBtn, 'used_remaining', b, function() { leftIn.value = ''; });
			});

			yleftIn = input('mud-traffic-yearlyusedremainingin', '');
			yleftBtn = E('button', { 'class': 'mud-btn' }, _('Set'));
			yleftBtn.addEventListener('click', function() {
				var b = gbBytes(yleftIn.value);
				if (b == null) { M.toast(_('Enter a size in GB, for example 50 or 2.5'), { type: 'error' }); return; }
				self.set(yleftBtn, 'yearly_used_remaining', b, function() { yleftIn.value = ''; });
			});
		}

		var clearBtn = E('button', { 'class': 'mud-btn warn', 'id': 'mud-traffic-clear' }, _('Clear'));
		clearBtn.addEventListener('click', function() {
			M.confirmBox(_('Clear the count'), _('Every day and billing cycle counted so far is forgotten. Counting goes on from now.'),
				{ danger: true, okText: _('Clear') }).then(function(go) { if (go) self.set(clearBtn, 'clear', 'yes'); });
		});

		var fields = [
			field(_('A billing cycle starts on day'), day, dayBtn, _('31: on the last day of each month')),
			field(_('Monthly cap (GB, 0: none)'), capIn, capBtn),
			field(_('Warning at this percentage of the cap and the yearly cap'), warnIn, warnBtn),
			field(_('Turn mobile data off at the cap'), cutBtn, ''),
			field(_('Daily quota (GB, 0: none)'), dailyIn, dailyBtn),
			field(_('Turn mobile data off at the daily quota'), dcutBtn, '')
		];
		if (y) fields.push(
			field(_('Yearly cap (GB, 0: none)'), yearlyIn, yearlyBtn),
			field(_('A billing year starts on (MM-DD)'), ystartIn, ystartBtn,
				_('For example 01-01; 02-29 is 02-28 in a common year.')),
			field(_('Turn mobile data off at the yearly cap'), ycutBtn, ''));
		fields.push(
			field(_('The cap and the daily quota count'), count, countBtn),
			field(_('Plan name'), planIn, planBtn),
			field(_('Used so far in this cycle (GB)'), usedIn, usedBtn,
				_('What the operator shows for this cycle (for example when counting started in the middle of it); the count is corrected to it.')));
		if (y) fields.push(
			field(_('Used so far this year (GB)'), yusedIn, yusedBtn),
			field(_('Left in this cycle as the operator shows it (GB)'), leftIn, leftBtn, leftNote),
			field(_('Left this year as the operator shows it (GB)'), yleftIn, yleftBtn, leftNote));
		fields.push(field(_('Clear the count'), clearBtn, ''));
		return E('section', { 'class': 'mud-card', 'style': 'margin-top:10px', 'id': 'mud-traffic-settings' },
			[ E('h3', {}, _('Billing cycle and cap')) ].concat(fields));
	}
});
