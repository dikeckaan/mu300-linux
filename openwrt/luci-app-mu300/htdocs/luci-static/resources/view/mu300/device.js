'use strict';
'require view';
'require mu300.common as M';

return view.extend({
	load: function() { return L.resolveDefault(M.callUsbGet(), {}); },
	render: function(state) {
		M.injectCss();
		M.localizeMenu();
		var root = document.createElement('div');
		root.className = 'mud';
		root.innerHTML = `
<style>
.mud-device-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.mud-device-field{display:flex;flex-direction:column;gap:7px;margin:12px 0}
.mud-device-field label{font-size:.8rem;color:var(--text-muted,var(--text-light,#777))}
.mud-device-field select{width:100%;min-height:38px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);padding:6px 10px;background:var(--surface,var(--background,#fff));color:var(--text,#222)}
.mud-device-toggle{display:flex;align-items:center;gap:9px;font-size:.82rem;line-height:1.45;cursor:pointer}
.mud-device-toggle input{accent-color:var(--brand,var(--primary,#2f7bf6))}
.mud-device-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.mud-device-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.mud-device-head h3{margin:0;font-size:.85rem}
.mud-device-list{display:grid;gap:8px;margin-top:12px}
.mud-device-item{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border:1px solid var(--hairline,var(--border,#ddd));border-radius:var(--radius-base,.5rem)}
.mud-device-item-main{min-width:0;display:flex;align-items:center;gap:10px}
.mud-device-dot{width:9px;height:9px;border-radius:50%;background:var(--text-muted,#888);flex:none}
.mud-device-dot.up{background:var(--success,#2fbf71)}
.mud-device-item-name{font-weight:650;overflow-wrap:anywhere}
.mud-device-item-sub{font-size:.72rem;color:var(--text-muted,var(--text-light,#777))}
@media(max-width:720px){.mud-device-grid{grid-template-columns:1fr}.mud-device-item{align-items:flex-start}.mud-device-item .mud-btn{white-space:nowrap}}
</style>
<div class="mud-device-grid">
 <section class="mud-card">
  <h3>USB 角色</h3>
  <div class="mud-r"><span class="mud-k">当前角色</span><span class="mud-v" id="mud-usb-role-now">--</span></div>
  <div class="mud-device-field"><label for="mud-usb-role">切换 USB 角色</label>
   <select id="mud-usb-role"><option value="device">设备模式</option><option value="host">主机模式</option></select></div>
  <label class="mud-device-toggle"><input type="checkbox" id="mud-usb-role-auto">开机自动启用主机模式</label>
  <div class="mud-device-actions"><button class="mud-btn" id="mud-usb-role-apply">应用角色</button></div>
  <div class="mud-note">主机模式会断开本端口的 USB 网络与串口。F50 没有电池；切换后可能失去管理连接，外接 USB 网卡通常需要自供电 Hub。</div>
 </section>
 <section class="mud-card" id="mud-usb-net-card">
  <h3>USB 网络模式</h3>
  <div class="mud-device-field"><label for="mud-usb-net-mode">网络协议</label>
   <select id="mud-usb-net-mode"><option value="ncm">NCM</option><option value="ecm">ECM</option><option value="rndis">RNDIS</option></select></div>
  <div class="mud-device-field"><label for="mud-usb-net-scope">生效期限</label>
   <select id="mud-usb-net-scope"><option value="once">仅下次重启</option><option value="permanent">永久生效</option></select></div>
  <label class="mud-device-toggle"><input type="checkbox" id="mud-usb-net-auto">启用所选协议</label>
  <div class="mud-device-actions"><button class="mud-btn" id="mud-usb-net-apply">保存，重启后生效</button></div>
  <div class="mud-note" id="mud-usb-net-note">NCM 为默认模式。Windows 不原生支持 ECM；RNDIS 会改变枚举方式。关闭“启用所选协议”时仅保存选择；选择“仅下次重启”则成功应用一次后恢复默认 NCM。</div>
 </section>
</div>
<section class="mud-card" style="margin-top:14px" id="mud-usb-adapters-card">
 <div class="mud-device-head"><h3>USB 网卡</h3><button class="mud-btn" id="mud-usb-refresh">刷新</button></div>
 <div class="mud-note">仅主机模式可用。刷新时会尝试启用发现的 USB 网卡；添加到 LAN 后将保存到网桥并重新加载网络。</div>
 <div class="mud-device-list" id="mud-usb-adapters"></div>
</section>`;
		M.localize(root);
		this.root = root;
		this.state = state || {};
		this.wire();
		this.paint();
		return root;
	},
	q: function(id) { return this.root.querySelector('#mud-usb-' + id); },
	paint: function() {
		var s = this.state || {};
		this.q('role-now').textContent = s.role === 'host' ? M.translate('主机模式') : s.role === 'device' ? M.translate('设备模式') : M.translate('不可用');
		this.q('role').querySelector('option[value="host"]').disabled = s.host_supported === 0;
		this.q('role').value = s.role === 'host' || s.role_auto ? 'host' : 'device';
		this.q('role-auto').checked = !!s.role_auto;
		this.q('net-mode').value = s.net_mode || 'ncm';
		this.q('net-scope').value = s.net_scope || 'permanent';
		this.q('net-auto').checked = !!s.net_auto;
		this.updateDisabled();
		this.refreshAdapters();
	},
	updateDisabled: function() {
		var host = this.state.role === 'host', hostAuto = this.q('role-auto').checked && this.q('role').value === 'host';
		this.q('role-auto').disabled = this.q('role').value !== 'host';
		if (this.q('role').value !== 'host') this.q('role-auto').checked = false;
		var locked = host || !!this.state.role_auto || hostAuto;
		[ 'net-mode', 'net-scope', 'net-auto', 'net-apply' ].forEach(function(id) { this.q(id).disabled = locked; }, this);
		if (locked) this.q('net-auto').checked = false;
		this.q('net-note').textContent = M.translate(locked ? '主机模式下不可选择 USB 网络模式；主机开机自启会自动关闭 USB 网络开机自启。' : 'NCM 为默认模式。Windows 不原生支持 ECM；RNDIS 会改变枚举方式。关闭“启用所选协议”时仅保存选择；选择“仅下次重启”则成功应用一次后恢复默认 NCM。');
		this.q('refresh').disabled = !host;
	},
	wire: function() {
		var self = this;
		this.q('role').addEventListener('change', function() { self.updateDisabled(); });
		this.q('role-auto').addEventListener('change', function() { self.updateDisabled(); });
		this.q('net-mode').addEventListener('change', function() { self.q('net-auto').checked = true; });
		this.q('net-scope').addEventListener('change', function() { self.q('net-auto').checked = true; });
		this.q('role-apply').addEventListener('click', function() {
			var role = self.q('role').value, auto = self.q('role-auto').checked ? '1' : '0';
			var warning = role === 'host' ? '切换主机模式会立即断开 USB 管理连接。F50 没有电池，外设可能需要自供电；请确认有其他管理途径。' : '切回设备模式后 USB 网络和串口会重新枚举。';
			M.confirmBox('确认切换 USB 角色？', warning, { danger: role === 'host', okText: '应用' }).then(function(yes) {
				if (!yes) return;
				var btn = self.q('role-apply'); M.busy(btn, true);
				var msg = M.toast('正在切换 USB 角色…', { type: 'busy', timeout: 0 });
				M.callUsbSet('role', role, '', auto).then(function(r) {
					M.busy(btn, false);
					if (!r || r.ok !== 1) {
						msg.update(r && r.ok === 0 ? '切换失败：' + (r.error || '未知错误') : '管理连接已中断；请重新连接后确认 USB 角色。', r && r.ok === 0 ? 'error' : 'info');
						setTimeout(function() { msg.close(); }, 6000);
						return;
					}
					if (r.pending) {
						msg.update('切换请求已接收，USB 连接可能短暂中断。', 'info');
						self.watchRole(role, msg, 0);
					} else {
						msg.update('USB 角色已应用', 'success'); setTimeout(function() { msg.close(); }, 2500);
						self.reloadState();
					}
				}, function() {
					M.busy(btn, false);
					msg.update('管理连接已中断；请重新连接后确认 USB 角色。', 'info');
					setTimeout(function() { msg.close(); }, 6000);
				});
			});
		});
		this.q('net-apply').addEventListener('click', function() {
			var mode = self.q('net-mode').value, scope = self.q('net-scope').value, auto = self.q('net-auto').checked ? '1' : '0';
			M.confirmBox('保存 USB 网络模式？', auto === '1' ? '网络模式将在下次重启时生效，USB 管理连接可能需要重新识别。' : '只保存选择；未启用所选协议，下次重启仍使用默认 NCM。', { okText: '保存' }).then(function(yes) {
				if (!yes) return;
				var btn = self.q('net-apply'); M.busy(btn, true);
				var msg = M.toast('正在保存 USB 网络设置…', { type: 'busy', timeout: 0 });
				L.resolveDefault(M.callUsbSet('net', mode, scope, auto), {}).then(function(r) {
					M.busy(btn, false); msg.update(r.ok ? '设置已保存' : '保存失败：' + (r.error || '未知错误'), r.ok ? 'success' : 'error');
					setTimeout(function() { msg.close(); }, 3500);
					if (r.ok) self.reloadState();
				});
			});
		});
		this.q('refresh').addEventListener('click', function() { self.refreshAdapters(0); });
	},
	reloadState: function() {
		var self = this;
		L.resolveDefault(M.callUsbGet(), {}).then(function(s) { if (s.ok) { self.state = s; self.paint(); } });
	},
	watchRole: function(role, msg, attempt) {
		var self = this;
		setTimeout(function() {
			M.callUsbGet().then(function(s) {
				if (s && s.ok && s.role === role) {
					msg.update('USB 角色已应用', 'success');
					setTimeout(function() { msg.close(); }, 2500);
					self.state = s; self.paint();
					return;
				}
				self.finishRoleWatch(role, msg, attempt);
			}, function() { self.finishRoleWatch(role, msg, attempt); });
		}, attempt ? 1000 : 350);
	},
	finishRoleWatch: function(role, msg, attempt) {
		if (attempt < 4) { this.watchRole(role, msg, attempt + 1); return; }
		msg.update('暂时无法确认角色；请重新连接后刷新页面。', 'info');
		setTimeout(function() { msg.close(); }, 5000);
	},
	refreshAdapters: function(attempt) {
		attempt = attempt || 0;
		var self = this, list = this.q('adapters');
		list.replaceChildren();
		if (this.state.role !== 'host') {
			list.textContent = M.translate('切换到主机模式后显示 USB 网卡。'); return;
		}
		var wait = document.createElement('div'); wait.className = 'mud-note mud-booting';
		wait.textContent = M.translate('正在扫描 USB 网卡…'); list.appendChild(wait);
		M.busy(this.q('refresh'), true);
		L.resolveDefault(M.callUsbNetList(), {}).then(function(r) {
			M.busy(self.q('refresh'), false);
			list.replaceChildren();
			if (!r.ok || !r.devices || !r.devices.length) {
				list.textContent = M.translate('没有发现 USB 网卡。');
				if (self.state.role === 'host' && attempt < 2)
					setTimeout(function() { if (self.state.role === 'host') self.refreshAdapters(attempt + 1); }, 1600);
				return;
			}
			r.devices.forEach(function(d) {
				var row = document.createElement('div'); row.className = 'mud-device-item';
				var main = document.createElement('div'); main.className = 'mud-device-item-main';
				var dot = document.createElement('i'); dot.className = 'mud-device-dot' + (d.carrier ? ' up' : ''); main.appendChild(dot);
				var info = document.createElement('div');
				var name = document.createElement('div'); name.className = 'mud-device-item-name'; name.textContent = d.name;
				var sub = document.createElement('div'); sub.className = 'mud-device-item-sub'; sub.textContent = M.translate(d.carrier ? '链路已连接' : '链路未连接，已尝试启用');
				info.appendChild(name); info.appendChild(sub); main.appendChild(info); row.appendChild(main);
				var btn = document.createElement('button'); btn.className = 'mud-btn'; btn.textContent = M.translate(d.in_lan ? '已加入 LAN' : '添加到 LAN'); btn.disabled = !!d.in_lan;
				btn.addEventListener('click', function() {
					M.confirmBox('添加 USB 网卡到 LAN？', '这会保存网桥配置并重新加载网络，现有连接可能短暂中断。', { okText: '添加' }).then(function(yes) {
						if (!yes) return;
						M.busy(btn, true); var msg = M.toast('正在添加 USB 网卡…', { type: 'busy', timeout: 0 });
						L.resolveDefault(M.callUsbNetAdd(d.name), {}).then(function(a) {
							M.busy(btn, false); msg.update(a.ok ? '已添加到 LAN' : '添加失败：' + (a.error || '未知错误'), a.ok ? 'success' : 'error');
							setTimeout(function() { msg.close(); }, 3500); self.refreshAdapters();
						});
					});
				});
				row.appendChild(btn); list.appendChild(row);
			});
		});
	}
});
