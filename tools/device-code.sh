# The device code under Android, for the installers (sourced): the same 16 hex digits as Linux's mu300-device-code
# (rootfs/overlay/opt/mu300/lib/storage.sh, mu300_device_code) - the first 16 of sha256("mu300-audio-device-v1\n" +
# IDENTITY), IDENTITY "emmc:CID" or "ufs:MANUFACTURER:SERIAL" - read from the disk that holds userdata, the way
# resume_facts (tools/resume.sh) and install.ps1's FactsCmd read the CID. One line, no quotes of either kind (su_do
# puts it in single ones; Windows PowerShell 5.1 drops double ones on the way to adb), so install.ps1 can send the
# same text: Get-Content this file and take the value between the first and the last single quote of the
# MU300_DEVICE_CODE_CMD line. The raw identity stays on the device: only its hash comes back. It needs no root (cid
# and the string descriptors are world-readable) but works under su too. Prints nothing when there is no identity.
#   device_code      the code of the device adb sees (adb shell)
MU300_DEVICE_CODE_CMD='d=$(readlink -f /dev/block/by-name/userdata); n=${d##*/}; b=${n%p*}; case $n in sd*) b=${n%%[0-9]*} ;; esac; s=/sys/class/block/$b/device; IFS=; set -f; i=; case $n in sd*) u=$s/../../../string_descriptors; m=$(cat $u/manufacturer_name 2>/dev/null); r=$(cat $u/serial_number 2>/dev/null); case ${m:+1}${r:+1} in 11) i=ufs:$m:$r ;; esac ;; mmcblk*) c=$(cat $s/cid 2>/dev/null); i=${c:+emmc:$c} ;; esac; case $i in ?*) { echo mu300-audio-device-v1; printf %s $i; } | sha256sum | cut -c1-16 ;; esac'
device_code() { ${ADB:-adb} shell "$MU300_DEVICE_CODE_CMD" </dev/null 2>/dev/null | tr -d '\r' | grep -E '^[0-9a-f]{16}$' | head -n1; }
