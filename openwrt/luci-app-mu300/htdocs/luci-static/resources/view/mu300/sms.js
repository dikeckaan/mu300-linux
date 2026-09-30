'use strict';
'require view';
'require poll';
'require mu300.common as M';

/* 短信 -- 聊天式界面。数据在设备本地池（mu300-smsd 与 SIM 同步）：
 *   左列会话列表（按联系人分组，最新时间排序，未读徽标）
 *   右侧对话区：气泡（收到的左侧灰底 / 发出的右侧品牌底）+ 时间戳
 *   底部输入栏：号码 + 内容，Enter 发送、Shift+Enter 换行
 * 打开会话时逐条取全文（sms_show 顺带把未读标记已读）。列表/取文都是纯文件读，
 * 发送与 SIM 同步走 AT（后者后台执行）。删除单条：气泡上右键或长按。 */

var MAX_PAGES = 5;   /* 一次聚合的池子页数（每页 10 条），纯文件读，很便宜 */

return view.extend({
	load: function() { return Promise.resolve(); },

	render: function() {
		M.injectCss();
		M.watchSms();
		var root = document.createElement('div');
		root.className = 'mud';
		root.innerHTML = `
<div class="mud-sec" style="margin-top:0">
  <h3>短信 <span id="mud-sms-stat" style="font-weight:400"></span></h3>
  <input id="mud-sms-num" placeholder="收件人：号码，如 10086 或 +86..." spellcheck="false"
    style="width:100%;margin-bottom:8px;padding:7px 11px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222)"/>
  <div class="mud-ctl" style="max-width:460px;margin-bottom:8px">
    <button class="mud-btn" id="mud-sms-refresh">刷新</button>
    <button class="mud-btn" id="mud-sms-sync">从 SIM 同步</button>
    <button class="mud-btn warn" id="mud-sms-clear">清空本地池</button>
  </div>
  <div class="mud-chat">
    <div class="mud-convs" id="mud-sms-convs"><div class="mud-note">加载中…</div></div>
    <div class="mud-thread">
      <div class="mud-msgs" id="mud-sms-msgs"><div class="mud-note" style="margin:8px 2px">选择左侧会话，或直接在下方输入号码发送。</div></div>
      <div class="mud-comp">
        <textarea id="mud-sms-text" placeholder="短信内容（Enter 发送，Shift+Enter 换行）" rows="1"></textarea>
        <button class="mud-btn" id="mud-sms-send" style="align-self:flex-end;padding:8px 18px">发送</button>
      </div>
    </div>
  </div>
  <div class="mud-note" id="mud-sms-note">发送走 AT+CMGS（PDU 模式）；通道忙会提示重试。删除单条：在气泡上右键（手机长按）。</div>
</div>`;
		M.localize(root);
		this.Q = function(id) { return root.querySelector('#mud-' + id); };
		this.sel = null;          /* 当前会话的 peer */
		this.convs = {};          /* peer -> {msgs:[], unread:n} */
		this.wire(root);
		this.reload();
		return root;
	},

	wire: function(root) {
		var self = this;

		this.Q('sms-refresh').onclick = function() { self.reload(); };
		/* 每 5 s 自动刷新（纯本地池读）；打开中的会话随 build() 重渲染，滚动位置保持 */
		poll.add(function() { return self.reload(); }, 5);
		this.Q('sms-sync').onclick = function() {
			var btn = this;
			M.busy(btn, true);
			M.toast('正在后台从 SIM 同步（AT+CMGL）…', { type: 'busy' });
			L.resolveDefault(M.callSmsSync()).then(function() {
				M.busy(btn, false);
				M.toast('SIM 同步已开始，几秒后自动刷新。', { type: 'success' });
				setTimeout(function() { self.reload(); }, 8000);
			});
		};
		this.Q('sms-clear').onclick = function() {
			M.confirmBox('清空本地短信池', '只删本地文件，SIM 上的不动。', { danger: true, okText: '清空' })
				.then(function(go) {
					if (!go) return;
					L.resolveDefault(M.callSmsDel('all')).then(function() { self.sel = null; self.reload(); });
				});
		};
		this.Q('sms-send').onclick = function() { self.send(); };
		var txt = this.Q('sms-text');
		txt.addEventListener('keydown', function(ev) {
			if (ev.key == 'Enter' && !ev.shiftKey) { ev.preventDefault(); self.send(); }
		});
		txt.addEventListener('input', function() {
			this.style.height = 'auto';
			this.style.height = Math.min(120, this.scrollHeight) + 'px';
		});
	},

	/* 删除走气泡右上角的垃圾桶图标，多选对话框区分「仅本地 / 本地+SIM」 */
	delMsg: function(id) {
			var self = this;
			M.choiceBox('删除这条短信', '删除后不可恢复。',
				[ { label: '取消', value: null },
				  { label: '仅删本地', value: 'local' },
				  { label: '本地 + SIM', value: 'sim', danger: true } ])
				.then(function(choice) {
					if (!choice) return;
					L.resolveDefault(M.callSmsDel(id, choice === 'sim')).then(function(r) {
						r = r || {};
						if (r.ok === false) { self.note('删除失败', 'error'); return; }
						delete self.cache[id];
						self.note(choice === 'sim' ? '已删除（本地 + SIM）' : '已删除（仅本地）', 'success');
						self.reload();
					});
				});
		},

	/* 动态提示统一走顶部 toast；页面底部那行只保留静态帮助文案 */
	note: function(t, type) { M.toast(t, { type: type || 'info' }); },

	send: function() {
		var self = this;
		var num = (this.Q('sms-num').value || '').trim();
		var text = (this.Q('sms-text').value || '').replace(/\s+$/, '');
		if (!num || !text) { this.note('号码和内容都要填。', 'error'); return; }
		var btn = this.Q('sms-send');
		M.busy(btn, true);
		this.note('发送中…', 'busy');
		L.resolveDefault(M.callSmsSend(num, text)).then(function(r) {
			r = r || {};
			M.busy(btn, false);
			if (r.ok) {
				self.note('已发送，稍后自动刷新。', 'success');
				self.Q('sms-text').value = '';
				setTimeout(function() { self.reload(); }, 2500);
			} else {
				self.note('发送失败：' + (r.error || '未知错误') + (r.busy ? '（AT 通道正忙，稍后重试）' : ''), 'error');
			}
		}, function() { M.busy(btn, false); self.note('调用失败', 'error'); });
	},

	/* 聚合池子里的几页，按联系人分组 */
	reload: function() {
		var self = this;
		var all = [], page = 1;
		var step = function() {
			return L.resolveDefault(M.callSmsList(page)).then(function(r) {
				r = r || {};
				if (r.error) {
					self.Q('sms-convs').innerHTML = '<div class="mud-note">' + M.esc(r.error) + '</div>';
					return;
				}
				all = all.concat(r.msgs || []);
				var pages = r.pages || 1;
				if (page < pages && page < MAX_PAGES) { page++; return step(); }
				self.stat = r;
					self.build(all);
			});
		};
		return step();
	},

	build: function(all) {
		var self = this;
		/* 5 秒轮询的防闪烁：数据签名没变（无新消息、无未读状态翻转）就完全
		 * 不重绘——整块 innerHTML 重建 + 全文异步回填会产生肉眼可见的闪烁 */
		var sig = (this.stat && this.stat.total) + '|' + all.map(function(m) {
			return m.id + ':' + m.status;
		}).join(',');
		if (sig === this._sig) return;
		this._sig = sig;
		this.convs = {};
		all.forEach(function(m) {
			var peer = m.peer || '?';
			if (!self.convs[peer]) self.convs[peer] = { msgs: [], unread: 0 };
			self.convs[peer].msgs.push(m);
			if (m.status === 'unread') self.convs[peer].unread++;
		});
		var peers = Object.keys(this.convs).sort(function(a, b) {
			var ma = self.convs[a].msgs[0], mb = self.convs[b].msgs[0];
			return (mb && mb.time || '').localeCompare(ma && ma.time || '');
		});
		var st = this.stat || {};
		this.Q('sms-stat').textContent = M.translate('· ' + (st.total || all.length) + ' 条' +
			(st.unread ? '，' + st.unread + ' 条未读' : '') + ' · ' + peers.length + ' 个会话');
		var box = this.Q('sms-convs');
		if (!peers.length) {
			box.innerHTML = '<div class="mud-note" style="margin:6px">' + M.esc(M.translate('池子是空的：收到/发出的短信会出现在这里，或点「从 SIM 同步」。')) + '</div>';
			return;
		}
		box.innerHTML = peers.map(function(p) {
			var cv = self.convs[p];
			var last = cv.msgs[0];
			return '<div class="mud-conv' + (p === self.sel ? ' sel' : '') + '" data-peer="' + M.esc(p) + '">' +
				'<div class="n"><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + M.esc(p) + '</span>' +
				(cv.unread ? '<span class="mud-badge">' + cv.unread + '</span>' : '') + '</div>' +
				'<div class="p">' + M.esc((last.dir === 'mo' ? M.translate('我: ') : '') + (last.preview || '')) + '</div>' +
				'<div class="p" style="opacity:.7">' + M.esc(last.time || '') + '</div></div>';
		}).join('');
		box.querySelectorAll('.mud-conv').forEach(function(el) {
			el.onclick = function() { self.open(el.getAttribute('data-peer')); };
		});
		if (this.sel && this.convs[this.sel]) this.open(this.sel);
	},

	/* 打开会话：渲染气泡，全文按 id 缓存（首取后不再重拉，重绘不再闪预览） */
	open: function(peer) {
		var self = this;
		var keepScroll = this.Q('sms-msgs') ? this.Q('sms-msgs').scrollTop : 0;
		this.sel = peer;
		this.cache = this.cache || {};
		this.Q('sms-num').value = peer.replace(/[^+0-9]/g, '');
		this.Q('sms-convs').querySelectorAll('.mud-conv').forEach(function(el) {
			el.className = (el.getAttribute('data-peer') === peer ? 'mud-conv sel' : 'mud-conv');
		});
		var cv = this.convs[peer];
		var msgsEl = this.Q('sms-msgs');
		msgsEl.innerHTML = '';
		cv.msgs.slice().reverse().forEach(function(m) {   /* 旧 -> 新 */
			var div = document.createElement('div');
			div.className = 'mud-bub' + (m.dir === 'mo' ? ' out' : '');
			div.setAttribute('data-id', m.id);
			var full = self.cache[m.id];
			div.innerHTML = '<span class="bd">' + M.esc(full || m.preview || '') +
				(!full && m.preview && m.preview.length >= 44 ? '…' : '') + '</span>' +
				'<span class="tm">' + M.esc((m.time || '').split(' ').pop() || '') + '</span>';
			msgsEl.appendChild(div);
			if (!full && m.status === 'unread') div.querySelector('.bd').style.fontWeight = '600';
			msgsEl.scrollTop = keepScroll;
			/* 没缓存的才拉全文（本地池读）：拉到后缓存，重绘直接用 */
			if (!full) {
				L.resolveDefault(M.callSmsShow(m.id)).then(function(r) {
					r = r || {};
					if (!r.ok) return;
					/* show 的输出是头部 + "---" + 正文（单换行，无空行）：
					 * 按 \n\n 切分会取到空串——气泡被清空的根源 */
					var body = (r.text || '').split('\n---\n').slice(1).join('\n---\n').trim();
					if (!body) return;
					self.cache[m.id] = body;
					var bd = div.querySelector('.bd');
					if (bd && document.contains(div)) {
						bd.textContent = body;
						bd.style.fontWeight = '';
						bd.classList.add('fadein');   /* 预览 -> 全文的淡入过渡 */
					}
				});
			}
			/* 垃圾桶删除按钮：气泡右上角，悬停显形（触屏常显由 opacity 常开保证） */
			var del = document.createElement('button');
			del.className = 'mud-del';
			del.title = M.translate('删除');
			del.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
				'<path d="M3 6h18"/><path d="M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2"/>' +
				'<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';
			del.onclick = function(ev) { ev.stopPropagation(); self.delMsg(m.id); };
			div.appendChild(del);
		});
		msgsEl.scrollTop = msgsEl.scrollHeight;
	}
});
