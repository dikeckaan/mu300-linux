'use strict';
'require rpc';
'require baseclass';
/* mu300 面板共享模块：rpc 声明、格式化/信号质量助手、主题感知的样式表。
 * 页面通过 'require mu300.common' 引用（LuCI 的 dotted require 映射到
 * /luci-static/resources/mu300/common.js）。
 *
 * 样式只引用主题令牌：本机装的是 luci-theme-aurora（--surface/--hairline/
 * --brand/--text-muted/--success 等，html[data-darkmode] 一键翻转深浅色），
 * 其它主题时逐级回退到 LuCI 标准变量（--background-alt/--border/--primary...）。
 * 质量色不用写死的色值，走 --success/--warning/--danger 与 color-mix，
 * 深浅两套模式都跟随主题。 */

var callStatus = rpc.declare({ object: 'mu300dash', method: 'status', expect: { '': {} } });
var callSignal = rpc.declare({ object: 'mu300dash', method: 'signal', expect: { '': {} } });
var callSysinfo = rpc.declare({ object: 'mu300dash', method: 'sysinfo', expect: { '': {} } });
var callAct    = rpc.declare({ object: 'mu300dash', method: 'act', params: [ 'op', 'arg' ], expect: { '': {} } });
var callAt     = rpc.declare({ object: 'mu300dash', method: 'at', params: [ 'cmd' ], expect: { '': {} } });
var callAtHist = rpc.declare({ object: 'mu300dash', method: 'at_history', expect: { '': {} } });
var callLockGet = rpc.declare({ object: 'mu300dash', method: 'lock_get', expect: { '': {} } });
var callLockFresh = rpc.declare({ object: 'mu300dash', method: 'lock_get', params: [ 'fresh' ], expect: { '': {} } });
var callLockSet = rpc.declare({ object: 'mu300dash', method: 'lock_set', params: [ 'kind', 'val' ], expect: { '': {} } });
var callSmsList = rpc.declare({ object: 'mu300dash', method: 'sms_list', params: [ 'page' ], expect: { '': {} } });
var callSmsShow = rpc.declare({ object: 'mu300dash', method: 'sms_show', params: [ 'id' ], expect: { '': {} } });
var callSmsSend = rpc.declare({ object: 'mu300dash', method: 'sms_send', params: [ 'num', 'text' ], expect: { '': {} } });
var callSmsDel  = rpc.declare({ object: 'mu300dash', method: 'sms_delete', params: [ 'id', 'sim' ], expect: { '': {} } });
var callSmsSync = rpc.declare({ object: 'mu300dash', method: 'sms_sync', expect: { '': {} } });

/* Dashboard translations deliberately ship as a tiny runtime catalog: a
 * standalone package works in any OpenWrt buildroot without po2lmo or extra
 * language packages. Chinese remains the source/fallback language. */
var DASH_I18N = {
	'链路与流量': ['Link & traffic', 'Bağlantı ve trafik'],
	'下行速率': ['Download rate', 'İndirme hızı'],
	'上行速率': ['Upload rate', 'Yükleme hızı'],
	'累计接收': ['Total received', 'Toplam alınan'],
	'累计发送': ['Total sent', 'Toplam gönderilen'],
	'会话时长': ['Session duration', 'Oturum süresi'],
	'注册状态': ['Registration', 'Kayıt durumu'],
	'调制方式 下/上': ['Modulation DL/UL', 'Modülasyon İndirme/Yükleme'],
	'MCS 下/上': ['MCS DL/UL', 'MCS İndirme/Yükleme'],
	'BLER 下/上': ['BLER DL/UL', 'BLER İndirme/Yükleme'],
	'按当前 MCS 估算': ['Estimated from current MCS', 'Geçerli MCS değerinden tahmin'],
	'频宽': ['Bandwidth', 'Bant genişliği'],
	'AMBR 下/上': ['AMBR DL/UL', 'AMBR İndirme/Yükleme'],
	'无线 · 局域网 · 设备 · SIM': ['Wi-Fi · LAN · Device · SIM', 'Wi-Fi · LAN · Cihaz · SIM'],
	'CPU 占用': ['CPU usage', 'CPU kullanımı'],
	'内存': ['Memory', 'Bellek'],
	'存储': ['Storage', 'Depolama'],
	'电源': ['Power', 'Güç'],
	'信道': ['Channel', 'Kanal'],
	'加密': ['Encryption', 'Şifreleme'],
	'隐藏 SSID': ['Hidden SSID', 'Gizli SSID'],
	'国家': ['Country', 'Ülke'],
	'AP 状态': ['AP status', 'AP durumu'],
	'USB 网络': ['USB network', 'USB ağı'],
	'连接跟踪': ['Connection tracking', 'Bağlantı izleme'],
	'LAN 地址': ['LAN address', 'LAN adresi'],
	'无线客户端': ['Wi-Fi clients', 'Wi-Fi istemcileri'],
	'DHCP 租约': ['DHCP leases', 'DHCP kiraları'],
	'设备型号': ['Device model', 'Cihaz modeli'],
	'系统': ['System', 'Sistem'],
	'调制解调器': ['Modem', 'Modem'],
	'运营商': ['Carrier', 'Operatör'],
	'模组': ['Module', 'Modül'],
	'固件': ['Firmware', 'Ürün yazılımı'],
	'显示卡号信息': ['Show SIM identifiers', 'SIM kimliklerini göster'],
	'隐藏卡号信息': ['Hide SIM identifiers', 'SIM kimliklerini gizle'],
	'快捷控制': ['Quick controls', 'Hızlı denetimler'],
	'数据连接': ['Data connection', 'Veri bağlantısı'],
	'蜂窝射频': ['Cellular radio', 'Hücresel radyo'],
	'Wi-Fi 热点': ['Wi-Fi hotspot', 'Wi-Fi erişim noktası'],
	'重启调制解调器': ['Restart modem', 'Modemi yeniden başlat'],
	'重启设备': ['Restart device', 'Cihazı yeniden başlat'],
	'切换到 Android': ['Switch to Android', 'Android’e geç'],
	'邻区': ['Neighbor cells', 'Komşu hücreler'],
	'制式/频段': ['RAT/Band', 'Teknoloji/Bant'],
	'频点': ['Frequency', 'Frekans'],
	'暂无邻区数据': ['No neighbor-cell data', 'Komşu hücre verisi yok'],
	'已锁定': ['Locked', 'Kilitli'],
	'锁定小区': ['Lock cell', 'Hücreyi kilitle'],
	'锁定': ['Lock', 'Kilitle'],
	'已运行': ['Uptime', 'Çalışma süresi'],
	'无线电已关': ['Radio off', 'Radyo kapalı'],
	'未驻留小区': ['No serving cell', 'Bağlı olunan hücre yok'],
	'无应答': ['No response', 'Yanıt yok'],
	'信号': ['Signal', 'Sinyal'],
	'优秀': ['Excellent', 'Mükemmel'],
	'良好': ['Good', 'İyi'],
	'一般': ['Fair', 'Orta'],
	'较差': ['Poor', 'Zayıf'],
	'未知': ['Unknown', 'Bilinmiyor'],
	'未注册': ['Not registered', 'Kayıtlı değil'],
	'已注册（漫游）': ['Registered (roaming)', 'Kayıtlı (dolaşım)'],
	'已注册': ['Registered', 'Kayıtlı'],
	'搜索中': ['Searching', 'Aranıyor'],
	'注册被拒': ['Registration denied', 'Kayıt reddedildi'],
	'仅紧急': ['Emergency only', 'Yalnızca acil arama'],
	'状态': ['Status', 'Durum'],
	'LTE 锚点': ['LTE anchor', 'LTE bağlantı noktası'],
	'LTE 链路': ['LTE link', 'LTE bağlantısı'],
	'锚点': ['Anchor', 'Bağlantı noktası'],
	'已隐藏': ['Hidden', 'Gizli'],
	'运行中': ['Running', 'Çalışıyor'],
	'未运行': ['Not running', 'Çalışmıyor'],
	'已连接': ['Connected', 'Bağlı'],
	'未连接': ['Disconnected', 'Bağlı değil'],
	'未读': ['unread', 'okunmamış'],
	' 条未读': [' unread', ' okunmamış'],
	'约半分钟': ['about 30 seconds', 'yaklaşık 30 saniye'],
	'近期 DHCP 租约': ['Recent DHCP leases', 'Son DHCP kiraları'],
	'主板': ['Board', 'Anakart'],
	'无温度读数': ['No temperature readings', 'Sıcaklık verisi yok'],
	'在线': ['Online', 'Çevrimiçi'],
	'AT 适配器不可用': ['AT adapter unavailable', 'AT bağdaştırıcısı kullanılamıyor'],
	'正在执行': ['Running', 'Çalıştırılıyor'],
	'已后台执行': ['Started in background', 'Arka planda başlatıldı'],
	'已执行': ['Done', 'Tamamlandı'],
	'失败': ['Failed', 'Başarısız'],
	'未知错误': ['Unknown error', 'Bilinmeyen hata'],
	'调用失败': ['Request failed', 'İstek başarısız'],
	'正在断开数据连接': ['Disconnecting data', 'Veri bağlantısı kesiliyor'],
	'正在拨号': ['Connecting data', 'Veri bağlantısı kuruluyor'],
	'关闭蜂窝射频': ['Turn off cellular radio', 'Hücresel radyoyu kapat'],
	'打开蜂窝射频': ['Turn on cellular radio', 'Hücresel radyoyu aç'],
	'蜂窝连接会中断': ['Cellular connectivity will be interrupted', 'Hücresel bağlantı kesilecek'],
	'将执行 SFUN 上电序列（最多约 1 分钟）': ['The SFUN power-on sequence will run (up to about 1 minute)', 'SFUN açılış sırası çalışacak (yaklaşık 1 dakikaya kadar)'],
	'蜂窝连接会中断 1-2 分钟': ['Cellular connectivity may stop for 1–2 minutes', 'Hücresel bağlantı 1–2 dakika kesilebilir'],
	'重启整个设备': ['Restart the entire device', 'Tüm cihazı yeniden başlat'],
	'所有连接会断开': ['All connections will be interrupted', 'Tüm bağlantılar kesilecek'],
	'切换到 Android 系统': ['Switch to Android', 'Android sistemine geç'],
	'下次启动将进入 Android 并立即重启，此管理页面与蜂窝共享都会断开': ['The next boot will enter Android and reboot now. This management page and cellular sharing will disconnect', 'Sonraki açılış Android’e geçecek ve cihaz şimdi yeniden başlayacak. Yönetim sayfası ve hücresel paylaşım kesilecek'],
	'回到 OpenWrt：在 Android 上执行 mu300-next-boot linux 后重启': ['To return to OpenWrt, run mu300-next-boot linux in Android and reboot', 'OpenWrt’ye dönmek için Android’de mu300-next-boot linux çalıştırıp yeniden başlatın'],
	'或什么都不做，连续 5 次开机未完成会自动回退': ['Or do nothing: five failed boots trigger automatic fallback', 'Ya da hiçbir şey yapmayın: beş başarısız açılışta otomatik geri dönülür'],
	'切换并重启': ['Switch and reboot', 'Geç ve yeniden başlat'],
	'正在武装 Android 引导并重启': ['Preparing Android boot and rebooting', 'Android açılışı hazırlanıyor ve yeniden başlatılıyor'],
	'协议栈会重启（SFUN），蜂窝断开约半分钟': ['The radio stack will restart (SFUN); cellular service will stop for about 30 seconds', 'Radyo yığını yeniden başlayacak (SFUN); hücresel bağlantı yaklaşık 30 saniye kesilecek'],
	'正在后台锁定': ['Locking in background', 'Arka planda kilitleniyor'],
	'已后台锁定': ['Lock started in background', 'Kilit arka planda başlatıldı'],
	'稍后自动刷新状态': ['status will refresh shortly', 'durum birazdan yenilenecek'],
	'锁定失败': ['Lock failed', 'Kilitleme başarısız'],
	'确认': ['Confirm', 'Onayla'],
	'确定': ['OK', 'Tamam'],
	'取消': ['Cancel', 'İptal'],
	'新短信': ['New SMS', 'Yeni SMS'],
	'未知号码': ['Unknown number', 'Bilinmeyen numara'],
	'中国移动': ['China Mobile', 'China Mobile'],
	'中国联通': ['China Unicom', 'China Unicom'],
	'中国电信': ['China Telecom', 'China Telecom'],
	'中国广电': ['China Broadnet', 'China Broadnet'],
	'中国铁通': ['China Tietong', 'China Tietong'],
	' 天 ': [' d ', ' gün '],
	' 小时': [' h', ' sa'],
	' 分': [' min', ' dk'],
	' 条': [' entries', ' kayıt'],
	' 台': [' clients', ' istemci'],
	' 簇': [' cluster', ' küme'],
	'共 ': ['Total ', 'Toplam '],
	'余 ': ['Free ', 'Boş '],
	'簇': ['Cluster ', 'Küme '],
	'否': ['No', 'Hayır'],
	'状态看板': ['Dashboard', 'Durum paneli'],
	'蜂窝': ['Cellular', 'Hücresel'],
	'网络锁定': ['Network locks', 'Ağ kilitleri'],
	'短信': ['SMS', 'SMS'],
	'AT 终端': ['AT terminal', 'AT terminali'],
	'适配设置': ['Adapter settings', 'Bağdaştırıcı ayarları'],
	'当前驻网': ['Serving network', 'Bağlı olunan ağ'],
	'网络模式 · EN-DC': ['Network mode · EN-DC', 'Ağ modu · EN-DC'],
	'自动（5G/4G）': ['Automatic (5G/4G)', 'Otomatik (5G/4G)'],
	'仅 4G': ['4G only', 'Yalnızca 4G'],
	'仅 5G SA': ['5G SA only', 'Yalnızca 5G SA'],
	'仅 5G NSA': ['5G NSA only', 'Yalnızca 5G NSA'],
	'自动': ['Automatic', 'Otomatik'],
	'刷新锁定状态': ['Refresh lock status', 'Kilit durumunu yenile'],
	'开机自动应用': ['Apply at startup', 'Başlangıçta uygula'],
	'开机自动应用已': ['Apply at startup is ', 'Başlangıçta uygulama '],
	'关闭后只停止下次开机回放，已保存的网络模式、EN-DC、频段和小区配置不会被删除。': ['Turning this off only stops replay at the next boot; saved network mode, EN-DC, band and cell settings remain.', 'Kapatılması yalnızca sonraki açılışta yeniden uygulamayı durdurur; kayıtlı ağ modu, EN-DC, bant ve hücre ayarları korunur.'],
	'频段锁定': ['Band locking', 'Bant kilitleme'],
	'NR 频段': ['NR bands', 'NR bantları'],
	'LTE 频段': ['LTE bands', 'LTE bantları'],
	'应用 NR 频段': ['Apply NR bands', 'NR bantlarını uygula'],
	'应用 LTE 频段': ['Apply LTE bands', 'LTE bantlarını uygula'],
	'邻区与小区锁定': ['Neighbor cells and cell locking', 'Komşu hücreler ve hücre kilidi'],
	'锁定当前服务小区': ['Lock current serving cell', 'Geçerli hizmet hücresini kilitle'],
	'解除小区锁定': ['Unlock cell', 'Hücre kilidini kaldır'],
	'已锁定小区': ['Locked cells', 'Kilitli hücreler'],
	'解锁': ['Unlock', 'Kilidi kaldır'],
	' 小区锁定': [' cell lock', ' hücre kilidi'],
	' 的小区锁定': [' cell lock', ' hücre kilidi'],
	'应用后协议栈重启（SFUN），蜂窝会短暂断开；设置会持久保存，并在启用“开机自动应用”时由插件于 AT 就绪后回放。接入平台的射频前钩子时可无重启回放。频段全不选再点应用 = 恢复自动。': ['Applying restarts the radio stack (SFUN) and briefly interrupts cellular service. Settings are saved and replayed by the plugin after AT is ready when Apply at startup is enabled. A platform pre-radio hook can replay without a restart. Apply with no bands selected to restore automatic mode.', 'Uygulama radyo yığınını (SFUN) yeniden başlatır ve hücresel bağlantıyı kısa süre keser. Ayarlar kaydedilir ve Başlangıçta uygula etkinse AT hazır olduğunda eklenti tarafından yeniden uygulanır. Platformun radyo öncesi kancasıyla yeniden başlatmadan uygulanabilir. Otomatik moda dönmek için hiçbir bant seçmeden uygulayın.'],
	'正在后台应用': ['Applying in background', 'Arka planda uygulanıyor'],
	'协议栈会重启（SFUN），约半分钟': ['The radio stack will restart (SFUN), taking about 30 seconds', 'Radyo yığını yeniden başlayacak (SFUN), yaklaşık 30 saniye sürecek'],
	'协议栈会重启（SFUN），蜂窝断开约半分钟': ['The radio stack will restart (SFUN); cellular service will stop for about 30 seconds', 'Radyo yığını yeniden başlayacak (SFUN); hücresel bağlantı yaklaşık 30 saniye kesilecek'],
	'SFUN 重启约半分钟': ['SFUN restart takes about 30 seconds', 'SFUN yeniden başlatması yaklaşık 30 saniye sürer'],
	'SFUN 重启 + 重新驻网，约半分钟': ['SFUN restart and re-registration take about 30 seconds', 'SFUN yeniden başlatması ve ağa yeniden kayıt yaklaşık 30 saniye sürer'],
	'约半分钟': ['about 30 seconds', 'yaklaşık 30 saniye'],
	'自动回读状态': ['status will be read back automatically', 'durum otomatik olarak geri okunacak'],
	'NR 频段锁定': ['NR band lock', 'NR bant kilidi'],
	'LTE 频段锁定': ['LTE band lock', 'LTE bant kilidi'],
	'选择': ['Select', 'Seç'],
	'已后台执行': ['Started in background', 'Arka planda başlatıldı'],
	'已排队：另一项锁定正在应用（SFUN 重启中），随后自动生效': ['Queued: another lock is being applied during SFUN restart; this will take effect afterward', 'Sıraya alındı: SFUN yeniden başlarken başka bir kilit uygulanıyor; ardından etkinleşecek'],
	'正在确认 EN-DC 状态': ['Confirming EN-DC status', 'EN-DC durumu doğrulanıyor'],
	'正在确认开机自动应用': ['Confirming startup setting', 'Başlangıç ayarı doğrulanıyor'],
	'正在直读调制解调器（最多几秒）': ['Reading modem directly (a few seconds at most)', 'Modem doğrudan okunuyor (en fazla birkaç saniye)'],
	'已刷新': ['Refreshed', 'Yenilendi'],
	'刷新失败': ['Refresh failed', 'Yenileme başarısız'],
	'暂无驻网数据': ['No serving-network data', 'Bağlı olunan ağ verisi yok'],
	'NR 服务小区': ['NR serving cell', 'NR hizmet hücresi'],
	'回读超时，请点「刷新锁定状态」': ['Readback timed out; select “Refresh lock status”', 'Geri okuma zaman aşımına uğradı; “Kilit durumunu yenile”yi seçin'],
	'状态已回读': ['Status confirmed', 'Durum doğrulandı'],
	'已生效（EN-DC 不需要重启协议栈）': ['Applied (EN-DC does not require a radio-stack restart)', 'Uygulandı (EN-DC için radyo yığını yeniden başlatılmaz)'],
	'状态回读超时，点「刷新锁定状态」确认': ['Status readback timed out; use “Refresh lock status” to confirm', 'Durum geri okuması zaman aşımına uğradı; doğrulamak için “Kilit durumunu yenile”yi kullanın'],
	'已锁': ['Locked', 'Kilitli'],
	'支持': ['supported', 'destekleniyor'],
	' 个会话': [' conversations', ' görüşme'],
	' 个': [' bands', ' bant'],
	'网络模式': ['Network mode', 'Ağ modu'],
	'关闭 EN-DC': ['Disable EN-DC', 'EN-DC’yi kapat'],
	'开启 EN-DC': ['Enable EN-DC', 'EN-DC’yi aç'],
	'关闭开机自动应用': ['Disable apply at startup', 'Başlangıçta uygulamayı kapat'],
	'开启开机自动应用': ['Enable apply at startup', 'Başlangıçta uygulamayı aç'],
	'关闭': ['Disabled', 'Kapalı'],
	'开启': ['Enabled', 'Açık'],
	'已开启': [' enabled', ' etkin'],
	'已关闭': [' disabled', ' devre dışı'],
	'应用': ['Apply', 'Uygula'],
	'恢复自动': ['Restore automatic', 'Otomatiğe dön'],
	'解除': ['Unlock', 'Kilidi kaldır'],
	'正在解除': ['Unlocking', 'Kilit kaldırılıyor'],
	'解锁失败': ['Unlock failed', 'Kilit kaldırılamadı'],
	'已后台解除': ['Unlock started in background', 'Kilit kaldırma arka planda başlatıldı'],
	'重新驻网': ['re-registering', 'yeniden ağa kaydoluyor'],
	'回读状态': ['read back status', 'durumu geri oku'],
	'基础': ['Basic', 'Temel'],
	'注册/信号': ['Registration/signal', 'Kayıt/sinyal'],
	'承载': ['Bearer', 'Taşıyıcı'],
	'工程模式': ['Engineering mode', 'Mühendislik modu'],
	'AT 命令（↑↓ 翻历史，Enter 发送）': ['AT command (↑↓ history, Enter to send)', 'AT komutu (↑↓ geçmiş, göndermek için Enter)'],
	'发送': ['Send', 'Gönder'],
	'清屏': ['Clear screen', 'Ekranı temizle'],
	'就绪': ['Ready', 'Hazır'],
	'会话历史（点击复用）': ['Session history (click to reuse)', 'Oturum geçmişi (yeniden kullanmak için tıklayın)'],
	'无输出': ['No output', 'Çıktı yok'],
	'错误': ['Error', 'Hata'],
	'AT 通道正忙，命令未发出': ['AT channel busy; command not sent', 'AT kanalı meşgul; komut gönderilmedi'],
	'空': ['Empty', 'Boş'],
	'收件人：号码，如 10086 或 +86...': ['Recipient: number, e.g. 10086 or +86...', 'Alıcı: numara, ör. 10086 veya +86...'],
	'刷新': ['Refresh', 'Yenile'],
	'从 SIM 同步': ['Sync from SIM', 'SIM’den eşitle'],
	'清空本地池': ['Clear local pool', 'Yerel havuzu temizle'],
	'加载中': ['Loading', 'Yükleniyor'],
	'选择左侧会话，或直接在下方输入号码发送。': ['Select a conversation on the left, or enter a number below to send.', 'Soldan bir görüşme seçin veya göndermek için aşağıya bir numara girin.'],
	'短信内容（Enter 发送，Shift+Enter 换行）': ['Message (Enter to send, Shift+Enter for newline)', 'Mesaj (göndermek için Enter, yeni satır için Shift+Enter)'],
	'发送走 AT+CMGS（PDU 模式）；通道忙会提示重试。删除单条：在气泡上右键（手机长按）。': ['Sending uses AT+CMGS (PDU mode); retry if the channel is busy. To delete one message, right-click its bubble (long-press on mobile).', 'Gönderme AT+CMGS (PDU modu) kullanır; kanal meşgulse yeniden deneyin. Bir mesajı silmek için balona sağ tıklayın (mobilde uzun basın).'],
	'正在后台从 SIM 同步（AT+CMGL）': ['Syncing from SIM in background (AT+CMGL)', 'SIM’den arka planda eşitleniyor (AT+CMGL)'],
	'SIM 同步已开始，几秒后自动刷新': ['SIM sync started; refreshing shortly', 'SIM eşitlemesi başladı; birazdan yenilenecek'],
	'清空本地短信池': ['Clear local SMS pool', 'Yerel SMS havuzunu temizle'],
	'只删本地文件，SIM 上的不动': ['Only local files will be deleted; messages on the SIM remain.', 'Yalnızca yerel dosyalar silinir; SIM’deki mesajlar korunur.'],
	'清空': ['Clear', 'Temizle'],
	'删除这条短信': ['Delete this SMS', 'Bu SMS’i sil'],
	'删除后不可恢复': ['Deletion cannot be undone', 'Silme işlemi geri alınamaz'],
	'仅删本地': ['Local only', 'Yalnızca yerel'],
	'本地 + SIM': ['Local + SIM', 'Yerel + SIM'],
	'删除失败': ['Delete failed', 'Silme başarısız'],
	'已删除': ['Deleted', 'Silindi'],
	'已删除（仅本地）': ['Deleted (local only)', 'Silindi (yalnızca yerel)'],
	'删除': ['Delete', 'Sil'],
	'号码和内容都要填': ['Enter both a number and a message', 'Numara ve mesaj girin'],
	'发送中': ['Sending', 'Gönderiliyor'],
	'已发送，稍后自动刷新': ['Sent; refreshing shortly', 'Gönderildi; birazdan yenilenecek'],
	'发送失败': ['Send failed', 'Gönderme başarısız'],
	'AT 通道正忙，稍后重试': ['AT channel busy; retry shortly', 'AT kanalı meşgul; birazdan yeniden deneyin'],
	'池子是空的：收到/发出的短信会出现在这里，或点「从 SIM 同步」。': ['The pool is empty. Incoming and sent messages appear here, or select “Sync from SIM”.', 'Havuz boş. Gelen ve gönderilen mesajlar burada görünür veya “SIM’den eşitle”yi seçin.'],
	'我: ': ['Me: ', 'Ben: '],
	'这里定义插件与当前紫光 OpenWrt 的边界。修改后无需改动看板、AT、锁定或短信页面。': ['Configure how this plugin connects to the current Unisoc OpenWrt platform. Changes do not require editing the dashboard, AT, locks or SMS pages.', 'Bu eklentinin mevcut Unisoc OpenWrt platformuna nasıl bağlandığını yapılandırın. Değişiklikler panel, AT, kilit veya SMS sayfalarını düzenlemeyi gerektirmez.'],
	'平台适配': ['Platform adapter', 'Platform bağdaştırıcısı'],
	'AT 后端': ['AT backend', 'AT arka ucu'],
	'自动检测': ['Auto-detect', 'Otomatik algıla'],
	'atinout + 串口': ['atinout + serial port', 'atinout + seri port'],
	'自定义适配器': ['Custom adapter', 'Özel bağdaştırıcı'],
	'AT 串口': ['AT serial port', 'AT seri portu'],
	'自定义 AT 适配器': ['Custom AT adapter', 'Özel AT bağdaştırıcısı'],
	'可执行文件依次接收超时秒数和完整 AT 命令。它必须与平台拨号程序共享串口锁。': ['The executable receives a timeout in seconds and the complete AT command, in that order. It must share the serial lock with the platform dialer.', 'Yürütülebilir dosya sırayla saniye cinsinden zaman aşımını ve tam AT komutunu alır. Seri port kilidini platform arama programıyla paylaşmalıdır.'],
	'短信适配器': ['SMS adapter', 'SMS bağdaştırıcısı'],
	'实现 list、show、send、delete、sync 子命令；留空时自动查找 mu300-sms。': ['Implement the list, show, send, delete and sync subcommands; leave blank to find mu300-sms automatically.', 'list, show, send, delete ve sync alt komutlarını uygulayın; mu300-sms otomatik bulunsun diye boş bırakın.'],
	'短信池目录': ['SMS pool directory', 'SMS havuzu dizini'],
	'蜂窝逻辑接口': ['Cellular logical interface', 'Hücresel mantıksal arabirim'],
	'蜂窝 IPv6 接口': ['Cellular IPv6 interface', 'Hücresel IPv6 arabirimi'],
	'蜂窝网卡': ['Cellular network device', 'Hücresel ağ aygıtı'],
	'留空则从 netifd 自动获取': ['Leave blank to detect from netifd', 'netifd’den otomatik algılamak için boş bırakın'],
	'LAN 网桥': ['LAN bridge', 'LAN köprüsü'],
	'Wi-Fi 网卡': ['Wi-Fi device', 'Wi-Fi aygıtı'],
	'USB 网卡': ['USB device', 'USB aygıtı'],
	'等待 AT 就绪上限（秒）': ['Maximum wait for AT readiness (seconds)', 'AT hazır olma üst bekleme süresi (saniye)'],
	'持久化状态目录': ['Persistent state directory', 'Kalıcı durum dizini'],
	'，': [', ', ', '],
	'。': ['.', '.'],
	'；': ['; ', '; '],
	'：': [': ', ': '],
	'（': ['(', '('],
	'）': [')', ')'],
	'？': ['?', '?'],
	'「': ['“', '“'],
	'」': ['”', '”']
};
var DASH_KEYS = Object.keys(DASH_I18N).sort(function(a, b) { return b.length - a.length; });
var DASH_PATTERN = new RegExp(DASH_KEYS.map(function(k) { return k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }).join('|'), 'g');
function uiLanguage() {
	var lang = (L.env && L.env.lang) || document.documentElement.lang || navigator.language || 'en';
	if (lang === 'auto') lang = document.documentElement.lang || navigator.language || 'en';
	lang = String(lang).toLowerCase().replace('_', '-');
	return lang.indexOf('zh') === 0 ? 'zh' : lang.indexOf('tr') === 0 ? 'tr' : 'en';
}
function translate(text) {
	var lang = uiLanguage();
	if (lang === 'zh' || text == null) return String(text == null ? '' : text);
	var column = lang === 'tr' ? 1 : 0;
	return String(text).replace(DASH_PATTERN, function(key) { return DASH_I18N[key][column]; });
}
function localize(root) {
	if (uiLanguage() === 'zh' || !root) return;
	var walk = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), node;
	while ((node = walk.nextNode())) {
		if (node.parentElement && /^(SCRIPT|STYLE|TEXTAREA)$/.test(node.parentElement.tagName)) continue;
		var translated = translate(node.nodeValue);
		if (translated !== node.nodeValue) node.nodeValue = translated;
	}
	var elements = [root].concat(Array.prototype.slice.call(root.querySelectorAll('*')));
	elements.forEach(function(el) {
		[ 'title', 'placeholder', 'aria-label' ].forEach(function(attr) {
			if (el.hasAttribute && el.hasAttribute(attr)) el.setAttribute(attr, translate(el.getAttribute(attr)));
		});
	});
}
var menuObserver, menuRoot;
function localizeMenu() {
	/* Bootstrap builds #topmenu asynchronously, often after the view renders.
	 * Its parent dropdown uses href="#", so link-URL matching alone misses 蜂窝. */
	var root = document.getElementById('topmenu');
	if (!root || !root.querySelectorAll) return;
	var update = function() {
		if (uiLanguage() === 'zh') return;
		Array.prototype.forEach.call(root.querySelectorAll('a[href*="/admin/home"], a[href*="/admin/modem"]'), localize);
		Array.prototype.forEach.call(root.children, function(li) {
			var a = li.querySelector('a');
			if (a && a.textContent.trim() === '蜂窝') localize(a);
		});
	};
	if (menuRoot !== root) {
		if (menuObserver) menuObserver.disconnect();
		menuRoot = root;
		if (typeof MutationObserver !== 'undefined') {
			menuObserver = new MutationObserver(update);
			menuObserver.observe(root, { childList: true, subtree: true });
		}
	}
	update();
}

/* 大陆运营商 PLMN -> 名称；COPS 给数字格式时用它还原 */
var PLMN_CN = {
	'46000': '中国移动', '46002': '中国移动', '46004': '中国移动', '46007': '中国移动', '46008': '中国移动',
	'46001': '中国联通', '46006': '中国联通', '46009': '中国联通',
	'46003': '中国电信', '46005': '中国电信', '46011': '中国电信', '46012': '中国电信',
	'46015': '中国广电', '46020': '中国铁通'
};

function carrierName(op) {
	if (!op) return '--';
	return translate(op.name || PLMN_CN[op.plmn] || op.plmn || '--');
}

/* 信号质量分级（阈值来自 ufi_tools 的 SignalQuality.kt），返回 CSS 颜色表达式 */
function qLabel(rsrp, rsrq, sinr) {
	if (rsrp == null && sinr == null && rsrq == null) return '未知';
	if (rsrp != null) {
		if (rsrp >= -90) return '优秀';
		if (rsrp >= -100) return '良好';
		if (rsrp >= -110) return '一般';
		return '较差';
	}
	if (sinr != null) {
		if (sinr >= 20) return '优秀';
		if (sinr >= 13) return '良好';
		if (sinr >= 0) return '一般';
		return '较差';
	}
	if (rsrq >= -8) return '优秀';
	if (rsrq >= -11) return '良好';
	if (rsrq >= -14) return '一般';
	return '较差';
}
function qCol(label) {
	switch (label) {
		case '优秀': return 'var(--success, #2FBF71)';
		case '良好': return 'color-mix(in oklab, var(--success, #7BC96F) 62%, var(--text, #444))';
		case '一般': return 'var(--warning, #F2B544)';
		case '较差': return 'var(--danger, #E25555)';
		default:     return 'var(--text-subtle, var(--text-light, #8A8F98))';
	}
}
/* 10 分制：RSRP 40% / RSRQ 25% / SINR 35%，锚点插值，缺项权重重分配 */
function interp(v, pts) {
	if (v == null) return null;
	for (var i = 0; i < pts.length - 1; i++)
		if (v <= pts[i][0])
			return pts[i][1] + (v - pts[i][0]) * (pts[i+1][1] - pts[i][1]) / (pts[i+1][0] - pts[i][0]);
	return pts[pts.length - 1][1];
}
function qScore(s) {
	var parts = [
		[ interp(s.rsrp, [ [ -120, 0 ], [ -110, 3.5 ], [ -100, 6.5 ], [ -90, 8.5 ], [ -80, 10 ] ]), 0.40 ],
		[ interp(s.rsrq, [ [ -20, 0 ], [ -14, 3.5 ], [ -11, 6.5 ], [ -8, 8.5 ], [ -3, 10 ] ]), 0.25 ],
		[ interp(s.sinr, [ [ -5, 0 ], [ 0, 3.5 ], [ 13, 6.5 ], [ 20, 8.5 ], [ 30, 10 ] ]), 0.35 ]
	];
	var sum = 0, w = 0;
	parts.forEach(function(p) { if (p[0] != null) { sum += p[0] * p[1]; w += p[1]; } });
	return w == 0 ? null : Math.max(0, Math.min(10, sum / w));
}

/* ---------------------------------------------------------------- 格式化 */
function esc(s) {
	return String(s == null ? '' : s).replace(/[&<>"']/g, function(c) {
		return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
	});
}
function fmtBytes(b) {
	if (b == null || isNaN(b)) return '--';
	var u = [ 'B', 'KB', 'MB', 'GB', 'TB' ], i = 0;
	while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
	return (b >= 100 ? b.toFixed(0) : b.toFixed(1)) + ' ' + u[i];
}
function fmtRate(bps) {
	if (bps == null || isNaN(bps) || bps < 0) return '--';
	var u = [ 'B/s', 'KB/s', 'MB/s', 'GB/s' ], i = 0;
	while (bps >= 1024 && i < u.length - 1) { bps /= 1024; i++; }
	return (bps >= 100 ? bps.toFixed(0) : bps.toFixed(1)) + ' ' + u[i];
}
function fmtUptime(s) {
	if (s == null) return '--';
	var d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
	if (d > 0) return d + ' 天 ' + h + ' 小时';
	if (h > 0) return h + ' 小时 ' + m + ' 分';
	return m + ' 分';
}

/* ------------------------------------------------------------------ 样式 */
var CSS = `
/* Bootstrap exposes a different token family. Only activate this bridge when
 * Aurora's --surface token is absent, so existing Aurora styling wins intact.
 * Bootstrap's data-darkmode switch updates these aliases without a reload. */
html.mud-bootstrap-theme{--surface:var(--background-color-high);--surface-sunken:var(--background-color-low);--brand-subtle:color-mix(in srgb,var(--primary-color-high) 10%,var(--background-color-high));--hairline:var(--border-color-low);--text:var(--text-color-high);--text-muted:var(--text-color-medium);--text-subtle:var(--text-color-low);--brand:var(--primary-color-high);--success:var(--success-color-high);--warning:var(--warn-color-high);--danger:var(--error-color-high);--info:var(--primary-color-high);--on-brand:var(--on-primary-color);--hover-faint:var(--background-color-medium)}
.mud{color:var(--text,#222);font-size:.85rem;line-height:1.45}
.mud *{box-sizing:border-box}
.mud-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:10px;margin-top:6px}
.mud-card{background:var(--surface,var(--background-alt,var(--background,#fff)));border:1px solid var(--hairline,var(--border,#e3e6ea));border-radius:calc(var(--radius-base,.5rem) + .375rem);padding:14px 16px;box-shadow:var(--app-shadow-sm,0 1px 3px rgba(0,0,0,.04));transition:border-color .15s}
.mud-card:hover{border-color:color-mix(in oklab,var(--brand,var(--primary,#2f7bf6)) 30%,var(--hairline,var(--border,#e3e6ea)))}
.mud-card>h3{margin:0 0 8px;font-size:.7rem;font-weight:600;color:var(--text-muted,var(--text-light,#787d85));letter-spacing:.08em}
.mud-card>h3::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--brand,var(--primary,#2f7bf6));margin-right:7px;vertical-align:1px}
.mud-hero{display:flex;flex-wrap:wrap;gap:12px 28px;align-items:center;background:var(--brand-subtle,var(--surface,#fff));margin-bottom:12px;padding:16px 20px}
.mud-sec{padding:2px 2px 6px}
.mud-sec>h3{margin:16px 0 10px;font-size:.7rem;font-weight:600;color:var(--text-muted,var(--text-light,#787d85));letter-spacing:.08em}
.mud-sec>h3::before{content:'';display:inline-block;width:6px;height:6px;border-radius:50%;background:var(--brand,var(--primary,#2f7bf6));margin-right:7px;vertical-align:1px}
.mud-cols{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:0 28px}
.mud-body>.mud-sec+.mud-sec{border-top:1px dashed color-mix(in oklab,var(--hairline,var(--border,#ddd)) 60%,transparent);margin-top:14px;padding-top:2px}
/* 首屏骨架：卡片正常占位，只让待填字段呼吸；第一份快照到达后停止。 */
@keyframes mudpulse{0%,100%{opacity:1}50%{opacity:.35}}
.mud-booting .mud-v,.mud-booting .mud-kpi b,.mud-booting .mud-rsrp,.mud-booting .mud-rat,.mud-booting .mud-temp span{animation:mudpulse 1.1s ease-in-out infinite}
/* 紧凑键值行：键与值相邻排布（不两端对齐拉开），用于驻网参照等 */
.mud-srvline{display:flex;flex-wrap:wrap;gap:4px 10px;padding:2px 0;font-size:.84rem}
.mud-srvline .k{color:var(--text-muted,var(--text-light,#777));flex:0 0 auto}
.mud-srvline .v{font-variant-numeric:tabular-nums;font-weight:500}
.mud-charts{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px}
.mud-chart{background:transparent;border-radius:var(--radius-base,.5rem);padding:2px 4px 0}
.mud-chart .t{display:flex;align-items:baseline;gap:8px}
.mud-chart .t b{font-size:1.2rem;font-weight:700;font-variant-numeric:tabular-nums}
.mud-chart .t span{font-size:.72rem;color:var(--text-muted,var(--text-light,#777))}
.mud-chart .c{height:40px;margin-top:2px}
.mud-chart .c svg{display:block;width:100%;height:100%}
.mud-lockbtn{padding:0 10px;border-radius:99px;border:1px solid var(--hairline,var(--border,#ccc));background:var(--surface,var(--background,#fff));color:var(--text,#222);font-size:.72rem;cursor:pointer;line-height:1.7}
.mud-lockbtn.on,.mud-lockbtn:active{background:var(--brand,var(--primary,#2f7bf6));border-color:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-lockbtn.locked{opacity:.45;pointer-events:none;background:var(--surface-sunken,rgba(127,127,127,.1));color:var(--text-muted,var(--text-light,#888));border-color:transparent}
.mud-hero-l{flex:1 1 260px;min-width:0;display:flex;flex-direction:column;gap:5px}
.mud-hero-r{flex:0 0 auto;text-align:right;display:flex;flex-direction:column;gap:8px;align-items:flex-end}
.mud-rat{font-size:1.7rem;font-weight:700;line-height:1.1;letter-spacing:.01em}
.mud-op{color:var(--text-muted,var(--text-light,#777));font-size:.85rem}
.mud-cellline{font-size:.78rem;color:var(--text-muted,var(--text-light,#777));font-variant-numeric:tabular-nums;line-height:1.55}
.mud-rsrp{font-size:2.3rem;font-weight:700;font-variant-numeric:tabular-nums;line-height:1}
.mud-rsrp small{font-size:.9rem;font-weight:500}
.mud-chips{display:flex;gap:6px;justify-content:flex-end;flex-wrap:wrap}
.mud-tag{display:inline-block;padding:1px 8px;border-radius:99px;background:var(--surface-sunken,rgba(127,127,127,.1));font-size:.74rem;font-weight:600;font-variant-numeric:tabular-nums}
.mud-q{display:inline-block;min-width:3em;padding:1px 8px;border-radius:99px;font-size:.74rem;font-weight:600;text-align:center}
.mud-rows{display:grid;gap:2px}
.mud-r{display:flex;justify-content:space-between;gap:10px;padding:3px 0;border-bottom:1px dashed color-mix(in oklab,var(--hairline,var(--border,#ddd)) 55%,transparent)}
.mud-r:last-child{border-bottom:none}
.mud-k{color:var(--text-muted,var(--text-light,#777));flex:0 0 auto}
.mud-v{font-variant-numeric:tabular-nums;text-align:right;word-break:break-all;font-weight:500}
.mud-bars{display:inline-flex;align-items:flex-end;gap:2px;height:16px;margin-left:8px;vertical-align:baseline}
.mud-bars i{width:3px;border-radius:1px;background:var(--hairline,var(--border,#ccc))}
.mud-bars i.on{background:currentColor}
.mud-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(122px,1fr));gap:10px;margin-bottom:10px}
.mud-kpi{background:var(--surface-sunken,rgba(127,127,127,.06));border-radius:var(--radius-base,.5rem);padding:9px 12px}
.mud-kpi b{display:block;font-size:1.05rem;font-variant-numeric:tabular-nums;font-weight:700;line-height:1.25}
.mud-kpi span{font-size:.68rem;color:var(--text-muted,var(--text-light,#777))}
.mud-sub{font-size:.68rem;color:var(--text-subtle,var(--text-light,#999));font-variant-numeric:tabular-nums}
.mud-meter{height:5px;border-radius:3px;background:var(--surface-sunken,rgba(127,127,127,.15));overflow:hidden;margin:3px 0 1px}
.mud-meter i{display:block;height:100%;border-radius:3px}
.mud-freq{display:flex;align-items:center;font-size:.76rem;font-variant-numeric:tabular-nums;padding:1px 0}
.mud-freq .mud-k{flex:0 0 2.4em}
.mud-btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:7px 12px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-size:.82rem;cursor:pointer;user-select:none}
.mud-btn:active{transform:scale(.97)}
.mud-btn.on{background:var(--brand,var(--primary,#2f7bf6));border-color:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-btn.warn{border-color:color-mix(in oklab,var(--danger,#E25555) 55%,transparent);color:var(--danger,#E25555)}
.mud-btn[disabled]{opacity:.4;pointer-events:none}
.mud-ctl{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:7px}
.mud-note{font-size:.72rem;color:var(--text-subtle,var(--text-light,#999));margin-top:7px}
.mud-table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums;font-size:.8rem}
.mud-table th{font-weight:500;color:var(--text-muted,var(--text-light,#777));text-align:right;padding:1px 4px;border-bottom:1px solid var(--hairline,var(--border,#ddd));font-size:.72rem;position:sticky;top:0;background:var(--surface,var(--background-alt,var(--background,#fff)))}
.mud-table td{text-align:right;padding:3px 6px;border-bottom:1px dashed color-mix(in oklab,var(--hairline,var(--border,#ddd)) 5%,transparent)}
.mud-table th:first-child,.mud-table td:first-child{text-align:left}
.mud-scroll{max-height:230px;overflow:auto;border:1px solid color-mix(in oklab,var(--hairline,var(--border,#ddd)) 45%,transparent);border-radius:var(--radius-base,.5rem);padding:4px}
.mud-cli{padding:4px 8px;border-radius:var(--radius-base,.5rem);border:1px solid color-mix(in oklab,var(--hairline,var(--border,#ddd)) 55%,transparent);margin-bottom:5px}
.mud-cli .t{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.mud-cli .s{font-size:.72rem;color:var(--text-muted,var(--text-light,#888));font-variant-numeric:tabular-nums;margin-top:1px}
/* ---- 聊天式短信 ---- */
.mud-chat{display:flex;gap:12px;min-height:420px}
.mud-convs{flex:0 0 240px;overflow:auto;max-height:520px}
.mud-conv{padding:7px 9px;border-radius:var(--radius-base,.5rem);cursor:pointer;margin-bottom:4px;border:1px solid transparent}
.mud-conv:hover{background:var(--hover-faint,rgba(127,127,127,.06))}
.mud-conv.sel{background:var(--brand-subtle,var(--surface-sunken,rgba(127,127,127,.08)));border-color:color-mix(in oklab,var(--brand,var(--primary,#2f7bf6)) 30%,transparent)}
.mud-conv .n{display:flex;justify-content:space-between;gap:6px;font-weight:600;font-size:.84rem}
.mud-conv .p{font-size:.74rem;color:var(--text-muted,var(--text-light,#888));white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.mud-thread{flex:1;display:flex;flex-direction:column;min-width:0;border-left:1px solid var(--hairline,var(--border,#ddd));padding-left:12px}
.mud-msgs{flex:1;overflow:auto;max-height:460px;padding:4px 2px;display:flex;flex-direction:column;gap:6px}
.mud-bub{max-width:78%;padding:6px 11px;border-radius:calc(var(--radius-base,.5rem) + .25rem);font-size:.85rem;white-space:pre-wrap;word-break:break-word;align-self:flex-start;background:var(--surface-sunken,rgba(127,127,127,.08))}
.mud-bub.out{align-self:flex-end;background:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-bub .tm{display:block;font-size:.64rem;opacity:.65;margin-top:2px;text-align:right;font-variant-numeric:tabular-nums}
.mud-comp{display:flex;gap:8px;margin-top:8px}
.mud-comp input,.mud-comp textarea{padding:7px 11px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-family:inherit}
.mud-comp input{flex:0 0 170px}
.mud-comp textarea{flex:1;resize:none;min-height:40px;max-height:120px}
@media(max-width:700px){.mud-chat{flex-direction:column}.mud-convs{flex:none;max-height:150px}.mud-thread{border-left:none;padding-left:0;border-top:1px solid var(--hairline,var(--border,#ddd));padding-top:8px}}
/* ---- 专业 AT 终端 ---- */
.mud-at-grid{display:grid;grid-template-columns:1fr 220px;gap:10px}
.mud-at-grid .mud-scroll{max-height:340px}
@media(max-width:700px){.mud-at-grid{grid-template-columns:1fr}.mud-term{height:300px}.mud-at-grid .mud-scroll{max-height:120px}}
.mud-term{font-family:var(--font-mono,monospace);font-size:.8rem;line-height:1.5;background:color-mix(in oklab,var(--surface,#14161a) 92%,var(--brand,#2f7bf6) 3%);color:var(--text,#d5d9de);border:1px solid var(--hairline,var(--border,#2a2d33));border-radius:var(--radius-base,.5rem);padding:12px;height:380px;overflow:auto;white-space:pre-wrap;word-break:break-all}
.mud-term .ln-cmd{color:var(--brand,#6ab0ff);font-weight:600}
.mud-term .ln-ok{color:var(--success,#57c98a);font-weight:600}
.mud-term .ln-err{color:var(--danger,#ff7b72);font-weight:600}
.mud-term .ln-data{color:var(--text,#d5d9de)}
.mud-term .ln-meta{color:var(--text-subtle,#7d8590);font-style:italic}
.mud-term .ln-ms{float:right;color:var(--text-subtle,#7d8590);font-size:.7rem}
.mud-dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--text-subtle,#8A8F98);margin-right:6px;vertical-align:1px}
.mud-dot.on{background:var(--success,#2FBF71)}
.mud-temp{display:inline-flex;gap:5px;flex-wrap:wrap}
.mud-temp span{padding:1px 8px;border-radius:var(--radius-base,.5rem);background:var(--surface-sunken,rgba(127,127,127,.08));font-variant-numeric:tabular-nums;font-size:.76rem}
.mud-at-in{display:flex;gap:7px;margin-bottom:7px}
.mud-at-in input{flex:1;min-width:0;padding:6px 10px;border:1px solid var(--hairline,var(--border,#ccc));border-radius:var(--radius-base,.5rem);background:var(--surface,var(--background,#fff));color:var(--text,#222);font-family:var(--font-mono,monospace)}
.mud-out{font-family:var(--font-mono,monospace);font-size:.78rem;white-space:pre-wrap;background:var(--surface-sunken,rgba(127,127,127,.07));border-radius:var(--radius-base,.5rem);padding:9px;max-height:260px;overflow:auto;margin:7px 0 0}
.mud-chiprow{display:flex;flex-wrap:wrap;gap:5px;margin-top:7px}
.mud-chip{padding:2px 9px;border-radius:99px;border:1px solid var(--hairline,var(--border,#ccc));font-size:.72rem;font-family:var(--font-mono,monospace);cursor:pointer}
.mud-chip.on{background:var(--brand,var(--primary,#2f7bf6));border-color:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
.mud-sms-item{padding:6px 8px;border-radius:var(--radius-base,.5rem);border:1px solid color-mix(in oklab,var(--hairline,var(--border,#ddd)) 60%,transparent);margin-bottom:6px;cursor:pointer}
.mud-sms-item:hover{background:var(--hover-faint,rgba(127,127,127,.05))}
.mud-sms-top{display:flex;justify-content:space-between;gap:8px;align-items:baseline}
.mud-badge{display:flex;align-items:center;justify-content:center;font-size:.68rem;padding:0 7px;min-width:20px;height:20px;box-sizing:border-box;border-radius:99px;background:var(--brand,var(--primary,#2f7bf6));color:var(--on-brand,#fff)}
/* 手机端 hero 与锁定页一致：信息块在上、RSRP 块自然换行到下一行（右对齐） */
@media(max-width:600px){
.mud-hero{gap:8px}
.mud-hero-l{flex:1 1 100%}
.mud-hero-r{flex:1 0 100%;flex-direction:row;justify-content:space-between;align-items:baseline;text-align:left}
.mud-rsrp{font-size:1.9rem}
.mud-chips{justify-content:flex-end}}
/* ---- 顶部 toast 与按钮忙碌态（各页共用的反馈框架） ---- */
.mud-toasts{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:9999;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;width:max-content;max-width:min(92vw,560px)}
.mud-toast{pointer-events:auto;display:flex;align-items:center;gap:9px;padding:9px 16px;border-radius:99px;background:var(--surface,var(--background,#fff));border:1px solid var(--hairline,var(--border,#ddd));box-shadow:0 6px 24px rgba(0,0,0,.14);font-size:.82rem;color:var(--text,#222);animation:mudtoast-in .22s ease-out;max-width:100%}
.mud-toast.out{animation:mudtoast-out .25s ease-in forwards}
.mud-toast .mud-tico{flex:0 0 auto;width:8px;height:8px;border-radius:50%;background:var(--brand,var(--primary,#2f7bf6))}
.mud-toast.success .mud-tico{background:var(--success,#2FBF71)}
.mud-toast.error .mud-tico{background:var(--danger,#E25555)}
.mud-toast.busy .mud-tico{width:12px;height:12px;background:transparent;border:2px solid color-mix(in oklab,var(--brand,#2f7bf6) 30%,transparent);border-top-color:var(--brand,#2f7bf6);animation:mudspin .7s linear infinite}
@keyframes mudtoast-in{from{opacity:0;transform:translateY(-12px)}to{opacity:1;transform:none}}
@keyframes mudtoast-out{to{opacity:0;transform:translateY(-8px)}}
@keyframes mudspin{to{transform:rotate(360deg)}}
.mud-toast.notify{flex-direction:row;align-items:center;max-width:340px;text-align:left;border-radius:calc(var(--radius-base,.5rem) + .375rem)}
.mud-toast.notify .mud-nb{display:flex;flex-direction:column;gap:2px;min-width:0}
.mud-toast.notify .mud-nb b{font-size:.82rem;font-weight:700}
.mud-toast.notify .mud-nb span{font-size:.76rem;color:var(--text-muted,var(--text-light,#888));overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
.mud-btn .mud-spin,.mud-lockbtn .mud-spin{flex:0 0 auto;width:12px;height:12px;border-radius:50%;border:2px solid color-mix(in oklab,currentColor 30%,transparent);border-top-color:currentColor;animation:mudspin .7s linear infinite}
.mud-btn.busy,.mud-lockbtn.busy{pointer-events:none;opacity:.75}
/* ---- 主题化对话框（替代浏览器 confirm/alert） ---- */
.mud-dlg-wrap{position:fixed;inset:0;z-index:10000;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.42);animation:mudfade-in .16s ease-out;padding:20px}
.mud-dlg{background:var(--surface,var(--background,#fff));border:1px solid var(--hairline,var(--border,#ddd));border-radius:calc(var(--radius-base,.5rem) + .5rem);box-shadow:0 18px 50px rgba(0,0,0,.28);max-width:420px;width:100%;padding:18px 20px 16px;animation:muddlg-in .2s cubic-bezier(.2,.9,.3,1.15)}
.mud-dlg h4{margin:0 0 8px;font-size:.95rem;font-weight:700;color:var(--text,#222)}
.mud-dlg .mud-dlg-msg{font-size:.84rem;line-height:1.6;color:var(--text-muted,var(--text-light,#666));white-space:pre-wrap;word-break:break-word}
.mud-dlg .mud-dlg-btns{display:flex;gap:8px;justify-content:flex-end;margin-top:16px;flex-wrap:wrap}
/* 短信气泡的删除按钮：红色垃圾桶，平时隐淡、悬停显形；正文留出右侧空间防重叠 */
.mud-bub{position:relative;padding-right:28px}
.mud-del{position:absolute;top:2px;right:2px;display:flex;align-items:center;justify-content:center;width:24px;height:24px;padding:0;border:none;background:transparent;color:var(--danger,#E25555);opacity:.4;cursor:pointer;border-radius:50%}
.mud-del:hover{opacity:.9;background:color-mix(in oklab,var(--danger,#E25555) 12%,transparent)}
.mud-del svg{display:block}
/* 预览 -> 全文回填的过渡动画，消除首载的生硬跳变 */
@keyframes mudfadein{from{opacity:.25}to{opacity:1}}
.mud-bub .bd.fadein{animation:mudfadein .25s ease-out}
@keyframes muddlg-in{from{opacity:0;transform:scale(.94) translateY(10px)}to{opacity:1;transform:none}}
@keyframes mudfade-in{from{opacity:0}to{opacity:1}}
/* 手机端锁定页 hero：RSRP 数字左对齐（其余屏幕保持右对齐） */
@media(max-width:600px){
.mud-rsrp{text-align:left}}
`;

function injectCss() {
	localizeMenu();
	// Discard our own aliases before probing, otherwise the second LuCI page
	// would mistake this bridge for Aurora and turn it off.
	document.documentElement.classList.remove('mud-bootstrap-theme');
	var theme = getComputedStyle(document.documentElement);
	var hasAuroraTokens = theme.getPropertyValue('--surface').trim() ||
		getComputedStyle(document.body).getPropertyValue('--surface').trim();
	document.documentElement.classList.toggle('mud-bootstrap-theme',
		!hasAuroraTokens && !!theme.getPropertyValue('--background-color-high').trim());
	if (document.getElementById('mud-style')) return;
	var st = document.createElement('style');
	st.id = 'mud-style';
	st.textContent = CSS;
	document.head.appendChild(st);
}
function v(id) { return document.getElementById('mud-' + id); }
function set(id, text, color) {
	var e = v(id);
	if (!e) return;
	e.textContent = (text == null || text === '') ? '--' : text;
	if (color !== undefined) e.style.color = color;
}
function spark(el, arr, min, max, win) {
	if (!el || !arr || arr.length < 2) return;
	var w = 100, h = 34, pts = [];
	for (var i = 0; i < arr.length; i++) {
		pts.push([ i / (win - 1) * w,
			h - Math.max(0, Math.min(1, (arr[i] - min) / (max - min || 1))) * (h - 3) - 1.5 ]);
	}
	/* Catmull-Rom 转三次贝塞尔：折线变平滑曲线 */
	var d = 'M' + pts[0][0].toFixed(1) + ',' + pts[0][1].toFixed(1);
	for (var i = 0; i < pts.length - 1; i++) {
		var p0 = pts[Math.max(0, i - 1)], p1 = pts[i], p2 = pts[i + 1], p3 = pts[Math.min(pts.length - 1, i + 2)];
		d += 'C' + (p1[0] + (p2[0] - p0[0]) / 6).toFixed(1) + ',' + (p1[1] + (p2[1] - p0[1]) / 6).toFixed(1) +
			' ' + (p2[0] - (p3[0] - p1[0]) / 6).toFixed(1) + ',' + (p2[1] - (p3[1] - p1[1]) / 6).toFixed(1) +
			' ' + p2[0].toFixed(1) + ',' + p2[1].toFixed(1);
	}
	var last = pts.length - 1;
	var area = d + ' L' + pts[last][0].toFixed(1) + ',' + h + ' L' + pts[0][0].toFixed(1) + ',' + h + ' Z';
	var gid = 'mudg-' + (el.id || Math.floor(Math.random() * 1e6));
	el.innerHTML = '<svg viewBox="0 0 ' + w + ' ' + h + '" preserveAspectRatio="none">' +
		'<defs><linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">' +
		'<stop offset="0" stop-color="currentColor" stop-opacity=".32"/>' +
		'<stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>' +
		'<path d="' + area + '" fill="url(#' + gid + ')"/>' +
		'<path d="' + d + '" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" vector-effect="non-scaling-stroke"/></svg>';
}

/* 邻区表（主页与网络锁定页共用）：NR 置顶按 RSRP 排序，行尾带锁定按钮。
 * lockedCell 是 lock_get 的 cell 字段（如 "nr:627264,501"），命中行显示灰色"已锁定"。
 * 点击事件由页面用事件委托绑定（[data-lock] 属性："<rat>:<arfcn>,<pci>"）。 */
function neighborRows(c, lockedCell) {
	var nb = (c && c.neigh) || [];
	nb.sort(function(a, b) {
		if ((a.rat == 'nr') != (b.rat == 'nr')) return a.rat == 'nr' ? -1 : 1;
		return (b.rsrp || -999) - (a.rsrp || -999);
	});
	if (!nb.length)
		return '<tr><td colspan="7" style="color:var(--text-muted,var(--text-light,#777))">' + esc(translate('暂无邻区数据')) + '</td></tr>';
	var lk = Array.isArray(lockedCell) ? lockedCell.join('|') : (lockedCell || '');
	return nb.map(function(n) {
		var l = qLabel(n.rsrp, n.rsrq, n.sinr);
		var key = n.rat + ':' + n.arfcn + ',' + n.pci;
		var isLocked = lk.split('|').indexOf(key) >= 0;
		return '<tr><td>' + (n.rat == 'nr' ? 'NR n' + esc(n.band) : 'LTE B' + esc(n.band)) + '</td>' +
			'<td>' + esc(n.pci != null ? n.pci : '--') + '</td>' +
			'<td>' + esc(n.arfcn != null ? n.arfcn : '--') + '</td>' +
			'<td style="color:' + qCol(l) + '">' + (n.rsrp != null ? n.rsrp.toFixed(1) : '--') + '</td>' +
			'<td>' + (n.rsrq != null ? n.rsrq.toFixed(1) : '--') + '</td>' +
			'<td>' + (n.sinr != null ? n.sinr.toFixed(1) : '--') + '</td>' +
			'<td><button class="mud-lockbtn' + (isLocked ? ' locked' : '') + '" data-lock="' + key + '"' +
			(isLocked ? ' disabled' : '') + '>' + esc(translate(isLocked ? '已锁定' : '锁定')) + '</button></td></tr>';
	}).join('');
}

/* ------------------------------------------------------------------ 反馈框架
 * M.toast(text, {type, timeout})：顶部弹出的统一提示，type = info|success|error|busy
 * （busy 自带转圈点，适合“正在…”进行态）。返回句柄 {update(text,type), close()}，
 * 长操作可以一路 update 下去而不堆叠。timeout=0 表示不自动消失。
 * M.busy(btn[, on])：给按钮加/去内嵌转圈并禁点；不传 on 则翻转。 */
function toast(text, opts) {
	opts = opts || {};
	if (!document.getElementById('mud-toasts')) {
		var w = document.createElement('div');
		w.id = 'mud-toasts';
		w.className = 'mud-toasts';
		document.body.appendChild(w);
	}
	var t = document.createElement('div');
	t.className = 'mud-toast ' + (opts.type || 'info');
	t.innerHTML = '<i class="mud-tico"></i><span></span>';
	t.lastChild.textContent = translate(text);
	document.getElementById('mud-toasts').appendChild(t);
	var timer = null, dead = false;
	var life = opts.timeout !== undefined ? opts.timeout : 3500;
	var arm = function() {
		if (timer) clearTimeout(timer);
		if (life > 0) timer = setTimeout(close, life);
	};
	var close = function() {
		if (dead) return;
		dead = true;
		if (timer) clearTimeout(timer);
		t.classList.add('out');
		setTimeout(function() { t.remove(); }, 260);
	};
	arm();
	return {
		update: function(text2, type2) {
			if (dead) return;
			t.lastChild.textContent = translate(text2);
			if (type2) t.className = 'mud-toast ' + type2;
			arm();
		},
		close: close
	};
}
function busy(btn, on) {
	if (!btn || !btn.classList) return;
	if (on === undefined) on = !btn.classList.contains('busy');
	if (on && !btn.classList.contains('busy')) {
		btn.classList.add('busy');
		var s = document.createElement('i');
		s.className = 'mud-spin';
		btn.insertBefore(s, btn.firstChild);
	} else if (!on && btn.classList.contains('busy')) {
		btn.classList.remove('busy');
		var sp = btn.querySelector('.mud-spin');
		if (sp) sp.remove();
	}
}

/* ------------------------------------------------------------------ 对话框
 * M.confirmBox(title, message, opts) -> Promise<boolean>：主题化确认框，
 * 取消/遮罩/Escape 都 resolve(false)，确定/Enter resolve(true)。
 * M.alertBox(title, message, opts) -> Promise<true>：单按钮提示框。
 * opts: { danger:true 红色确认键, okText, cancelText }；danger 时默认焦点在取消上。 */
function dialog(opts) {
	opts = opts || {};
	return new Promise(function(resolve) {
		var wrap = document.createElement('div');
		wrap.className = 'mud-dlg-wrap';
		var withCancel = opts.cancelText !== null;
		wrap.innerHTML = '<div class="mud-dlg" role="dialog" aria-modal="true">' +
			'<h4></h4><div class="mud-dlg-msg"></div><div class="mud-dlg-btns">' +
			(withCancel ? '<button type="button" class="mud-btn" data-r="0"></button>' : '') +
			'<button type="button" class="mud-btn' + (opts.danger ? ' warn' : '') + '" data-r="1"></button>' +
			'</div></div>';
		wrap.querySelector('h4').textContent = translate(opts.title || '确认');
		wrap.querySelector('.mud-dlg-msg').textContent = translate(opts.message || '');
		var btns = wrap.querySelectorAll('.mud-dlg-btns .mud-btn');
		btns[btns.length - 1].textContent = translate(opts.okText || '确定');
		if (withCancel) btns[0].textContent = translate(opts.cancelText || '取消');
		var done = function(r) {
			document.removeEventListener('keydown', onKey, true);
			wrap.remove();
			resolve(r);
		};
		var onKey = function(ev) {
			if (ev.key == 'Escape') { ev.preventDefault(); done(withCancel ? false : true); }
			else if (ev.key == 'Enter') { ev.preventDefault(); done(true); }
		};
		wrap.addEventListener('click', function(ev) {
			var b = ev.target.closest('button');
			if (b) done(b.getAttribute('data-r') == '1');
			else if (ev.target === wrap && withCancel) done(false);
		});
		document.addEventListener('keydown', onKey, true);
		document.body.appendChild(wrap);
		/* 危险操作默认焦点给取消，防手滑回车 */
		(withCancel && opts.danger ? btns[0] : btns[btns.length - 1]).focus();
	});
}
/* 手机通知样式的横幅：标题（发件人）+ 两行预览，默认 6 s */
function notify(title, message, opts) {
	opts = opts || {};
	if (!document.getElementById('mud-toasts')) {
		var w = document.createElement('div');
		w.id = 'mud-toasts';
		w.className = 'mud-toasts';
		document.body.appendChild(w);
	}
	var t = document.createElement('div');
	t.className = 'mud-toast notify ' + (opts.type || 'info');
	t.innerHTML = '<i class="mud-tico"></i><div class="mud-nb"><b></b><span></span></div>';
	t.querySelector('b').textContent = translate(title);
	t.querySelector('span').textContent = message == null ? '' : String(message);
	document.getElementById('mud-toasts').appendChild(t);
	var life = opts.timeout !== undefined ? opts.timeout : 6000;
	var timer = life > 0 ? setTimeout(function() {
		t.classList.add('out');
		setTimeout(function() { t.remove(); }, 260);
	}, life) : null;
	t.addEventListener('click', function() {
		if (timer) clearTimeout(timer);
		t.remove();
	});
	return t;
}

/* 新短信监视（每个页面 render 时调用一次，内部单例）：
 * 每 5 s 读一次本地池第 1 页（纯文件读，不打 AT），首次只记基线；
 * 之后出现更大的消息 id 且为收件（mt）时，按手机通知样式弹出
 * 「发件人 + 预览」。池子被清空（id 回落）时静默重建基线。 */
var smsWatch = null;
function watchSms() {
	if (smsWatch) return;
	smsWatch = { seen: null };
	window.setInterval(function() {
		Promise.resolve(callSmsList(1)).catch(function() { return {}; }).then(function(r) {
			r = r || {};
			var msgs = r.msgs || [], max = 0;
			msgs.forEach(function(m) {
				var id = parseInt(m.id, 10) || 0;
				if (id > max) max = id;
			});
			if (!max) return;
			if (smsWatch.seen == null || max < smsWatch.seen) { smsWatch.seen = max; return; }
			if (max > smsWatch.seen) {
				msgs.forEach(function(m) {
					var id = parseInt(m.id, 10) || 0;
					if (id > smsWatch.seen && m.dir === 'mt')
						notify('新短信 · ' + (m.peer || '未知号码'), m.preview || '', { type: 'success' });
				});
				smsWatch.seen = max;
			}
		});
	}, 5000);
}

function confirmBox(title, message, opts) {
	opts = opts || {};
	opts.title = title;
	opts.message = message;
	return dialog(opts);
}
function alertBox(title, message, opts) {
	opts = opts || {};
	opts.title = title;
	opts.message = message;
	opts.cancelText = null;
	return dialog(opts);
}

/* 多选对话框：M.choiceBox(title, message, [{label, value, danger}], opts)
 * -> Promise(选中项的 value)；取消/遮罩/Escape resolve(undefined)。
 * choices 里的按钮从左到右排，danger 项红色。 */
function choiceBox(title, message, choices, opts) {
	opts = opts || {};
	return new Promise(function(resolve) {
		var wrap = document.createElement('div');
		wrap.className = 'mud-dlg-wrap';
		var btns = (choices || []).map(function(c, i) {
			return '<button type="button" class="mud-btn' + (c.danger ? ' warn' : '') +
				'" data-i="' + i + '"></button>';
		}).join('');
		wrap.innerHTML = '<div class="mud-dlg" role="dialog" aria-modal="true">' +
			'<h4></h4><div class="mud-dlg-msg"></div>' +
			'<div class="mud-dlg-btns">' + btns + '</div></div>';
		wrap.querySelector('h4').textContent = translate(title || '选择');
		wrap.querySelector('.mud-dlg-msg').textContent = translate(message || '');
		(choices || []).forEach(function(c, i) {
			wrap.querySelector('[data-i="' + i + '"]').textContent = translate(c.label || '?');
		});
		var done = function(v) {
			document.removeEventListener('keydown', onKey, true);
			wrap.remove();
			resolve(v);
		};
		var onKey = function(ev) {
			if (ev.key == 'Escape') { ev.preventDefault(); done(undefined); }
		};
		wrap.addEventListener('click', function(ev) {
			var b = ev.target.closest('button');
			if (b) done(choices[parseInt(b.getAttribute('data-i'), 10)].value);
			else if (ev.target === wrap) done(undefined);
		});
		document.addEventListener('keydown', onKey, true);
		document.body.appendChild(wrap);
		var first = wrap.querySelector('.mud-dlg-btns .mud-btn');
		if (first) first.focus();
	});
}

/* LuCI 的 require 把模块当类工厂：必须返回 baseclass 派生的类，加载后拿到的是它的实例 */
return baseclass.extend({
	callStatus: callStatus, callSignal: callSignal, callSysinfo: callSysinfo, callAct: callAct, callAt: callAt, callAtHist: callAtHist,
	callLockGet: callLockGet, callLockFresh: callLockFresh, callLockSet: callLockSet,
	callSmsList: callSmsList, callSmsShow: callSmsShow, callSmsSend: callSmsSend,
	callSmsDel: callSmsDel, callSmsSync: callSmsSync,
	carrierName: carrierName, qLabel: qLabel, qCol: qCol, qScore: qScore,
	esc: esc, fmtBytes: fmtBytes, fmtRate: fmtRate, fmtUptime: fmtUptime, PLMN_CN: PLMN_CN,
	uiLanguage: uiLanguage, translate: translate, localize: localize, localizeMenu: localizeMenu,
	injectCss: injectCss, v: v, set: set, spark: spark, neighborRows: neighborRows,
	toast: toast, busy: busy, confirmBox: confirmBox, alertBox: alertBox, choiceBox: choiceBox,
	notify: notify, watchSms: watchSms
});
