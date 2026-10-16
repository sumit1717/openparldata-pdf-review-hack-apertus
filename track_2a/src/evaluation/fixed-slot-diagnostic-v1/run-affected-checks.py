"""Two explicitly separate pure-offline source scopes under one total deadline.

Historical commands prove historical-source compatibility only. Current-source
commands exercise every shared-policy consumer and the new diagnostic contracts.

No aggregate check, HTTP server, browser, container, install, credential or provider
operation is included. Workflow dependency installation is a separate earlier phase.
Logs and the receipt are new evidence only; cumulative ledger bytes are untouched.
"""
from __future__ import annotations
import argparse
import importlib.util
import tempfile
import ctypes
import errno
import platform
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event

ROOT = Path(__file__).resolve().parents[2]
PROFILE = 'fixed-slot-diagnostic-v2-affected-pure-checks-v1'
BUDGET_SECONDS = 360
LOG_LIMIT = 1024 * 1024
RECEIPT_RESERVE_SECONDS = 2
MAX_PARALLEL_CHECKS = 2
NETWORK_BOUNDARY = 'linux-x86_64-seccomp-deny-network-v1'
DIRECT_CONSUMERS = [
    'comparison-container-workflow.test.mjs',
    'fresh-rule-r10-workflow.test.mjs',
    'independent-recovery-workflow.test.mjs',
    'packaging.test.mjs',
    'parliament-format-r9-workflow.test.mjs',
    'parliament-h08-r11-workflow.test.mjs',
    'parliament-h08-r12-workflow.test.mjs',
    'prospective-pair-v6-v8a-workflow.test.mjs',
    'sparse-comparison-workflow.test.mjs',
    'sparse-development-r6-workflow.test.mjs',
    'sparse-prompt-successor-r8-workflow.test.mjs',
    'staged-acceptance-workflow.test.mjs',
    'track2a-review-offline-workflow.test.mjs',
    'track2a-review-visual-workflow.test.mjs',
    'track2a-synthetic-review-acceptance-workflow.test.mjs',
]
# These pure contracts cover the helper-matched browser/review trigger boundary.
# Playwright, local HTTP services and Docker are deliberately outside this inventory.
ADDITIONAL_NODE_TESTS = ['browser-contract.test.mjs', 'offline-ci-integration.test.mjs']
HISTORICAL_COMMANDS = [
    ['node', '--test', '--test-concurrency=1', *[
        'track_2b/tests/' + name for name in sorted(DIRECT_CONSUMERS + ADDITIONAL_NODE_TESTS)]],
    ['python', 'evaluation/verify_portable.py'],
    ['python', '-m', 'unittest', 'discover', '-s', 'evaluation/runner/tests', '-v'],
    ['python', '-m', 'unittest', 'discover', '-s', 'evaluation/scorer/tests', '-v'],
    ['python', 'evaluation/runner/launch.py'],
    ['python', 'evaluation/runner/artifact_restore.py'],
    ['python', 'evaluation/runner/prospective_pair_v6_v8a.py', 'preflight'],
    ['node', '--test', '--test-concurrency=1',
     'evaluation/prospective-pair-v6-v8a/tests/integration-controls.test.mjs',
     'evaluation/prospective-pair-v6-v8a/tests/scorer-controls.test.mjs'],
    ['python', '-m', 'unittest', 'discover', '-s', 'track_2a_projection_review/tests', '-v'],
    ['python', '-m', 'unittest', 'discover', '-s', 'track_2a_baseline_context/tests', '-v'],
    ['python', '-m', 'unittest', 'discover', '-s', 'track_2a_review_notes/tests', '-v'],
]
CURRENT_COMMANDS = [
    [*HISTORICAL_COMMANDS[0], 'evaluation/fixed-slot-diagnostic-v1/tests/workflow.test.mjs'],
    ['python', '-m', 'unittest', 'discover', '-s', 'evaluation/fixed-slot-diagnostic-v1/tests', '-p', 'test_*.py', '-v'],
    ['python', '-m', 'unittest', 'discover', '-s', 'evaluation/fixed-slot-diagnostic-v1/portable-tests', '-p', 'test_*.py', '-v'],
]
COMMANDS = HISTORICAL_COMMANDS + CURRENT_COMMANDS
COMMAND_SCOPES = ['historical_source_compatibility'] * len(HISTORICAL_COMMANDS) + ['current_source'] * len(CURRENT_COMMANDS)
HISTORICAL_FIXTURE_LABEL = 'historical-source-compatibility'


def fixture_helper():
    path = Path(__file__).resolve().with_name('historical_fixture.py')
    spec = importlib.util.spec_from_file_location('_fixed_slot_historical_fixture', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def command_records():
    return [{'scope': scope, 'argv': argv} for scope, argv in zip(COMMAND_SCOPES, COMMANDS, strict=True)]



def install_network_boundary():
    """Deny network syscalls in this process and every descendant, without privilege.

    Only the reviewed Linux x86_64 ABI is admitted. Unsupported platforms fail
    closed. Network socket creation/connection/listening and io_uring return EPERM.
    AF_UNIX socketpair IPC and its I/O remain available for Node test subprocesses.
    This is a network boundary, not a claim to sandbox arbitrary filesystem code.
    """
    if sys.platform != 'linux' or platform.machine() != 'x86_64':
        raise RuntimeError('unsupported_network_boundary_platform')
    class Filter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte),
                    ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint)]
    class Program(ctypes.Structure):
        _fields_ = [('len', ctypes.c_ushort), ('filter', ctypes.POINTER(Filter))]
    # seccomp_data.arch then nr; reject foreign ABIs and the x32 syscall bit.
    rules = [(0x20, 0, 0, 4), (0x15, 1, 0, 0xC000003E),
             (0x06, 0, 0, 0x80000000), (0x20, 0, 0, 0),
             (0x45, 0, 1, 0x40000000), (0x06, 0, 0, 0x00050000 | errno.EPERM)]
    # Node's child-process IPC requires AF_UNIX socketpair; this is not a
    # listener or network connection. All socket() and bind/connect/listen stay denied.
    rules.extend([(0x15, 0, 4, 53), (0x20, 0, 0, 16), (0x15, 0, 1, 1),
                  (0x06, 0, 0, 0x7FFF0000), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    for number in [41, 42, 43, 49, 50, 288, 425, 426, 427]:
        rules.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x00050000 | errno.EPERM)])
    rules.append((0x06, 0, 0, 0x7FFF0000))
    filters = (Filter * len(rules))(*(Filter(*rule) for rule in rules))
    program = Program(len(rules), filters)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'no_new_privileges_failed')
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'network_filter_failed')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def inventory():
    records = command_records()
    return {'profile': PROFILE, 'budget_seconds': BUDGET_SECONDS,
            'commands': records, 'inventory_sha256': sha(canonical(records)),
            'max_parallel_checks': MAX_PARALLEL_CHECKS, 'network_boundary': NETWORK_BOUNDARY,
            'historical_source_manifest_sha256': sha((ROOT / 'evaluation/fixed-slot-diagnostic-v1/live/historical-source-manifest.json').read_bytes()),
            'historical_source_commit': fixture_helper().COMMIT}


def verify_consumers(root=ROOT):
    actual = sorted(p.name for p in (root / 'track_2b/tests').glob('*.test.mjs')
                    if 'reviewed-workflow-policy.mjs' in p.read_text())
    if actual != DIRECT_CONSUMERS:
        raise ValueError('shared_policy_consumer_inventory_changed')
    for command in COMMANDS:
        for part in command:
            if (part.endswith(('.py', '.mjs')) and '*' not in part) or part.endswith(('/tests', '/portable-tests')):
                if not (root / part).exists():
                    raise ValueError('missing_affected_check:' + part)


def bindings():
    event_path = os.environ.get('GITHUB_EVENT_PATH')
    inputs = {}
    if event_path:
        raw = Path(event_path).read_bytes()
        if len(raw) > 262144:
            raise ValueError('event_size_bound')
        event = json.loads(raw)
        inputs = event.get('inputs') or {}
    return {'reviewed_commit': inputs.get('reviewed_commit'),
            'github_sha': os.environ.get('GITHUB_SHA'),
            'github_run_id': os.environ.get('GITHUB_RUN_ID'),
            'github_run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
            'source_manifest_sha256': inputs.get('source_manifest_sha256')}


def stop_group(process):
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run_command(argv, log, deadline, env, cancelled=None, cwd=None):
    started = time.monotonic()
    status = 'failed'
    if started >= deadline or (cancelled is not None and cancelled.is_set()):
        return {'argv': argv, 'status': 'not_started', 'exit_code': None, 'elapsed_seconds': 0,
                'log': None, 'log_sha256': None, 'log_bytes': 0}
    size = 0
    digest = hashlib.sha256()
    process = subprocess.Popen(argv, cwd=ROOT if cwd is None else cwd, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               start_new_session=True, close_fds=True)
    try:
        with log.open('xb') as stream, selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if cancelled is not None and cancelled.is_set():
                    status = 'cancelled'
                    stop_group(process)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    stop_group(process)
                    break
                ready = selector.select(min(remaining, 0.1))
                for key, _ in ready:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if size + len(chunk) > LOG_LIMIT:
                        status = 'output_limit'
                        stop_group(process)
                        break
                    stream.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                if status == 'output_limit':
                    break
            while process.poll() is None:
                if cancelled is not None and cancelled.is_set():
                    status = 'cancelled'
                    stop_group(process)
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    status = 'timeout'
                    stop_group(process)
                    break
                try:
                    process.wait(timeout=min(.1, remaining))
                except subprocess.TimeoutExpired:
                    pass
            if status not in ('timeout', 'output_limit', 'cancelled'):
                status = 'passed' if process.returncode == 0 else 'failed'
            stream.flush()
            os.fsync(stream.fileno())
    except InterruptedError:
        status = 'cancelled'
        stop_group(process)
    finally:
        if process.poll() is None:
            stop_group(process)
        process.stdout.close()
    return {'argv': argv, 'status': status, 'exit_code': process.returncode,
            'elapsed_seconds': time.monotonic() - started,
            'log': log.relative_to(ROOT).as_posix() if log.is_relative_to(ROOT) else log.as_posix(),
            'log_sha256': digest.hexdigest(), 'log_bytes': size}


def child_environment(root, output):
    # No event path, GitHub identity, approval, provider key or ambient credentials.
    return {'PATH': os.environ.get('PATH', os.defpath), 'HOME': str(output.resolve()),
            'TZ': 'UTC', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONPATH': str(root), 'REVIEW_REPO_ROOT': str(root)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='Print exact scoped inventory; execute nothing')
    parser.add_argument('--local-historical-source', type=Path,
                        help='Explicit verified local baseline only; forbidden in hosted/event-bearing execution')
    args = parser.parse_args()
    if args.list:
        print(canonical(inventory()).decode())
        return 0
    started = time.monotonic()
    deadline = started + BUDGET_SECONDS - RECEIPT_RESERVE_SECONDS
    output = ROOT / 'evaluation-checks'
    output.mkdir(mode=0o700, exist_ok=False)
    receipt = {**inventory(), 'status': 'failed', 'elapsed_seconds': None,
               'started_at_unix': time.time(), 'helper_sha256': sha(Path(__file__).read_bytes()),
               'bindings': None, 'scopes': {},
               'commands': [{**record, 'status': 'not_started', 'exit_code': None,
                             'elapsed_seconds': 0, 'log': None, 'log_sha256': None, 'log_bytes': 0}
                            for record in command_records()]}
    cancelled = Event()
    def interrupted(signum, frame):
        cancelled.set()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, interrupted)
    try:
        receipt['bindings'] = bindings()
        verify_consumers()
        install_network_boundary()
        helper = fixture_helper()
        # Both materialization and both check scopes consume this SAME deadline.
        # The fixture is visibly outside the current source, never published.
        with tempfile.TemporaryDirectory(prefix=HISTORICAL_FIXTURE_LABEL + '-', dir=ROOT.parent) as folder:
            historical_root = Path(folder) / HISTORICAL_FIXTURE_LABEL
            historical_proof = helper.build(ROOT, historical_root, deadline, args.local_historical_source)
            old_inventory = helper.old_inventory(historical_root)
            if old_inventory['commands'] != HISTORICAL_COMMANDS or len(HISTORICAL_COMMANDS) != 11:
                raise ValueError('historical_command_inventory_drift')
            historical_proof['command_inventory_sha256'] = old_inventory['inventory_sha256']
            receipt['scopes'] = {
                'historical_source_compatibility': historical_proof,
                'current_source': {'scope': 'current_source',
                    'source_manifest_sha256': receipt['bindings']['source_manifest_sha256'],
                    'github_sha': receipt['bindings']['github_sha'],
                    'historical_runtime_current_tree_pass_claim': False},
            }
            roots = {'historical_source_compatibility': historical_root, 'current_source': ROOT}
            with ThreadPoolExecutor(max_workers=MAX_PARALLEL_CHECKS) as pool:
                futures = {pool.submit(run_command, record['argv'], output / f'{index + 1:02d}.log',
                                       deadline, child_environment(roots[record['scope']], output),
                                       cancelled, roots[record['scope']]): index
                           for index, record in enumerate(command_records())}
                for future in as_completed(futures):
                    index = futures[future]
                    try:
                        result = future.result()
                    except Exception as error:
                        result = {**receipt['commands'][index], 'status': 'failed',
                                  'error': type(error).__name__}
                    result['scope'] = COMMAND_SCOPES[index]
                    receipt['commands'][index] = result
                    print(f"{index + 1}/{len(COMMANDS)} {result['scope']} {result['status']} {result['elapsed_seconds']:.3f}s", flush=True)
            # Preserve complete failures/timeouts; neither scope can substitute for the other.
            if all(item['status'] == 'passed' for item in receipt['commands']) and time.monotonic() < deadline and not cancelled.is_set():
                receipt['status'] = 'passed'
    except Exception as error:
        receipt['error'] = type(error).__name__
        receipt['error_detail'] = str(error)[:1024]
    finally:
        if cancelled.is_set():
            receipt['status'] = 'cancelled'
        receipt['elapsed_seconds'] = time.monotonic() - started
        receipt['finished_at_unix'] = time.time()
        with (output / 'affected-checks.json').open('xb') as stream:
            stream.write(canonical(receipt) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
    return 0 if receipt['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
