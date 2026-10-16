"""Execute an inert test file only; outer pinned launcher installs seccomp first."""
import os
from pathlib import Path
import runpy
import sys
import socket
try:
    socket.socket(socket.AF_INET,socket.SOCK_STREAM)
except PermissionError:
    pass
else:
    raise AssertionError('pinned kernel socket denial is required before tests')
def audit(event,args):
    if event.startswith(('subprocess.','os.exec','os.spawn','os.posix_spawn','os.fork')) or event in ('os.system','socket.connect','socket.bind','socket.__new__'):
        raise AssertionError('pure test attempted process or socket activity: '+event)
sys.addaudithook(audit)
path=Path(sys.argv[1]).resolve();sys.argv=sys.argv[1:];sys.path.insert(0,str(path.parent));sys.path.insert(0,str(path.parent.parent))
print('PURE_PROCESS_AND_SOCKET_AUDIT_ENABLED',flush=True)
runpy.run_path(str(path),run_name='__main__')
