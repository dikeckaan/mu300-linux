# SMS

**In one sentence:** `sudo sms list` reads the text messages on your SIM and `sudo sms send NUMBER TEXT` sends one,
straight from the modem, with no Android involved.

**The simple version:** the modem keeps a small mailbox on the SIM card. These commands open the mailbox, read the
letters and post new ones.

## Commands

```sh
sudo sms list                       # every message, long ones joined back together
sudo sms read INDEX                 # one message in full
sudo sms send NUMBER TEXT...        # send one (Turkish and emoji included; it picks the encoding)
sudo sms delete INDEX               # remove one from the SIM (also: read, all)
sudo sms watch [COMMAND]            # wait for new messages, run COMMAND for each
```

No `sudo` on OpenWrt. All of it goes through `mu300-atd`, so it queues behind anything else talking to the modem.

## On OpenWrt with the control panel

Use **Cellular -> SMS** in the panel: read, send and delete. There a pool daemon syncs the SIM every 30 s with
`AT+CMGL`, which **marks unread messages on the SIM as read**; the panel keeps its own unread state.

> **Do not run `sms delete read` on that system.** Because the pool marks everything it has seen as read, it would
> delete messages nobody has looked at. Delete from the panel, or with `mu300-sms delete` (which touches the SIM only
> with `--sim`). For automation use the panel's hook, `/etc/mu300/sms-hook`, rather than `sms watch`.

## USSD

Balance checks and similar codes:

```sh
sudo mu300-ussd '*101#'
```

## Why PDU mode

The modem's text mode garbles senders that are names rather than numbers and cannot tell that several stored parts
are one long message, so `sms` uses PDU mode and decodes the frames itself, including the Turkish national language
shift. Sending picks GSM 7-bit when every character fits, UCS-2 otherwise. Details:
[FINDINGS 26c](https://github.com/dikeckaan/mu300-linux/blob/main/docs/FINDINGS.md#26c-sms-needs-pdu-mode-and-turkish-needs-more-than-that).

## Voice calls

Not available: the board has no speaker or microphone, and call audio through the modem's audio DSP is work in
progress that does not carry sound yet. See [Hardware Notes](Hardware-Notes#no-sound-no-screen).
