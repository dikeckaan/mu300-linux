include $(TOPDIR)/rules.mk

PKG_NAME:=luci-app-mu300-speedtest
PKG_VERSION:=1.0.0
PKG_RELEASE:=6
PKG_LICENSE:=MIT AND LGPL-3.0-only
PKG_BUILD_DEPENDS:=luci-base/host

include $(INCLUDE_DIR)/package.mk

LUCI_MENU_TIMESTAMP:=$(shell date -u -d "@$$((1767225600 + $(PKG_RELEASE)))" +%Y%m%d%H%M.%S)

define Package/luci-app-mu300-speedtest
  SECTION:=luci
  CATEGORY:=LuCI
  SUBMENU:=3. Applications
  TITLE:=MU300 network speed test
  DEPENDS:=+luci-base
  PKGARCH:=all
endef

define Package/luci-app-mu300-speedtest/description
  Browser network speed test for the MU300 LuCI interface.
endef

define Build/Compile
	$(INSTALL_DIR) $(PKG_BUILD_DIR)
	$(STAGING_DIR_HOSTPKG)/bin/po2lmo ./po/zh_Hans/mu300-speedtest.po $(PKG_BUILD_DIR)/mu300-speedtest.zh-cn.lmo
endef

define Package/luci-app-mu300-speedtest/install
	$(INSTALL_DIR) $(1)/www
	$(CP) ./root/. $(1)/
	$(CP) ./htdocs/. $(1)/www/
	$(INSTALL_DATA) ./po/zh_Hans/speedtest.js $(1)/www/luci-static/resources/mu300-speedtest/r$(PKG_RELEASE)/zh-Hans.js
	TZ=UTC touch -t "$(LUCI_MENU_TIMESTAMP)" $(1)/usr/share/luci/menu.d/$(PKG_NAME).json
	$(INSTALL_DIR) $(1)/usr/lib/lua/luci/i18n
	$(INSTALL_DATA) $(PKG_BUILD_DIR)/mu300-speedtest.zh-cn.lmo $(1)/usr/lib/lua/luci/i18n/
endef

# The APK build can normalize file timestamps after staging.
define Package/luci-app-mu300-speedtest/postinst
TZ=UTC touch -t "$(LUCI_MENU_TIMESTAMP)" "$${IPKG_INSTROOT}/usr/share/luci/menu.d/$(PKG_NAME).json"
endef

$(eval $(call BuildPackage,luci-app-mu300-speedtest))
