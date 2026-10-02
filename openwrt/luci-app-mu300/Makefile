include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-mu300
PKG_VERSION:=1.0.1
PKG_RELEASE:=3
PKG_LICENSE:=MIT
PKG_MAINTAINER:=MU300 Linux contributors
PKGARCH:=all

include $(INCLUDE_DIR)/package.mk

define Package/luci-app-mu300
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=Unisoc modem control center
  DEPENDS:=+luci-base +rpcd +jsonfilter
endef

define Package/luci-app-mu300/description
 A single LuCI application for the MU300 dashboard, cellular locks, raw AT
 terminal and SMS. Platform adapters isolate the UI from the modem daemon,
 serial port, SMS store and network-interface layout of the host firmware.
endef

define Package/luci-app-mu300/conffiles
/etc/config/unisoc_modem
endef

define Build/Compile
endef

define Package/luci-app-mu300/install
	$(INSTALL_DIR) $(1)/www
	$(CP) ./htdocs/. $(1)/www/
	$(CP) ./root/. $(1)/
	chmod 0755 $(1)/etc/init.d/unisoc-modem-ui $(1)/etc/hotplug.d/net/90-unisoc-usb-host $(1)/etc/hotplug.d/iface/90-unisoc-usb-host $(1)/usr/libexec/rpcd/mu300dash $(1)/usr/libexec/unisoc-modem/*
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/i18n
	$(CP) ./lmo/. $(1)/usr/lib/lua/luci/i18n/
endef

define Package/luci-app-mu300/postinst
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	state=$$(uci -q get unisoc_modem.main.state_dir 2>/dev/null)
	state=$${state:-/etc/unisoc-modem/lock-state.d}
	old=/etc/mu300/dash/lock-state.d
	if [ -d "$$old" ] && [ ! -d "$$state" ]; then
		mkdir -p "$$state"
		cp -a "$$old"/. "$$state"/
	fi
	rm -f /tmp/luci-indexcache /tmp/luci-modulecache/* 2>/dev/null
	uci -q get luci.languages.tr >/dev/null || uci set luci.languages.tr='Türkçe'
	uci commit luci
	/etc/init.d/rpcd restart 2>/dev/null || true
	/etc/init.d/unisoc-modem-ui enable 2>/dev/null || true
	/etc/init.d/unisoc-modem-ui start 2>/dev/null || true
}
exit 0
endef

define Package/luci-app-mu300/postrm
#!/bin/sh
[ -n "$${IPKG_INSTROOT}" ] || {
	if [ "$$1" = remove ]; then
		/etc/init.d/unisoc-modem-ui stop 2>/dev/null || true
		/etc/init.d/unisoc-modem-ui disable 2>/dev/null || true
		rm -f /etc/unisoc-modem/usb-boot.conf
	fi
	rm -f /tmp/luci-indexcache /tmp/luci-modulecache/* 2>/dev/null
	/etc/init.d/rpcd restart 2>/dev/null || true
}
exit 0
endef

$(eval $(call BuildPackage,luci-app-mu300))
