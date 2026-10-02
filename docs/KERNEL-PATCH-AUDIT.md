# 5.4 vendor patch audit for the 6.18 / 7.2 builds

The mainline builds use the same `upstream/modules/` vendor module source. `upstream/build-modules.sh` copies that source at build time; it does not apply `kernel/patches/`. A source fix is therefore shared by both kernels, but **already-built modules and TF packages do not update automatically**.

| 5.4 patch | 6.18 / 7.2 status |
| --- | --- |
| `bluetooth-marlin3-link-policy` | Kernel equivalent: `upstream/patches/0002-*`. |
| `of-reserved-mem-skip` | Kernel equivalent: `upstream/patches/0003-*`. |
| `of-reserved-mem-add` | Not applicable to the current minimal DT and module set; it only reserves RAM for the optional audio DSP port. Do not add reservations without audio. |
| `regdb-wens-certificate` | Not carried over. The mainline config does not request signed-regdb verification; the running 7.2.8 system uses country TR and operates a channel-36/80-MHz AP. Its early `regulatory.db` load fails because the file is absent, not because a signature is rejected. Revisit if signed regdb is enabled. |
| `sipa-delegate-einprogress` | Present in `upstream/modules/sprd_modem/sipa_delegate/`. |
| `sipc-base-addr-attr` | Present in `upstream/modules/sprd_modem/sipc/` and `mailbox/`; the unusable attributes are absent. |
| `sprdbt-tty-one-port` | Present in `upstream/modules/sprdbt_tty/tty-pcie/tty.c`. |
| `wcn-pcie-scan-timeout` | Present in `upstream/modules/wcn_bsp/pcie/pcie.c`. |
| `wlan_combo-5ghz-ap-ds-params`, `allow-bridging-ap`, `ap-stations-channel`, `default-board-config`, `pcie-post-init-retry`, `tx-complock-irqsave` | Present in `upstream/modules/sprd_wlan_combo/`. |
| `wlan_combo-rx-software-checksum` | Present in the shared source after the 7.2.8 Wi-Fi repair. The running 7.2.8 module was verified to return `CHECKSUM_NONE` without calling `rx_ipv6_csum`. The local `upstream/out` (6.18) and `upstream/out-7.2` WLAN modules were subsequently rebuilt from this source; old TF ZIPs and kernel bundles remain unchanged and must not be reused. |
| `audio-mem-fixed-region`, `audio-mem-shm-shift`, `mcdt-enable-clock`, `sprd-card-dummy-on-defer` | Only used by the separate optional 5.4 audio build. No corresponding audio modules are in the current 6.18 / 7.2 module set. |

Verification performed on the running 7.2.8 device: Wi-Fi AP is up at 5 GHz/80 MHz, the module hash matches the newly built `upstream/out-7.2.8` module, and disassembly of its `sc2355_fill_skb_csum` returns zero after setting `CHECKSUM_NONE`. The rebuilt local 6.18 and 7.2 artifacts were also disassembled and have the same safe checksum path. This audit is about patch parity, not a claim that every subsystem has been exhaustively runtime-tested.
