'use strict';
'require view';
'require poll';
'require mu300.common as M';

/* All destinations and rules are private to this authenticated editor. The
 * status poll never includes a URL, phone number, password or SMS body. */
var METHODS = { webhook: _('Webhook'), dingtalk: _('DingTalk bot'), smtp: _('Email (SMTP)'), sms: _('Local SMS'),
	telegram: _('Telegram') };
var RESULTS = {
	idle: _('No delivery yet'), sent: _('Delivered'), disabled: _('Forwarding is off'),
	self_forward_blocked: _('Forwarding to the original sender was blocked'),
	message_too_long: _('The SMS is too long; not sent'), storage_failed: _('The device could not save'),
	source_unavailable: _('The SMS service is unavailable'), power_unavailable: _('The device reports no valid battery state'),
	invalid_config: _('Invalid configuration'), invalid_forward_config: _('Invalid configuration'),
	invalid_destination: _('The destination is invalid'), delivery_failed: _('Delivery failed; check the settings and the device network'),
	smtp_auth_failed: _('The mail server rejected the login; check the authorization code')
};
var ERRORS = {
	invalid_config: _('Invalid configuration'), invalid_forward_config: _('Invalid configuration'),
	invalid_destination: _('The destination is invalid'), forward_storage_failed: _('The device could not save'),
	sms_list_unavailable: _('The SMS service is unavailable'), power_unavailable: _('The device reports no valid battery state')
};
function result(code) { return RESULTS[code] || _('No delivery yet'); }
function lines(value) { return String(value || '').split(/\r?\n/).map(function(s) { return s.trim(); }).filter(Boolean); }
function validPhones(value, max) {
	var a = lines(value), seen = {};
	return a.length <= max && a.every(function(p) {
		var key = p.replace(/^\+/, '');
		if (!/^\+?[0-9]{3,32}$/.test(p) || seen[key]) return false;
		seen[key] = true; return true;
	});
}

return view.extend({
	load: function() { return L.resolveDefault(M.callForwardGet(), {}); },
	render: function(data) {
		M.injectCss();
		var root = document.createElement('div');
		root.className = 'mud';
		root.innerHTML = `
<style>
.mud-fwd-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.mud-fwd-grid>.mud-card,.mud-fwd-channel{min-width:0}
.mud-fwd-field{display:flex;flex-direction:column;min-width:0;gap:6px;margin:12px 0}
.mud-fwd-field>label,.mud-fwd-label{font-size:.79rem;overflow-wrap:anywhere;color:var(--text-muted,var(--text-light,#777))}
.mud .mud-fwd-field input,.mud .mud-fwd-field textarea,.mud .mud-fwd-field select{box-sizing:border-box;width:100%;min-width:0;max-width:100%;min-height:38px;margin:0;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);padding:8px 10px;background:var(--surface,var(--background,#fff));color:var(--text,#222);font:inherit}
.mud-fwd-field textarea{min-height:90px;resize:vertical}
.mud-fwd-toggle{display:flex;align-items:center;gap:9px;margin:10px 0;font-size:.82rem;line-height:1.45;cursor:pointer}
.mud-fwd-toggle input{accent-color:var(--brand,var(--primary,#2f7bf6))}
.mud-fwd-row{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.mud-fwd-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.mud-fwd-state{font-weight:650}.mud-fwd-state.on{color:var(--success,#2fbf71)}
.mud-fwd-channel[hidden],.mud-fwd-error[hidden]{display:none}
.mud-fwd-error{color:var(--danger,#d45);margin-top:10px}
.mud-fwd-pair{display:flex;flex-wrap:wrap;align-items:flex-end;gap:0 12px}
.mud-fwd-pair>.mud-fwd-field{flex:1 1 14rem}
.mud-fwd-pair>.mud-fwd-field:last-child{flex:1 1 10rem}
@media(max-width:760px){.mud-fwd-grid{grid-template-columns:minmax(0,1fr)}.mud-fwd-pair{display:grid;grid-template-columns:minmax(0,1fr)}.mud-fwd-actions .mud-btn{flex:1}}
</style>
<div class="mud-fwd-grid">
 <section class="mud-card">
  <div class="mud-fwd-row"><h3>${_('SMS forwarding')}</h3><span class="mud-fwd-state" id="mud-fwd-state">--</span></div>
  <div class="mud-note" id="mud-fwd-last">${_('No delivery yet')}</div>
  <label class="mud-fwd-toggle"><input type="checkbox" id="mud-fwd-enabled">${_('Enable SMS forwarding')}</label>
  <div class="mud-fwd-field"><label for="mud-fwd-method">${_('Forwarding method')}</label>
   <select id="mud-fwd-method"><option value="webhook">${_('Webhook')}</option><option value="dingtalk">${_('DingTalk bot')}</option><option value="telegram">${_('Telegram')}</option><option value="smtp">${_('Email (SMTP)')}</option><option value="sms">${_('Local SMS')}</option></select></div>
  <div class="mud-fwd-field"><label for="mud-fwd-template_language">${_('Template language')}</label>
   <select id="mud-fwd-template_language"><option value="en">${_('English')}</option><option value="zh">${_('Simplified Chinese')}</option><option value="tr">${_('Turkish')}</option></select></div>
  <div class="mud-note">${_('Saved for the forward titles, hint text and power notifications; the SMS text and the device note are unchanged.')}</div>
  <div class="mud-fwd-channel" data-method="webhook">
   <div class="mud-fwd-field"><label for="mud-fwd-webhook_url">${_('HTTPS URL')}</label><input id="mud-fwd-webhook_url" type="url" autocomplete="off" placeholder="https://example.com/hook"></div>
   <div class="mud-note">${_('Sent as a fixed JSON payload; no custom command is run.')}</div>
  </div>
  <div class="mud-fwd-channel" data-method="dingtalk">
   <div class="mud-fwd-field"><label for="mud-fwd-dingtalk_webhook">${_('Bot webhook URL')}</label><input id="mud-fwd-dingtalk_webhook" type="url" autocomplete="off" placeholder="https://oapi.dingtalk.com/robot/send?..."></div>
   <div class="mud-fwd-field"><label for="mud-fwd-dingtalk_secret">${_('Signing secret · leave blank to keep')}</label><input id="mud-fwd-dingtalk_secret" type="password" autocomplete="new-password"></div>
   <label class="mud-fwd-toggle"><input id="mud-fwd-clear_dingtalk_secret" type="checkbox">${_('Clear the signing secret')}</label>
   <label class="mud-fwd-toggle"><input id="mud-fwd-dingtalk_forward_device_info" type="checkbox">${_('Include device information')}</label>
  </div>
  <div class="mud-fwd-channel" data-method="telegram">
   <div class="mud-fwd-field"><label for="mud-fwd-telegram_token">${_('Bot token · leave blank to keep')}</label><input id="mud-fwd-telegram_token" type="password" autocomplete="new-password"></div>
   <label class="mud-fwd-toggle"><input id="mud-fwd-clear_telegram_token" type="checkbox">${_('Clear the bot token')}</label>
   <div class="mud-fwd-field"><label for="mud-fwd-telegram_chat_id">${_('Target chat ID')}</label><input id="mud-fwd-telegram_chat_id" autocomplete="off" placeholder="-1001234567890"></div>
   <label class="mud-fwd-toggle"><input id="mud-fwd-telegram_forward_device_info" type="checkbox">${_('Include device information')}</label>
   <div class="mud-note">${_('The bot token and default chat come from the nanobot configuration (/root/.nanobot/config.json) unless set here.')}</div>
  </div>
  <div class="mud-fwd-channel" data-method="smtp">
   <div class="mud-fwd-pair">
    <div class="mud-fwd-field"><label for="mud-fwd-smtp_host">${_('SMTP server host')}</label><input id="mud-fwd-smtp_host" autocomplete="off"></div>
    <div class="mud-fwd-field"><label for="mud-fwd-smtp_port">${_('Port · 465 / 587')}</label><select id="mud-fwd-smtp_port"><option value="465">${_('465 TLS')}</option><option value="587">${_('587 STARTTLS')}</option></select></div>
   </div>
   <div class="mud-fwd-field"><label for="mud-fwd-smtp_username">${_('Sender mailbox')}</label><input id="mud-fwd-smtp_username" type="email" autocomplete="off"></div>
   <div class="mud-fwd-field"><label for="mud-fwd-smtp_to">${_('Recipient mailbox')}</label><input id="mud-fwd-smtp_to" type="email" autocomplete="off"></div>
   <div class="mud-fwd-field"><label for="mud-fwd-smtp_password">${_('Authorization code / password · leave blank to keep')}</label><input id="mud-fwd-smtp_password" type="password" autocomplete="new-password"></div>
   <label class="mud-fwd-toggle"><input id="mud-fwd-clear_smtp_password" type="checkbox">${_('Clear the mail settings')}</label>
   <label class="mud-fwd-toggle"><input id="mud-fwd-smtp_forward_device_info" type="checkbox">${_('Include device information')}</label>
   <div class="mud-note">${_('Use the SMTP authorization code from your mail provider; the TLS certificate is always verified.')}</div>
  </div>
  <div class="mud-fwd-channel" data-method="sms">
   <div class="mud-fwd-field"><label for="mud-fwd-sms_to_phone">${_('SMS recipient numbers · one per line, up to 3')}</label><textarea id="mud-fwd-sms_to_phone" placeholder="+8613800000000"></textarea></div>
   <label class="mud-fwd-toggle"><input id="mud-fwd-sms_forward_device_info" type="checkbox">${_('Include device information')}</label>
   <div class="mud-note">${_('Forwarded through the local SIM, which may incur SMS charges; one message is at most 70 UCS-2 units, with no daily limit.')}</div>
  </div>
 </section>
 <section class="mud-card">
  <h3>${_('Power notifications')}</h3>
  <label class="mud-fwd-toggle"><input id="mud-fwd-power_forward_enabled" type="checkbox">${_('Power status notifications')}</label>
  <div class="mud-note" id="mud-fwd-power-note">${_('Notified on a charge-state change, or when the level crosses 5%, 20%, 40%, 60%, 80% or 100%.')}</div>
  <div class="mud-note" id="mud-fwd-power-last"></div>
  <div class="mud-fwd-field"><label for="mud-fwd-nickname">${_('Device note')}</label><input id="mud-fwd-nickname" maxlength="255" autocomplete="off"></div>
  <h3 style="margin-top:22px">${_('Blacklist')}</h3>
  <div class="mud-fwd-field"><label for="mud-fwd-blacklist_phone">${_('Number blacklist · one per line, up to 64')}</label><textarea id="mud-fwd-blacklist_phone"></textarea></div>
  <div class="mud-fwd-field"><label for="mud-fwd-blacklist_keywords">${_('Keyword blacklist · one per line, up to 32')}</label><textarea id="mud-fwd-blacklist_keywords"></textarea></div>
  <div class="mud-note">${_('A matching new SMS is only marked as handled and is not forwarded; clearing a rule does not resend anything. The rules do not affect power notifications.')}</div>
 </section>
</div>
<section class="mud-card" style="margin-top:14px">
 <div class="mud-fwd-row"><h3>${_('Test and status')}</h3></div>
 <div class="mud-note">${_('The device runs it on its own, so it keeps working after the page is closed; only new SMS are forwarded and a failure is not retried automatically.')}</div>
 <div class="mud-fwd-error" id="mud-fwd-error" hidden></div>
 <div class="mud-fwd-actions">
  <button class="mud-btn on" id="mud-fwd-save">${_('Save settings')}</button>
  <button class="mud-btn" id="mud-fwd-test">${_('Send a test message')}</button>
  <button class="mud-btn" id="mud-fwd-refresh">${_('Refresh status')}</button>
 </div>
</section>`;
		this.root = root;
		this.data = data || {};
		this.saved = this.data.config || null;
		this.status = this.data.status || {};
		this.wire();
		if (this.saved) this.fill(this.saved);
		else this.error(this.data.error || _('Could not read the settings; refresh the page'));
		// A legacy config has no saved template language. The UI offers its
		// current choice, but it must be saved before a matching test can run.
		this.savedPayload = this.saved && this.saved.template_language ? JSON.stringify(this.payload()) : null;
		this.paintStatus();
		this.paintMethod();
		var self = this;
		poll.add(function() { return self.refreshStatus(); }, 5);
		return root;
	},
	q: function(id) { return this.root.querySelector('#mud-fwd-' + id); },
	error: function(s) {
		this.q('error').textContent = s ? (ERRORS[s] || s) : '';
		this.q('error').hidden = !s;
	},
	fill: function(c) {
		var self = this;
		[ 'enabled', 'power_forward_enabled', 'smtp_forward_device_info',
			'dingtalk_forward_device_info', 'sms_forward_device_info', 'telegram_forward_device_info' ].forEach(function(k) { self.q(k).checked = !!c[k]; });
		[ 'method', 'webhook_url', 'dingtalk_webhook', 'sms_to_phone', 'blacklist_phone',
			'blacklist_keywords', 'nickname', 'telegram_chat_id' ].forEach(function(k) { self.q(k).value = c[k] || ''; });
		this.q('template_language').value = c.template_language || 'en';
		[ 'host', 'port', 'username', 'to' ].forEach(function(k) { self.q('smtp_' + k).value = c.smtp && c.smtp[k] || (k === 'port' ? '465' : ''); });
		[ 'smtp_password', 'dingtalk_secret', 'telegram_token' ].forEach(function(k) { self.q(k).value = ''; self.q('clear_' + k).checked = false; });
		this.q('smtp_password').placeholder = c.smtp && c.smtp.password_configured ? _('configured; leave blank to keep') : _('enter the authorization code');
		this.q('dingtalk_secret').placeholder = c.dingtalk_secret_configured ? _('configured; leave blank to keep') : _('optional');
		this.q('telegram_token').placeholder = c.telegram_token_configured ? _('configured; leave blank to keep') : _('from the nanobot configuration');
		this.paintMethod();
	},
	payload: function() {
		var self = this, p = {};
		[ 'enabled', 'power_forward_enabled', 'smtp_forward_device_info',
			'dingtalk_forward_device_info', 'sms_forward_device_info', 'telegram_forward_device_info',
			'clear_smtp_password', 'clear_dingtalk_secret', 'clear_telegram_token' ].forEach(function(k) { p[k] = self.q(k).checked ? 1 : 0; });
		[ 'method', 'template_language', 'webhook_url', 'dingtalk_webhook', 'dingtalk_secret', 'sms_to_phone',
			'smtp_host', 'smtp_port', 'smtp_username', 'smtp_to', 'smtp_password',
			'blacklist_phone', 'blacklist_keywords', 'nickname', 'telegram_token', 'telegram_chat_id' ].forEach(function(k) { p[k] = self.q(k).value.trim(); });
		[ 'sms_to_phone', 'blacklist_phone', 'blacklist_keywords' ].forEach(function(k) { p[k] = lines(p[k]).join('\n'); });
		if (p.clear_smtp_password) {
			p.smtp_host = ''; p.smtp_username = ''; p.smtp_to = ''; p.smtp_password = ''; p.smtp_port = '465';
		}
		return p;
	},
	validate: function(p) {
		if (!validPhones(p.sms_to_phone, 3) || !validPhones(p.blacklist_phone, 64)) return _('A number is invalid, duplicated, or over the limit');
		var words = lines(p.blacklist_keywords);
		if (words.length > 32 || words.some(function(w) { return unescape(encodeURIComponent(w)).length > 128; }) ||
			new Set(words).size !== words.length) return _('A keyword is invalid, duplicated, or over the limit');
		if (p.power_forward_enabled && !this.status.power_supported) return _('The device reports no valid battery state');
		if (p.enabled && ((p.method === 'webhook' && !p.webhook_url) ||
			(p.method === 'dingtalk' && !p.dingtalk_webhook) ||
			(p.method === 'telegram' && !p.telegram_chat_id) ||
			(p.method === 'sms' && !p.sms_to_phone) ||
			(p.method === 'smtp' && !p.smtp_host))) return _('Configure the current channel first');
		return '';
	},
	paintMethod: function() {
		var method = this.q('method').value;
		this.root.querySelectorAll('.mud-fwd-channel').forEach(function(el) { el.hidden = el.getAttribute('data-method') !== method; });
	},
	paintStatus: function() {
		var s = this.status || {};
		this.q('state').textContent = s.enabled ? _('Forwarding is on') : _('Forwarding is off');
		this.q('state').classList.toggle('on', !!s.enabled);
		this.q('last').textContent = _('Last forward: ') + result(s.last_result);
		this.q('power-last').textContent = _('Last power notification: ') + result(s.power_last_result);
		this.q('power_forward_enabled').disabled = !s.power_supported && !this.q('power_forward_enabled').checked;
		this.q('power-note').textContent = s.power_supported
			? _('Notified on a charge-state change, or when the level crosses 5%, 20%, 40%, 60%, 80% or 100%.')
			: _('The device reports no valid battery state');
	},
	refreshStatus: function() {
		var self = this;
		return L.resolveDefault(M.callForwardStatus(), {}).then(function(r) {
			if (r.status) { self.status = r.status; self.paintStatus(); }
		});
	},
	wire: function() {
		var self = this;
		this.q('method').onchange = function() { self.paintMethod(); };
		this.q('save').onclick = function() {
			var p = self.payload(), error = self.validate(p);
			if (error) { self.error(error); return; }
			M.confirmBox(_('Save the SMS forwarding settings?'), _('Once on, only newly received SMS are handled; older messages are not forwarded.'), { okText: _('Save') }).then(function(yes) {
				if (!yes) return;
				var btn = self.q('save'), toast = M.toast(_('Saving the SMS forwarding settings…'), { type: 'busy', timeout: 0 });
				M.busy(btn, true); self.error('');
				L.resolveDefault(M.callForwardSet(JSON.stringify(p)), {}).then(function(r) {
					M.busy(btn, false);
					if (!r.ok) { self.error(r.error || _('Saving failed')); toast.update(_('Saving failed'), 'error'); }
					else {
						self.savedPayload = null;
						L.resolveDefault(M.callForwardGet(), {}).then(function(v) {
							if (v.config) {
								self.saved = v.config;
								self.status = v.status || {};
								self.fill(v.config);
								self.savedPayload = JSON.stringify(self.payload());
								self.paintStatus();
							}
						});
						toast.update(_('Saved'), 'success');
					}
					setTimeout(function() { toast.close(); }, 3000);
				});
			});
		};
		this.q('test').onclick = function() {
			var p = self.payload();
			if (JSON.stringify(p) !== self.savedPayload) {
				self.error(_('Save your changes before testing')); return;
			}
			if (!self.status.enabled) { self.error(_('Enable and save SMS forwarding first')); return; }
			var msg = p.method === 'sms' ? _('This sends from the local SIM to the saved numbers and may incur SMS charges.')
				: _('This sends one fixed test message to the currently saved channel.');
			M.confirmBox(_('Send a test message?'), msg, { okText: _('Send') }).then(function(yes) {
				if (!yes) return;
				var btn = self.q('test'); M.busy(btn, true);
				L.resolveDefault(M.callForwardTest(), {}).then(function(r) {
					M.busy(btn, false);
					M.toast(r.ok ? _('The test has started; refresh the status in a moment') : _('Test failed: ') + (r.error || _('unknown error')),
						{ type: r.ok ? 'success' : 'error' });
					setTimeout(function() { self.refreshStatus(); }, 1500);
				});
			});
		};
		this.q('refresh').onclick = function() { self.refreshStatus(); };
	}
});
