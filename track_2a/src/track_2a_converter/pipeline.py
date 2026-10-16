"""Offline PDF -> bound requests -> original captures -> source-first review.

No transport, credential, repair, adjudication, historical-score or provider path.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import uuid

from jsonschema import Draft202012Validator
from jsonschema.validators import extend

ROOT = Path(__file__).resolve().parent
PROFILE = 'formrehearsal-pdf-review-1'
CONVERTER_VERSION = '0.2.0'
EXTRACTION_POLICY = 'credential-free-native-text-2'
SOURCE_ERRORS = frozenset(('pdf_password_required', 'pdf_unreadable',
                          'pdf_page_inventory_unreadable', 'pdf_page_count_limit',
                          'pdf_reader_dependency_unavailable', 'total_text_limit',
                          'pdf_extraction_failed'))
FIELDS = ('source_type', 'affair', 'author', 'actor', 'addressee', 'event', 'outcome')
STATES = ('present', 'explicit_absence', 'not_stated_within_reviewed_scope',
          'unassessed', 'not_applicable', 'conflicting')
PDF_CAP = 32 * 1024 * 1024
JSON_CAP = 32 * 1024 * 1024
RESPONSE_CAP = 1024 * 1024
INDEX_CAP = 1024 * 1024
TOTAL_CAPTURE_CAP = 32 * 1024 * 1024
MAX_PAGES = 500
MAX_TEXT = 8 * 1024 * 1024
MAX_PAGE_TEXT = 1024 * 1024
MAX_REQUESTS = 2048
MAX_ENTRIES = 4096
DIGEST = re.compile(r'^[0-9a-f]{64}$')
StrictValidator = extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine('integer', lambda c, v: type(v) is int))


class PipelineError(ValueError):
    """Stable diagnostics only; never print original source/capture text."""


def require(test, code):
    if not test:
        raise PipelineError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def strict_load(raw, cap=JSON_CAP):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def finite(s):
        value = float(s)
        require(math.isfinite(value), 'nonfinite_json_number')
        return value
    def check(value, depth=0):
        require(depth <= 64, 'json_depth_limit')
        if isinstance(value, str):
            require(not any(0xD800 <= ord(c) <= 0xDFFF for c in value), 'invalid_unicode_scalar')
        elif isinstance(value, dict):
            for key, child in value.items():
                check(key, depth + 1); check(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                check(child, depth + 1)
    try:
        require(type(raw) is bytes and len(raw) <= cap, 'json_size_limit')
        require(not raw.startswith(b'\xef\xbb\xbf'), 'json_bom_rejected')
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_float=finite,
                           parse_constant=lambda _: (_ for _ in ()).throw(PipelineError('nonfinite_json_number')))
        check(value)
        return value
    except PipelineError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PipelineError('invalid_json') from None


def exact(value, keys, code):
    require(isinstance(value, dict) and set(value) == set(keys), code)


def safe_path(path):
    """Reject symlinks in every ancestor, including caller-supplied root paths."""
    p = Path(path).absolute()
    require('..' not in p.parts and '\x00' not in str(p), 'unsafe_path')
    current = Path(p.anchor)
    for part in p.parts[1:]:
        current /= part
        require(not current.is_symlink(), 'symlink_rejected')
    return p


def read_bytes(path, cap=JSON_CAP, reject_hardlinks=False):
    # Walk from / through descriptor-relative no-follow directories. Same fd is
    # checked and read; FIFOs cannot block even when replaced immediately before open.
    path = safe_path(path)
    descriptors = []
    try:
        fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in path.parts[1:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(fd)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), 'nonregular_file')
        require(not reject_hardlinks or info.st_nlink == 1, 'hardlink_rejected')
        require(info.st_size <= cap, 'file_size_limit')
        chunks, size = [], 0
        while True:
            data = os.read(fd, min(65536, cap + 1 - size))
            if not data:
                break
            chunks.append(data); size += len(data)
            require(size <= cap, 'file_size_limit')
        return b''.join(chunks)
    except OSError:
        raise PipelineError('required_file_unavailable') from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def relative_file(root, relative):
    require(isinstance(relative, str) and relative and '\\' not in relative and '\x00' not in relative, 'unsafe_relative_path')
    rel = Path(relative)
    require(not rel.is_absolute() and all(p not in ('', '.', '..') for p in relative.split('/')), 'unsafe_relative_path')
    return safe_path(Path(root) / rel)


def open_directory(path, create=False):
    path = safe_path(path)
    fd = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def write_new(path, raw):
    path = safe_path(path)
    require(len(raw) <= max(PDF_CAP, JSON_CAP), 'artifact_size_limit')
    parent_fd = None
    try:
        parent_fd = open_directory(path.parent, create=True)
        fd = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        os.fsync(parent_fd)
    except OSError:
        raise PipelineError('exclusive_artifact_write_failed') from None
    finally:
        if parent_fd is not None:
            os.close(parent_fd)


def begin(out, operation, inputs):
    out = safe_path(out)
    parent_fd = None
    try:
        parent_fd = open_directory(out.parent)
        os.mkdir(out.name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except OSError:
        raise PipelineError('fresh_output_directory_required') from None
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    start = {'profile': PROFILE, 'operation': operation, 'invocation_id': str(uuid.uuid4()),
             'status': 'started', 'inputs': inputs}
    write_new(out / 'invocation.json', canonical(start))
    return out, start


def finish(out, start, payload):
    files = {}
    for path in sorted(out.rglob('*')):
        require(not path.is_symlink(), 'symlink_rejected')
        if path.is_file():
            raw = read_bytes(path)
            files[path.relative_to(out).as_posix()] = {'sha256': sha(raw), 'bytes': len(raw)}
    result = {**start, 'status': 'complete', 'files': files, 'payload': payload}
    result['result_sha256'] = sha(canonical(result))
    write_new(out / 'result.json', canonical(result))
    return result


def record_failure(out, start, code):
    # Failure never emits result.json, so old or partial artifacts cannot be current.
    try:
        write_new(out / 'failure.json', canonical({**start, 'status': 'failed', 'error': code}))
    except PipelineError:
        pass


def verify_result(root, operation, expected):
    require(isinstance(expected, str) and DIGEST.fullmatch(expected), 'expected_result_pin_required')
    root = safe_path(root)
    result = strict_load(read_bytes(root / 'result.json'))
    exact(result, ('profile', 'operation', 'invocation_id', 'status', 'inputs', 'files', 'payload', 'result_sha256'), 'invalid_result_manifest')
    body = {k: v for k, v in result.items() if k != 'result_sha256'}
    require(result['result_sha256'] == expected == sha(canonical(body)), 'result_pin_mismatch')
    require(result['profile'] == PROFILE and result['operation'] == operation and result['status'] == 'complete', 'result_lifecycle_mismatch')
    require(isinstance(result['files'], dict) and 'invocation.json' in result['files'], 'invalid_artifact_inventory')
    actual = set()
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink_rejected')
        if not path.is_dir():
            actual.add(path.relative_to(root).as_posix())
    require(actual == set(result['files']) | {'result.json'}, 'artifact_inventory_mismatch')
    for name, record in result['files'].items():
        exact(record, ('sha256', 'bytes'), 'invalid_artifact_record')
        raw = read_bytes(relative_file(root, name))
        require(sha(raw) == record['sha256'] and len(raw) == record['bytes'], 'artifact_hash_mismatch')
    invocation = strict_load(read_bytes(root / 'invocation.json'))
    require(invocation == {k: result[k] for k in ('profile', 'operation', 'invocation_id', 'inputs')} | {'status': 'started'}, 'invocation_mismatch')
    return result


def _extract_pdf(source):
    import resource
    # Native PDF parsing is resource-bounded, not a hostile-code security sandbox.
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (45, 45))
    return _read_pdf(source)


def _read_pdf(source):
    """Use only what the ordinary reader opens without a credential argument.

    An encryption marker does not mean a password is required to read the file.
    Never supply a password, explicitly decrypt, modify permissions, or retry via
    a different parser. This preserves the existing strict-reader/plain-text mode.
    """
    from pypdf import PdfReader
    from pypdf.errors import DependencyError, FileNotDecryptedError, WrongPasswordError
    import pypdf
    try:
        reader = PdfReader(io.BytesIO(read_bytes(source, PDF_CAP)), strict=True)
    except (FileNotDecryptedError, WrongPasswordError):
        raise PipelineError('pdf_password_required') from None
    except DependencyError:
        raise PipelineError('pdf_reader_dependency_unavailable') from None
    except Exception:
        raise PipelineError('pdf_unreadable') from None
    try:
        page_count = len(reader.pages)
        is_encrypted = bool(reader.is_encrypted)
    except (FileNotDecryptedError, WrongPasswordError):
        raise PipelineError('pdf_password_required') from None
    except DependencyError:
        raise PipelineError('pdf_reader_dependency_unavailable') from None
    except Exception:
        raise PipelineError('pdf_page_inventory_unreadable') from None
    require(0 < page_count <= MAX_PAGES, 'pdf_page_count_limit')
    pages, total = [], 0
    for number in range(1, page_count + 1):
        try:
            page = reader.pages[number - 1]
            text = page.extract_text(extraction_mode='plain')
            require(isinstance(text, str), 'page_text_unavailable')
            text.encode('utf-8', errors='strict')
            require(len(text.encode('utf-8')) <= MAX_PAGE_TEXT, 'page_text_limit')
            status, error = ('text_extracted', None) if text.strip() else ('no_text_unresolved', None)
        except (FileNotDecryptedError, WrongPasswordError):
            text, status, error = '', 'extraction_failed', 'page_password_required'
        except DependencyError:
            text, status, error = '', 'extraction_failed', 'page_reader_dependency_unavailable'
        except PipelineError as exc:
            text, status, error = '', 'extraction_failed', str(exc)
        except Exception:
            text, status, error = '', 'extraction_failed', 'native_text_extraction_failed'
        total += len(text.encode('utf-8'))
        require(total <= MAX_TEXT, 'total_text_limit')
        pages.append({'page': number, 'status': status, 'error': error, 'text': text,
                      'text_sha256': sha(text.encode('utf-8')), 'ocr_status': 'not_attempted'})
    return {'status': 'complete',
            'source_access': {'status': 'opened_without_credentials', 'is_encrypted': is_encrypted},
            'extractor': {'name': 'pypdf', 'version': pypdf.__version__, 'mode': 'plain',
                          'normalization': 'none', 'offset_unit': 'unicode_code_point',
                          'converter_version': CONVERTER_VERSION, 'policy': EXTRACTION_POLICY,
                          'strict_reader': True, 'credential_arguments': 'none',
                          'explicit_decryption': 'not_attempted'},
            'pages': pages, 'page_status_counts': page_status_counts(pages)}


def page_status_counts(pages):
    counts = Counter(page['status'] for page in pages)
    return {status: counts[status] for status in ('text_extracted', 'no_text_unresolved', 'extraction_failed')}


def extraction_worker(source, destination):
    try:
        write_new(destination, canonical(_extract_pdf(source)))
    except Exception as exc:
        code = str(exc) if isinstance(exc, PipelineError) and str(exc) in SOURCE_ERRORS else 'pdf_extraction_failed'
        try:
            write_new(destination, canonical({'status': 'failed', 'error': code}))
        except Exception:
            pass
        return 1
    return 0


def extract(source, destination):
    try:
        proc = subprocess.run([sys.executable, str(ROOT / 'pipeline.py'), '_extract', str(source), str(destination)],
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                              env={}, timeout=60, check=False)
    except (subprocess.TimeoutExpired, OSError):
        raise PipelineError('pdf_extraction_process_failed') from None
    require(proc.returncode in (0, 1), 'pdf_extraction_process_failed')
    try:
        extracted = strict_load(read_bytes(destination))
    except PipelineError:
        raise PipelineError('pdf_extraction_process_failed') from None
    if proc.returncode == 1:
        exact(extracted, ('status', 'error'), 'pdf_extraction_process_failed')
        require(extracted['status'] == 'failed' and extracted['error'] in SOURCE_ERRORS, 'pdf_extraction_process_failed')
        raise PipelineError(extracted['error'])
    require(isinstance(extracted, dict) and extracted.get('status') == 'complete', 'pdf_extraction_process_failed')
    return extracted


def chunks_for(page, size):
    if page['status'] != 'text_extracted':
        return []
    text = page['text']
    return [{'page': page['page'], 'start': start, 'end': min(start + size, len(text)),
             'text_sha256': sha(text[start:start + size].encode('utf-8'))}
            for start in range(0, len(text), size)]


def make_request(source_sha, page, chunk, schema_sha, prompt_sha, extractor):
    binding = {'profile': PROFILE, 'source_sha256': source_sha, 'page_text_sha256': page['text_sha256'],
               'chunk': chunk, 'schema_sha256': schema_sha, 'prompt_sha256': prompt_sha,
               'extractor_sha256': sha(canonical(extractor))}
    request = {'binding': binding, 'reviewed_scope': chunk,
               'source_text': page['text'][chunk['start']:chunk['end']]}
    request['request_id'] = sha(canonical(request))
    # Full serialized request is hashed in the inventory, so no circular self-hash.
    return request


def prepare(pdf_path, out_dir, chunk_chars=4000):
    require(type(chunk_chars) is int and 256 <= chunk_chars <= 8000, 'chunk_size_limit')
    raw = read_bytes(pdf_path, PDF_CAP)
    require(raw.startswith(b'%PDF-'), 'pdf_header_required')
    prompt = read_bytes(ROOT / 'prompt.txt')
    schema = read_bytes(ROOT / 'response.schema.json')
    out, start = begin(out_dir, 'prepare', {'source_sha256': sha(raw), 'chunk_chars': chunk_chars})
    try:
        write_new(out / 'source.pdf', raw)
        extracted = extract(out / 'source.pdf', out / 'extraction.json')
        require(sha(read_bytes(out / 'source.pdf', PDF_CAP)) == sha(raw), 'source_changed_during_extraction')
        write_new(out / 'prompt.txt', prompt); write_new(out / 'response.schema.json', schema)
        requests = []
        for page in extracted['pages']:
            for chunk in chunks_for(page, chunk_chars):
                require(len(requests) < MAX_REQUESTS, 'request_count_limit')
                request = make_request(sha(raw), page, chunk, sha(schema), sha(prompt), extracted['extractor'])
                name = 'requests/' + request['request_id'] + '.json'
                data = canonical(request)
                write_new(out / name, data)
                requests.append({'request_id': request['request_id'], 'path': name, 'sha256': sha(data), 'chunk': chunk})
        bundle = {'profile': PROFILE, 'source_sha256': sha(raw), 'source_bytes': len(raw),
                  'page_count': len(extracted['pages']), 'pages': extracted['pages'],
                  'source_access': extracted['source_access'], 'page_status_counts': extracted['page_status_counts'],
                  'extractor': extracted['extractor'], 'chunk_chars': chunk_chars,
                  'schema_sha256': sha(schema), 'prompt_sha256': sha(prompt), 'requests': requests,
                  'coverage_claim': 'native_text_only_not_semantically_reviewed', 'ocr_status': 'not_attempted'}
        write_new(out / 'bundle.json', canonical(bundle))
        return finish(out, start, {'bundle_sha256': sha(canonical(bundle)), 'pages': len(extracted['pages']),
                                   'planned_requests': len(requests), 'network_calls': 0,
                                   'converter_version': CONVERTER_VERSION,
                                   'source_access': extracted['source_access'],
                                   'page_status_counts': extracted['page_status_counts']})
    except Exception as exc:
        record_failure(out, start, exc.args[0] if isinstance(exc, PipelineError) else 'preparation_failed')
        raise


def load_prepared(root, expected):
    result = verify_result(root, 'prepare', expected)
    bundle = strict_load(read_bytes(Path(root) / 'bundle.json'))
    require(sha(canonical(bundle)) == result['payload']['bundle_sha256'], 'bundle_hash_mismatch')
    require(bundle['profile'] == PROFILE and bundle['source_sha256'] == sha(read_bytes(Path(root) / 'source.pdf', PDF_CAP)), 'source_hash_mismatch')
    schema_raw = read_bytes(Path(root) / 'response.schema.json')
    prompt_raw = read_bytes(Path(root) / 'prompt.txt')
    require(sha(schema_raw) == bundle['schema_sha256'] == sha(read_bytes(ROOT / 'response.schema.json')), 'stale_schema_binding')
    require(sha(prompt_raw) == bundle['prompt_sha256'] == sha(read_bytes(ROOT / 'prompt.txt')), 'stale_prompt_binding')
    require(bundle['page_count'] == len(bundle['pages']) and 0 < bundle['page_count'] <= MAX_PAGES, 'page_inventory_mismatch')
    require(bundle['extractor'].get('policy') == EXTRACTION_POLICY and
            bundle['extractor'].get('converter_version') == CONVERTER_VERSION, 'extraction_policy_mismatch')
    exact(bundle['source_access'], ('status', 'is_encrypted'), 'source_access_status_mismatch')
    require(bundle['source_access']['status'] == 'opened_without_credentials' and
            type(bundle['source_access']['is_encrypted']) is bool, 'source_access_status_mismatch')
    require(bundle['page_status_counts'] == page_status_counts(bundle['pages']), 'page_status_count_mismatch')
    expected_requests = []
    requests = {}
    for number, page in enumerate(bundle['pages'], 1):
        require(page['page'] == number and page['status'] in ('text_extracted', 'no_text_unresolved', 'extraction_failed'), 'page_inventory_mismatch')
        require(sha(page['text'].encode('utf-8')) == page['text_sha256'] and page['ocr_status'] == 'not_attempted', 'page_text_binding_mismatch')
        require((bool(page['text'].strip())) == (page['status'] == 'text_extracted'), 'page_status_mismatch')
        require((page['error'] is not None) == (page['status'] == 'extraction_failed'), 'page_error_status_mismatch')
        require(page['status'] == 'text_extracted' or page['text'] == '' or
                (page['status'] == 'no_text_unresolved' and not page['text'].strip()), 'page_status_mismatch')
        for chunk in chunks_for(page, bundle['chunk_chars']):
            request = make_request(bundle['source_sha256'], page, chunk, bundle['schema_sha256'], bundle['prompt_sha256'], bundle['extractor'])
            name = 'requests/' + request['request_id'] + '.json'
            raw = read_bytes(Path(root) / name)
            require(raw == canonical(request), 'request_binding_mismatch')
            requests[request['request_id']] = request
            expected_requests.append({'request_id': request['request_id'], 'path': name, 'sha256': sha(raw), 'chunk': chunk})
    require(expected_requests == bundle['requests'], 'request_inventory_mismatch')
    return result, bundle, requests, strict_load(schema_raw)


def validate_candidate(candidate, request, bundle, schema):
    require(not list(StrictValidator(schema).iter_errors(candidate)), 'response_schema_failed')
    require(candidate['request_id'] == request['request_id'] and candidate['binding'] == request['binding'], 'response_binding_mismatch')
    require(candidate['reviewed_scope'] == request['reviewed_scope'], 'reviewed_scope_mismatch')
    chunk = request['reviewed_scope']
    page = bundle['pages'][chunk['page'] - 1]
    def location(loc):
        require(loc['page'] == chunk['page'] and chunk['start'] <= loc['start'] < loc['end'] <= chunk['end'], 'evidence_outside_request')
        require(page['text'][loc['start']:loc['end']] == loc['quote'], 'evidence_quote_mismatch')
    ids = set()
    for event in candidate['events']:
        require(event['candidate_id'] not in ids, 'duplicate_candidate_id'); ids.add(event['candidate_id'])
        for loc in event['anchors']:
            location(loc)
        for name in FIELDS:
            field = event[name]
            state = field['state']
            for loc in field['evidence']:
                location(loc)
            for alt in field['alternatives']:
                for loc in alt['evidence']:
                    location(loc)
                require((alt['state'] == 'present' and isinstance(alt['value'], str) and bool(alt['value'].strip())) or (alt['state'] == 'explicit_absence' and alt['value'] is None), 'invalid_conflict_alternative')
            value, evidence, alternatives, scope = field['value'], field['evidence'], field['alternatives'], field['reviewed_scope']
            if state == 'present':
                require(isinstance(value, str) and bool(value.strip()) and evidence and not alternatives and scope is None, 'invalid_present_field')
            elif state == 'conflicting':
                distinct = {(a['state'], a['value']) for a in alternatives}
                require(value is None and not evidence and len(distinct) >= 2 and scope is None, 'invalid_conflict_field')
            elif state == 'not_stated_within_reviewed_scope':
                require(value is None and not evidence and not alternatives and scope == chunk and bool(field['reason'].strip()), 'invalid_scoped_missingness')
            elif state in ('explicit_absence', 'not_applicable'):
                require(value is None and evidence and not alternatives and scope is None and bool(field['reason'].strip()), 'invalid_evidenced_missingness')
            else:
                require(value is None and not evidence and not alternatives and scope is None, 'invalid_unassessed_field')
    return candidate


def _entry_shape(entry):
    require(isinstance(entry, dict), 'invalid_capture_index_entry')
    status = entry.get('status')
    keys = {'request_id', 'status'}
    if status == 'captured':
        keys |= {'response_path'}
    elif status == 'failed':
        keys |= {'error_code'}
    else:
        require(status == 'unattempted', 'invalid_capture_status')
    exact(entry, keys, 'invalid_capture_index_entry')
    require(isinstance(entry['request_id'], str) and DIGEST.fullmatch(entry['request_id']), 'invalid_index_request_id')
    if status == 'failed':
        require(isinstance(entry['error_code'], str) and re.fullmatch(r'[a-z0-9_]{1,80}', entry['error_code']), 'invalid_failure_code')


def import_captures(prepare_dir, capture_index_path, out_dir, expected_prepare):
    prepared, bundle, requests, schema = load_prepared(prepare_dir, expected_prepare)
    index_raw = read_bytes(capture_index_path, INDEX_CAP, reject_hardlinks=True)
    capture_root = safe_path(capture_index_path).parent
    out, start = begin(out_dir, 'import', {'prepare_result_sha256': expected_prepare, 'index_sha256': sha(index_raw)})
    try:
        write_new(out / 'original-index.json', index_raw)
        index = strict_load(index_raw, INDEX_CAP)
        exact(index, ('profile', 'prepare_result_sha256', 'entries'), 'invalid_capture_index')
        require(index['profile'] == PROFILE and index['prepare_result_sha256'] == expected_prepare, 'capture_index_binding_mismatch')
        require(isinstance(index['entries'], list) and len(index['entries']) <= MAX_ENTRIES, 'capture_entry_count_limit')
        # Copy eligible original bytes before semantic/index-entry validation. Unsafe,
        # unavailable or oversized paths are recorded as unavailable, never dereferenced.
        records, total = [], 0
        for pos, entry in enumerate(index['entries']):
            record = {'index': pos, 'entry': entry, 'original_path': None, 'original_sha256': None, 'error': None}
            if isinstance(entry, dict) and 'response_path' in entry:
                try:
                    path = relative_file(capture_root, entry['response_path'])
                    require(not path.is_relative_to(out) and path != safe_path(capture_index_path), 'capture_alias_rejected')
                    raw = read_bytes(path, RESPONSE_CAP, reject_hardlinks=True)
                    require(total + len(raw) <= TOTAL_CAPTURE_CAP, 'total_capture_size_limit')
                    total += len(raw)
                    name = f'original-captures/{pos:04d}.bin'
                    write_new(out / name, raw)
                    record.update(original_path=name, original_sha256=sha(raw))
                except PipelineError as exc:
                    record['error'] = str(exc)
            records.append(record)
        counts = Counter(e.get('request_id') for e in index['entries'] if isinstance(e, dict) and isinstance(e.get('request_id'), str))
        units = {rid: {'request_id': rid, 'status': 'unattempted', 'attempted': False, 'candidates': [], 'capture_record': None, 'error': None}
                 for rid in requests}
        for record in records:
            entry = record['entry']
            rid = entry.get('request_id') if isinstance(entry, dict) else None
            unit = units.get(rid) if isinstance(rid, str) else None
            if unit is not None and isinstance(entry, dict) and (entry.get('status') != 'unattempted' or 'response_path' in entry):
                unit['attempted'] = True
            try:
                _entry_shape(entry)
                require(rid in requests, 'unknown_request_id')
                require(counts[rid] == 1, 'duplicate_capture_request')
                require(record['error'] is None, record['error'] or 'capture_read_failed')
                unit['capture_record'] = record['index']
                if entry['status'] == 'unattempted':
                    continue
                if entry['status'] == 'failed':
                    unit.update(status='attempt_failed', error=entry['error_code'])
                    continue
                require(record['original_path'] is not None, 'original_capture_required')
                candidate = strict_load(read_bytes(out / record['original_path'], RESPONSE_CAP), RESPONSE_CAP)
                validate_candidate(candidate, requests[rid], bundle, schema)
                unit.update(status='structurally_valid_unadjudicated', candidates=candidate['events'])
            except (PipelineError, TypeError, KeyError, RecursionError) as exc:
                code = str(exc) if isinstance(exc, PipelineError) else 'invalid_capture'
                record['error'] = code
                if unit is not None:
                    unit.update(status='rejected_capture', candidates=[], error=code)
        ledger = {'profile': PROFILE, 'prepare_result_sha256': expected_prepare,
                  'units': list(units.values()), 'capture_records': records,
                  'denominators': {'planned': len(requests), 'attempted': sum(u['attempted'] for u in units.values()),
                                   'unattempted': sum(not u['attempted'] for u in units.values()),
                                   'structurally_valid': sum(u['status'] == 'structurally_valid_unadjudicated' for u in units.values()),
                                   'rejected': sum(u['status'] == 'rejected_capture' for u in units.values()),
                                   'failed': sum(u['status'] == 'attempt_failed' for u in units.values())},
                  'adjudication': 'unadjudicated', 'answer_eligible': False,
                  'human_reference': False, 'semantic_accuracy': None, 'network_calls': 0}
        write_new(out / 'import-ledger.json', canonical(ledger))
        return finish(out, start, {'ledger_sha256': sha(canonical(ledger)), 'denominators': ledger['denominators']})
    except Exception as exc:
        record_failure(out, start, str(exc) if isinstance(exc, PipelineError) else 'import_failed')
        raise


def export_review(prepare_dir, import_dir, out_dir, expected_import):
    imported = verify_result(import_dir, 'import', expected_import)
    expected_prepare = imported['inputs']['prepare_result_sha256']
    prepared, bundle, requests, schema = load_prepared(prepare_dir, expected_prepare)
    ledger = strict_load(read_bytes(Path(import_dir) / 'import-ledger.json'))
    require(sha(canonical(ledger)) == imported['payload']['ledger_sha256'], 'ledger_hash_mismatch')
    out, start = begin(out_dir, 'review', {'prepare_result_sha256': expected_prepare, 'import_result_sha256': expected_import})
    try:
        pages = []
        units = {u['request_id']: u for u in ledger['units']}
        for page in bundle['pages']:
            rows = []
            for spec in bundle['requests']:
                if spec['chunk']['page'] != page['page']:
                    continue
                unit = units[spec['request_id']]
                events = [{**event, 'adjudication': 'unadjudicated', 'answer_eligible': False,
                           'request_id': unit['request_id'], 'original_capture_sha256':
                           ledger['capture_records'][unit['capture_record']]['original_sha256']}
                          for event in unit['candidates']]
                rows.append({'request_id': unit['request_id'], 'scope': spec['chunk'], 'status': unit['status'],
                             'attempted': unit['attempted'], 'error': unit['error'], 'candidates': events})
            pages.append({**page, 'review_status': 'unassessed', 'requests': rows})
        queue = {'profile': PROFILE, 'source_sha256': bundle['source_sha256'],
                 'source_access': bundle['source_access'], 'extractor': bundle['extractor'],
                 'prepare_result_sha256': expected_prepare, 'import_result_sha256': expected_import,
                 'page_count': bundle['page_count'], 'pages': pages, 'denominators': ledger['denominators'],
                 'page_status_counts': page_status_counts(pages),
                 'rejected_capture_records': [r for r in ledger['capture_records'] if r['error']],
                 'adjudication': 'unadjudicated', 'answer_eligible': False, 'human_reference': False,
                 'semantic_accuracy': None, 'coverage_claim': 'no_semantic_or_full_document_coverage',
                 'ocr_status': 'not_attempted'}
        write_new(out / 'review-queue.json', canonical(queue))
        # A complete offline review handoff: copy exact source PDF and original
        # responses alongside escaped HTML. No external URLs/scripts/resources.
        source_raw = read_bytes(Path(prepare_dir) / 'source.pdf', PDF_CAP)
        require(sha(source_raw) == bundle['source_sha256'], 'source_changed_during_review')
        write_new(out / 'source.pdf', source_raw)
        for record in ledger['capture_records']:
            if record['original_path']:
                capture_raw = read_bytes(Path(import_dir) / record['original_path'], RESPONSE_CAP)
                require(sha(capture_raw) == record['original_sha256'], 'capture_changed_during_review')
                write_new(out / record['original_path'], capture_raw)
        index_raw = read_bytes(Path(import_dir) / 'original-index.json', INDEX_CAP)
        require(sha(index_raw) == imported['inputs']['index_sha256'], 'index_changed_during_review')
        write_new(out / 'original-index.json', index_raw)
        write_new(out / 'review.html', render_review(queue, ledger).encode('utf-8'))
        verify_result(import_dir, 'import', expected_import)
        verify_result(prepare_dir, 'prepare', expected_prepare)
        return finish(out, start, {'queue_sha256': sha(canonical(queue)), 'pages': len(pages), 'denominators': ledger['denominators'], 'answer_eligible': False})
    except Exception as exc:
        record_failure(out, start, str(exc) if isinstance(exc, PipelineError) else 'review_export_failed')
        raise


def render_review(queue, ledger):
    esc = html.escape
    pieces = ['<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
              '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
              '<title>PDF source-first review queue</title><style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f6;padding:1rem}section{border-top:2px solid #aaa;margin-top:2rem}article{border:1px solid #bbb;padding:1rem;margin:1rem 0}strong{color:#793400}code{overflow-wrap:anywhere}</style>',
              '<h1>PDF source-first review queue</h1><strong>Unadjudicated. Every candidate is answer-ineligible.</strong>',
              '<p>This is a local engineering review packet. Exact quotes establish location, not semantic truth. No OCR, provider call, human identity verification, or adjudication occurred. Empty text is unresolved, never proof of a blank page.</p>',
              '<p><a href="source.pdf">Open original PDF</a> · <a href="review-queue.json">Review queue JSON</a> · <a href="original-index.json">Original capture index</a></p>',
              '<pre>' + esc(json.dumps(queue['denominators'], indent=2)) + '</pre>']
    pieces += ['<p>Source access: ' + esc(queue['source_access']['status']) +
               '. PDF encryption marker: ' + str(queue['source_access']['is_encrypted']).lower() +
               '. No credential argument or explicit decryption was used.</p>',
               '<pre>' + esc(json.dumps(queue['page_status_counts'], indent=2)) + '</pre>']
    for page in queue['pages']:
        pieces += [f'<section id="page-{page["page"]}"><h2>Page {page["page"]}: {esc(page["status"])}</h2>',
                   '<p>OCR: not attempted. Review: unassessed.</p><h3>Source text first</h3><pre>' + esc(page['text']) + '</pre>']
        if page['error']:
            pieces += ['<p>Page failure: ' + esc(page['error']) + '</p>']
        for request in page['requests']:
            pieces += ['<article><h3>Chunk ' + str(request['scope']['start']) + '–' + str(request['scope']['end']) + '</h3>',
                       '<p>' + esc(request['status']) + '</p><code>' + esc(request['request_id']) + '</code>']
            unit = next(u for u in ledger['units'] if u['request_id'] == request['request_id'])
            if unit['capture_record'] is not None:
                record = ledger['capture_records'][unit['capture_record']]
                if record['original_path']:
                    pieces += ['<p><a href="' + esc(record['original_path'], quote=True) + '">Original response bytes</a></p>']
            if request['error']:
                pieces += ['<p>Failure: ' + esc(request['error']) + '</p>']
            for event in request['candidates']:
                pieces += ['<h4>Candidate ' + esc(event['candidate_id']) + '</h4><pre>' + esc(json.dumps(event, ensure_ascii=False, indent=2)) + '</pre>']
            pieces += ['</article>']
        pieces += ['</section>']
    pieces += ['<h2>Retained rejected capture entries</h2><pre>' + esc(json.dumps(queue['rejected_capture_records'], ensure_ascii=False, indent=2)) + '</pre></html>']
    return ''.join(pieces)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == '_extract':
        return extraction_worker(argv[1], argv[2]) if len(argv) == 3 else 2
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--pdf', required=True); p.add_argument('--out', required=True); p.add_argument('--chunk-chars', type=int, default=4000)
    p = sub.add_parser('import'); p.add_argument('--prepared', required=True); p.add_argument('--expected-prepare', required=True); p.add_argument('--index', required=True); p.add_argument('--out', required=True)
    p = sub.add_parser('review'); p.add_argument('--prepared', required=True); p.add_argument('--imported', required=True); p.add_argument('--expected-import', required=True); p.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'prepare':
            result = prepare(args.pdf, args.out, args.chunk_chars)
        elif args.operation == 'import':
            result = import_captures(args.prepared, args.index, args.out, args.expected_prepare)
        else:
            result = export_review(args.prepared, args.imported, args.out, args.expected_import)
        print(json.dumps({'profile': PROFILE, 'operation': result['operation'], 'status': 'complete',
                          'result_sha256': result['result_sha256'], 'payload': result['payload']}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc) if isinstance(exc, PipelineError) else 'operation_failed'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
