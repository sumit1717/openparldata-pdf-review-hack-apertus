"""Authored JSON/byte fixtures only; never parse a PDF or contact a provider.

Run through the existing pinned socket/process-denial launcher and audit guard.
Any returned content is an inert fixture, never a claim of model performance.
"""
import base64
import io
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from apertus_capture import capture as bridge
from track_2a_converter import pipeline as converter

KEY = 'INERT-TEST-TOKEN-ONLY-0123456789'


def fixture(parent):
    """Author a preparation-shaped test inventory without running prepare/extract."""
    source = b'%PDF-1.7\nINERT AUTHORED PLACEHOLDER. NEVER PDF-PARSED.\n'
    text = 'The authored council proposes an example. ' * 8
    pages = [
        {'page': 1, 'text': text, 'text_sha256': converter.sha(text.encode()),
         'status': 'text_extracted', 'error': None, 'ocr_status': 'not_attempted'},
        {'page': 2, 'text': '', 'text_sha256': converter.sha(b''),
         'status': 'no_text_unresolved', 'error': None, 'ocr_status': 'not_attempted'},
        {'page': 3, 'text': '', 'text_sha256': converter.sha(b''),
         'status': 'extraction_failed', 'error': 'authored_page_failure', 'ocr_status': 'not_attempted'},
    ]
    extractor = {'policy': converter.EXTRACTION_POLICY, 'converter_version': converter.CONVERTER_VERSION,
                 'fixture_label': 'authored_metadata_no_extractor_execution'}
    prompt = converter.read_bytes(converter.ROOT / 'prompt.txt')
    schema = converter.read_bytes(converter.ROOT / 'response.schema.json')
    out, start = converter.begin(parent / 'prepared', 'prepare', {'source_sha256': converter.sha(source), 'chunk_chars': 256})
    for name, raw in (('source.pdf', source), ('prompt.txt', prompt), ('response.schema.json', schema)):
        converter.write_new(out / name, raw)
    requests = []
    for page in pages:
        for chunk in converter.chunks_for(page, 256):
            request = converter.make_request(converter.sha(source), page, chunk, converter.sha(schema), converter.sha(prompt), extractor)
            raw = converter.canonical(request)
            name = 'requests/' + request['request_id'] + '.json'
            converter.write_new(out / name, raw)
            requests.append({'request_id': request['request_id'], 'path': name, 'sha256': converter.sha(raw), 'chunk': chunk})
    bundle = {'profile': converter.PROFILE, 'source_sha256': converter.sha(source), 'source_bytes': len(source),
              'page_count': len(pages), 'pages': pages, 'source_access': {'status': 'opened_without_credentials', 'is_encrypted': False},
              'page_status_counts': converter.page_status_counts(pages), 'extractor': extractor,
              'chunk_chars': 256, 'schema_sha256': converter.sha(schema), 'prompt_sha256': converter.sha(prompt),
              'requests': requests, 'coverage_claim': 'authored_test_inventory', 'ocr_status': 'not_attempted'}
    converter.write_new(out / 'bundle.json', converter.canonical(bundle))
    result = converter.finish(out, start, {'bundle_sha256': converter.sha(converter.canonical(bundle))})
    rid = requests[0]['request_id']
    request = converter.strict_load(converter.read_bytes(out / requests[0]['path']))
    response = {k: request[k] for k in ('request_id', 'binding', 'reviewed_scope')}
    response['events'] = []
    return out, result['result_sha256'], rid, response


def envelope(content, **updates):
    body = {'model': bridge.MODEL, 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': content}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150}}
    body.update(updates)
    return json.dumps(body, ensure_ascii=True, indent=3).encode() + b'\n'


class Terminal(io.StringIO):
    def isatty(self):
        return True


class FakeReply:
    def __init__(self, body=b'{}', status=200, length=0, encoding='identity', failure=None):
        self.body, self.status, self.length = body, status, length
        self.encoding, self.failure, self.reads = encoding, failure, []
    def read(self, count):
        self.reads.append(count)
        if self.failure:
            raise self.failure
        return self.body[:count]
    def getheader(self, name, default=None):
        return self.encoding if name == 'Content-Encoding' else default


class FakeConnection:
    def __init__(self, reply, failure=None):
        self.reply, self.failure, self.requests = reply, failure, []
    def set_debuglevel(self, level):
        self.debuglevel = level
    def request(self, *args, **kwargs):
        self.requests.append((args, kwargs))
        if self.failure:
            raise self.failure
    def getresponse(self):
        return self.reply
    def close(self):
        pass


class CheckedEnvironment(dict):
    """An inert mapping; never consult the actual process environment."""
    def __init__(self, *args, forbid_key=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.key_reads = 0
        self.forbid_key = forbid_key
    def get(self, name, default=None):
        if name == 'LLM_API_KEY':
            self.key_reads += 1
            if self.forbid_key:
                raise AssertionError('credential read forbidden in this test')
        return super().get(name, default)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        # Replace, rather than inspect/copy, the entire actual environment.
        self.env_patch = patch.object(bridge.os, 'environ', {})
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.prepared, self.pin, self.rid, self.response = fixture(self.home)
        self.parent = self.home / 'captures'
        self.calls = []

    def capture(self, body=None, result=None, transport=None):
        def inert(raw, key):
            self.calls.append((raw, key))
            return result or bridge.Capture(200, body if body is not None else envelope(json.dumps(self.response)), True)
        return bridge.capture_one(self.prepared, self.pin, self.rid, self.parent, KEY, transport=transport or inert)

    def test_guard_denies_socket_and_process(self):
        for action in (lambda: socket.socket(), lambda: subprocess.Popen(['true'])):
            with self.assertRaises((AssertionError, PermissionError)):
                action()

    def test_no_pdf_or_extraction_runtime_loaded(self):
        self.assertNotIn('pypdf', sys.modules)
        with patch.object(converter, 'prepare', side_effect=AssertionError), \
             patch.object(converter, 'extract', side_effect=AssertionError), \
             patch.object(converter, '_read_pdf', side_effect=AssertionError):
            self.capture()

    def test_wire_is_exact_prepared_contract_and_fixed_bounds(self):
        selected = bridge.select(self.prepared, self.pin, self.rid)
        wire = converter.strict_load(selected.wire)
        self.assertEqual(set(wire), {'model', 'messages', 'max_tokens', 'temperature', 'stream'})
        self.assertEqual((wire['model'], wire['max_tokens'], wire['temperature'], wire['stream']),
                         (bridge.MODEL, bridge.MAX_TOKENS, 0, False))
        self.assertEqual(wire['messages'][0], {'role': 'system', 'content': selected.prompt.decode()})
        user = converter.strict_load(wire['messages'][1]['content'].encode())
        self.assertEqual(user, {'required_output_schema': converter.strict_load(selected.schema),
                               'request': converter.strict_load(selected.prepared_request)})
        self.assertNotIn('pypdf', sys.modules)

    def test_bad_prepare_pin_or_unknown_request_never_dispatches(self):
        for pin, rid in [('0' * 64, self.rid), (self.pin, '0' * 64)]:
            with self.assertRaises((bridge.SafeFailure, converter.PipelineError)):
                bridge.capture_one(self.prepared, pin, rid, self.parent, KEY, transport=lambda *_: self.fail('sent'))
        self.assertFalse(self.parent.exists())

    def test_any_prepared_file_tamper_blocks_dispatch(self):
        path = self.prepared / 'source.pdf'
        path.write_bytes(path.read_bytes() + b' altered')
        with self.assertRaises(converter.PipelineError):
            self.capture()
        self.assertFalse(self.calls)

    def test_selected_prompt_race_is_rejected(self):
        original = converter.load_prepared
        def race(*args):
            result = original(*args)
            (self.prepared / 'prompt.txt').write_bytes(b'changed after verification')
            return result
        with patch.object(converter, 'load_prepared', side_effect=race), self.assertRaises(bridge.SafeFailure):
            self.capture()
        self.assertFalse(self.calls)

    def test_private_reservation_is_durable_before_transport(self):
        def inert(raw, key):
            attempts = list(self.parent.iterdir())
            self.assertEqual(len(attempts), 1)
            self.assertEqual((attempts[0] / 'wire-request.original.json').read_bytes(), raw)
            self.assertEqual(converter.strict_load((attempts[0] / 'attempt.json').read_bytes())['attempt_state'], 'reserved_outcome_unknown')
            return bridge.Capture(200, envelope(json.dumps(self.response)), True)
        path, _, _ = self.capture(transport=inert)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o700)
        for child in path.iterdir():
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o600)

    def test_repeated_attempt_never_retries_or_overwrites(self):
        self.capture(result=bridge.Capture(error='transport_failure'))
        with self.assertRaisesRegex(bridge.SafeFailure, 'attempt_already_reserved_no_retry'):
            self.capture()
        self.assertEqual(len(self.calls), 1)

    def test_crash_reservation_is_not_resumed(self):
        selection = bridge.select(self.prepared, self.pin, self.rid)
        with bridge.reserve(self.parent, selection):
            pass
        with self.assertRaises(bridge.SafeFailure):
            self.capture()
        self.assertFalse(self.calls)

    def test_raw_original_is_saved_before_envelope_parse(self):
        original = bridge.envelope_content
        def inspect(raw):
            path = next(self.parent.iterdir())
            self.assertEqual((path / 'response.original.bin').read_bytes(), raw)
            return original(raw)
        with patch.object(bridge, 'envelope_content', side_effect=inspect):
            self.capture()

    def test_decoded_content_keeps_whitespace_unicode_and_no_repair(self):
        content = '  \n```json\n{"x":"Grüezi ☃"}\n```\n'
        raw = envelope(content)
        path, pin, receipt = self.capture(body=raw)
        self.assertEqual((path / 'response.original.bin').read_bytes(), raw)
        self.assertEqual((path / 'assistant-content.decoded.utf8').read_bytes(), content.encode())
        self.assertEqual(receipt['capture_status'], 'captured')
        self.assertEqual(bridge.verify_capture(path, pin), receipt)

    def test_structurally_valid_import_stays_unadjudicated_and_denominators_complete(self):
        path, pin, _ = self.capture()
        bridge.verify_capture(path, pin)
        result = converter.import_captures(self.prepared, path / 'index.json', self.home / 'imported', self.pin)
        self.assertEqual(result['payload']['denominators'], {'planned': 2, 'attempted': 1, 'unattempted': 1,
                          'structurally_valid': 1, 'rejected': 0, 'failed': 0})
        ledger = converter.strict_load((self.home / 'imported/import-ledger.json').read_bytes())
        self.assertFalse(ledger['answer_eligible'])
        self.assertFalse(ledger['human_reference'])
        self.assertEqual(ledger['adjudication'], 'unadjudicated')
        self.assertIsNone(ledger['semantic_accuracy'])

    def test_bad_assistant_json_is_retained_and_rejected_by_unchanged_import(self):
        content = '```json\n' + json.dumps(self.response) + '\n```'
        path, _, _ = self.capture(body=envelope(content))
        result = converter.import_captures(self.prepared, path / 'index.json', self.home / 'imported', self.pin)
        self.assertEqual(result['payload']['denominators']['rejected'], 1)
        self.assertEqual((self.home / 'imported/original-captures/0000.bin').read_bytes(), content.encode())

    def test_failed_transport_has_failed_index_and_no_candidate(self):
        path, pin, receipt = self.capture(result=bridge.Capture(error='deadline_or_socket_timeout'))
        self.assertEqual(receipt['capture_status'], 'failed')
        bridge.verify_capture(path, pin)
        result = converter.import_captures(self.prepared, path / 'index.json', self.home / 'imported', self.pin)
        self.assertEqual(result['payload']['denominators']['failed'], 1)
        self.assertEqual(len(self.calls), 1)

    def test_complete_malformed_duplicate_nonfinite_and_bom_envelope_retained_failed(self):
        for i, raw in enumerate((b'{', b'{"x":1,"x":2}', b'{"x":NaN}', b'\xef\xbb\xbf{}')):
            self.parent = self.home / ('captures' + str(i))
            path, pin, receipt = self.capture(body=raw)
            self.assertEqual((path / 'response.original.bin').read_bytes(), raw)
            self.assertEqual(receipt['capture_status'], 'failed')
            self.assertFalse((path / 'assistant-content.decoded.utf8').exists())
            bridge.verify_capture(path, pin)

    def test_model_finish_usage_and_tools_reject_without_content_repair(self):
        initial = converter.strict_load(envelope(json.dumps(self.response)))
        changes = [lambda b: b.update(model='other'),
                   lambda b: b['choices'][0].update(finish_reason='length'),
                   lambda b: b['choices'][0].update(index=True),
                   lambda b: b['usage'].update(completion_tokens=True),
                   lambda b: b['usage'].update(total_tokens=151),
                   lambda b: b['usage'].update(completion_tokens=bridge.MAX_TOKENS + 1, total_tokens=bridge.MAX_TOKENS + 101),
                   lambda b: b['choices'][0]['message'].update(tool_calls=[{'id': 'inert'}]),
                   lambda b: b['choices'][0]['message'].update(refusal='inert'),
                   lambda b: b.update(choices=b['choices'] * 2)]
        for i, change in enumerate(changes):
            self.parent = self.home / ('captures' + str(i))
            body = json.loads(json.dumps(initial)); change(body)
            path, pin, receipt = self.capture(body=converter.canonical(body))
            self.assertEqual(receipt['capture_status'], 'failed')
            self.assertTrue((path / 'response.original.bin').exists())
            self.assertFalse((path / 'assistant-content.decoded.utf8').exists())
            bridge.verify_capture(path, pin)

    def test_incomplete_oversize_non_utf8_and_compressed_never_saved(self):
        captures = [bridge.Capture(200, b'partial', False, 'incomplete_response'),
                    bridge.Capture(200, b'x' * (bridge.MAX_RESPONSE_BYTES + 1), True),
                    bridge.Capture(200, b'\xff', True), bridge.Capture(200, b'\x00{}', True),
                    bridge.Capture(200, b'', False, 'unsupported_content_encoding')]
        for i, capture in enumerate(captures):
            self.parent = self.home / ('captures' + str(i))
            path, pin, receipt = self.capture(result=capture)
            self.assertEqual(receipt['capture_status'], 'failed')
            self.assertFalse((path / 'response.original.bin').exists())
            bridge.verify_capture(path, pin)

    def test_secret_echo_variants_are_withheld_not_redacted(self):
        values = [KEY, base64.b64encode(KEY.encode()).decode(), KEY.encode().hex(),
                  ''.join('\\u%04x' % ord(c) for c in KEY), ''.join('%%%02X' % ord(c) for c in KEY)]
        for i, value in enumerate(values):
            self.parent = self.home / ('captures' + str(i))
            raw = ('{"secret":"' + value + '"}').encode()
            path, _, receipt = self.capture(body=raw)
            self.assertEqual(receipt['response_retention'], 'withheld_possible_secret_echo')
            self.assertFalse((path / 'response.original.bin').exists())
            for child in path.iterdir():
                self.assertNotIn(KEY.encode(), child.read_bytes())

    def test_invalid_key_and_input_key_overlap_are_not_sent(self):
        for key in ('short', 'bad\nheader-token-012345', 'ü' * 20, self.rid):
            with self.assertRaises(bridge.SafeFailure):
                bridge.capture_one(self.prepared, self.pin, self.rid, self.parent, key, transport=lambda *_: self.fail('sent'))
        self.assertFalse(self.parent.exists())

    def test_transport_exception_diagnostics_never_saved(self):
        def broken(*_):
            raise RuntimeError(KEY)
        path, _, receipt = self.capture(transport=broken)
        self.assertEqual(receipt['transport_error'], 'transport_failure')
        for child in path.iterdir():
            self.assertNotIn(KEY.encode(), child.read_bytes())

    def test_symlink_and_insecure_output_parent_reject_before_dispatch(self):
        self.parent.mkdir(mode=0o755)
        with self.assertRaises(bridge.SafeFailure):
            self.capture()
        self.assertFalse(self.calls)
        target = self.home / 'target'; target.mkdir(mode=0o700)
        self.parent = self.home / 'link'; self.parent.symlink_to(target)
        with self.assertRaises(converter.PipelineError):
            self.capture()
        self.assertFalse(self.calls)

    def test_receipt_or_artifact_tamper_rejected(self):
        path, pin, _ = self.capture()
        with self.assertRaises(bridge.SafeFailure):
            bridge.verify_capture(path, '0' * 64)
        content = path / 'assistant-content.decoded.utf8'
        content.write_bytes(content.read_bytes() + b' ')
        with self.assertRaises(bridge.SafeFailure):
            bridge.verify_capture(path, pin)

    def test_wire_transport_fixed_host_post_bounded_read_and_no_proxy(self):
        reply = FakeReply(body=b'authored raw')
        connection = FakeConnection(reply)
        with patch.object(bridge.http.client, 'HTTPSConnection', return_value=connection) as factory, \
             patch.object(bridge, 'tls_context', return_value='inert-context'):
            capture = bridge.send_once(b'authored request', KEY)
        factory.assert_called_once_with(bridge.HOST, port=443, timeout=bridge.TIMEOUT_SECONDS, context='inert-context')
        self.assertEqual(len(connection.requests), 1)
        args, kwargs = connection.requests[0]
        self.assertEqual(args, ('POST', bridge.ROUTE))
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer ' + KEY)
        self.assertEqual(connection.debuglevel, 0)
        self.assertEqual(reply.reads, [bridge.MAX_RESPONSE_BYTES + 1])
        self.assertEqual(capture, bridge.Capture(200, b'authored raw', True))

    def test_redirect_failure_oversize_and_incomplete_do_not_retry(self):
        for reply, error in [(FakeReply(status=302), None),
                             (FakeReply(encoding='gzip'), 'unsupported_content_encoding'),
                             (FakeReply(body=b'a' * (bridge.MAX_RESPONSE_BYTES + 1)), 'response_too_large'),
                             (FakeReply(length=1), 'incomplete_response'),
                             (FakeReply(failure=bridge.http.client.IncompleteRead(b'partial', 100)), 'incomplete_response'),
                             (FakeReply(failure=TimeoutError()), 'deadline_or_socket_timeout')]:
            connection = FakeConnection(reply)
            with patch.object(bridge.http.client, 'HTTPSConnection', return_value=connection) as factory, \
                 patch.object(bridge, 'tls_context', return_value=None):
                capture = bridge.send_once(b'{}', KEY)
            self.assertEqual(capture.error, error)
            self.assertEqual(factory.call_count, 1)
            self.assertEqual(len(connection.requests), 1)

    def test_custody_readback_failure_never_emits_index(self):
        original = converter.read_bytes
        def corrupt(path, *args, **kwargs):
            if Path(path).name == 'wire-request.original.json':
                return b'changed'
            return original(path, *args, **kwargs)
        with patch.object(converter, 'read_bytes', side_effect=corrupt), self.assertRaises(bridge.SafeFailure):
            self.capture()
        self.assertFalse((next(self.parent.iterdir()) / 'index.json').exists())

    def test_receipt_write_failure_leaves_originals_but_no_importable_index(self):
        original = bridge.write_private
        def fail_receipt(fd, name, raw):
            if name == 'receipt.json':
                raise OSError('inert simulated receipt write failure')
            return original(fd, name, raw)
        with patch.object(bridge, 'write_private', side_effect=fail_receipt), self.assertRaises(OSError):
            self.capture()
        path = next(self.parent.iterdir())
        self.assertTrue((path / 'attempt.json').exists())
        self.assertTrue((path / 'response.original.bin').exists())
        self.assertTrue((path / 'assistant-content.decoded.utf8').exists())
        self.assertFalse((path / 'index.json').exists())
        with self.assertRaises(converter.PipelineError):
            converter.import_captures(self.prepared, path / 'index.json', self.home / 'imported', self.pin)
        with self.assertRaises(bridge.SafeFailure):
            self.capture()
        self.assertEqual(len(self.calls), 1)

    def test_receipt_readback_tamper_blocks_index_publication(self):
        original = bridge.write_private
        def tamper_receipt(fd, name, raw):
            return original(fd, name, raw + b' ' if name == 'receipt.json' else raw)
        with patch.object(bridge, 'write_private', side_effect=tamper_receipt), self.assertRaises(bridge.SafeFailure):
            self.capture()
        path = next(self.parent.iterdir())
        self.assertTrue((path / 'receipt.json').exists())
        self.assertFalse((path / 'index.json').exists())

    def test_final_index_is_last_after_receipt_fsync_and_custody_verification(self):
        original_write, original_verify = bridge.write_private, bridge._verify_capture
        events = []
        def write(fd, name, raw):
            result = original_write(fd, name, raw)
            events.append(name)
            return result
        def verify(path, pin, **kwargs):
            self.assertTrue((path / 'receipt.json').exists())
            self.assertFalse((path / 'index.json').exists())
            result = original_verify(path, pin, **kwargs)
            events.append('custody_verified')
            return result
        with patch.object(bridge, 'write_private', side_effect=write), patch.object(bridge, '_verify_capture', side_effect=verify):
            self.capture()
        self.assertEqual(events[-3:], ['receipt.json', 'custody_verified', 'index.json'])

    def test_index_write_failure_cannot_verify_or_resume(self):
        original = bridge.write_private
        def fail_index(fd, name, raw):
            if name == 'index.json':
                raise OSError('inert simulated index write failure')
            return original(fd, name, raw)
        with patch.object(bridge, 'write_private', side_effect=fail_index), self.assertRaises(OSError):
            self.capture()
        path = next(self.parent.iterdir())
        self.assertTrue((path / 'receipt.json').exists())
        pin = converter.sha((path / 'receipt.json').read_bytes())
        with self.assertRaises(bridge.SafeFailure):
            bridge.verify_capture(path, pin)
        with self.assertRaises(bridge.SafeFailure):
            self.capture()
        self.assertEqual(len(self.calls), 1)

    def cli_args(self, command):
        args = [command, '--prepared', str(self.prepared), '--expected-prepare', self.pin, '--request-id', self.rid]
        if command == 'send':
            args += ['--out-parent', str(self.parent)]
        return args

    def test_inspect_does_not_prompt_write_or_dispatch(self):
        env = CheckedEnvironment({'LLM_API_KEY': KEY}, forbid_key=True)
        with patch('sys.stdout', io.StringIO()), patch.object(bridge.getpass, 'getpass', side_effect=AssertionError), \
             patch.object(bridge, 'send_once', side_effect=AssertionError), patch.object(bridge.os, 'environ', env):
            self.assertEqual(bridge.main(self.cli_args('inspect')), 0)
        self.assertFalse(self.parent.exists())
        self.assertEqual(env.key_reads, 0)

    def test_nonterminal_send_refuses_without_key_prompt(self):
        with patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()), patch('sys.stdin', io.StringIO()), \
             patch.object(bridge.getpass, 'getpass', side_effect=AssertionError):
            self.assertEqual(bridge.main(self.cli_args('send')), 2)
        self.assertFalse(self.parent.exists())

    def test_private_blank_key_cancels_and_warning_fails_closed(self):
        for warn in (False, True):
            def get_key(_):
                if warn:
                    import warnings
                    warnings.warn('inert', bridge.getpass.GetPassWarning)
                return ''
            with patch('sys.stdout', io.StringIO()), patch('sys.stderr', Terminal()), patch('sys.stdin', Terminal()), \
                 patch.object(bridge.resource, 'setrlimit'), patch.object(bridge.getpass, 'getpass', side_effect=get_key):
                self.assertEqual(bridge.main(self.cli_args('send')), 2 if warn else 0)
        self.assertFalse(self.parent.exists())

    def test_runtime_selectors_allow_only_exact_model_and_cscs_base_forms(self):
        for base in ('https://api.inference.cscs.ch', 'https://api.inference.cscs.ch/',
                     'https://api.inference.cscs.ch/v1', 'https://api.inference.cscs.ch/v1/'):
            env = CheckedEnvironment({'LLM_NAME': bridge.MODEL, 'LLM_BASE_URL': base}, forbid_key=True)
            bridge.validate_runtime_selectors(env)
            self.assertEqual(env.key_reads, 0)
        for base in ('http://api.inference.cscs.ch/v1', 'https://evil.example/v1',
                     'https://api.inference.cscs.ch.evil.example/v1', 'https://user@api.inference.cscs.ch/v1',
                     'https://api.inference.cscs.ch:443/v1', 'https://api.inference.cscs.ch/v1?token=' + KEY,
                     'https://api.inference.cscs.ch/v1#fragment', 'https://api.inference.cscs.ch/v1//',
                     'https://api.inference.cscs.ch/v2', 'https://api.inference.cscs.ch/v1/chat/completions',
                     ' https://api.inference.cscs.ch/v1', ''):
            with self.assertRaises(bridge.SafeFailure):
                bridge.validate_runtime_selectors({'LLM_BASE_URL': base})
        for model in ('swiss-ai/Apertus-8B-Instruct-2509', 'other', '', bridge.MODEL + ' '):
            with self.assertRaises(bridge.SafeFailure):
                bridge.validate_runtime_selectors({'LLM_NAME': model})

    def test_bad_runtime_settings_reject_before_any_key_read_or_output_echo(self):
        for settings in ({'LLM_NAME': KEY}, {'LLM_BASE_URL': 'https://evil.example/' + KEY}):
            env = CheckedEnvironment({**settings, 'LLM_API_KEY': KEY}, forbid_key=True)
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch.object(bridge.os, 'environ', env), patch('sys.stdout', stdout), patch('sys.stderr', stderr), \
                 patch.object(bridge.getpass, 'getpass', side_effect=AssertionError), \
                 patch.object(bridge, 'send_once', side_effect=AssertionError):
                self.assertEqual(bridge.main(self.cli_args('send')), 2)
            self.assertEqual(env.key_reads, 0)
            self.assertNotIn(KEY, stdout.getvalue() + stderr.getvalue())
        self.assertFalse(self.parent.exists())

    def test_explicit_send_uses_inert_environment_key_without_tty_or_persistence(self):
        env = CheckedEnvironment({'LLM_NAME': bridge.MODEL, 'LLM_BASE_URL': 'https://api.inference.cscs.ch/v1/',
                                  'LLM_API_KEY': KEY})
        stdout, stderr = io.StringIO(), io.StringIO()
        calls = []
        def inert(raw, key):
            calls.append((raw, key))
            return bridge.Capture(200, envelope(json.dumps(self.response)), True)
        with patch.object(bridge.os, 'environ', env), patch('sys.stdout', stdout), patch('sys.stderr', stderr), \
             patch('sys.stdin', io.StringIO()), patch.object(bridge.resource, 'setrlimit') as limits, \
             patch.object(bridge.getpass, 'getpass', side_effect=AssertionError), \
             patch.object(bridge, 'send_once', side_effect=inert):
            self.assertEqual(bridge.main(self.cli_args('send')), 0)
        self.assertEqual(env.key_reads, 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1], KEY)
        limits.assert_called_once_with(bridge.resource.RLIMIT_CORE, (0, 0))
        self.assertNotIn(KEY, stdout.getvalue() + stderr.getvalue())
        for child in next(self.parent.iterdir()).iterdir():
            self.assertNotIn(KEY.encode(), child.read_bytes())
        self.assertEqual(dict(env)['LLM_API_KEY'], KEY)  # No credential configuration/mutation.

    def test_environment_blank_or_invalid_key_does_not_fallback_or_send(self):
        for key, expected_code in (('', 0), ('short', 2), (KEY + '\n', 2)):
            env = CheckedEnvironment({'LLM_API_KEY': key})
            output = io.StringIO()
            with patch.object(bridge.os, 'environ', env), patch('sys.stdout', output), patch('sys.stderr', output), \
                 patch.object(bridge.resource, 'setrlimit'), patch.object(bridge.getpass, 'getpass', side_effect=AssertionError), \
                 patch.object(bridge, 'send_once', side_effect=AssertionError):
                self.assertEqual(bridge.main(self.cli_args('send')), expected_code)
            self.assertEqual(env.key_reads, 1)
            self.assertNotIn(KEY, output.getvalue())
        self.assertFalse(self.parent.exists())

    def test_bad_preparation_prevents_environment_key_read(self):
        env = CheckedEnvironment({'LLM_API_KEY': KEY}, forbid_key=True)
        (self.prepared / 'source.pdf').write_bytes(b'altered')
        with patch.object(bridge.os, 'environ', env), patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()):
            self.assertEqual(bridge.main(self.cli_args('send')), 2)
        self.assertEqual(env.key_reads, 0)

    def test_verify_ignores_all_runtime_settings_and_never_reads_key(self):
        path, pin, _ = self.capture()
        env = CheckedEnvironment({'LLM_NAME': KEY, 'LLM_BASE_URL': 'https://evil.example', 'LLM_API_KEY': KEY}, forbid_key=True)
        with patch.object(bridge.os, 'environ', env), patch('sys.stdout', io.StringIO()):
            self.assertEqual(bridge.main(['verify', '--capture', str(path), '--expected-receipt', pin]), 0)
        self.assertEqual(env.key_reads, 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
