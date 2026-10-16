"""Offline provisional evidence ledger. No ingestion, network, model call or truth certification."""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import date
import hashlib
import json
import math
import os
import re
from pathlib import Path
import stat
import sys
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.validators import extend
from jsonschema.exceptions import SchemaError
from referencing.exceptions import Unresolvable

ROOT = Path(__file__).resolve().parent
PROFILE = 'opd-offline-gap-ledger-0.1.0'
CAP = 2_000_000
StrictValidator = extend(Draft202012Validator, type_checker=Draft202012Validator.TYPE_CHECKER.redefine('integer', lambda checker, value: type(value) is int))

class LedgerError(ValueError):
    """Stable diagnostics; no arbitrary source text is emitted on validation failure."""

def require(test, code):
    if not test:
        raise LedgerError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')

def strict_load(raw):
    # Same duplicate/non-finite rejection contract as the existing offline evaluator.
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate_json_key')
            result[key] = value
        return result
    def finite(value):
        number = float(value)
        require(math.isfinite(number), 'nonfinite_json_number')
        return number
    try:
        data = raw.encode('utf-8') if isinstance(raw, str) else raw
        require(isinstance(data, bytes) and len(data) <= CAP, 'json_size_limit')
        value = json.loads(data.decode('utf-8'), object_pairs_hook=pairs, parse_float=finite,
                           parse_constant=lambda _: (_ for _ in ()).throw(LedgerError('nonfinite_json_number')))
        def unicode_valid(item):
            if isinstance(item, str):
                require(not any(0xD800 <= ord(c) <= 0xDFFF for c in item), 'invalid_unicode_scalar')
            elif isinstance(item, dict):
                for key, child in item.items():
                    unicode_valid(key); unicode_valid(child)
            elif isinstance(item, list):
                for child in item:
                    unicode_valid(child)
        unicode_valid(value)
        return value
    except LedgerError:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError):
        raise LedgerError('invalid_json') from None

def read_bytes(root, relative):
    # Open each directory using descriptors: no symlink traversal or FIFO blocking.
    require(isinstance(relative, (str, Path)) and '\x00' not in str(relative), 'unsafe_relative_path')
    rel = Path(relative)
    require(not rel.is_absolute() and bool(rel.parts) and '..' not in rel.parts, 'unsafe_relative_path')
    require(all(hasattr(os, key) for key in ('O_NOFOLLOW', 'O_NONBLOCK', 'O_DIRECTORY')), 'secure_open_unavailable')
    descriptors = []
    try:
        fd = os.open(Path(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        descriptors.append(fd)
        for part in rel.parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            descriptors.append(fd)
        fd = os.open(rel.parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        descriptors.append(fd)
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), 'nonregular_file')
        require(info.st_size <= CAP, 'file_size_limit')
        chunks, length = [], 0
        while True:
            chunk = os.read(fd, min(65536, CAP + 1 - length))
            if not chunk:
                break
            chunks.append(chunk)
            length += len(chunk)
            require(length <= CAP, 'file_size_limit')
        return b''.join(chunks)
    except OSError:
        raise LedgerError('required_file_unavailable') from None
    finally:
        for fd in reversed(descriptors):
            os.close(fd)

def read_json(root, name):
    return strict_load(read_bytes(root, name))

def read_jsonl(root, name):
    raw = read_bytes(root, name)
    return [strict_load(line) for line in raw.splitlines() if line.strip()]

def load_bundle(root=ROOT):
    meta = read_json(root, 'data/bundle.json')
    require(isinstance(meta, dict) and set(meta) == {'profile_id','inspection_scopes'}, 'bundle_metadata_keys_invalid')
    return {**meta, 'sources': read_jsonl(root, 'data/sources.jsonl'),
            'evidence': read_jsonl(root, 'data/evidence.jsonl'),
            'events': read_jsonl(root, 'data/annotations.jsonl'),
            'baselines': read_jsonl(root, 'data/baseline_runs.jsonl')}

def unique_index(items, key):
    result = {item[key]: item for item in items}
    require(len(result) == len(items), 'duplicate_' + key)
    return result

def fields(value):
    if isinstance(value, dict):
        if 'status' in value and 'evidence_refs' in value and 'alternatives' in value:
            yield value
        else:
            for child in value.values():
                yield from fields(child)
    elif isinstance(value, list):
        for child in value:
            yield from fields(child)

def field_evidence_refs(field):
    return field['evidence_refs'] + [r for alt in field['alternatives'] for r in alt['evidence_refs']]

def validate(bundle, repo_root, schema=None):
    schema = read_json(ROOT, 'schemas/ledger.schema.json') if schema is None else schema
    def local_refs_only(item):
        if isinstance(item, dict):
            for key, value in item.items():
                if key in ('$ref','$dynamicRef'):
                    require(isinstance(value,str) and value.startswith('#/'), 'nonlocal_schema_reference_forbidden')
                local_refs_only(value)
        elif isinstance(item,list):
            for value in item:
                local_refs_only(value)
    local_refs_only(schema)
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise LedgerError('invalid_schema') from None
    try:
        require(not list(StrictValidator(schema, format_checker=FormatChecker()).iter_errors(bundle)), 'schema_contract_failed')
    except (Unresolvable, RecursionError):
        raise LedgerError('unresolvable_or_recursive_schema_reference') from None
    sources = unique_index(bundle['sources'], 'source_id')
    evidence = unique_index(bundle['evidence'], 'evidence_id')
    events = unique_index(bundle['events'], 'event_id')
    scopes = unique_index(bundle['inspection_scopes'], 'scope_id')
    pages_by_source = {}
    for sid, source in sources.items():
        require(source['original_bytes_sha256'] is None, 'original_bytes_not_verified')
        binding = source['historical_text_binding']
        if not binding:
            require(source['historical_catalog_binding'] is None and source['historically_reported_original_sha256'] is None, 'unsupported_historical_provenance')
        if binding:
            catalog_binding = source['historical_catalog_binding']
            require(catalog_binding is not None, 'historical_catalog_required')
            catalog_raw = read_bytes(repo_root, catalog_binding['relative_path'])
            require(sha(catalog_raw) == catalog_binding['sha256'], 'historical_catalog_hash_mismatch')
            catalog = strict_load(catalog_raw)
            try:
                original = next(u for u in catalog[catalog_binding['protocol_key']]['units'] if u['unit_id'] == binding['unit_id'])
            except (KeyError, TypeError, StopIteration):
                raise LedgerError('historical_catalog_unit_missing') from None
            require(source['family_id'] == binding['unit_id'], 'historical_family_unit_mismatch')
            require(source['source_url'] == original['source_url'], 'historical_source_url_mismatch')
            require(binding['relative_path'] == original['request_file'] and binding['sha256'] == original['request_sha256'], 'historical_request_catalog_mismatch')
            raw = read_bytes(repo_root, binding['relative_path'])
            require(sha(raw) == binding['sha256'], 'historical_request_hash_mismatch')
            request = strict_load(raw)
            try:
                unit = strict_load(request['messages'][1]['content'])['source_unit']
                pages = unique_index(unit['pages'], 'page')
                require(unit['unit_id'] == binding['unit_id'], 'historical_unit_mismatch')
                require(unit['source_sha256'] == source['historically_reported_original_sha256'], 'historical_original_hash_mismatch')
                require(set(pages) == set(binding['pages']), 'historical_page_inventory_mismatch')
                require(all(sha(p['text'].encode('utf-8')) == p['text_sha256'] for p in pages.values()), 'historical_page_hash_mismatch')
                pages_by_source[sid] = pages
            except (KeyError, IndexError, TypeError):
                raise LedgerError('historical_context_invalid') from None
    for scope in scopes.values():
        source = sources.get(scope['source_id'])
        require(source is not None and source['historical_text_binding'] is not None, 'scope_source_unbound')
        require(scope['artifact_sha256'] == source['historical_text_binding']['sha256'], 'scope_hash_mismatch')
        require(set(scope['pages']) <= set(pages_by_source[scope['source_id']]), 'scope_page_unbound')
    for ev in evidence.values():
        source = sources.get(ev['source_id'])
        require(source is not None, 'evidence_source_missing')
        require(ev['source_url'] == source['source_url'], 'evidence_source_url_mismatch')
        require(ev['supports_family_id'] == source['family_id'], 'cross_family_evidence')
        if ev['page'] is not None and source['total_pages_reported'] is not None:
            require(ev['page'] <= source['total_pages_reported'], 'page_out_of_range')
        if ev['binding_state'] == 'bound_historical_text':
            binding = source['historical_text_binding']
            require(binding is not None and ev['artifact_sha256'] == binding['sha256'], 'evidence_artifact_mismatch')
            page = pages_by_source[ev['source_id']].get(ev['page'])
            require(page is not None, 'evidence_page_unbound')
            require(0 <= ev['start'] < ev['end'] <= len(page['text']), 'span_out_of_range')
            require(page['text'][ev['start']:ev['end']] == ev['quote'], 'quote_span_mismatch')
    def check_field(field, family):
        refs = list(field['evidence_refs'])
        for alt in field['alternatives']:
            refs += alt['evidence_refs']
        require(all(ref in evidence for ref in refs), 'field_evidence_missing')
        require(all(evidence[ref]['supports_family_id'] == family for ref in refs), 'field_cross_family_evidence')
        if field['status'] == 'conflict':
            alternatives = [alt['value'] for alt in field['alternatives']]
            require(len(set(alternatives)) >= 2, 'conflict_requires_distinct_values')
        scope = field['inspection_scope_ref']
        require(scope is None or (scope in scopes and sources[scopes[scope]['source_id']]['family_id'] == family), 'field_scope_invalid')
        if field['status'] == 'not_mentioned':
            require(scope is not None and scopes[scope]['inspection_complete'], 'not_mentioned_requires_completed_scope')
    for source in sources.values():
        check_field(source['source_document_date'], source['family_id'])
        document_date = source['source_document_date']
        document_dates = [document_date['value']] if document_date['status']=='present' else [a['value'] for a in document_date['alternatives']]
        require(all(FormatChecker().conforms(value,'date') for value in document_dates), 'invalid_document_date')
        require(all('source_document_date' in evidence[r]['supports_fields'] for r in field_evidence_refs(source['source_document_date'])), 'document_date_support_mismatch')
    for event in events.values():
        require(event['affair_id'].startswith('CH:'), 'unqualified_affair_id')
        require(event['mode'] == event['payload']['type'], 'mode_payload_mismatch')
        refs = list(event['mode_evidence_refs'])
        require(all(r in evidence and event['mode'] in evidence[r]['supports_fields'] for r in refs), 'mode_support_mismatch')
        for name in ('actor', 'addressee', 'target'):
            require(all(r in evidence and name in evidence[r]['supports_fields'] for r in field_evidence_refs(event[name])), name + '_support_mismatch')
        if event['mode'] == 'decision':
            refs += event['payload']['scope_evidence_refs']
            require(all(r in evidence and 'scope' in evidence[r]['supports_fields'] for r in event['payload']['scope_evidence_refs']), 'scope_support_mismatch')
        require(all(ref in evidence and evidence[ref]['supports_family_id'] == event['family_id'] for ref in refs), 'mode_scope_evidence_invalid')
        for field in fields(event):
            check_field(field, event['family_id'])
        d = event['event_date']
        for value in ([d['value']] if d['status'] == 'present' else [a['value'] for a in d['alternatives']]):
            try:
                require(date.fromisoformat(value).isoformat() == value, 'invalid_event_date')
            except ValueError:
                raise LedgerError('invalid_event_date') from None
        date_refs = d['evidence_refs'] + [r for alt in d['alternatives'] for r in alt['evidence_refs']]
        require(all('event_date' in evidence[r]['supports_fields'] for r in date_refs), 'event_date_not_bound_as_event_date')
        def require_role(field, role):
            require(all(role in evidence[r]['supports_fields'] for r in field_evidence_refs(field)), role + '_support_mismatch')
        require_role(event['stage'], event['mode'])
        if event['mode']=='proposal':
            require_role(event['payload']['requested_action'],'proposal')
            require_role(event['payload']['draft_instrument'],'draft_instrument')
        elif event['mode']=='recommendation':
            require_role(event['payload']['recommended_action'],'recommendation')
        elif event['mode']=='other_reported_action':
            require_role(event['payload']['action'],'other_reported_action')
        if event['mode'] == 'decision':
            decision = event['payload']
            require_role(decision['disposition'],'decision')
            for clause in decision['financial_clauses']:
                require_role(clause,'financial_clauses')
            vote = decision['vote']
            if vote is not None:
                require_role(vote['voting_body'],'actor')
                require_role(vote['session_attendance'],'session_attendance')
                counts = []
                for key in ('yes', 'no', 'abstentions'):
                    field = vote[key]
                    require_role(field,'vote')
                    alternatives = [a['value'] for a in field['alternatives']]
                    require(all(re.fullmatch(r'(0|[1-9][0-9]{0,8})', value) is not None for value in alternatives), 'invalid_vote_count')
                    if field['status'] == 'present':
                        require(re.fullmatch(r'(0|[1-9][0-9]{0,8})', field['value']) is not None, 'invalid_vote_count')
                        counts.append(int(field['value']))
                if vote['denominator'] is not None:
                    require(len(counts) == 3 and vote['denominator'] == sum(counts), 'vote_denominator_mismatch')
    families = {s['family_id'] for s in sources.values()}
    require({(b['family_id'], b['baseline_type']) for b in bundle['baselines']} == {(f,t) for f in families for t in ('API','search','official_page','manual_PDF')}, 'baseline_denominator_mismatch')
    combinations = [(b['family_id'], b['baseline_type']) for b in bundle['baselines']]
    require(len(combinations) == len(set(combinations)), 'duplicate_baseline')
    for baseline in bundle['baselines']:
        require(all(s in sources and sources[s]['family_id'] == baseline['family_id'] for s in baseline['source_ids']), 'baseline_source_invalid')
        require(all(e in evidence and evidence[e]['supports_family_id'] == baseline['family_id'] for e in baseline['evidence_refs']), 'baseline_evidence_invalid')
        if baseline['retrieval_state'] != 'research_inspected':
            require(baseline['observation_state'] in ('unknown','not_assessed') and not baseline['facts'], 'uninspected_baseline_cannot_claim_facts_or_absence')
        if baseline['observation_state'] != 'recorded':
            require(not baseline['facts'], 'unrecorded_baseline_cannot_claim_facts')
        if baseline['observation_state'] == 'recorded':
            require(baseline['source_ids'] and all(evidence[e]['source_id'] in baseline['source_ids'] for e in baseline['evidence_refs']), 'recorded_baseline_source_binding_missing')
            require(baseline['evidence_refs'] and baseline['facts'], 'recorded_baseline_requires_evidence')
    return {'schema_and_structural_invariants':'pass','semantic_entailment':'pending_human_review',
            'original_source_bytes_verified':0,'coverage':'selected_historical_native_text_pages_and_research_locators_only_not_exhaustive','historical_text_artifacts_verified':len(pages_by_source),
            'bound_evidence_regions':sum(e['binding_state']=='bound_historical_text' for e in evidence.values()),
            'incomplete_evidence_regions':sum(e['binding_state']!='bound_historical_text' for e in evidence.values())}

def event_evidence_refs(event):
    refs = set(event['mode_evidence_refs'])
    if event['mode'] == 'decision':
        refs.update(event['payload']['scope_evidence_refs'])
    for field in fields(event):
        refs.update(field['evidence_refs'])
        for alternative in field['alternatives']:
            refs.update(alternative['evidence_refs'])
    return sorted(refs)

def query(bundle, family=None, scope=None, after=None):
    evidence = {e['evidence_id']:e for e in bundle['evidence']}
    rows, unresolved = [], []
    for event in bundle['events']:
        if family is not None and event['family_id'] != family:
            continue
        if scope is not None and (event['mode'] != 'decision' or event['payload']['scope'] != scope):
            continue
        problems = ['human_semantic_review_pending']
        refs = event_evidence_refs(event)
        provenance = 'bound_historical_text' if all(evidence[r]['binding_state']=='bound_historical_text' for r in refs) else 'incomplete_research_locator_only'
        if provenance != 'bound_historical_text':
            problems.append('provenance_incomplete')
        d = event['event_date']
        if d['status'] == 'conflict':
            problems.append('event_date_conflict')
        row = {'event_id':event['event_id'],'family_id':event['family_id'],'affair_id':event['affair_id'],
               'mode':event['mode'],'scope':event['payload'].get('scope'),
               'actor':event['actor'],'addressee':event['addressee'],'target':event['target'],
               'event_date':d,'payload':event['payload'],'evidence_refs':refs,
               'source_urls':sorted({evidence[r]['source_url'] for r in refs}),
               'provenance':provenance,'annotation_origin':event['annotation_origin'],
               'answer_eligible':False,'limitations':problems}
        if after is not None:
            if d['status'] != 'present':
                row['date_filter_state']='unresolved_not_silently_excluded'
                unresolved.append(row)
                continue
            if d['value'] < after:
                continue
        rows.append(row)
    return {'profile_id':PROFILE,'scope':'frozen_researcher_seen_document_bundle_only',
            'provisional_rows':rows,'unresolved_date_rows':unresolved,
            'human_verified_answer_rows':[], 'global_affair_status':None,
            'warning':'AI-prepared research annotations, not converter output or human gold. Quote binding is not entailment.'}

def gap_rows(bundle):
    result=[]
    families=sorted({s['family_id'] for s in bundle['sources']})
    for family in families:
        bs=[b for b in bundle['baselines'] if b['family_id']==family]
        recorded=[b['baseline_type'] for b in bs if b['observation_state']=='recorded']
        result.append({'family_id':family,'recorded_baselines':recorded,
          'baseline_API_coverage':'unknown','baseline_search_coverage':'unknown',
          'observed_structured_metadata_reuse':family=='H08',
          'document_semantics_available_to_researcher':bool([b for b in bs if b['baseline_type']=='manual_PDF' and b['observation_state']=='recorded']),
          'proposed_model_semantic_output':None,'demonstrated_API_gap':None,
          'model_incremental_correct_facts':None,'human_minutes_saved':None,
          'disposition':'baseline_metadata_already_available_for_recorded_fields' if family=='H08' else 'document_semantics_observed_API_comparison_unknown',
          'limits':'Provisional source interpretation; no live API field coverage, independent human review or model comparison.'})
    return result

def verify_freeze(root, protocol):
    require(isinstance(protocol,dict), 'protocol_object_required')
    expected={'protocol_id','profile_id','freeze_at_utc','source_cutoff_date','source_cutoff_at_utc','source_cutoff_note','families','selection','prior_exposure','human_gold_status','annotation_origin','planned_sources','planned_research_annotation_events','provider_calls_allowed','provider_tokens_allowed','source_downloads_allowed','package_installs_allowed','source_redistribution_allowed','old_schema_or_reference_edits_allowed','retrospective_credit_allowed','stop_condition','frozen_files','manifest_sha256'}
    require(set(protocol)==expected, 'protocol_keys_invalid')
    require(all(isinstance(protocol[k],str) and protocol[k].strip() for k in ('protocol_id','profile_id','freeze_at_utc','source_cutoff_date','source_cutoff_note','selection','prior_exposure','human_gold_status','annotation_origin','stop_condition')), 'protocol_strings_invalid')
    require(protocol['profile_id']==PROFILE and protocol['prior_exposure']=='all_researcher_seen' and protocol['annotation_origin']=='AI_prepared_research_annotation_unadjudicated', 'protocol_identity_invalid')
    require(FormatChecker().conforms(protocol['freeze_at_utc'],'date-time') and FormatChecker().conforms(protocol['source_cutoff_date'],'date'), 'protocol_dates_invalid')
    require(protocol['source_cutoff_at_utc'] is None, 'unsupported_exact_source_cutoff')
    require(all(type(protocol[k]) is int and protocol[k]==0 for k in ('provider_calls_allowed','provider_tokens_allowed','source_downloads_allowed','package_installs_allowed')), 'protocol_allowances_invalid')
    require(all(protocol[k] is False for k in ('source_redistribution_allowed','old_schema_or_reference_edits_allowed','retrospective_credit_allowed')), 'protocol_permissions_invalid')
    require(isinstance(protocol.get('manifest_sha256'),str), 'protocol_digest_required')
    require(isinstance(protocol.get('frozen_files'),dict) and bool(protocol['frozen_files']), 'protocol_file_map_required')
    require(isinstance(protocol.get('families'),list) and all(isinstance(f,str) for f in protocol['families']), 'protocol_families_required')
    require(all(isinstance(path,str) and isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) for path,digest in protocol['frozen_files'].items()), 'protocol_file_binding_invalid')
    require(all(type(protocol.get(k)) is int and protocol[k]>0 for k in ('planned_research_annotation_events','planned_sources')), 'protocol_denominators_required')
    body={k:v for k,v in protocol.items() if k!='manifest_sha256'}
    require(sha(canonical(body))==protocol['manifest_sha256'], 'manifest_identity_mismatch')
    for path,digest in protocol['frozen_files'].items():
        require(sha(read_bytes(root,path))==digest, 'frozen_input_changed')
    require(protocol['provider_calls_allowed']==0 and protocol['human_gold_status']=='not_started', 'protocol_claim_boundary_changed')

def validate_products(products, families):
    expected={'family_id','status','semantic_output','model','provider_calls','tokens','model_correctness','human_correctness','human_minutes','model_minutes','reason'}
    require(isinstance(products,list), 'product_list_required')
    for product in products:
        require(isinstance(product,dict) and set(product)==expected, 'product_keys_invalid')
        require(isinstance(product['family_id'],str) and isinstance(product['reason'],str) and product['reason'].strip(), 'product_strings_invalid')
        require(product['status']=='not_attempted' and all(type(product[k]) is int and product[k]==0 for k in ('provider_calls','tokens')), 'unexpected_product_attempt')
        require(all(product[k] is None for k in ('semantic_output','model','model_correctness','human_correctness','human_minutes','model_minutes')), 'unmeasured_product_claim')
    require(sorted(p['family_id'] for p in products)==sorted(families), 'product_denominator_mismatch')

def run(repo_root, packet_root=ROOT, family=None, scope=None, after=None):
    protocol=read_json(packet_root,'protocol.json')
    verify_freeze(packet_root,protocol)
    bundle=load_bundle(packet_root)
    observed=sorted({s['family_id'] for s in bundle['sources']})
    require(observed==sorted(protocol['families']), 'family_denominator_changed')
    products=read_jsonl(packet_root,'data/product_runs.jsonl')
    validate_products(products,observed)
    checks=validate(bundle,repo_root,read_json(packet_root,'schemas/ledger.schema.json'))
    require(len(bundle['events'])==protocol['planned_research_annotation_events'], 'annotation_denominator_changed')
    require(len(bundle['sources'])==protocol['planned_sources'], 'source_denominator_changed')
    return {'manifest_sha256':protocol['manifest_sha256'],'validation':checks,
       'query':query(bundle,family,scope,after),'event_gap_ledger':gap_rows(bundle),
       'metrics':{'planned_families':len(observed),'planned_sources':len(bundle['sources']),
         'local_historical_text_sources_acquired':checks['historical_text_artifacts_verified'],
         'original_source_files_acquired_in_experiment':0,'planned_annotation_events':len(bundle['events']),
         'schema_admitted_provisional_events':len(bundle['events']),
         'model_attempted_families':0,'model_completed_families':0,'model_assessed_families':0,
         'model_output':None,'model_accuracy':None,'human_accuracy':None,'human_effort_minutes':None,
         'model_effort_minutes':None,'human_reviewed_events':0,'answer_eligible_events':0,
         'provisional_event_modes':dict(sorted(Counter(e['mode'] for e in bundle['events']).items())),
         'provisional_event_date_conflicts':sum(e['event_date']['status']=='conflict' for e in bundle['events']),
         'provider_calls':0,'provider_tokens':0,'infrastructure_cost':None}}

def report(result):
    m=result['metrics']; v=result['validation']
    lines=['# Offline parliamentary evidence-gap ledger','',
      'Development diagnostic only. Every annotation is AI-prepared and unadjudicated; none is converter output or human gold.', '',
      f"{m['planned_families']} exposed families; {m['planned_sources']} source records; {m['planned_annotation_events']} provisional event records.",
      f"Structural checks passed. {v['historical_text_artifacts_verified']} historical text artifacts bound; {v['bound_evidence_regions']} exact text regions bound; {v['incomplete_evidence_regions']} locator-only regions remain incomplete.",
      'Original PDFs were not downloaded, parsed or redistributed. Historical request text covers selected pages only; the event inventory is partial. Matching quotes/hashes do not establish semantic entailment.', '',
      '## Findings','',
      '- H03 preserves contradictory chamber-adoption years separately from committee recommendations.',
      '- H04 retains draft/proposal language without a substantive decision payload.',
      '- H08 has an existing official-page baseline; recorded metadata are not newly unlocked by conversion.',
      '- Geneva M3068 has separate agenda-inclusion and referral decisions; neither answers substantive adoption.',
      '- Lugano 12150 keeps the recorded credit decision and 52–0–0 vote separate from maximum session attendance 56. Exact spending amounts/clauses remain unavailable; four-year expiry is a research-note observation only.', '',
      'All five API and search coverage comparisons remain unknown or unassessed. No measured API deficit, model-added fact or user time saving is established.', '',
      '## Gates and limits','',
      'Human/model correctness and time metrics remain null. Human-verified answer-eligible rows: 0. New provider calls/tokens: 0. Infrastructure cost: unmeasured.',
      'This utility validates representation and evidence-binding invariants. It cannot decide whether the evidence entails the annotation, resolve ambiguous legal stages, or catch every false adoption. An explicit adversarial test preserves this limit: a semantically wrong annotation with structurally consistent declared support still passes structural validation and remains answer-ineligible.',
      'Historical 2A schemas, requests, references and failure receipts are unchanged. This packet grants no retrospective credit.', '',
      '## Next evidence needed','',
      'Inspect permitted API/search responses with endpoint/cutoff/pagination receipts, materialize rights-appropriate source bytes, obtain independent language/domain review, and freeze genuinely unseen affair families before a model or utility comparison.','']
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root',required=True,type=Path)
    parser.add_argument('--format',choices=['json','report'],default='json')
    parser.add_argument('--family')
    parser.add_argument('--decision-scope',choices=['agenda_inclusion','referral','substantive_affair','credit_authorization','administrative_step','other'])
    parser.add_argument('--after')
    args=parser.parse_args()
    try:
        if args.after:
            require(date.fromisoformat(args.after).isoformat()==args.after,'invalid_after_date')
        result=run(args.repo_root,family=args.family,scope=args.decision_scope,after=args.after)
        print(report(result) if args.format=='report' else canonical(result).decode())
        return 0
    except (LedgerError,ValueError) as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,LedgerError) else 'invalid_date'}),file=sys.stderr)
        return 2
if __name__=='__main__':
    raise SystemExit(main())
