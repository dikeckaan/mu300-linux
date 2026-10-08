'use strict';
'require view';
'require uci';
'require rpc';
'require form';
'require fs';

/* Keep LuCI's normal LED actions; add controls for the two physical status
 * lamps, whose channels are driven by led-status rather than kernel triggers.
 * Based on luci-mod-system's 25.12 LED view. */
const callLeds = rpc.declare({
	object: 'luci',
	method: 'getLEDs',
	expect: { '': {} }
});

return view.extend({
	load() {
		return Promise.all([
			callLeds(),
			L.resolveDefault(fs.list('/www' + L.resource('view/system/led-trigger')), [])
		]).then(function([leds, plugins]) {
			const tasks = [];

			for (let p of plugins) {
				const m = p.name.match(/^(.+)\.js$/);
				if (p.type != 'file' || m == null)
					continue;

				tasks.push(L.require('view.system.led-trigger.' + m[1]).then(L.bind(function(name) {
					return L.resolveDefault(L.require('view.system.led-trigger.' + name)).then(function(form) {
						return { name: name, form: form };
					});
				}, this, m[1])));
			}

			return Promise.all(tasks).then(function(plugins) {
				return [leds, plugins];
			});
		});
	},

	render([leds, plugins]) {
		let m, s, o;
		let wifiMax = leds['keyboard-backlight'] && Number(leds['keyboard-backlight'].max_brightness);
		if (!Number.isInteger(wifiMax) || wifiMax < 1 || wifiMax > 255) wifiMax = 255;
		const triggers = [];
		for (let k in leds)
			for (let t of leds[k].triggers)
				triggers.push(t);

		m = new form.Map('system',
			_('LED Configuration'),
			_('Configure physical status lamps and optional LED trigger actions.'));

		/* One RGB signal lamp and one separate Wi-Fi lamp. A single sysfs LED
		 * action cannot disable all RGB channels, while led-status would also
		 * overwrite its brightness at the next state change. */
		s = m.section(form.NamedSection, 'mu300_leds', 'mu300_leds', _('Physical status lamps'));
		s.anonymous = true;
		s.addremove = false;
		o = s.option(form.Flag, 'signal', _('Signal lamp (LTE / 5G / no service)'));
		o.default = '1';
		o.rmempty = false;
		o = s.option(form.Value, 'signal_brightness', _('Signal lamp brightness'),
			_('0–255; 0 is dark. LTE stays blue, 5G white, and no service red.'));
		o.datatype = 'range(0,255)';
		o.default = '255';
		o.rmempty = false;
		o = s.option(form.Flag, 'wifi', _('Wi-Fi hotspot lamp'));
		o.default = '1';
		o.rmempty = false;
		o = s.option(form.Value, 'wifi_brightness', _('Wi-Fi lamp brightness'),
			_('0 is dark. Hardware maximum: ') + wifiMax);
		o.datatype = 'range(0,' + wifiMax + ')';
		o.default = String(Math.min(127, wifiMax));
		o.rmempty = false;

		s = m.section(form.GridSection, 'led', '');
		s.anonymous = true;
		s.addremove = true;
		s.sortable = true;
		s.addbtntitle = _('Add LED action');
		s.nodescriptions = true;

		s.option(form.Value, 'name', _('Name'));
		o = s.option(form.ListValue, 'sysfs', _('LED Name'));
		Object.keys(leds).sort().forEach(function(name) {
			o.value(name);
		});
		o = s.option(form.ListValue, 'trigger', _('Trigger'));
		for (let plugin of plugins) {
			if (plugin.form.kernel == false) {
				o.value(plugin.name, plugin.form.trigger);
			} else if (triggers.indexOf(plugin.name) >= 0) {
				o.value(plugin.name, plugin.form.trigger);
			}
		}
		o.onchange = function(ev, section, value) {
			const nes = this.map.findElement('id', 'cbid.system.%s.trigger'.format(section)).nextElementSibling;
			for (let plugin of plugins) {
				if (plugin.name === value && nes)
					nes.innerText = plugin.form.description || '';
			}
		};
		o.load = function(section_id) {
			const trigger = uci.get('system', section_id, 'trigger');
			for (let plugin of plugins) {
				if (plugin.name === trigger)
					this.description = plugin.form.description || ' ';
			}
			return trigger;
		};
		s.addModalOptions = function(s) {
			for (let plugin of plugins)
				plugin.form.addFormOptions(s);

			const opts = s.getOption();
			const removeIfNoneActive = function(original_remove_fn, section_id) {
				let isAnyActive = false;
				for (let optname in opts) {
					if (opts[optname].ucioption != this.ucioption)
						continue;
					if (!opts[optname].isActive(section_id))
						continue;
					isAnyActive = true;
					break;
				}
				if (!isAnyActive)
					original_remove_fn.call(this, section_id);
			};

			for (let optname in opts) {
				if (!opts[optname].ucioption || optname == opts[optname].ucioption)
					continue;
				opts[optname].remove = removeIfNoneActive.bind(opts[optname], opts[optname].remove);
			}
		};
		o = s.option(form.Value, 'interval', _('Interval'), _('milliseconds'));
		o.placeholder = '50';

		return m.render();
	}
});
