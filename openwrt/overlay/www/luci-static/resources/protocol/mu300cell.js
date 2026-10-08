'use strict';
'require form';
'require network';

/* LuCI needs a handler per protocol or the interface page shows "unsupported protocol" and offers nothing to
   edit - which is what the modem interface looked like, even though /lib/netifd/proto/mu300cell.sh has read an
   apn option all along. The options here are exactly the ones that protocol handler understands. */

return network.registerProtocol('mu300cell', {
	getI18n: function() {
		return _('MU300 cellular');
	},

	getIfname: function() {
		return this._ubus('l3_device') || 'sipa_eth0';
	},

	getOpkgPackage: function() {
		return null;
	},

	/* the modem is reached over AT commands, not by claiming a network device, so there is nothing for the
	   user to pick in the device list */
	isFloating: function() {
		return true;
	},

	isVirtual: function() {
		return true;
	},

	getDevices: function() {
		return null;
	},

	containsDevice: function(ifname) {
		return (network.getIfnameOf(ifname) == this.getIfname());
	},

	renderFormOptions: function(s) {
        var o;

        o = s.taboption('general', form.ListValue, 'sim_slot', _('SIM source'),
            _('Applies after reboot. The internal SIM is available only on devices fitted with one.'));
        o.value('0', _('External SIM (slot 0)'));
        o.value('1', _('Internal SIM (slot 1)'));
        o.default = '0';

        o = s.taboption('general', form.Value, 'apn_internal', _('Internal SIM APN'),
            _('Use the APN supplied by the internal SIM provider. China Mobile was tested with cmnet.'));
        o.depends('sim_slot', '1');
        o.retain = true;
        o.placeholder = 'cmnet';

        o = s.taboption('general', form.ListValue, 'pdptype_internal', _('Internal SIM PDP type'));
        o.value('IPV4V6', _('IPv4 and IPv6'));
        o.value('IP', _('IPv4 only'));
        o.default = 'IPV4V6';
        o.depends('sim_slot', '1');
        o.retain = true;

		o = s.taboption('general', form.Value, 'apn', _('APN'),
			_('Leave empty unless the carrier needs a specific one. Empty means the modem keeps the context the SIM already defines, which is what most SIMs expect and what this device has been using.'));
		o.placeholder = _('whatever the SIM defines');
		o.depends('sim_slot', '0');
		o.retain = true;

		o = s.taboption('general', form.ListValue, 'pdptype', _('PDP type'),
			_('IPv4 only is what Android asks this modem for, and what has been measured working here. Ask for both only if the carrier requires it.'));
		o.value('IP', _('IPv4 only (default)'));
		o.value('IPV4V6', _('IPv4 and IPv6'));
		o.default = 'IP';
		o.depends('sim_slot', '0');
		o.retain = true;

		o = s.taboption('general', form.Flag, 'peerdns', _('Use DNS servers advertised by peer'));
		o.default = o.enabled;

		o = s.taboption('general', form.DynamicList, 'dns', _('Use custom DNS servers'));
		o.depends('peerdns', '0');
		o.datatype = 'ipaddr';
	}
});
