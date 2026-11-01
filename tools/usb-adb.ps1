# Shared by install.ps1 and uninstall.ps1, as tools/usb-adb.sh is by install.sh and uninstall.sh: Android's USB
# functions set to adb alone for the time of a run (no MTP, no PTP), and set back at its end when the device is still
# in the same boot of Android. Reported by kanoqwq: an F50's stock MTP hangs, and Windows then resets the USB device
# about every ten seconds, which cuts the adb session each time. The device side is tools/android-usb.sh. Not
# persistent: the next start of Android has the user's functions again.
#   $env:MU300_USB_ADB_ONLY = '0'   leave the USB functions as they are
#   $env:MU300_USB_WAIT = SECONDS   how long to wait for adb after the switch (default 60)
# Uses: SuDo, Info, Die, T, Quiet (the caller's).
$script:MuUsbWas = ''
$script:MuUsbBoot = ''

# the device script with LF line ends whatever the clone has (Android's sh stops at "\r"), pushed
function UsbPush {
    $tmp = [IO.Path]::GetTempFileName()
    try {
        [IO.File]::WriteAllText($tmp, ([IO.File]::ReadAllText((Join-Path (Join-Path $Top 'tools') 'android-usb.sh')) -replace "`r`n", "`n"))
        Quiet { adb push $tmp /data/local/tmp/android-usb.sh } | Out-Null
        return $LASTEXITCODE -eq 0
    } finally { Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue }
}
# the words after MU300-USB in what android-usb.sh printed
function UsbWords([string]$Out) {
    foreach ($l in ($Out -split "`n")) { if ($l -match '^MU300-USB (.*)$') { return @($Matches[1].Trim() -split '\s+') } }
    return @()
}
function UsbWaitSeconds { $w = 0; if ([int]::TryParse([string]$env:MU300_USB_WAIT, [ref]$w) -and $w -gt 0) { $w } else { 60 } }

# UsbAdbOnly: call when root is known to work; again after Android restarted in the same run
function UsbAdbOnly {
    if ($env:MU300_USB_ADB_ONLY -eq '0') { return }
    if (-not (UsbPush)) { return }
    $w = @(UsbWords (SuDo 'sh /data/local/tmp/android-usb.sh adb-only'))
    if ($w.Count -lt 2 -or $w[0] -ne 'switch') { if ($w.Count -ge 2) { Info 'usb.functions' $w[1] }; return }
    $script:MuUsbWas = $w[1]; $script:MuUsbBoot = if ($w.Count -ge 3) { $w[2] } else { '' }
    Write-Host ('  ' + (T 'USB of Android: adb only for this run (was {1}; MTP can stall the connection, Windows then resets it)' $script:MuUsbWas))
    $limit = UsbWaitSeconds
    $seen = ''
    for ($i = 0; $i -lt $limit; $i++) {
        Start-Sleep -Seconds 1
        $seen = (([string]((Quiet { adb shell getprop sys.usb.state }) -join "`n")) -replace "`r", '').Trim()
        if ($seen -eq 'adb') { Info 'usb.functions' 'adb'; Info 'usb.was' $script:MuUsbWas; return }
    }
    $script:MuUsbWas = ''
    # adb is back, with other functions: Android set them again. Not worse than before: go on with them.
    if ($seen) { Write-Host ('  ' + (T 'Android kept its USB functions ({1}); going on with them' $seen)); Info 'usb.functions' $seen; return }
    Die (T 'the device did not come back on adb within {1} seconds after its USB was set to adb only: unplug it and plug it in again (or restart Android), then run this again (MU300_USB_ADB_ONLY=0 leaves the USB as it is)' $limit)
}

# UsbRestore: the functions of before, when the device is still in the boot that was switched and nothing else has
# changed them (android-usb.sh decides; nothing while a reboot is under way). Not waited for.
function UsbRestore {
    if (-not $script:MuUsbWas) { return }
    $was = $script:MuUsbWas; $script:MuUsbWas = ''
    try {
        if (-not (UsbPush)) { return }
        $w = @(UsbWords (SuDo "sh /data/local/tmp/android-usb.sh restore $was $($script:MuUsbBoot)"))
        if ($w.Count -ge 1 -and $w[0] -eq 'restore') { Write-Host ('  ' + (T 'USB of Android set back to {1}' $was)) }
    } catch { }
}
