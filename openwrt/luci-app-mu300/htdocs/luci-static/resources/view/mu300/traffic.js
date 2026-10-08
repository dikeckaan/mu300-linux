'use strict';
'require view';
'require poll';
'require mu300.common as M';

function formatUsage(n) { return M.fmtTrafficBytes(n); }
var ERRORS = { invalid_config: _('Invalid configuration'), traffic_unavailable: _('The traffic accounting service is unavailable'),
	storage_failed: _('The traffic totals could not be saved'), clock_unsynced: _('The system clock is not synchronised yet') };

return view.extend({
	load: function() { return L.resolveDefault(M.callTrafficGet(), {}); },
	render: function(data) {
		M.injectCss();
		var root = document.createElement('div'); root.className = 'mud';
		root.innerHTML = `
<style>
.mud-tr-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}
.mud-tr-summary .mud-card{min-width:0}.mud-tr-summary b{display:block;font-size:1.3rem;overflow-wrap:anywhere;margin:7px 0}
.mud-tr-label{font-size:.8rem;color:var(--text-muted,#777)}.mud-tr-sub{font-size:.75rem;color:var(--text-subtle,var(--text-muted,#777));overflow-wrap:anywhere}
.mud-tr-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px}.mud-tr-grid>.mud-card{min-width:0}
.mud-tr-field{display:flex;flex-direction:column;gap:6px;margin:12px 0;min-width:0}
.mud-tr-field label{font-size:.8rem;overflow-wrap:anywhere}
.mud .mud-tr-field input,.mud .mud-tr-field select{box-sizing:border-box;width:100%;min-width:0;max-width:100%;margin:0;padding:8px 10px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font:inherit}
.mud-tr-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 12px}
.mud-tr-line{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:10px 0}.mud-tr-line>span{overflow-wrap:anywhere}
.mud-tr-warn{color:var(--warning,#b76d00)}.mud-tr-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.mud-tr-scroll{overflow-x:auto}.mud-tr-table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:.8rem}
.mud-tr-table th,.mud-tr-table td{padding:8px 4px;text-align:right;overflow-wrap:anywhere;border-bottom:1px solid var(--hairline,var(--border,#ddd))}.mud-tr-table th:first-child,.mud-tr-table td:first-child{text-align:left;width:30%}
@media(max-width:1000px){.mud-tr-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.mud-tr-grid{grid-template-columns:minmax(0,1fr)}}
@media(max-width:480px){.mud-tr-form{grid-template-columns:minmax(0,1fr)}.mud-tr-summary b{font-size:1.1rem}}
</style>
<div class="mud-tr-summary">
 <section class="mud-card"><span class="mud-tr-label">${_('Today')}</span><b id="mud-tr-today">--</b><span class="mud-tr-sub" id="mud-tr-today-detail"></span></section>
 <section class="mud-card"><span class="mud-tr-label">${_('This month')}</span><b id="mud-tr-month">--</b><span class="mud-tr-sub">${_('Calendar month')}</span></section>
 <section class="mud-card"><span class="mud-tr-label">${_('Used this cycle')}</span><b id="mud-tr-cycle">--</b><span class="mud-tr-sub" id="mud-tr-cycle-date"></span></section>
 <section class="mud-card"><span class="mud-tr-label">${_('Plan remaining')}</span><b id="mud-tr-remaining">--</b><span class="mud-tr-sub" id="mud-tr-plan-name"></span></section>
</div>
<section class="mud-card">
 <div class="mud-tr-line"><span id="mud-tr-quota"></span><span id="mud-tr-reset"></span></div>
 <div class="mud-meter"><i id="mud-tr-meter" style="width:0;background:var(--brand,#2f7bf6)"></i></div>
 <div class="mud-tr-line mud-tr-sub"><span id="mud-tr-daily"></span><span id="mud-tr-updated"></span></div>
 <div class="mud-tr-warn" id="mud-tr-warning"></div>
</section>
<div class="mud-tr-grid">
 <section class="mud-card">
  <h3>${_('Plan and traffic pool')}</h3>
  <div class="mud-tr-field"><label for="mud-tr-plan_name">${_('Plan name')}</label><input id="mud-tr-plan_name" maxlength="128"></div>
  <div class="mud-tr-form">
   <div class="mud-tr-field"><label for="mud-tr-monthly_gb">${_('Quota per cycle (GB)')}</label><input id="mud-tr-monthly_gb" type="number" min="0" max="100000" step="0.001"></div>
   <div class="mud-tr-field"><label for="mud-tr-daily_gb">${_('Daily reference quota (GB)')}</label><input id="mud-tr-daily_gb" type="number" min="0" max="100000" step="0.001"></div>
   <div class="mud-tr-field"><label for="mud-tr-reset_day">${_('Monthly reset day (1–31)')}</label><input id="mud-tr-reset_day" type="number" min="1" max="31" step="1"></div>
   <div class="mud-tr-field"><label for="mud-tr-count_mode">${_('Plan counting mode')}</label><select id="mud-tr-count_mode"><option value="total">${_('Uplink + downlink')}</option><option value="rx">${_('Downlink only')}</option><option value="tx">${_('Uplink only')}</option></select></div>
  </div>
  <div class="mud-note">${_('A quota of 0 means unlimited; 1 GB = 1000 MB. The reset day takes effect at local midnight, and short months use their last day.')}</div>
  <div class="mud-tr-field"><label for="mud-tr-device">${_('Interface to account')}</label><input id="mud-tr-device" placeholder="${_('Use the cellular WAN interface automatically')}" maxlength="15"></div>
  <div class="mud-tr-field"><label for="mud-tr-used_gb">${_('Calibrate used this cycle (GB, optional)')}</label><input id="mud-tr-used_gb" type="number" min="0" max="100000" step="0.001" placeholder="${_('Leave blank to keep the current total')}"></div>
  <div class="mud-note">${_('Calibration only adjusts the current plan cycle; the daily and calendar-month histories are unchanged, and the next cycle counts real traffic again.')}</div>
  <div class="mud-tr-actions"><button class="mud-btn on" id="mud-tr-save">${_('Save settings')}</button><button class="mud-btn" id="mud-tr-refresh">${_('Refresh status')}</button></div>
 </section>
 <section class="mud-card">
  <h3>${_('Recent daily usage')}</h3>
  <div class="mud-tr-scroll"><table class="mud-tr-table"><thead><tr><th>${_('Date')}</th><th>${_('Down')}</th><th>${_('Up')}</th><th>${_('Total')}</th></tr></thead><tbody id="mud-tr-days"></tbody></table></div>
 </section>
</div>
<section class="mud-card" style="margin-top:14px">
 <h3>${_('Monthly usage history')}</h3>
 <div class="mud-tr-scroll"><table class="mud-tr-table"><thead><tr><th>${_('Month')}</th><th>${_('Down')}</th><th>${_('Up')}</th><th>${_('Total')}</th></tr></thead><tbody id="mud-tr-months"></tbody></table></div>
 <div class="mud-note" style="margin-top:12px">${_('Recording starts when accounting is enabled; it updates about every 10 seconds and saves every 60. A sudden power loss can lose the most recent unsaved records.')}</div>
 <div class="mud-note">${_('The local interface totals are for reference; the carrier’s billing is authoritative. The quota is for display and alerts only and never disconnects the link.')}</div>
</section>`;
		this.root = root; this.data = data || {};
		this.fill(this.data.config || {}); this.paint(); this.wire();
		var self = this; poll.add(function() { return self.refresh(); }, 10);
		return root;
	},
	q: function(k) { return this.root.querySelector('#mud-tr-' + k); },
	fill: function(c) {
		var self = this;
		['plan_name','device'].forEach(function(k) { self.q(k).value = c[k] || ''; });
		['monthly_gb','daily_gb'].forEach(function(k) { self.q(k).value = c[k] || 0; });
		this.q('reset_day').value = c.reset_day || 1; this.q('count_mode').value = c.count_mode || 'total';
		this.q('used_gb').value = '';
	},
	paint: function() {
		var d = this.data, s = d.status || {}, c = d.config || {}, self = this;
		this.q('today').textContent = formatUsage(s.today_used); this.q('month').textContent = formatUsage(s.month_used);
		this.q('cycle').textContent = formatUsage(s.cycle_used);
		this.q('remaining').textContent = s.remaining == null ? _('Unlimited') : formatUsage(s.remaining);
		this.q('today-detail').textContent = _('Down') + ' ' + formatUsage(s.today && s.today.rx) + ' / ' + _('Up') + ' ' + formatUsage(s.today && s.today.tx);
		this.q('cycle-date').textContent = s.cycle_start || '--';
		this.q('plan-name').textContent = c.plan_name || _('No plan name set');
		this.q('quota').textContent = _('Quota per cycle: ') + (s.monthly_limit ? formatUsage(s.monthly_limit) : _('Unlimited'));
		this.q('reset').textContent = _('Next reset: ') + (s.cycle_end || '--');
		this.q('daily').textContent = _('Daily reference quota: ') + (s.daily_limit ? formatUsage(s.daily_limit) : _('Unlimited'));
		this.q('updated').textContent = (s.device || '--') + ' · ' + _('Updated: ') + (s.updated_at ? new Date(s.updated_at * 1000).toLocaleTimeString() : '--');
		this.q('meter').style.width = (s.monthly_limit ? Math.min(100, 100 * s.cycle_used / s.monthly_limit) : 0) + '%';
		this.q('meter').style.background = s.over_limit ? 'var(--danger,#d45)' : 'var(--brand,#2f7bf6)';
		var warnings = [];
		if (!d.status) warnings.push(_('The traffic accounting service is unavailable'));
		else {
			if (!s.available) warnings.push(_('The accounting interface is unavailable'));
			if (!s.clock_ok) warnings.push(_('The system clock is not synchronised yet'));
			if (s.storage_error) warnings.push(_('The traffic totals could not be saved'));
			if (s.over_limit) warnings.push(_('The plan quota is reached'));
			if (s.daily_over_limit) warnings.push(_('The daily reference quota is reached'));
		}
		this.q('warning').textContent = warnings.join(' · ');
		['days','months'].forEach(function(k) {
			self.q(k).innerHTML = (d[k] || []).map(function(row) {
				return '<tr><td>' + M.esc(row.date) + '</td><td>' + formatUsage(row.rx) + '</td><td>' + formatUsage(row.tx) + '</td><td>' + formatUsage(row.rx + row.tx) + '</td></tr>';
			}).join('') || '<tr><td colspan="4">' + M.esc(_('No records yet')) + '</td></tr>';
		});
	},
	refresh: function() {
		var self = this;
		return L.resolveDefault(M.callTrafficGet(), {}).then(function(d) { self.data = d; self.paint(); });
	},
	wire: function() {
		var self = this;
		this.q('refresh').onclick = function() { self.refresh(); };
		this.q('save').onclick = function() {
			var p = { plan_name:self.q('plan_name').value.trim(), device:self.q('device').value.trim(), count_mode:self.q('count_mode').value,
				monthly_gb:Number(self.q('monthly_gb').value), daily_gb:Number(self.q('daily_gb').value), reset_day:Number(self.q('reset_day').value) };
			if (self.q('used_gb').value.trim() !== '') p.used_gb = Number(self.q('used_gb').value);
			if (!Number.isInteger(p.reset_day) || p.reset_day < 1 || p.reset_day > 31 ||
				['monthly_gb','daily_gb','used_gb'].some(function(k) { return p[k] != null && (!Number.isFinite(p[k]) || p[k] < 0 || p[k] > 100000); })) {
				M.toast(_('Invalid configuration'), {type:'error'}); return;
			}
			var confirmed = p.used_gb == null ? Promise.resolve(true) :
				M.confirmBox(_('Calibrate used traffic this cycle?'), _('This sets the current cycle’s used value to the entered amount; the daily and calendar-month records are unchanged.'), {okText:_('Save')});
			confirmed.then(function(yes) {
				if (!yes) return;
				M.busy(self.q('save'), true); var toast = M.toast(_('Saving the traffic pool settings…'), {type:'busy', timeout:0});
				L.resolveDefault(M.callTrafficSet(JSON.stringify(p)), {}).then(function(r) {
					M.busy(self.q('save'), false);
					if (!r.ok) toast.update(ERRORS[r.error] || _('Saving failed'), 'error');
					else { self.q('used_gb').value = ''; toast.update(_('Saved'), 'success'); self.refresh(); }
					setTimeout(function() { toast.close(); }, 3000);
				});
			});
		};
	}
});
