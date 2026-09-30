'use strict';
'require view';
'require poll';
'require mu300.common as M';

/* 网络锁定 -- 模式 / 频段 / 小区 / EN-DC，全部经 ubus mu300dash lock_set -> 后端
 * mu300-dash-lock（编码按 ufi_tools 权威实现），应用后 SFUN 重启协议栈并落盘，
 * 开机由插件自己的 procd 服务在 AT 适配器就绪后回放，不依赖平台拨号脚本。
 *
 * 当前驻网 hero 每 2 秒执行一次独立的实时 AT 快照，不读取蜂窝缓存；运营商与
 * 邻区等低频元数据只在打开页面时从 status 取一次。
 * 邻区表每行带「锁定」按钮，与主页共用 M.neighborRows。 */

var MODES = [ [ 'auto', '自动' ], [ '4g', '仅 4G' ], [ 'sa', '5G SA' ], [ 'nsa', '5G NSA' ] ];
var NR_CAND = [ 1, 5, 6, 8, 28, 41, 78 ];   /* 本机 SP5GCMDS 实测；LTE 无能力查询命令，用固定表 */
var LTE_CAND = [ 1, 3, 5, 8, 34, 38, 39, 40, 41 ];

return view.extend({
	load: function() { return Promise.resolve(); },

	render: function() {
		M.injectCss();
		M.watchSms();
		var root = document.createElement('div');
		root.className = 'mud';
		root.innerHTML = `
<!-- 与主页同一套 hero 结构：mud-hero-l/mud-hero-r 让手机端媒体查询统一生效
     （信息块在上，RSRP 行左对齐、芯片右对齐），桌面端保持 RSRP 块右对齐 -->
<div class="mud-card mud-hero">
  <div class="mud-hero-l">
    <div style="font-size:.78rem;color:var(--text-muted,var(--text-light,#777))">当前驻网</div>
    <div style="font-size:1.25rem;font-weight:700;margin-top:2px" id="mud-srv-rat">--</div>
    <div class="mud-cellline" id="mud-srv"></div>
  </div>
  <div class="mud-hero-r">
    <div class="mud-rsrp" id="mud-srv-rsrp" style="font-size:1.9rem">--</div>
    <div class="mud-chips" id="mud-srv-chips"></div>
  </div>
</div>

<div class="mud-sec">
  <h3>网络模式 · EN-DC</h3>
  <div class="mud-ctl" id="mud-lock-modes" style="grid-template-columns:repeat(4,1fr);max-width:520px"></div>
  <div class="mud-ctl" style="margin-top:7px;grid-template-columns:1fr 1fr;max-width:340px">
    <button class="mud-btn" id="mud-lock-endc">EN-DC</button>
    <button class="mud-btn" id="mud-lock-refresh">刷新锁定状态</button>
  </div>
  <div class="mud-ctl" style="margin-top:7px;max-width:340px">
    <button class="mud-btn" id="mud-lock-auto-apply">开机自动应用</button>
  </div>
  <div class="mud-note">关闭后只停止下次开机回放，已保存的网络模式、EN-DC、频段和小区配置不会被删除。</div>
</div>

<div class="mud-sec">
  <h3>频段锁定</h3>
  <div class="mud-cols">
    <div>
      <div class="mud-rows">
        <div class="mud-r"><span class="mud-k">NR 频段</span><span class="mud-v" id="mud-lock-nrline">--</span></div>
      </div>
      <div class="mud-chiprow" id="mud-lock-nr"></div>
    </div>
    <div>
      <div class="mud-rows">
        <div class="mud-r"><span class="mud-k">LTE 频段</span><span class="mud-v" id="mud-lock-lteline">--</span></div>
      </div>
      <div class="mud-chiprow" id="mud-lock-lte"></div>
    </div>
  </div>
  <div class="mud-ctl" style="margin-top:8px;max-width:360px">
    <button class="mud-btn" id="mud-lock-nr-apply">应用 NR 频段</button>
    <button class="mud-btn" id="mud-lock-lte-apply">应用 LTE 频段</button>
  </div>
</div>

<div class="mud-sec">
  <h3>邻区与小区锁定</h3>
  <div id="mud-lockedcells"></div>
  <div class="mud-ctl" style="max-width:400px;margin-bottom:8px">
    <button class="mud-btn" id="mud-lock-cell">锁定当前服务小区</button>
    <button class="mud-btn warn" id="mud-lock-cell-off">解除小区锁定</button>
  </div>
  <div class="mud-scroll">
  <table class="mud-table"><thead><tr><th>制式/频段</th><th>PCI</th><th>频点</th><th>RSRP</th><th>RSRQ</th><th>SINR</th><th></th></tr></thead>
  <tbody id="mud-neigh"><tr><td colspan="7" style="color:var(--text-muted,var(--text-light,#777))">--</td></tr></tbody></table>
  </div>
  <div class="mud-note">应用后协议栈重启（SFUN），蜂窝会短暂断开；设置会持久保存，并在启用“开机自动应用”时由插件于 AT 就绪后回放。接入平台的射频前钩子时可无重启回放。频段全不选再点应用 = 恢复自动。</div>
</div>`;
		M.localize(root);
		this.wire(root);
		return root;
	},

	wire: function(root) {
		var self = this;
		this.lockSel = { nr: {}, lte: {} };
		this.lockCand = { nr: NR_CAND, lte: LTE_CAND };
		this.Q = function(id) { return root.querySelector('#mud-' + id); };

		/* 主题化确认框替代浏览器 confirm；确认后再进入实际执行 */
		var apply = function(kind, val, what, opts) {
			opts = opts || {};
			M.confirmBox('应用「' + what + '」？',
				opts.noSfun ? '' : '协议栈会重启（SFUN），蜂窝断开约半分钟。',
				{ danger: !opts.noSfun, okText: '应用' })
				.then(function(go) { if (go) applyNow(kind, val, what, opts); });
		};
		var applyNow = function(kind, val, what, opts) {
			var btn = opts.btn;
			if (opts.optimistic) opts.optimistic();   /* 按钮立刻切到目标态，回读负责校正 */
			M.busy(btn, true);   /* 在 optimistic 之后：它可能重置按钮的 className */
			self.note('正在后台应用 ' + what + ' …' + (opts.noSfun ? '' : '（SFUN 重启 + 重新驻网，约半分钟）'), 'busy');
			L.resolveDefault(M.callLockSet(kind, val)).then(function(r) {
				r = r || {};
				if (!r.ok) {
					M.busy(btn, false);
					self.note('失败：' + (r.error || '未知错误'), 'error');
					return;
				}
				if (kind == 'endc') {
					self.note(r.queued
						? '已排队：另一项锁定正在应用（SFUN 重启中），随后自动生效'
						: '正在确认 EN-DC 状态…', r.queued ? 'info' : 'busy');
					return self.confirmToggle(kind, val, btn);
				}
				if (kind == 'auto_apply') {
					self.note('正在确认开机自动应用…', 'busy');
					return self.confirmToggle(kind, val, btn);
				}
				self.note('已后台执行：' + (r.op || kind) + '（SFUN 重启约半分钟），自动回读状态…', 'busy');
				self.readback(Date.now(), btn);
			}, function() { M.busy(btn, false); self.note('调用失败', 'error'); });
		};

		this.Q('lock-modes').innerHTML = MODES.map(function(m) {
			return '<button class="mud-btn" data-mode="' + m[0] + '">' + M.esc(M.translate(m[1])) + '</button>';
		}).join('');
		root.querySelectorAll('#mud-lock-modes .mud-btn').forEach(function(b) {
			b.onclick = function() {
				var m = b.getAttribute('data-mode');
				if (m === (self.lastLock && self.lastLock.mode && self.lastLock.mode.label)) return;
				var btn = b;
				apply('mode', m, '网络模式：' + b.textContent, { btn: btn, optimistic: function() {
					Array.prototype.forEach.call(self.Q('lock-modes').querySelectorAll('.mud-btn'), function(x) {
						x.className = x === btn ? 'mud-btn on' : 'mud-btn';
					});
				} });
			};
		});
		this.Q('lock-endc').onclick = function() {
			var on = self.lastLock && self.lastLock.endc === '1';
			var btn = this;
			apply('endc', on ? 'off' : 'on', on ? '关闭 EN-DC（NSA 锚点）' : '开启 EN-DC（NSA 锚点）',
				{ btn: btn, noSfun: true, optimistic: function() {
					btn.className = 'mud-btn' + (on ? '' : ' on');
					btn.textContent = on ? 'EN-DC' : 'EN-DC ✓';
				} });
		};
		this.Q('lock-auto-apply').onclick = function() {
			var on = !self.lastLock || self.lastLock.auto_apply !== 0;
			var btn = this;
			apply('auto_apply', on ? 'off' : 'on', on ? '关闭开机自动应用' : '开启开机自动应用',
				{ btn: btn, noSfun: true, optimistic: function() {
					btn.className = 'mud-btn' + (on ? '' : ' on');
					btn.textContent = on ? '开机自动应用' : '开机自动应用 ✓';
				} });
		};
		this.Q('lock-refresh').onclick = function() {
			var btn = this;
			M.busy(btn, true);
			self.note('正在直读调制解调器（最多几秒）…', 'busy');
			L.resolveDefault(M.callLockFresh('1')).then(function(l) {
				M.busy(btn, false);
				self.lastLock = l || {};
				self.paint();
				self.note('已刷新', 'success');
				var nb = self.Q('neigh');
				if (nb && self.lastCell) nb.innerHTML = M.neighborRows(self.lastCell, self.lastLock.cells || []);
			}, function() { M.busy(btn, false); self.note('刷新失败', 'error'); });
			self.loadServing();
		};

		this.chipRow = function(el, rat, cand) {
			el.innerHTML = cand.map(function(b) {
				return '<span class="mud-chip" data-rat="' + rat + '" data-b="' + b + '">' + (rat === 'nr' ? 'n' : 'B') + b + '</span>';
			}).join('');
			/* chips 重建后恢复选中态 */
			Array.prototype.forEach.call(el.children, function(ch) {
				var b = ch.getAttribute('data-b');
				if (self.lockSel[rat][b]) ch.className = 'mud-chip on';
			});
		};
		this.chipRow(this.Q('lock-nr'), 'nr', NR_CAND);
		this.chipRow(this.Q('lock-lte'), 'lte', LTE_CAND);
		/* 事件委托绑在容器上：paint() 依模组能力重建 chips 后点击依然有效 */
		[ 'nr', 'lte' ].forEach(function(rat) {
			self.Q('lock-' + rat).addEventListener('click', function(ev) {
				var ch = ev.target;
				if (!ch.getAttribute || !ch.getAttribute('data-b')) return;
				var b = ch.getAttribute('data-b');
				self.lockSel[rat][b] = !self.lockSel[rat][b];
				ch.className = self.lockSel[rat][b] ? 'mud-chip on' : 'mud-chip';
			});
		});
		var selBands = function(rat) {
			return Object.keys(self.lockSel[rat]).filter(function(b) { return self.lockSel[rat][b]; })
				.map(Number).sort(function(a, b) { return a - b; });
		};
		this.Q('lock-nr-apply').onclick = function() {
			var sel = selBands('nr');
			if (!sel.length) return apply('nr', '', 'NR 频段：恢复自动', { btn: this });
			apply('nr', sel.join(','), 'NR 频段锁定：n' + sel.join(' n'), { btn: this });
		};
		this.Q('lock-lte-apply').onclick = function() {
			var sel = selBands('lte');
			if (!sel.length) return apply('lte', '', 'LTE 频段：恢复自动', { btn: this });
			apply('lte', sel.join(','), 'LTE 频段锁定：B' + sel.join(' B'), { btn: this });
		};
		this.Q('lock-cell').onclick = function() { apply('cell', 'auto', '锁定当前服务小区', { btn: this }); };
		this.Q('lock-cell-off').onclick = function() { apply('cell', 'off', '解除小区锁定', { btn: this }); };

		/* 已锁定小区表的解锁按钮（委托） */
		this.Q('lockedcells').addEventListener('click', function(ev) {
			var btn = ev.target;
			if (!btn.getAttribute || !btn.getAttribute('data-unlock')) return;
			var rat = btn.getAttribute('data-unlock');
			M.confirmBox('解除 ' + rat.toUpperCase() + ' 的小区锁定', '协议栈会重启（SFUN），约半分钟。', { danger: true })
				.then(function(go) {
				if (!go) return;
				M.busy(btn, true);
			self.note('正在解除 ' + rat.toUpperCase() + ' 小区锁定…', 'busy');
			L.resolveDefault(M.callLockSet('cell', 'off-' + rat)).then(function(r) {
				r = r || {};
				M.busy(btn, false);
				if (!r.ok) { self.note('解锁失败：' + (r.error || '未知错误'), 'error'); return; }
					self.note('已后台解除，SFUN 重启约半分钟，自动回读状态…', 'busy');
					self.readback(Date.now());
				});
			});
		});

		/* 邻区行内锁定（事件委托，与主页一致） */
		this.Q('neigh').addEventListener('click', function(ev) {
			var btn = ev.target;
			if (!btn.getAttribute || !btn.getAttribute('data-lock')) return;
			var key = btn.getAttribute('data-lock');
			M.confirmBox('锁定小区 ' + key.replace(':', ' ') + '?', '协议栈会重启（SFUN），蜂窝断开约半分钟。', { danger: true })
				.then(function(go) {
				if (!go) return;
				M.busy(btn, true);
			self.note('正在后台锁定 ' + key + ' …', 'busy');
			L.resolveDefault(M.callLockSet('cell', key)).then(function(r) {
				r = r || {};
				M.busy(btn, false);
				if (!r.ok) { self.note('锁定失败：' + (r.error || '未知错误'), 'error'); return; }
					self.note('已后台锁定 ' + key + '（SFUN 重启约半分钟），自动回读状态…', 'busy');
					self.readback(Date.now());
				});
			});
		});

		this.refresh();
		this.loadServingMeta();
		this.loadServing();
		poll.add(function() { return self.loadServing(); }, 2);
	},

	/* 统一反馈：所有提示走顶部 toast（M.toast），进行中的用 busy 自带转圈；
	 * 同一时间只保留一条（新提示顶掉旧提示，进度→结果一路更新不堆叠）。 */
	note: function(txt, type) {
		if (this._toast) this._toast.close();
		this._toast = M.toast(txt, { type: type || 'info' });
	},

	/* 运营商与邻区属于低频元数据；实时信号不会从这里读取。 */
	loadServingMeta: function() {
		var self = this;
		return L.resolveDefault(M.callStatus()).then(function(st) {
			self.servingMeta = (st || {}).cell || {};
		});
	},

	/* 每次都由后端完成一轮新的 AT 快照；不接受上一轮 signal/cell 缓存。 */
	loadServing: function() {
		var self = this;
		return L.resolveDefault(M.callSignal()).then(function(live) {
			live = live || {};
			var c = {}, meta = self.servingMeta || {};
			Object.keys(meta).forEach(function(k) { c[k] = meta[k]; });
			Object.keys(live).forEach(function(k) { c[k] = live[k]; });
			self.paintServing(c);
		});
	},

	paintServing: function(c) {
		var e = this.Q('srv'); if (!e) return;
		this.lastCell = c;
		if (!c || c.error) {
			this.Q('srv-rat').textContent = c && c.error ? c.error : M.translate('暂无驻网数据');
			e.innerHTML = '';
			return;
		}
		var ratTxt = (c.nr && c.nr.band) ? ((c.lte && c.lte.band) ? '5G NSA' : '5G SA') : 'LTE';
		var sig = c.sig || {}, label = M.qLabel(sig.rsrp, sig.rsrq, sig.sinr);
		var operName = M.carrierName(c.operator);
			if (operName === '--' && c.ident && c.ident.imsi)
				operName = M.translate(M.PLMN_CN[c.ident.imsi.substring(0, 5)] || c.ident.imsi.substring(0, 5));
			this.Q('srv-rat').textContent = ratTxt + ' · ' + operName;
		this.Q('srv-rat').style.color = M.qCol(label);
		var rsrpEl = this.Q('srv-rsrp');
		if (sig.rsrp != null) { rsrpEl.innerHTML = sig.rsrp.toFixed(1) + '<small> dBm</small>'; rsrpEl.style.color = M.qCol(label); }
		this.Q('srv-chips').innerHTML =
			(sig.rsrq != null ? '<span class="mud-tag">RSRQ ' + sig.rsrq.toFixed(1) + '</span>' : '') +
			(sig.sinr != null ? '<span class="mud-tag">SINR ' + sig.sinr.toFixed(1) + '</span>' : '');
		var rows = [];
		if (c.nr && c.nr.band) rows.push([ 'NR 服务小区', 'n' + c.nr.band + ' · PCI ' + c.nr.pci + ' · ARFCN ' + c.nr.arfcn + (c.nr.bw_mhz ? ' · ' + c.nr.bw_mhz + ' MHz' : '') ]);
		if (c.lte && c.lte.band) rows.push([ 'LTE 锚点', 'B' + c.lte.band + ' · PCI ' + c.lte.pci + ' · EARFCN ' + c.lte.earfcn ]);
		e.innerHTML = rows.map(function(x) {
			return '<div class="mud-srvline"><span class="k">' + M.esc(M.translate(x[0])) + '</span><span class="v">' + M.esc(x[1]) + '</span></div>';
		}).join('');
		var nb = this.Q('neigh');
		if (nb) nb.innerHTML = M.neighborRows(c, (this.lastLock || {}).cells || []);
	},

	/* 应用后自动回读：轮询缓存 lock_get 直到 ts 越过本次应用（后端 apply 后会 fresh 刷新缓存） */
	/* 应用后自动回读：轮询缓存直到 ts 落在“点击应用”之后（SFUN 重启 + fresh 读
	 * 最长约一两分钟；期间后端不会用空读数覆盖缓存），拿到新状态才重绘高亮 */
	readback: function(t0ms, btn) {
		var self = this, tries = 0, t0 = t0ms || Date.now();
		var step = function() {
			L.resolveDefault(M.callLockGet()).then(function(l) {
				l = l || {};
				if ((l.ts && l.ts * 1000 > t0) || ++tries > 40) {
					M.busy(btn, false);
					self.lastLock = l; self.paint(); self.paintServing(self.lastCell);
					self.note((l.ts && l.ts * 1000 > t0) ? '状态已回读' : '回读超时，请点「刷新锁定状态」',
						(l.ts && l.ts * 1000 > t0) ? 'success' : 'error');
				} else setTimeout(step, 2500);
			});
		};
		step();
	},
	refreshSoon: function() {
		var self = this;
		setTimeout(function() { self.refresh(); }, 1500);
	},

	/* 即时开关（EN-DC / 开机自动应用）确认式回读：后端已把这些状态即时写进
	 * lock 缓存，正常第一轮（1.5s）就能对上；对不上（比如排在 SFUN 后面）
	 * 就保持乐观状态继续等，最多 15 秒才回滚，避免按钮闪回造成“没点上”的错觉。 */
	confirmToggle: function(kind, val, btn) {
		var self = this, tries = 0;
		var matches = function(l) {
			if (kind == 'endc') return (l.endc === '1') == (val == 'on');
			if (kind == 'auto_apply') return (l.auto_apply !== 0) == (val == 'on');
			return true;
		};
		var step = function() {
			L.resolveDefault(M.callLockGet()).then(function(l) {
				l = l || {};
				if (matches(l) || ++tries > 10) {
					M.busy(btn, false);
					self.lastLock = l;
					self.paint();
					if (matches(l))
						self.note(kind == 'endc' ? '已生效（EN-DC 不需要重启协议栈）' : '开机自动应用已' + (val == 'on' ? '开启' : '关闭'), 'success');
					else
						self.note((kind == 'endc' ? 'EN-DC' : '开机自动应用') + '状态回读超时，点「刷新锁定状态」确认', 'error');
				} else setTimeout(step, 1500);
			});
		};
		setTimeout(step, 1500);
	},

	refresh: function() {
		var self = this;
		L.resolveDefault(M.callLockGet()).then(function(l) {
			l = l || {};
			/* 空结果多半是 rpcd 高并发下的一次瞬时失败（实测同请求重发即好）：轻量重试 */
			if (!l.mode && !l.error && (self._retry = (self._retry || 0) + 1) <= 3)
				return setTimeout(function() { self.refresh(); }, 1800);
			self._retry = 0;
			self.lastLock = l;
			self.paint();
			/* 锁定状态回来了，把邻区表的“已锁定”标记也刷新一下 */
			var nb = self.Q('neigh');
			if (nb && self.lastCell) nb.innerHTML = M.neighborRows(self.lastCell, self.lastLock.cells || []);
		});
	},

	paint: function() {
		var l = this.lastLock || {};
		var self = this;
		var setR = function(id, txt) { var e = self.Q(id); if (e) e.textContent = (txt == null || txt === '') ? '--' : txt; };
		if (l.error) { setR('lock-nrline', l.error); setR('lock-lteline', ''); return; }
		var MODE_TXT = { auto: '自动（5G/4G）', '4g': '仅 4G', sa: '仅 5G SA', nsa: '仅 5G NSA' };
		var cur = this.Q('lock-modes');
		if (cur) Array.prototype.forEach.call(cur.querySelectorAll('.mud-btn'), function(b) {
			b.className = (b.getAttribute('data-mode') === (l.mode && l.mode.label)) ? 'mud-btn on' : 'mud-btn';
		});
		var eb = this.Q('lock-endc');
		if (eb) { eb.className = 'mud-btn' + (l.endc === '1' ? ' on' : ''); eb.textContent = l.endc === '1' ? 'EN-DC' : 'EN-DC'; }
		var ab = this.Q('lock-auto-apply'), autoApply = l.auto_apply !== 0;
		if (ab) { ab.className = 'mud-btn' + (autoApply ? ' on' : ''); ab.textContent = M.translate(autoApply ? '开机自动应用 ✓' : '开机自动应用'); }

		/* 支持频段优先取模组能力（SPLBAND=4 / =0 解码），读不到才用静态表 */
		var caps = l.caps || {};
		/* 已锁定小区独立表：多小区都列出来，每个 RAT 一个解锁按钮 */
		var lc = self.Q('lockedcells');
		if (lc) {
			var cells = l.cells || [];
			lc.innerHTML = cells.length
				? '<div class="mud-note" style="margin:0 0 4px">' + M.esc(M.translate('已锁定小区')) + '</div><table class="mud-table"><tbody>' +
					cells.map(function(k) {
						var parts = k.split(':'), rat = parts[0], fp = (parts[1] || '').split(',');
						return '<tr><td>' + (rat == 'nr' ? 'NR' : 'LTE') + '</td><td>' + M.esc(fp[0] || '?') + '</td>' +
							'<td>' + M.esc(fp[1] || '?') + '</td>' +
							'<td><button class="mud-lockbtn" data-unlock="' + rat + '">' + M.esc(M.translate('解锁 ')) + (rat == 'nr' ? 'NR' : 'LTE') + '</button></td></tr>';
					}).join('') + '</tbody></table>'
				: '';
		}
		[ 'nr', 'lte' ].forEach(function(rat) {
			var capList = (caps[rat] || '').split(',').map(Number).filter(function(b) { return b > 0; });
			if (capList.length) {
				capList.sort(function(a, b) { return a - b; });
				self.lockCand[rat] = capList;
				var box = self.Q('lock-' + rat);
				if (box) self.chipRow(box, rat, capList);
			}
			var locked = (l[rat] && l[rat].locked) || '';
			var arr = locked ? locked.split(',').map(Number) : [];
			var isAuto = arr.length === 0 || arr.length >= self.lockCand[rat].length;
			setR('lock-' + rat + 'line', M.translate(isAuto
				? '自动（支持 ' + self.lockCand[rat].length + ' 个）'
				: '已锁 ' + arr.length + ' 个：' + (rat === 'nr' ? 'n' : 'B') + arr.join(' ' + (rat === 'nr' ? 'n' : 'B'))));
			var box = self.Q('lock-' + rat);
			if (box) Array.prototype.forEach.call(box.children, function(ch) {
				var b = ch.getAttribute('data-b');
				var on = !isAuto && arr.indexOf(Number(b)) >= 0;
				self.lockSel[rat][b] = on;
				ch.className = on ? 'mud-chip on' : 'mud-chip';
			});
		});
	}
});
