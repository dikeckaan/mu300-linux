'use strict';
'require view';
'require mu300.common as M';

/* AT 终端 -- 专业串口调试风格：深色输出区、行级高亮（命令/OK/错误/数据）、
 * 每条耗时、↑↓ 翻本地历史、右侧会话历史可点选复用、常用命令分组。
 * 所有命令经 rpcd -> mu300-at 走 nr1 通道（采集器在 nr6/nr7，互不干扰）；守卫在后端：
 * 必须 AT 开头、禁止 ";" 级联、AT+SPENGMD=0,1,0 直接拒绝（会锁死 AT 口直到重启）。 */

var GROUPS = [
	[ '基础', [ 'AT', 'AT+CFUN?', 'AT+CPIN?', 'AT+CGMR', 'AT+CCID', 'AT+CIMI', 'AT+CGSN', 'AT+CNUM' ] ],
	[ '注册/信号', [ 'AT+CSQ', 'AT+CESQ', 'AT+CEREG?', 'AT+C5GREG?', 'AT+COPS?', 'AT+CGATT?', 'AT+CGACT?' ] ],
	[ '承载', [ 'AT+CGDCONT?', 'AT+CGPADDR=1', 'AT+CGCONTRDP=1', 'AT+CGEQOSRDP=1' ] ],
	[ '工程模式', [ 'AT+SPENGMD=0,6,0', 'AT+SPENGMD=0,14,1', 'AT+SPENGMD=0,6,6', 'AT+SPQ5GNCELLEX', 'AT+SPENDC?', 'AT+SPTESTMODE?', 'AT+SP5GRAN?' ] ]
];

return view.extend({
	load: function() { return Promise.resolve(); },

	render: function() {
		M.injectCss();
		M.watchSms();
		var root = document.createElement('div');
		root.className = 'mud';
		root.innerHTML = `
<div class="mud-sec" style="margin-top:0">
  <h3>AT 终端</h3>
  <div style="display:flex;flex-direction:column;gap:8px">
    <div style="display:flex;gap:8px">
      <input id="mud-at-cmd" spellcheck="false" autocomplete="off"
        style="flex:1;min-width:0;padding:8px 12px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-family:var(--font-mono,monospace);font-size:.85rem"
        placeholder="AT 命令（↑↓ 翻历史，Enter 发送）"/>
      <button class="mud-btn" id="mud-at-go" style="padding:8px 18px">发送</button>
      <button class="mud-btn" id="mud-at-clear" style="padding:8px 12px">清屏</button>
    </div>
    <div class="mud-at-grid">
      <div class="mud-term" id="mud-at-out"><span class="ln-meta">就绪。
</span></div>
      <div>
        <div class="mud-note" style="margin:0 0 4px">会话历史（点击复用）</div>
        <div class="mud-scroll" id="mud-at-hist" style="font-family:var(--font-mono,monospace);font-size:.74rem"></div>
      </div>
    </div>
    <div>
      ${GROUPS.map(function(g) {
        return '<div class="mud-note" style="margin:4px 0 2px">' + g[0] + '</div>' +
          '<div class="mud-chiprow" style="margin-top:2px">' +
          g[1].map(function(c) { return '<span class="mud-chip">' + c + '</span>'; }).join('') + '</div>';
      }).join('')}
    </div>
  </div>
</div>`;
		M.localize(root);
		this.wire(root);
		this.loadHist();
		return root;
	},

	wire: function(root) {
		var self = this;
		this.Q = function(id) { return root.querySelector('#mud-' + id); };
		this.localHist = [];
		this.histIdx = -1;

		var line = function(cls, text) {
			var el = self.Q('at-out');
			var span = document.createElement('span');
			span.className = cls;
			span.textContent = text + '\n';
			el.appendChild(span);
			el.scrollTop = el.scrollHeight;
		};

		this.send = function() {
			var cmd = (self.Q('at-cmd').value || '').trim();
			if (!cmd) return;
			self.localHist.push(cmd);
			self.histIdx = self.localHist.length;
			line('ln-cmd', '> ' + cmd);
			var t0 = Date.now();
			L.resolveDefault(M.callAt(cmd)).then(function(r) {
				r = r || {};
				var ms = Date.now() - t0;
				if (r.ok) {
					(r.reply || M.translate('(无输出)')).split('\n').forEach(function(l) {
						if (/^OK$/.test(l)) line('ln-ok', l);
						else if (/ERROR|^NO CARRIER/.test(l)) line('ln-err', l);
						else if (l) line('ln-data', l);
					});
					line('ln-meta', '—— ' + ms + ' ms');
					self.loadHist();
				} else {
					line('ln-err', M.translate('错误：') + (r.error || M.translate('失败')) + (r.busy ? M.translate('（AT 通道正忙，命令未发出）') : ''));
				}
			}, function() { line('ln-err', M.translate('调用失败')); });
			self.Q('at-cmd').value = '';
		};

		this.Q('at-go').onclick = function() { self.send(); };
		this.Q('at-clear').onclick = function() { self.Q('at-out').innerHTML = ''; };
		this.Q('at-cmd').addEventListener('keydown', function(ev) {
			if (ev.key == 'Enter') { ev.preventDefault(); self.send(); }
			else if (ev.key == 'ArrowUp') {
				ev.preventDefault();
				if (self.histIdx > 0) { self.histIdx--; self.Q('at-cmd').value = self.localHist[self.histIdx] || ''; }
			} else if (ev.key == 'ArrowDown') {
				ev.preventDefault();
				if (self.histIdx < self.localHist.length - 1) { self.histIdx++; self.Q('at-cmd').value = self.localHist[self.histIdx] || ''; }
				else { self.histIdx = self.localHist.length; self.Q('at-cmd').value = ''; }
			}
		});
		root.querySelectorAll('.mud-chip').forEach(function(ch) {
			ch.onclick = function() { self.Q('at-cmd').value = ch.textContent; self.send(); };
		});
		this.Q('at-hist').addEventListener('click', function(ev) {
			if (ev.target && ev.target.getAttribute && ev.target.getAttribute('data-cmd')) {
				self.Q('at-cmd').value = ev.target.getAttribute('data-cmd');
				self.send();
			}
		});
	},

	loadHist: function() {
		var self = this;
		L.resolveDefault(M.callAtHist()).then(function(r) {
			r = r || {};
			var h = (r.history || '').split('\n').filter(Boolean).slice().reverse();
			self.Q('at-hist').innerHTML = h.length
				? h.map(function(l) {
					var cmd = l.replace(/^[0-9-]+ [0-9:]+ /, '');
					return '<div style="padding:2px 4px;border-radius:6px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis" data-cmd="' + M.esc(cmd) + '" title="' + M.esc(cmd) + '">' + M.esc(cmd) + '</div>';
				}).join('')
				: '<div class="mud-note">' + M.translate('（空）') + '</div>';
		});
	}
});
