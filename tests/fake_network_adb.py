"""TCP transport adapter around fakeadb.py; never executes a device command."""
import contextlib
import hashlib
import io
import os
import re
import shlex
import sys

import fakeadb


def main(argv):
    fakeadb.log('network-call', argv)
    st = fakeadb.load()
    address = '192.168.0.1:5555'
    if argv == ['connect', address]:
        print('connected to ' + address)
        return 0
    if argv[:2] != ['-s', address]:
        raise RuntimeError('wireless installer did not pin the expected TCP endpoint')
    args = argv[2:]
    os.environ['ANDROID_SERIAL'] = st['serial']
    if args[:1] == ['shell']:
        line = args[1]
        marker = re.search(r'MU300-NET-RC-[a-f0-9]+:', line)
        if marker:
            wrapped = shlex.split(line)[2]
            command = shlex.split(wrapped)[2]
            if command.endswith(';'):
                command = command[:-1]  # shell separator following the quoted -c argument
            if command.startswith('umask 077; mkdir -p /data/adb/service.d && printf %s '):
                words = shlex.split(command); script = words[words.index('printf') + 2]
                fakeadb.log('adb-resume-script', {'script': script})
                print(hashlib.sha256(script.encode()).hexdigest() + '  ' + words[-1])
                rc = 0
            elif 'echo CID=$(cat /sys/class/block/mmcblk0/device/cid)' in command:
                fields = {'SERIAL': st['serial'], 'CID': st['cid'], 'SLOT': '_' + st['slot'],
                          'MODEL': st['model'], 'PRODUCT': st['device'], 'BOOT': st.get('network_boot', 'fake-boot'),
                          'BATTERY': '96', 'POWERED': '0', 'STATUS': 'Discharging', 'COMPLETED': '1', 'MAGISK': '1'}
                print('\n'.join(k + '=' + v for k, v in fields.items()))
                rc = 0
            else:
                # The ordinary fake uses one conventional staging path. No real filesystem is mapped here.
                command = re.sub(r'/data/local/tmp/mu300-wireless-[a-f0-9]{32}', '/data/local/tmp', command)
                out = io.StringIO()
                parts = shlex.split(command)
                shell_args = [command] if parts[:2] == ['su', '-c'] else parts
                with contextlib.redirect_stdout(out):
                    rc = fakeadb.main(['-s', st['serial'], 'shell', *shell_args])
                print(out.getvalue(), end='')
            print('\n' + marker[0] + str(rc))
            return 0
    args = [re.sub(r'/data/local/tmp/mu300-wireless-[a-f0-9]{32}', '/data/local/tmp', x) for x in args]
    return fakeadb.main(['-s', st['serial'], *args])


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
