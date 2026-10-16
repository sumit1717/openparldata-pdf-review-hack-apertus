"""Explicit, local, single-attempt Apertus capture; never a semantic admission.

The unchanged converter owns preparation and import validation. This optional
bridge owns only the wire envelope, private custody and declared attempt index.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from dataclasses import dataclass
import getpass
import http.client
import os
from pathlib import Path
import re
import resource
import signal
import ssl
import stat
import sys
import warnings

from track_2a_converter import pipeline as converter

HOST = 'api.inference.cscs.ch'
ROUTE = '/v1/chat/completions'
ENDPOINT = 'https://' + HOST + ROUTE
MODEL = 'swiss-ai/Apertus-v1.5-70B'
ALLOWED_BASE_URLS = frozenset(('https://' + HOST, 'https://' + HOST + '/v1'))
PROFILE = 'formrehearsal-pdf-apertus-capture-1'
MAX_TOKENS = 4096
TIMEOUT_SECONDS = 90
MAX_REQUEST_BYTES = 131072
MAX_RESPONSE_BYTES = converter.RESPONSE_CAP
CONVERTER_PINS = {
    'pipeline.py': 'ac98ec192daa3255b14fe38195559dac2e9c375d501f56ead1942eccd95109d4',
    'prompt.txt': 'adf72cbb9d7917e94e41bcc3da834291a2392815048d4f4087d7e57a99d07f1a',
    'response.schema.json': '4d3fe8ec44eb458c13e0ca00c07297952833b4dc09c5e0b27b186605c23939c3',
}


class SafeFailure(ValueError):
    """Fixed code only. Never include source text, headers or provider errors."""


def require(condition, code):
    if not condition:
        raise SafeFailure(code)


def validate_runtime_selectors(environ):
    """Template variables constrain the fixed route; they cannot override it.

    This function deliberately never reads LLM_API_KEY. A single trailing slash
    is harmless; userinfo, ports, queries, fragments and alternate paths reject.
    """
    name = environ.get('LLM_NAME', MODEL)
    base = environ.get('LLM_BASE_URL', 'https://' + HOST + '/v1')
    require(name == MODEL, 'runtime_model_not_allowlisted')
    require(isinstance(base, str), 'runtime_base_url_not_allowlisted')
    if base.endswith('/'):
        base = base[:-1]
    require(base in ALLOWED_BASE_URLS, 'runtime_base_url_not_allowlisted')


def checked_converter():
    require(converter.CONVERTER_VERSION == '0.2.0', 'converter_version_mismatch')
    for name, expected in CONVERTER_PINS.items():
        require(converter.sha(converter.read_bytes(converter.ROOT / name)) == expected,
                'converter_source_pin_mismatch')


@dataclass(frozen=True)
class Selection:
    prepare_pin: str
    request_id: str
    source_sha256: str
    prepared_request: bytes
    prompt: bytes
    schema: bytes
    wire: bytes


def select(prepared, expected_prepare, request_id):
    """Recheck every prepared artifact and every request before constructing wire bytes."""
    checked_converter()
    result, bundle, requests, schema = converter.load_prepared(prepared, expected_prepare)
    require(isinstance(request_id, str) and request_id in requests, 'selected_request_missing')
    root = Path(prepared)
    request_raw = converter.read_bytes(root / 'requests' / (request_id + '.json'))
    prompt_raw = converter.read_bytes(root / 'prompt.txt')
    schema_raw = converter.read_bytes(root / 'response.schema.json')
    # A second read cannot silently substitute bytes after load_prepared checked them.
    require(request_raw == converter.canonical(requests[request_id]), 'selected_request_changed')
    require(converter.sha(prompt_raw) == bundle['prompt_sha256'] and
            converter.sha(schema_raw) == bundle['schema_sha256'], 'selected_contract_changed')
    user = converter.canonical({'required_output_schema': schema, 'request': requests[request_id]}).decode('utf-8')
    wire = converter.canonical({
        'model': MODEL, 'temperature': 0, 'stream': False, 'max_tokens': MAX_TOKENS,
        'messages': [{'role': 'system', 'content': prompt_raw.decode('utf-8')},
                     {'role': 'user', 'content': user}],
    })
    require(len(wire) <= MAX_REQUEST_BYTES, 'wire_request_size_limit')
    return Selection(expected_prepare, request_id, bundle['source_sha256'], request_raw,
                     prompt_raw, schema_raw, wire)


def echoes_key(raw, key):
    """Conservatively screen plaintext and common reversible encodings before writes.

    This is not a proof against arbitrary adversarial encodings. Incomplete,
    compressed or non-UTF-8 bodies are withheld, never partly redacted as originals.
    """
    token = key.encode('ascii')
    encoded = (base64.b64encode(token), base64.urlsafe_b64encode(token))
    variants = (token, *(item for value in encoded for item in (value, value.rstrip(b'='))),
                token.hex().encode(), token.hex().upper().encode())
    normalized = re.sub(rb'\\u00([0-9a-fA-F]{2})', lambda m: bytes([int(m[1], 16)]), raw)
    normalized = re.sub(rb'%([0-9a-fA-F]{2})', lambda m: bytes([int(m[1], 16)]), normalized)
    normalized = normalized.replace(b'\\/', b'/').replace(b'\\\\', b'\\').replace(b'\\"', b'"')
    return any(value in raw or value in normalized for value in variants)


@contextmanager
def deadline():
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'existing_process_timer')
    previous = signal.getsignal(signal.SIGALRM)
    budget = {'expired': False}
    def expired(_signum, _frame):
        budget['expired'] = True
        raise TimeoutError()
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, TIMEOUT_SECONDS)
    try:
        yield budget
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class Capture:
    status: int | None = None
    body: bytes = b''
    complete: bool = False
    error: str | None = None


TRANSPORT_ERRORS = frozenset(('unsupported_content_encoding', 'incomplete_response',
    'response_too_large', 'deadline_or_socket_timeout', 'transport_failure', 'interrupted_outcome_unknown'))


def tls_context():
    # create_default_context() honors SSLKEYLOGFILE; this path does not.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_default_certs()
    return context


def send_once(raw, key):
    """One fixed HTTPS POST. http.client has no redirects, proxy-env use or retries."""
    connection, status, body = None, None, b''
    try:
        with deadline() as budget:
            try:
                connection = http.client.HTTPSConnection(HOST, port=443,
                    timeout=TIMEOUT_SECONDS, context=tls_context())
                connection.set_debuglevel(0)
                connection.request('POST', ROUTE, body=raw, headers={
                    'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
                    'Accept': 'application/json', 'Accept-Encoding': 'identity', 'Connection': 'close'})
                response = connection.getresponse()
                status = response.status
                if response.getheader('Content-Encoding', 'identity').lower() != 'identity':
                    return Capture(status, b'', False, 'unsupported_content_encoding')
                try:
                    body = response.read(MAX_RESPONSE_BYTES + 1)
                except http.client.IncompleteRead:
                    return Capture(status, b'', False, 'incomplete_response')
                if len(body) > MAX_RESPONSE_BYTES:
                    return Capture(status, b'', False, 'response_too_large')
                if response.length not in (None, 0):
                    return Capture(status, b'', False, 'incomplete_response')
                return Capture(status, body, True)
            finally:
                if connection is not None and not budget['expired']:
                    try:
                        connection.close()
                    except Exception:
                        pass
    except TimeoutError:
        return Capture(status, b'', False, 'deadline_or_socket_timeout')
    except KeyboardInterrupt:
        return Capture(status, b'', False, 'interrupted_outcome_unknown')
    except Exception:
        return Capture(status, b'', False, 'transport_failure')


@contextmanager
def reserve(parent, selection):
    """The prepare/request pair gets one durable directory in this private store.

    Never resume, overwrite or delete a prior attempt, even after a crash. This
    is an at-most-one attempt within the selected store, not provider idempotency.
    """
    parent = converter.safe_path(parent)
    fd = converter.open_directory(parent, create=True)
    capture_fd = None
    try:
        info = os.fstat(fd)
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o700,
                'private_owned_capture_store_required')
        name = selection.prepare_pin + '-' + selection.request_id
        try:
            os.mkdir(name, mode=0o700, dir_fd=fd)
        except FileExistsError:
            raise SafeFailure('attempt_already_reserved_no_retry') from None
        os.fsync(fd)
        capture_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
        os.fchmod(capture_fd, 0o700)
        yield capture_fd, parent / name
    finally:
        if capture_fd is not None:
            os.close(capture_fd)
        os.close(fd)


def write_private(fd, name, raw):
    require('/' not in name and '\\' not in name and name not in ('', '.', '..'), 'invalid_output_name')
    stream_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
    with os.fdopen(stream_fd, 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.fsync(fd)


def envelope_content(raw):
    """Strict metadata gate only. Do not parse, rewrite or repair assistant content."""
    try:
        envelope = converter.strict_load(raw, MAX_RESPONSE_BYTES)
        require(isinstance(envelope, dict) and envelope.get('model') == MODEL, 'envelope_model_mismatch')
        choices = envelope.get('choices')
        require(isinstance(choices, list) and len(choices) == 1, 'envelope_choice_mismatch')
        choice = choices[0]
        require(isinstance(choice, dict) and type(choice.get('index')) is int and choice['index'] == 0,
                'envelope_choice_mismatch')
        require(choice.get('finish_reason') == 'stop', 'envelope_finish_not_stop')
        message = choice.get('message')
        require(isinstance(message, dict) and message.get('role') == 'assistant' and
                isinstance(message.get('content'), str) and
                message.get('refusal') in (None, '') and not message.get('tool_calls') and
                not message.get('function_call'), 'envelope_message_mismatch')
        usage = envelope.get('usage')
        require(isinstance(usage, dict), 'envelope_usage_invalid')
        counts = {name: usage.get(name) for name in ('prompt_tokens', 'completion_tokens', 'total_tokens')}
        require(all(type(n) is int and 0 <= n <= 10000000 for n in counts.values()) and
                counts['prompt_tokens'] + counts['completion_tokens'] == counts['total_tokens'] and
                0 < counts['completion_tokens'] <= MAX_TOKENS, 'envelope_usage_invalid')
        content = message['content'].encode('utf-8')
        require(0 < len(content) <= converter.RESPONSE_CAP, 'assistant_content_size_invalid')
        return content, counts
    except (converter.PipelineError, TypeError, KeyError, UnicodeError, RecursionError):
        raise SafeFailure('envelope_invalid_json_or_shape') from None


def retained_body(capture, key):
    require(isinstance(capture, Capture), 'invalid_transport_capture')
    require(capture.error is None or capture.error in TRANSPORT_ERRORS, 'invalid_transport_capture')
    require(capture.status is None or type(capture.status) is int and 100 <= capture.status <= 599,
            'invalid_transport_capture')
    require(type(capture.complete) is bool and type(capture.body) is bytes, 'invalid_transport_capture')
    if not capture.complete or capture.error is not None:
        return 'withheld_incomplete_or_uninspectable_body'
    if len(capture.body) > MAX_RESPONSE_BYTES:
        return 'withheld_response_size_limit'
    try:
        capture.body.decode('utf-8', errors='strict')
    except UnicodeError:
        return 'withheld_uninspectable_text_encoding'
    if b'\x00' in capture.body:
        return 'withheld_uninspectable_text_encoding'
    if echoes_key(capture.body, key):
        return 'withheld_possible_secret_echo'
    return 'complete_original_retained'


def capture_one(prepared, expected_prepare, request_id, output_parent, key, *, transport=None):
    """Explicit dispatch API. Transport injection is solely for inert offline tests.

    The caller must authorize source transmission and any charge independently.
    This API receives a key only from its caller. The explicit CLI send path can
    use the template's existing process LLM_API_KEY or private getpass fallback;
    neither path stores credentials or reads a credential file/store.
    """
    require(isinstance(key, str) and 16 <= len(key) <= 4096 and
            all(33 <= ord(ch) <= 126 for ch in key), 'invalid_key_format')
    selected = select(prepared, expected_prepare, request_id)
    metadata = {
        'profile': PROFILE, 'prepare_result_sha256': expected_prepare,
        'request_id': request_id, 'source_sha256': selected.source_sha256,
        'endpoint': ENDPOINT, 'model': MODEL, 'max_output_tokens': MAX_TOKENS,
        'maximum_http_post_attempts': 1, 'retries': 0,
        'semantic_validation': 'unadjudicated', 'answer_eligible': False,
        'human_reference': False, 'provider_execution_or_charge': 'not_inferred',
        'attempt_state': 'reserved_outcome_unknown',
    }
    inputs = {'request.original.json': selected.prepared_request, 'prompt.original.txt': selected.prompt,
              'schema.original.json': selected.schema, 'wire-request.original.json': selected.wire}
    preflight = [*inputs.values(), converter.canonical(metadata),
                 str(Path(output_parent).absolute()).encode('utf-8')]
    require(not any(echoes_key(raw, key) for raw in preflight), 'key_matches_saved_input_no_request_sent')
    files = {}
    with reserve(output_parent, selected) as (fd, path):
        def save(name, raw):
            require(not echoes_key(raw, key), 'artifact_withheld_possible_secret_echo')
            write_private(fd, name, raw)
            files[name] = {'sha256': converter.sha(raw), 'bytes': len(raw)}
        # All reservation and request bytes are fsynced before the sole dispatch site.
        save('attempt.json', converter.canonical(metadata))
        for name, raw in inputs.items():
            save(name, raw)
        try:
            capture = (send_once if transport is None else transport)(selected.wire, key)
            retention = retained_body(capture, key)
        except KeyboardInterrupt:
            capture = Capture(error='interrupted_outcome_unknown')
            retention = 'withheld_incomplete_or_uninspectable_body'
        except Exception:
            capture = Capture(error='transport_failure')
            retention = 'withheld_incomplete_or_uninspectable_body'
        receipt = {**metadata, 'attempt_state': 'capture_recorded', 'transport_invocations': 1,
                   'http_status': capture.status, 'response_complete': capture.complete,
                   'transport_error': capture.error, 'response_retention': retention,
                   'finish_reason': None, 'usage': None, 'assistant_content_derivation': None}
        entry = {'request_id': request_id, 'status': 'failed', 'error_code': 'external_capture_failed_outcome_unknown'}
        if retention == 'complete_original_retained':
            # Save and fsync exact complete bytes before strict JSON parsing.
            save('response.original.bin', capture.body)
            if capture.status == 200:
                try:
                    content, usage = envelope_content(capture.body)
                    require(not echoes_key(content, key), 'assistant_content_secret_echo')
                    save('assistant-content.decoded.utf8', content)
                    receipt.update(finish_reason='stop', usage=usage,
                        assistant_content_derivation='exact_choices_0_message_content_utf8_no_repair')
                    entry = {'request_id': request_id, 'status': 'captured',
                             'response_path': 'assistant-content.decoded.utf8'}
                except SafeFailure as exc:
                    entry['error_code'] = str(exc)
            else:
                entry['error_code'] = 'provider_http_status_not_200'
        elif retention == 'withheld_possible_secret_echo':
            entry['error_code'] = 'response_withheld_possible_secret_echo'
        # Read-back custody must pass before an importable index is emitted.
        for name, record in files.items():
            actual = converter.read_bytes(path / name, reject_hardlinks=True)
            require(len(actual) == record['bytes'] and converter.sha(actual) == record['sha256'],
                    'capture_custody_readback_failed')
        index = {'profile': converter.PROFILE, 'prepare_result_sha256': expected_prepare, 'entries': [entry]}
        index_raw = converter.canonical(index)
        require(not echoes_key(index_raw, key), 'index_withheld_possible_secret_echo')
        # Bind the planned final index before publication. It is not yet on disk.
        files['index.json'] = {'sha256': converter.sha(index_raw), 'bytes': len(index_raw)}
        receipt['files'] = files
        receipt['capture_status'] = entry['status']
        receipt['capture_error'] = entry.get('error_code')
        receipt_raw = converter.canonical(receipt)
        receipt_pin = converter.sha(receipt_raw)
        # The final index is published only after a durable, verified receipt.
        # Receipt-write failure cannot leave an index consumable by the importer.
        require(not echoes_key(receipt_raw, key), 'receipt_withheld_possible_secret_echo')
        write_private(fd, 'receipt.json', receipt_raw)
        _verify_capture(path, receipt_pin, pending_index=index_raw)
        write_private(fd, 'index.json', index_raw)
        return path, receipt_pin, receipt


def verify_capture(path, expected_receipt):
    """Read-only custody check with an independently retained receipt byte hash.

    Hashes are consistency checks, not provider authenticity or human review.
    The converter index remains a declaration and does not embed this receipt.
    """
    return _verify_capture(path, expected_receipt)


def _verify_capture(path, expected_receipt, *, pending_index=None):
    """Internal pre-publication mode verifies held index bytes before writing them."""
    require(isinstance(expected_receipt, str) and converter.DIGEST.fullmatch(expected_receipt),
            'expected_receipt_pin_required')
    path = converter.safe_path(path)
    raw = converter.read_bytes(path / 'receipt.json', reject_hardlinks=True)
    require(converter.sha(raw) == expected_receipt, 'receipt_pin_mismatch')
    receipt = converter.strict_load(raw)
    require(receipt['profile'] == PROFILE and receipt['endpoint'] == ENDPOINT and receipt['model'] == MODEL,
            'capture_contract_mismatch')
    require(receipt['answer_eligible'] is False and receipt['semantic_validation'] == 'unadjudicated',
            'capture_adjudication_mismatch')
    expected_files = set(receipt['files']) | {'receipt.json'}
    if pending_index is not None:
        expected_files -= {'index.json'}
    require(set(p.name for p in path.iterdir()) == expected_files,
            'capture_inventory_mismatch')
    for name, record in receipt['files'].items():
        require('/' not in name and '\\' not in name, 'capture_inventory_mismatch')
        original = (pending_index if name == 'index.json' and pending_index is not None else
                    converter.read_bytes(path / name, reject_hardlinks=True))
        require(len(original) == record['bytes'] and converter.sha(original) == record['sha256'],
                'capture_artifact_hash_mismatch')
    index = converter.strict_load(pending_index if pending_index is not None else
                                  converter.read_bytes(path / 'index.json'))
    entry = index['entries'][0]
    require(index == {'profile': converter.PROFILE, 'prepare_result_sha256': receipt['prepare_result_sha256'],
                     'entries': [entry]} and entry['request_id'] == receipt['request_id'] and
            entry['status'] == receipt['capture_status'], 'capture_index_mismatch')
    converter._entry_shape(entry)
    if entry['status'] == 'captured':
        require(receipt['http_status'] == 200 and receipt['response_complete'] is True and
                receipt['transport_error'] is None and receipt['response_retention'] == 'complete_original_retained' and
                entry['response_path'] == 'assistant-content.decoded.utf8', 'capture_success_metadata_mismatch')
        content, usage = envelope_content(converter.read_bytes(path / 'response.original.bin', MAX_RESPONSE_BYTES))
        require(content == converter.read_bytes(path / entry['response_path']) and usage == receipt['usage'] and
                receipt['finish_reason'] == 'stop', 'assistant_derivation_mismatch')
    else:
        require(entry['status'] == 'failed' and entry['error_code'] == receipt['capture_error'],
                'capture_failure_metadata_mismatch')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('inspect', 'send'):
        p = sub.add_parser(command)
        p.add_argument('--prepared', type=Path, required=True)
        p.add_argument('--expected-prepare', required=True)
        p.add_argument('--request-id', required=True)
        if command == 'send':
            p.add_argument('--out-parent', type=Path, required=True)
    p = sub.add_parser('verify')
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--expected-receipt', required=True)
    key = None
    try:
        args = parser.parse_args(argv)
        if args.command == 'verify':
            verify_capture(args.capture, args.expected_receipt)
            print('Capture custody verified against the selected pin. Unadjudicated; no provider-authenticity or human-review claim.')
            return 0
        validate_runtime_selectors(os.environ)
        selected = select(args.prepared, args.expected_prepare, args.request_id)
        print('Endpoint:', ENDPOINT, '\nModel:', MODEL)
        print('Source SHA-256:', selected.source_sha256, '\nRequest ID:', selected.request_id)
        print('Prepare pin:', selected.prepare_pin, '\nWire SHA-256:', converter.sha(selected.wire))
        print('One request; max output tokens:', MAX_TOKENS, '; deadline seconds:', TIMEOUT_SECONDS)
        print('No retry, redirect, proxy or automatic import. Source text is sent to CSCS; provider charges may apply.')
        if args.command == 'inspect':
            return 0
        require(os.name == 'posix', 'POSIX_runtime_required')
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        print('Proceed only with permission to send this exact source and approval for any provider charge.')
        # Credential access occurs only after explicit send and all public checks.
        # Do not expand this to dotenv, files, keychains or inherited subprocesses.
        key = os.environ.get('LLM_API_KEY')
        if key is None:
            require(sys.stdin.isatty() and sys.stderr.isatty(), 'private_POSIX_terminal_required')
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                key = getpass.getpass('Enter the existing CSCS key privately for this one attempt (blank cancels): ')
        if key == '':
            print('Cancelled. No request sent.')
            return 0
        _, pin, receipt = capture_one(args.prepared, args.expected_prepare, args.request_id,
                                     args.out_parent, key)
        # Never print paths, provider strings, exception text, request text or the key.
        print('Private capture recorded. Receipt SHA-256:', pin)
        print('Capture status:', receipt['capture_status'], '; semantic validation: unadjudicated.')
        print('Keep this receipt pin separately; verify custody before importing index.json. Never retry automatically.')
        return 0 if receipt['capture_status'] == 'captured' else 2
    except (Exception, KeyboardInterrupt):
        print('Stopped safely. No automatic retry. A reserved attempt may have reached the provider; retain its private directory.', file=sys.stderr)
        return 2
    finally:
        key = None


if __name__ == '__main__':
    raise SystemExit(main())
