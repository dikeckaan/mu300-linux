'use strict';
'require view';

return view.extend({
	render: function() {
		var frame = E('iframe', {
			'title': _('Network Speed Test'),
			'src': L.resource('mu300-speedtest/r6/index.html'),
			'referrerpolicy': 'no-referrer',
			'style': 'display:block;width:100%;height:70vh;min-height:26rem;border:0'
		});

		frame.addEventListener('load', function() {
			var body = frame.contentDocument && frame.contentDocument.body;
			var page = frame.contentWindow;

			if (!body || !page)
				return;

			function fit() {
				var height = Math.ceil(body.getBoundingClientRect().height);

				if (height > 0)
					frame.style.height = height + 'px';
			}

			fit();

			if (typeof page.ResizeObserver === 'function') {
				var observer = new page.ResizeObserver(function() {
					if (frame.isConnected)
						fit();
					else
						observer.disconnect();
				});

				observer.observe(body);
				page.addEventListener('pagehide', function(event) {
					if (!event.persisted)
						observer.disconnect();
				});
			}
		});

		return frame;
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
