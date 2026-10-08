//<script>
/*
 * 【插件】mu300 系统切换器 v2
 * 运行环境：设备 Android 侧的网页管理面板（与飞猫系列插件同一宿主）
 *
 * 功能：一键从 Android 切换到 Linux（OpenWrt）。
 * 方法：运行时检测当前槽位（getprop ro.boot.slot_suffix），推导 Linux 在
 *       哪个槽；从 misc 分区读取现有 32 字节 bootloader_control 块，
 *       动态构建目标槽的引导块（改 slot_suffix 和元数据字节，重算 CRC32），
 *       回读校验通过后才重启。
 *
 * v2：不再硬编码 slot 字母——任意 A/B 布局都能用。
 */
(() => {
    const MISC_PATH = '/dev/block/by-name/misc';
    const BC_OFFSET = 2048;
    const ARMED_META = 0x2f;  // priority 15, tries 2, successful 0
    const IDLE_META  = 0x9e;  // priority 14, tries 1, successful 1

    const run = async (command, timeout = 15000) => {
        try {
            const res = await runShellWithRoot(command, timeout);
            return { ok: Boolean(res && res.success), text: String((res && res.content) || '').trim() };
        } catch (e) {
            return { ok: false, text: '' };
        }
    };

    const readMisc = async () => {
        const r = await run(
            `dd if=${MISC_PATH} bs=1 skip=${BC_OFFSET} count=32 2>/dev/null | od -An -tx1 -v | tr -d ' \\n'`
        );
        return r.ok ? r.text.replace(/[\r\n ]/g, '') : '';
    };

    const getAndroidSlot = async () => {
        const r = await run('getprop ro.boot.slot_suffix');
        const s = r.text.trim().replace(/_/g, '');
        if (s === 'a' || s === 'b') return s;
        // fallback: parse from misc's slot_suffix bytes
        const misc = await readMisc();
        if (misc.length >= 4) {
            const suffix = misc.substring(0, 4);
            if (suffix === '5f61') return 'a';
            if (suffix === '5f62') return 'b';
        }
        return null;
    };

    // CRC-32 (IEEE 802.3, same as gzip) over a byte array
    const crc32 = (bytes) => {
        let c = 0xFFFFFFFF;
        for (let i = 0; i < bytes.length; i++) {
            c ^= bytes[i];
            for (let k = 0; k < 8; k++) {
                c = (c & 1) ? ((c >>> 1) ^ 0xEDB88320) : (c >>> 1);
            }
        }
        return (c ^ 0xFFFFFFFF) >>> 0;
    };

    // Build a 32-byte bootloader_control block arming the Linux slot
    const buildBlock = (liveHex, linuxSlot) => {
        const bytes = [];
        for (let i = 0; i < 64; i += 2) {
            bytes.push(parseInt(liveHex.substring(i, i + 2), 16));
        }
        // slot_suffix at bytes 0-1: "_a" or "_b"
        bytes[0] = 0x5f;
        bytes[1] = linuxSlot === 'a' ? 0x61 : 0x62;
        // metadata: byte 12 = slot a, byte 14 = slot b
        const targetByte = linuxSlot === 'a' ? 12 : 14;
        const otherByte  = linuxSlot === 'a' ? 14 : 12;
        bytes[targetByte] = ARMED_META;
        bytes[otherByte]  = IDLE_META;
        // CRC32 over first 28 bytes, stored little-endian at bytes 28-31
        const crc = crc32(bytes.slice(0, 28));
        bytes[28] = crc & 0xff;
        bytes[29] = (crc >> 8) & 0xff;
        bytes[30] = (crc >> 16) & 0xff;
        bytes[31] = (crc >> 24) & 0xff;
        return bytes.map(b => b.toString(16).padStart(2, '0')).join('');
    };

    const btns = document.createElement('button');
    btns.textContent = '系统切换器';
    btns.onclick = () => {
        const { el, close } = createFixedToast('mu300_os_switch', `
            <div style="pointer-events:all;width:80vw;max-width:320px">
                <div class="title" style="margin:0">系统切换器</div>
                <div style="margin:6px 0;font-size:.65rem;color:var(--dark-text-sub-color,#999)">
                    切换到 Linux（OpenWrt）需要重启设备
                </div>
                <div style="margin:6px 0;font-size:.65rem">
                    <span id="mu300_os_slot" style="font-family:monospace">检测中…</span>
                </div>
                <div style="margin:10px 0;display:flex;justify-content:space-around" class="mu300_os_content"></div>
                <div style="text-align:right">
                    <button style="font-size:.64rem" id="mu300_os_close">${t('close_btn')}</button>
                </div>
            </div>
        `);

        const switchBtn = document.createElement('button');
        const rebootBtn = document.createElement('button');
        const content = el.querySelector('.mu300_os_content');
        const slotEl = el.querySelector('#mu300_os_slot');
        const closeBtn = el.querySelector('#mu300_os_close');
        if (!closeBtn) { close(); return; }
        closeBtn.onclick = () => close();

        const lockUI = (lock) => {
            [switchBtn, rebootBtn].forEach((b) => {
                b.disabled = lock;
                b.style.background = lock ? 'var(--dark-btn-disabled-color)' : '';
            });
        };

        switchBtn.textContent = '切换到 Linux';
        switchBtn.onclick = async () => {
            lockUI(true);
            createToast('正在检测槽位…');
            const androidSlot = await getAndroidSlot();
            if (!androidSlot) {
                createToast('无法确定当前槽位，已取消', 'red');
                lockUI(false);
                return;
            }
            const linuxSlot = androidSlot === 'a' ? 'b' : 'a';
            createToast(`Android 在 slot ${androidSlot}，Linux 在 slot ${linuxSlot}，正在构建引导块…`);

            const live = await readMisc();
            if (live.length !== 64) {
                createToast('读取 misc 失败，未做任何更改', 'red');
                lockUI(false);
                return;
            }

            const newBlock = buildBlock(live, linuxSlot);
            const printfArg = newBlock.match(/../g).map(b => '\\x' + b).join('');
            const r = await run(
                `printf '${printfArg}' | dd of=${MISC_PATH} bs=1 seek=${BC_OFFSET} conv=notrunc && sync`
            );
            if (!r.ok) {
                createToast('引导块写入失败，未重启', 'red');
                lockUI(false);
                return;
            }

            createToast('正在校验…');
            const back = await readMisc();
            if (back !== newBlock) {
                createToast('校验不一致，已放弃（设备未重启）', 'red');
                lockUI(false);
                return;
            }
            createToast(`校验通过，即将重启进入 Linux（slot ${linuxSlot}）…`, 'green');
            setTimeout(async () => {
                await run('reboot', 3000);
            }, 1500);
        };

        rebootBtn.textContent = '仅重启';
        rebootBtn.onclick = async () => {
            lockUI(true);
            createToast('重启中…');
            await run('reboot', 3000);
        };

        content.appendChild(switchBtn);
        content.appendChild(rebootBtn);

        (async () => {
            const s = await getAndroidSlot();
            slotEl.textContent = s
                ? `Android: slot ${s} · Linux: slot ${s === 'a' ? 'b' : 'a'}`
                : '槽位检测失败';
            if (!s) {
                switchBtn.disabled = true;
                switchBtn.style.background = 'var(--dark-btn-disabled-color)';
                slotEl.style.color = 'var(--red-color,#E25555)';
            }
        })();
    };

    const collapseBtn_menu = document.querySelector('#collapseBtn_menu');
    collapseBtn_menu.nextElementSibling.querySelector('.collapse_box').appendChild(btns);
})();
//</script>
