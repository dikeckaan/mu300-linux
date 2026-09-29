# a newer mu300-linux release (mu300-update notice, run by mu300-post at boot and every 6 hours)
[ -s /run/mu300/update-available ] && { echo; cat /run/mu300/update-available; echo; }
