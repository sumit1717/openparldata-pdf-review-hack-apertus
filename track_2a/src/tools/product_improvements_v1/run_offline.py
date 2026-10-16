"""Run an explicit local command with pinned network denial; no installation."""
import argparse
import hashlib
import os
from pathlib import Path
import socket
import sys
import types

ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = 'evaluation/fixed-slot-diagnostic-v1/run-affected-checks.py'
BOUNDARY_SHA = 'a6530d1c7d956c3f6294f182097cad36c81b288d251ffb8e1aa2b6c35bdf712b'
GUARD = 'tools/product_offline_v3/offline-node.mjs'
GUARD_SHA = 'f00762a085bb5cc13961047f174dab01c4183edd8e39319caa77acfdc8c07edc'


def install():
    for name, digest in ((BOUNDARY, BOUNDARY_SHA), (GUARD, GUARD_SHA)):
        path = ROOT / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('boundary_pin_mismatch:' + name)
    module = types.ModuleType('_product_improvements_boundary')
    module.__file__ = str(ROOT / BOUNDARY)
    exec(compile((ROOT / BOUNDARY).read_bytes(), module.__file__, 'exec'), module.__dict__)
    module.install_network_boundary()
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except PermissionError:
        pass
    else:
        probe.close()
        raise RuntimeError('network_boundary_probe_failed')
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cwd', default='.')
    parser.add_argument('runtime', choices=['python', 'node'])
    parser.add_argument('args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.args:
        parser.error('an explicit command is required')
    relative = Path(args.cwd)
    if relative.is_absolute() or '..' in relative.parts:
        parser.error('cwd must be a repository-relative directory')
    cwd = ROOT / relative
    if not cwd.is_dir() or any(p.is_symlink() for p in [cwd, *cwd.parents]):
        parser.error('cwd must not contain symlinks')
    if any(os.environ.get(k) for k in ('GITHUB_ACTIONS', 'GITHUB_RUN_ID', 'GITHUB_EVENT_PATH')):
        parser.error('this entrypoint is local-only')
    install()
    env = {'PATH': os.environ['PATH'], 'HOME': '/tmp', 'LANG': 'C.UTF-8',
           'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(ROOT)}
    os.chdir(cwd)
    print('PINNED_SECCOMP_VERIFIED socket_creation=EPERM', file=sys.stderr, flush=True)
    if args.runtime == 'node':
        print('STRICT_NODE_GUARD_PIN_VERIFIED', file=sys.stderr, flush=True)
        os.execvpe('node', ['node', '--import', str(ROOT / GUARD), *args.args], env)
    os.execve(sys.executable, [sys.executable, '-B', *args.args], env)


if __name__ == '__main__':
    main()
