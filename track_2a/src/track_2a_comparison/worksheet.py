"""Assemble one bounded parliamentary question from pinned local evidence packets."""
from __future__ import annotations

import argparse
from collections import Counter
import copy
import html
import json
from pathlib import Path
import re
import sys
import tempfile

PROFILE = 'opd-question-worksheet-1'
SELECTION_PROFILE = 'opd-question-selection-1'
QUESTION = 'What was proposed or recommended, and what substantive decision is actually evidenced?'
MAX_PACKETS = 16
MAX_ROWS = 4096
TOTAL_COPY_CAP = 128 * 1024 * 1024
BASELINES = ('API', 'search', 'official_page', 'manual_PDF')
MAPPING_OPTIONS = ('proposal', 'recommendation', 'substantive_decision', 'agenda_decision',
                   'referral_decision', 'credit_decision', 'other_reported_action',
                   'unmappable', 'multiple_interpretations')


def dependencies(repo_root):
    # This is the explicitly selected trusted code checkout, never a packet path.
    sys.path.insert(0, str(Path(repo_root).absolute()))
    from track_2a_converter import pipeline
    from track_2a_gap_ledger import ledger
    return pipeline, ledger


def missing(reason):
    return {'state': 'unassessed', 'value': None, 'reason': reason}


def manual_cells():
    return {'status': 'not_started', 'proposed_mappings': [], 'explanation': '',
            'document_author_observation': '', 'document_date_observation': '',
            'event_date_observation': '', 'unresolved_annexes_or_pages': '',
            'additional_interpretations': [], 'source_verification_steps': None,
            'source_reading_minutes': None}


def unknown_baselines():
    return [{'baseline_type': kind, 'observation_state': 'unknown',
             'retrieval_state': 'not_inspected', 'endpoint_or_query': None,
             'requested_at': None, 'pagination': None, 'scope': None,
             'returned_evidence': [], 'limitations': 'No selected baseline receipt.'}
            for kind in BASELINES]


def baseline_cells():
    return [{'baseline_type': kind, 'status': 'not_started', 'endpoint_or_query': '',
             'observed_at': '', 'pagination_and_scope': '', 'returned_evidence': '',
             'unresolved_limits': '', 'incremental_evidence_or_negative_finding': ''}
            for kind in BASELINES]


def selection(path, p):
    raw = p.read_bytes(path, p.INDEX_CAP)
    value = p.strict_load(raw, p.INDEX_CAP)
    p.exact(value, ('profile', 'converter_packets', 'frozen_gap_ledger'), 'invalid_selection')
    p.require(value['profile'] == SELECTION_PROFILE, 'unsupported_selection_profile')
    packets = value['converter_packets']
    p.require(isinstance(packets, list) and len(packets) <= MAX_PACKETS, 'packet_count_limit')
    ids = set()
    paths = set()
    keys = ('selection_id', 'label', 'prepared_directory', 'imported_directory',
            'review_directory', 'expected_prepare_sha256', 'expected_import_sha256',
            'expected_review_sha256')
    for packet in packets:
        p.exact(packet, keys, 'invalid_packet_selection')
        identity = packet['selection_id']
        p.require(isinstance(identity, str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', identity), 'invalid_selection_id')
        p.require(identity not in ids, 'duplicate_selection_id'); ids.add(identity)
        p.require(isinstance(packet['label'], str) and 0 < len(packet['label']) <= 2000, 'invalid_selection_label')
        for key in ('prepared_directory', 'imported_directory', 'review_directory'):
            p.require(isinstance(packet[key], str) and 0 < len(packet[key]) <= 4096, 'invalid_packet_directory')
            directory = Path(packet[key])
            if not directory.is_absolute():
                directory = Path(path).absolute().parent / directory
            packet[key] = str(p.safe_path(directory))
        p.require(packet['review_directory'] not in paths, 'duplicate_review_selection')
        paths.add(packet['review_directory'])
        for key in ('expected_prepare_sha256', 'expected_import_sha256', 'expected_review_sha256'):
            p.require(isinstance(packet[key], str) and p.DIGEST.fullmatch(packet[key]), 'expected_result_pin_required')
    gap = value['frozen_gap_ledger']
    if gap is not None:
        p.exact(gap, ('packet_directory', 'expected_manifest_sha256', 'families'), 'invalid_ledger_selection')
        p.require(isinstance(gap['packet_directory'], str) and 0 < len(gap['packet_directory']) <= 4096, 'invalid_packet_directory')
        directory = Path(gap['packet_directory'])
        if not directory.is_absolute():
            directory = Path(path).absolute().parent / directory
        gap['packet_directory'] = str(p.safe_path(directory))
        p.require(isinstance(gap['expected_manifest_sha256'], str) and p.DIGEST.fullmatch(gap['expected_manifest_sha256']), 'expected_ledger_pin_required')
        fs = gap['families']
        p.require(isinstance(fs, list) and 0 < len(fs) <= 32 and all(isinstance(f, str) and 0 < len(f) <= 100 for f in fs), 'invalid_family_selection')
        p.require(len(fs) == len(set(fs)), 'duplicate_family_selection')
    p.require(packets or gap is not None, 'empty_selection')
    packets.sort(key=lambda e: e['selection_id'])
    if gap is not None:
        gap['families'].sort()
    return value, raw


def replay_import_units(p, import_root, index, records, requests, bundle, schema):
    """Replay converter classification, never trust a unit's declared status.

    Retained originals are authoritative for parsing/validation. A capture with
    no retained bytes can only carry its existing read-failure declaration;
    the worksheet cannot prove what was available at original capture time.
    """
    counts = Counter(e.get('request_id') for e in index['entries'] if isinstance(e, dict) and isinstance(e.get('request_id'), str))
    units = {rid: {'request_id': rid, 'status': 'unattempted', 'attempted': False,
                   'candidates': [], 'capture_record': None, 'error': None} for rid in requests}
    expected_records = []
    for record in records:
        original = copy.deepcopy(record)
        entry = record['entry']
        # Successful reads may subsequently have schema/index errors. Replay
        # those errors rather than using them to suppress an existing capture.
        original['error'] = (record['error'] if record['original_path'] is None and
                             isinstance(entry, dict) and 'response_path' in entry else None)
        rid = entry.get('request_id') if isinstance(entry, dict) else None
        unit = units.get(rid) if isinstance(rid, str) else None
        if unit is not None and isinstance(entry, dict) and (entry.get('status') != 'unattempted' or 'response_path' in entry):
            unit['attempted'] = True
        try:
            p._entry_shape(entry)
            p.require(rid in requests, 'unknown_request_id')
            p.require(counts[rid] == 1, 'duplicate_capture_request')
            p.require(original['error'] is None, original['error'] or 'capture_read_failed')
            unit['capture_record'] = record['index']
            if entry['status'] == 'unattempted':
                pass
            elif entry['status'] == 'failed':
                unit.update(status='attempt_failed', error=entry['error_code'])
            else:
                p.require(record['original_path'] is not None, 'original_capture_required')
                candidate = p.strict_load(p.read_bytes(p.relative_file(import_root, record['original_path']), p.RESPONSE_CAP), p.RESPONSE_CAP)
                p.validate_candidate(candidate, requests[rid], bundle, schema)
                unit.update(status='structurally_valid_unadjudicated', candidates=candidate['events'])
        except (p.PipelineError, TypeError, KeyError, RecursionError) as exc:
            code = str(exc) if isinstance(exc, p.PipelineError) else 'invalid_capture'
            original['error'] = code
            if unit is not None:
                unit.update(status='rejected_capture', candidates=[], error=code)
        expected_records.append(original)
    return list(units.values()), expected_records


def verify_import(p, entry, prepared, bundle, requests, schema):
    imported = p.verify_result(entry['imported_directory'], 'import', entry['expected_import_sha256'])
    p.exact(imported['inputs'], ('prepare_result_sha256', 'index_sha256'), 'invalid_import_inputs')
    p.exact(imported['payload'], ('ledger_sha256', 'denominators'), 'invalid_import_payload')
    p.require(imported['inputs']['prepare_result_sha256'] == entry['expected_prepare_sha256'], 'prepare_pin_selection_mismatch')
    index_raw = p.read_bytes(Path(entry['imported_directory']) / 'original-index.json', p.INDEX_CAP)
    p.require(p.sha(index_raw) == imported['inputs']['index_sha256'], 'index_hash_mismatch')
    index = p.strict_load(index_raw, p.INDEX_CAP)
    p.exact(index, ('profile', 'prepare_result_sha256', 'entries'), 'invalid_capture_index')
    p.require(index['profile'] == p.PROFILE and index['prepare_result_sha256'] == entry['expected_prepare_sha256'], 'capture_index_binding_mismatch')
    ledger = p.strict_load(p.read_bytes(Path(entry['imported_directory']) / 'import-ledger.json'))
    p.exact(ledger, ('profile', 'prepare_result_sha256', 'units', 'capture_records', 'denominators',
                     'adjudication', 'answer_eligible', 'human_reference', 'semantic_accuracy', 'network_calls'), 'invalid_import_ledger')
    p.require(p.sha(p.canonical(ledger)) == imported['payload']['ledger_sha256'], 'ledger_hash_mismatch')
    p.require(ledger['profile'] == p.PROFILE and ledger['prepare_result_sha256'] == entry['expected_prepare_sha256'], 'ledger_binding_mismatch')
    p.require(ledger['adjudication'] == 'unadjudicated' and ledger['answer_eligible'] is False and
              ledger['human_reference'] is False and ledger['semantic_accuracy'] is None and
              type(ledger['network_calls']) is int and ledger['network_calls'] == 0, 'unsupported_import_claim')
    units = ledger['units']; records = ledger['capture_records']
    p.require(isinstance(units, list) and len(units) == len(requests) and isinstance(records, list) and len(records) <= p.MAX_ENTRIES, 'import_inventory_mismatch')
    p.require(isinstance(index['entries'], list) and len(index['entries']) == len(records), 'capture_index_inventory_mismatch')
    p.require([u.get('request_id') for u in units if isinstance(u, dict)] == list(requests), 'import_inventory_mismatch')
    for pos, record in enumerate(records):
        p.exact(record, ('index', 'entry', 'original_path', 'original_sha256', 'error'), 'invalid_capture_record')
        p.require(type(record['index']) is int and record['index'] == pos, 'capture_record_index_mismatch')
        p.require(record['entry'] == index['entries'][pos], 'capture_record_entry_mismatch')
        p.require(record['error'] is None or isinstance(record['error'], str), 'invalid_capture_error')
        if record['original_path'] is not None:
            p.require(record['original_path'] == f'original-captures/{pos:04d}.bin', 'capture_record_path_mismatch')
            original = p.read_bytes(p.relative_file(entry['imported_directory'], record['original_path']), p.RESPONSE_CAP)
            p.require(p.sha(original) == record['original_sha256'], 'original_capture_hash_mismatch')
        else:
            p.require(record['original_sha256'] is None, 'capture_record_hash_mismatch')
    expected_files = {'invocation.json', 'original-index.json', 'import-ledger.json'} | {
        r['original_path'] for r in records if r['original_path'] is not None}
    p.require(set(imported['files']) == expected_files, 'import_capture_inventory_mismatch')
    for unit in units:
        p.exact(unit, ('request_id', 'status', 'attempted', 'candidates', 'capture_record', 'error'), 'invalid_import_unit')
        p.require(type(unit['attempted']) is bool and isinstance(unit['candidates'], list), 'invalid_import_unit')
        p.require(unit['status'] in ('structurally_valid_unadjudicated', 'attempt_failed', 'rejected_capture', 'unattempted'), 'unsupported_unit_status')
        ref = unit['capture_record']
        p.require(ref is None or (type(ref) is int and 0 <= ref < len(records)), 'invalid_capture_record_reference')
        if ref is not None:
            p.require(isinstance(records[ref]['entry'], dict) and records[ref]['entry'].get('request_id') == unit['request_id'], 'capture_request_mismatch')
        if unit['status'] == 'structurally_valid_unadjudicated':
            p.require(unit['attempted'] and unit['error'] is None and ref is not None, 'invalid_valid_unit')
            record = records[ref]
            p._entry_shape(record['entry'])
            p.require(record['entry']['status'] == 'captured', 'valid_capture_status_mismatch')
            p.require(record['error'] is None and record['original_path'] is not None, 'invalid_valid_capture')
            original = p.strict_load(p.read_bytes(p.relative_file(entry['imported_directory'], record['original_path']), p.RESPONSE_CAP), p.RESPONSE_CAP)
            p.validate_candidate(original, requests[unit['request_id']], bundle, schema)
            p.require(unit['candidates'] == original['events'], 'candidate_original_capture_mismatch')
        else:
            p.require(unit['candidates'] == [], 'unsuccessful_unit_has_candidates')
            if unit['status'] == 'unattempted':
                p.require(unit['attempted'] is False and unit['error'] is None, 'invalid_unattempted_unit')
            else:
                p.require(isinstance(unit['error'], str) and bool(unit['error']), 'missing_unit_failure')
            if unit['status'] == 'attempt_failed':
                p.require(unit['attempted'] and ref is not None, 'invalid_failed_unit')
                p._entry_shape(records[ref]['entry'])
                p.require(records[ref]['entry']['status'] == 'failed' and records[ref]['entry']['error_code'] == unit['error'], 'failed_unit_entry_mismatch')
    replayed_units, replayed_records = replay_import_units(p, entry['imported_directory'], index, records, requests, bundle, schema)
    p.require(units == replayed_units and records == replayed_records, 'import_classification_replay_mismatch')
    counts = {'planned': len(units), 'attempted': sum(u['attempted'] for u in units),
              'unattempted': sum(not u['attempted'] for u in units),
              'structurally_valid': sum(u['status'] == 'structurally_valid_unadjudicated' for u in units),
              'rejected': sum(u['status'] == 'rejected_capture' for u in units),
              'failed': sum(u['status'] == 'attempt_failed' for u in units)}
    p.require(ledger['denominators'] == counts == imported['payload']['denominators'], 'import_denominator_mismatch')
    p.require(all(type(v) is int for v in ledger['denominators'].values()), 'invalid_denominator_type')
    p.require(all(type(v) is int for v in imported['payload']['denominators'].values()), 'invalid_denominator_type')
    return imported, ledger


def converter_packet(entry, p):
    # Enforce preparation bounds before request reconstruction. Selected pins
    # do not make out-of-contract numeric types or chunk limits admissible.
    bounded = p.strict_load(p.read_bytes(Path(entry['prepared_directory']) / 'bundle.json'))
    p.exact(bounded, ('profile', 'source_sha256', 'source_bytes', 'page_count', 'pages',
                      'source_access', 'page_status_counts', 'extractor', 'chunk_chars',
                      'schema_sha256', 'prompt_sha256', 'requests', 'coverage_claim', 'ocr_status'), 'invalid_prepared_bundle')
    p.require(type(bounded['chunk_chars']) is int and 256 <= bounded['chunk_chars'] <= 8000, 'chunk_size_limit')
    p.require(type(bounded['page_count']) is int and 0 < bounded['page_count'] <= p.MAX_PAGES and
              isinstance(bounded['pages'], list) and len(bounded['pages']) == bounded['page_count'], 'page_inventory_mismatch')
    p.require(isinstance(bounded['requests'], list) and len(bounded['requests']) <= p.MAX_REQUESTS, 'request_count_limit')
    p.require(bounded['coverage_claim'] == 'native_text_only_not_semantically_reviewed' and bounded['ocr_status'] == 'not_attempted', 'unsupported_preparation_claim')
    total_text = 0
    for page in bounded['pages']:
        p.exact(page, ('page', 'status', 'error', 'text', 'text_sha256', 'ocr_status'), 'invalid_prepared_page')
        p.require(type(page['page']) is int and isinstance(page['text'], str), 'invalid_prepared_page')
        size = len(page['text'].encode('utf-8')); total_text += size
        p.require(size <= p.MAX_PAGE_TEXT and total_text <= p.MAX_TEXT, 'page_text_size_limit')
    prepared, bundle, requests, schema = p.load_prepared(entry['prepared_directory'], entry['expected_prepare_sha256'])
    extraction = p.strict_load(p.read_bytes(Path(entry['prepared_directory']) / 'extraction.json'))
    p.require(extraction == {'status': 'complete', **{k: bundle[k] for k in ('pages', 'source_access', 'extractor', 'page_status_counts')}}, 'extraction_bundle_mismatch')
    imported, ledger = verify_import(p, entry, prepared, bundle, requests, schema)
    reviewed = p.verify_result(entry['review_directory'], 'review', entry['expected_review_sha256'])
    p.require(reviewed['inputs'] == {'prepare_result_sha256': entry['expected_prepare_sha256'],
                                    'import_result_sha256': entry['expected_import_sha256']}, 'review_pin_selection_mismatch')
    # Reuse the canonical source-first exporter, including all unresolved pages.
    # Its fresh lifecycle IDs differ; every payload/source/capture/HTML byte must match.
    with tempfile.TemporaryDirectory(prefix='opd-worksheet-verify-') as temp:
        regenerated = Path(temp) / 'review'
        expected = p.export_review(entry['prepared_directory'], entry['imported_directory'], regenerated, entry['expected_import_sha256'])
        p.require(reviewed['payload'] == expected['payload'], 'review_payload_mismatch')
        p.require(set(reviewed['files']) == set(expected['files']), 'review_inventory_mismatch')
        for name in expected['files']:
            if name != 'invocation.json':
                p.require(p.read_bytes(p.relative_file(entry['review_directory'], name)) == p.read_bytes(regenerated / name), 'review_regeneration_mismatch')
    queue = p.strict_load(p.read_bytes(Path(entry['review_directory']) / 'review-queue.json'))
    key = 'converter:' + entry['selection_id']
    document = {'document_key': key, 'kind': 'verified_converter_packet', 'label': entry['label'],
                'selection': copy.deepcopy(entry), 'source_sha256': bundle['source_sha256'],
                'verification': 'pinned_chain_and_exact_review_regeneration',
                'source_access': queue['source_access'], 'extractor': queue['extractor'],
                'page_count': queue['page_count'], 'page_status_counts': queue['page_status_counts'],
                'request_denominators': queue['denominators'],
                'scope': 'complete_prepared_page_inventory_native_text_only_not_semantic_coverage',
                'page_inventory': [{k: page[k] for k in ('page', 'status', 'error', 'ocr_status', 'text_sha256')}
                                   for page in queue['pages']],
                'rejected_capture_records': queue['rejected_capture_records'],
                'baselines': unknown_baselines(), 'manual_baseline_receipt': baseline_cells(),
                'original_review_local': f'packets/{entry["selection_id"]}/review.html'}
    rows = []
    for page in queue['pages']:
        for request in page['requests'] or [None]:
            candidates = request['candidates'] if request else []
            for candidate in candidates or [None]:
                rid = request['request_id'] if request else None
                cid = candidate['candidate_id'] if candidate else None
                identity = {'document_key': key, 'source_sha256': queue['source_sha256'],
                            'review_result_sha256': entry['expected_review_sha256'], 'page': page['page'],
                            'request_id': rid, 'candidate_id': cid}
                rows.append({'identity': identity, 'kind': 'converter_candidate' if candidate else 'unresolved_coverage',
                    'adjudication': 'UNADJUDICATED', 'answer_eligible': False,
                    'source_context': {'page_status': page['status'], 'page_error': page['error'],
                                       'request_status': request['status'] if request else 'no_request',
                                       'request_error': request['error'] if request else None,
                                       'reviewed_scope': request['scope'] if request else None,
                                       'page_text_sha256': page['text_sha256'],
                                       'coverage_note': 'No candidate is never evidence of no relevant event.'},
                    'document_author': candidate['author'] if candidate else missing('No candidate.'),
                    'actor': candidate['actor'] if candidate else missing('No candidate.'),
                    'addressee': candidate['addressee'] if candidate else missing('No candidate.'),
                    'event': candidate['event'] if candidate else missing('No candidate.'),
                    'outcome': candidate['outcome'] if candidate else missing('No candidate.'),
                    'document_dates': missing('Converter contract has no document-date field; do not infer from event text.'),
                    'event_date': missing('Converter contract has no event-date field; preserve original wording and review manually.'),
                    'original_candidate': copy.deepcopy(candidate), 'provenance': candidate['anchors'] if candidate else [],
                    'original_review_page': f'packets/{entry["selection_id"]}/review.html#page-{page["page"]}',
                    'original_pdf_page': f'packets/{entry["selection_id"]}/source.pdf#page={page["page"]}',
                    'manual_review': manual_cells()})
                p.require(len(rows) <= MAX_ROWS, 'comparison_row_limit')
    return document, rows, reviewed


def frozen_ledger(entry, repo_root, p, g):
    root = Path(entry['packet_directory'])
    protocol = g.read_json(root, 'protocol.json')
    p.require(protocol.get('manifest_sha256') == entry['expected_manifest_sha256'], 'ledger_pin_mismatch')
    verified = g.run(Path(repo_root), root)
    bundle = g.load_bundle(root)
    families = sorted(entry['families'])
    available = {s['family_id'] for s in bundle['sources']}
    p.require(set(families) <= available, 'selected_family_unavailable')
    documents = []
    evidence = {e['evidence_id']: e for e in bundle['evidence']}
    sources = {s['source_id']: s for s in bundle['sources']}
    for family in families:
        selected_sources = sorted((s for s in bundle['sources'] if s['family_id'] == family), key=lambda s: s['source_id'])
        documents.append({'document_key': 'ledger:' + family, 'kind': 'frozen_research_ledger_family',
                          'label': family, 'manifest_sha256': verified['manifest_sha256'],
                          'verification': 'frozen_ledger_structure_and_selected_historical_text_only',
                          'sources': selected_sources,
                          'inspection_scopes': [s for s in bundle['inspection_scopes'] if sources[s['source_id']]['family_id'] == family],
                          'scope': 'selected_historical_pages_and_incomplete_research_locators_not_exhaustive',
                          'baselines': [b for b in bundle['baselines'] if b['family_id'] == family],
                          'manual_baseline_receipt': baseline_cells(),
                          'baseline_gap': next(r for r in verified['event_gap_ledger'] if r['family_id'] == family)})
    rows = []
    for event in sorted(bundle['events'], key=lambda e: (e['family_id'], e['event_id'])):
        if event['family_id'] not in families:
            continue
        refs = g.event_evidence_refs(event)
        event_sources = sorted({evidence[r]['source_id'] for r in refs})
        # Include document-date evidence separately, without collapsing it into event dates.
        all_refs = set(refs)
        for sid in event_sources:
            all_refs.update(g.field_evidence_refs(sources[sid]['source_document_date']))
        rows.append({'identity': {'document_key': 'ledger:' + event['family_id'],
                                  'manifest_sha256': verified['manifest_sha256'], 'family_id': event['family_id'],
                                  'affair_id': event['affair_id'], 'event_id': event['event_id'], 'source_ids': event_sources},
            'kind': 'AI_prepared_research_annotation', 'adjudication': 'UNADJUDICATED', 'answer_eligible': False,
            'source_context': {'coverage_note': event['coverage_note'], 'language': event['language'], 'level': event['level'],
                               'provisional_mode': event['mode'], 'provisional_decision_scope': event['payload'].get('scope')},
            'document_author': missing('Not recorded in the ledger contract. Never substitute the event actor.'),
            'actor': event['actor'], 'addressee': event['addressee'], 'event': event['stage'],
            'outcome': event['payload'], 'event_date': event['event_date'],
            'document_dates': [{'source_id': sid, 'field': sources[sid]['source_document_date']} for sid in event_sources],
            'original_annotation': event, 'provenance': [evidence[r] for r in sorted(all_refs)],
            'manual_review': manual_cells()})
    return documents, rows, {'manifest_sha256': verified['manifest_sha256'],
                            'validation': verified['validation'], 'registered_metrics': verified['metrics']}


def build(selected, repo_root, p, g):
    documents, rows, packets = [], [], []
    for entry in sorted(selected['converter_packets'], key=lambda e: e['selection_id']):
        document, more, reviewed = converter_packet(entry, p)
        documents.append(document); rows.extend(more); packets.append((entry, reviewed))
        p.require(len(rows) <= MAX_ROWS, 'comparison_row_limit')
    registered = None
    if selected['frozen_gap_ledger'] is not None:
        more_documents, more_rows, registered = frozen_ledger(selected['frozen_gap_ledger'], repo_root, p, g)
        documents.extend(more_documents); rows.extend(more_rows)
    p.require(len(rows) <= MAX_ROWS, 'comparison_row_limit')
    for row in rows:
        row['row_id'] = p.sha(p.canonical(row['identity']))
    rows.sort(key=lambda r: (r['identity']['document_key'], r['identity'].get('page', 0),
                             r['source_context'].get('reviewed_scope', {}).get('start', 0) if r['source_context'].get('reviewed_scope') else 0,
                             r['identity'].get('request_id') or '', r['identity'].get('candidate_id') or r['identity'].get('event_id') or ''))
    p.require(len({r['row_id'] for r in rows}) == len(rows), 'duplicate_comparison_identity')
    converter_documents = [d for d in documents if d['kind'] == 'verified_converter_packet']
    request_counts = {k: sum(d['request_denominators'][k] for d in converter_documents)
                      for k in ('planned', 'attempted', 'unattempted', 'structurally_valid', 'rejected', 'failed')}
    baseline_states = Counter(b['observation_state'] for d in documents for b in d['baselines'])
    result = {'profile': PROFILE, 'question': QUESTION, 'selection': selected,
              'adjudication': 'UNADJUDICATED', 'answer_eligible': False, 'human_reference': False,
              'global_affair_status': None, 'semantic_accuracy': None, 'human_minutes_saved': None,
              'provider_calls': 0, 'network_calls': 0, 'manual_mapping_vocabulary': list(MAPPING_OPTIONS),
              'documents': documents, 'rows': rows, 'frozen_ledger_verification': registered,
              'coverage': {'selected_converter_packets': len(converter_documents),
                           'selected_ledger_families': len(documents) - len(converter_documents),
                           'converter_page_inventory': sum(d['page_count'] for d in converter_documents),
                           'converter_page_statuses': {k: sum(d['page_status_counts'][k] for d in converter_documents)
                                                       for k in ('text_extracted', 'no_text_unresolved', 'extraction_failed')},
                           'converter_requests': request_counts, 'comparison_rows': len(rows),
                           'row_kinds': dict(sorted(Counter(r['kind'] for r in rows).items())),
                           'unmapped_rows': len(rows), 'answer_eligible_rows': 0, 'independently_reviewed_rows': 0,
                           'baseline_slots': sum(len(d['baselines']) for d in documents),
                           'baseline_observation_states': dict(sorted(baseline_states.items())),
                           'API_field_coverage': 'unknown', 'search_field_coverage': 'unknown',
                           'semantic_or_whole_document_coverage': None},
              'limitations': ['A comparison queue, never a substantive answer or adjudication.',
                  'No automatic affair equivalence, event merging, date resolution or semantic mapping.',
                  'All mappings are blank. Structural checks cannot detect a wrong actor supported by a real quote.',
                  'Source pages, unresolved text, zero candidates and missing annexes never prove absence.',
                  'Historical ledger checks do not verify original PDFs or locator-only evidence.',
                  'Recorded baseline observations are AI-prepared research notes, not timed human review.',
                  'Unknown or blocked baseline coverage is never missing data.',
                  'Hashes establish selected-byte consistency, not authority, source rights or semantic correctness.']}
    return result, packets


def render(result):
    esc = html.escape
    def data(value):
        return '<pre>' + esc(json.dumps(value, ensure_ascii=False, indent=2)) + '</pre>'
    def field(value):
        if isinstance(value, dict) and ('state' in value or 'status' in value):
            state = value.get('state', value.get('status'))
            primary = value.get('value')
            return '<p><strong>' + esc(state) + '</strong>: ' + esc(str(primary) if primary is not None else 'not established') + '</p><details><summary>Exact field and evidence</summary>' + data(value) + '</details>'
        if isinstance(value, dict) and 'type' in value:
            pieces = ['<p><strong>Existing provisional type: ' + esc(value['type']) + '</strong></p>']
            if 'scope' in value:
                pieces.append('<p>Existing decision scope: ' + esc(value['scope']) + '</p>')
            for key in ('requested_action', 'recommended_action', 'disposition', 'action', 'draft_instrument'):
                if key in value:
                    pieces.append('<p>' + esc(key.replace('_', ' ')) + '</p>' + field(value[key]))
            pieces.append('<details><summary>Complete unchanged payload</summary>' + data(value) + '</details>')
            return ''.join(pieces)
        return data(value)
    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">',
        '<title>Parliamentary comparison worksheet</title><style>body{font:16px system-ui;max-width:1500px;margin:2rem auto;padding:1rem;color:#202b32;background:#f8faf9}h1{max-width:1050px}.warning{padding:1rem;border:2px solid #955400;background:#fff5de}table{border-collapse:collapse;width:100%}th,td{vertical-align:top;border:1px solid #aaa;padding:.6rem;text-align:left}th{background:#e6efeb}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}article,section{border-top:3px solid #526c60;padding-top:1rem;margin-top:2rem}.manual{background:#fffdf2;border:1px dashed #8d845d;padding:1rem}.blank{height:2.2rem;border-bottom:1px solid #aaa}code{overflow-wrap:anywhere}@media print{details{display:block}body{font-size:11px}article{break-inside:avoid}.manual{break-inside:avoid}}</style></head><body>',
        '<h1>' + esc(QUESTION) + '</h1><div class="warning"><strong>UNADJUDICATED. Every row is answer-ineligible.</strong><p>Question-specific comparison queue. No answer, human review, semantic mapping or model call is asserted. All unmapped, conflicting and unresolved rows remain visible.</p></div>',
        '<p><a href="worksheet.json">Strict JSON worksheet template</a> · <a href="selection.original.json">Unchanged selection manifest</a></p>',
        '<h2>Coverage denominators</h2>' + data(result['coverage']),
        '<p>Request counts describe mechanical processing. They do not measure event recall, source entailment, API deficits or time saved. Ledger counts remain a separate selected historical inventory.</p>',
        '<h2>Comparison index</h2><table><thead><tr><th>Original identity</th><th>Document author</th><th>Acting body</th><th>Event and outcome, unchanged</th><th>Mapping</th></tr></thead><tbody>']
    for row in result['rows']:
        parts += ['<tr><td><a href="#row-' + row['row_id'] + '">' + esc(row['identity']['document_key']) + '</a>' + data(row['identity']) + '</td><td>' + field(row['document_author']) + '</td><td>' + field(row['actor']) + '</td><td>' + field(row['event']) + field(row['outcome']) + '</td><td>UNMAPPED<br>UNADJUDICATED<br>Answer-ineligible</td></tr>']
    parts += ['</tbody></table><h2>Source scope and baseline receipts</h2>']
    for doc in result['documents']:
        parts += ['<section><h3>' + esc(doc['label']) + '</h3>']
        if 'original_review_local' in doc:
            parts += ['<p><a href="' + esc(doc['original_review_local'], quote=True) + '">Open unchanged source-first review packet</a></p>']
        parts += [data(doc), '<p>Baseline observation counts are receipt states, never a percentage of facts available. Remote source URLs are inert text; nothing is fetched.</p></section>']
    for row in result['rows']:
        parts += ['<article id="row-' + row['row_id'] + '"><h2>' + esc(row['identity']['document_key']) + ': ' + esc(row['identity'].get('candidate_id') or row['identity'].get('event_id') or 'Unresolved coverage') + '</h2>',
                  '<p><strong>UNADJUDICATED · UNMAPPED · Answer-ineligible</strong></p>', data(row['identity'])]
        if 'original_review_page' in row:
            parts += ['<p><a href="' + esc(row['original_review_page'], quote=True) + '">Source-first page and original capture</a> · <a href="' + esc(row['original_pdf_page'], quote=True) + '">Exact original PDF page</a></p>']
        parts += ['<h3>Original page/quote provenance</h3>', data(row['provenance']), '<h3>Source context, missingness and scope</h3>', data(row['source_context']),
                  '<table><tr><th>Document author</th><th>Acting body</th><th>Addressee</th></tr><tr><td>' + field(row['document_author']) + '</td><td>' + field(row['actor']) + '</td><td>' + field(row['addressee']) + '</td></tr></table>',
                  '<h3>Event wording</h3>', field(row['event']), '<h3>Outcome / original payload</h3>', field(row['outcome']),
                  '<h3>Document dates, kept separate</h3>', field(row['document_dates']), '<h3>Event date and all alternatives</h3>', field(row['event_date']),
                  '<details><summary>Complete unchanged original candidate / annotation</summary>', data(row.get('original_candidate', row.get('original_annotation'))), '</details>',
                  '<div class="manual"><h3>Manual worksheet cells, blank and not reviewed</h3><p>Print or edit a separate JSON copy. This read-only page does not save, submit, adjudicate or unlock answers. Multiple interpretations and unmappable are valid notes.</p><p>Suggested vocabulary: ' + esc(', '.join(MAPPING_OPTIONS)) + '</p>']
        for label in ('Proposed mapping(s)', 'Explanation with exact supporting evidence', 'Document author / date observation', 'Event date observation', 'Unresolved pages, annexes or conflicts', 'Additional interpretations'):
            parts += ['<p>' + label + '</p><div class="blank"></div>']
        parts += ['</div></article>']
    parts += ['<h2>Limits</h2><ul>'] + ['<li>' + esc(v) + '</li>' for v in result['limitations']] + ['</ul></body></html>']
    return ''.join(parts).encode('utf-8')


def generate(selection_path, repo_root, out_dir):
    p, g = dependencies(repo_root)
    selected, original = selection(selection_path, p)
    out = p.safe_path(out_dir)
    inputs = [p.safe_path(selection_path)]
    for entry in selected['converter_packets']:
        inputs += [Path(entry[k]) for k in ('prepared_directory', 'imported_directory', 'review_directory')]
    if selected['frozen_gap_ledger']:
        inputs.append(Path(selected['frozen_gap_ledger']['packet_directory']))
    p.require(not any(out == path or out.is_relative_to(path) or path.is_relative_to(out) for path in inputs), 'output_input_alias')
    result, packets = build(selected, repo_root, p, g)
    json_bytes, html_bytes = p.canonical(result), render(result)
    p.require(len(json_bytes) <= p.JSON_CAP and len(html_bytes) <= p.JSON_CAP, 'worksheet_output_size_limit')
    # All admission checks precede any output directory or successful HTML.
    copies, total = [], 0
    for entry, reviewed in packets:
        for name, receipt in reviewed['files'].items():
            raw = p.read_bytes(p.relative_file(entry['review_directory'], name))
            p.require(p.sha(raw) == receipt['sha256'], 'packet_changed_before_copy')
            total += len(raw)
            p.require(total <= TOTAL_COPY_CAP, 'worksheet_copy_size_limit')
            copies.append((f'packets/{entry["selection_id"]}/{name}', raw))
        raw = p.read_bytes(Path(entry['review_directory']) / 'result.json')
        total += len(raw); p.require(total <= TOTAL_COPY_CAP, 'worksheet_copy_size_limit')
        copies.append((f'packets/{entry["selection_id"]}/result.json', raw))
        p.verify_result(entry['review_directory'], 'review', entry['expected_review_sha256'])
    out, start = p.begin(out, 'question_worksheet', {'selection_sha256': p.sha(original), 'worksheet_profile': PROFILE})
    try:
        for name, raw in copies:
            p.write_new(out / name, raw)
        p.write_new(out / 'selection.original.json', original)
        p.write_new(out / 'worksheet.json', json_bytes)
        p.write_new(out / 'worksheet.html', html_bytes)
        receipt = p.finish(out, start, {'worksheet_profile': PROFILE, 'worksheet_sha256': p.sha(json_bytes),
                                       'html_sha256': p.sha(html_bytes), 'rows': len(result['rows']), 'answer_eligible': False})
        return receipt
    except Exception as exc:
        p.record_failure(out, start, str(exc) if isinstance(exc, p.PipelineError) else 'worksheet_write_failed')
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path, help='Trusted existing converter/gap-ledger code checkout')
    parser.add_argument('--selection', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path, help='Fresh local output directory with an existing parent')
    args = parser.parse_args(argv)
    try:
        receipt = generate(args.selection, args.repo_root, args.out)
        print(json.dumps({'status': 'complete', 'worksheet_profile': PROFILE,
                          'result_sha256': receipt['result_sha256'], 'rows': receipt['payload']['rows'],
                          'answer_eligible': False, 'provider_calls': 0}, sort_keys=True))
        return 0
    except Exception as exc:
        # Do not echo hostile source text, file paths or exception internals.
        code = str(exc) if type(exc).__name__ in ('PipelineError', 'LedgerError') else 'worksheet_validation_or_io_failed'
        if not re.fullmatch(r'[a-z0-9_]{1,100}', code):
            code = 'worksheet_validation_or_io_failed'
        print(json.dumps({'status': 'failed', 'error': code}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
