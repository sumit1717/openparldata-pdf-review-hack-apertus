"""Authored engineering controls only; no independent semantic/human reference."""
import copy
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from track_2a_comparison import worksheet as w
REPO = Path(os.environ['WORKSHEET_REPO_ROOT'])
p, g = w.dependencies(REPO)
from track_2a_converter.tests.fixtures import pdf_bytes, response, unassessed


def digest_tree(root):
    return {str(f.relative_to(root)): p.sha(f.read_bytes()) for f in sorted(root.rglob('*')) if f.is_file()}


def pin_again(directory):
    """Authored adversarial manifest; does not imply authenticity."""
    path = directory / 'result.json'
    manifest = p.strict_load(path.read_bytes())
    manifest['files'] = {str(f.relative_to(directory)): {'sha256': p.sha(f.read_bytes()), 'bytes': f.stat().st_size}
                         for f in sorted(directory.rglob('*')) if f.is_file() and f != path}
    manifest['result_sha256'] = p.sha(p.canonical({k: v for k, v in manifest.items() if k != 'result_sha256'}))
    path.write_bytes(p.canonical(manifest))
    return manifest['result_sha256']


class Links(HTMLParser):
    def __init__(self):
        super().__init__(); self.links = []; self.tags = []; self.attrs = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag); self.attrs += attrs
        self.links += [v for k, v in attrs if k in ('href', 'src')]


class WorksheetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='worksheet-authored-tests-')
        cls.root = Path(cls.temp.name)
        cls.packet = cls.make_packet(cls.root / 'packet')
        cls.empty = cls.make_packet(cls.root / 'empty', blank=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    @classmethod
    def make_packet(cls, root, blank=False):
        root.mkdir()
        text = ('Clerk authored the report. Committee recommends rejection. '
                'Chamber placed the proposal on its agenda. REPEATED QUOTE. REPEATED QUOTE. '
                '<script>alert(1)</script> Annex B is not included.')
        pdf = root / 'owned-fixture.pdf'
        pages = ['', ''] if blank else [text, '', 'A malformed response for this page.', 'Not attempted.', 'A declared failed attempt.', 'No candidate in a valid response.']
        pdf.write_bytes(pdf_bytes(pages))
        prep = p.prepare(pdf, root / 'prepared')
        bundle = p.strict_load((root / 'prepared/bundle.json').read_bytes())
        requests = [p.strict_load((root / 'prepared' / s['path']).read_bytes()) for s in bundle['requests']]
        captures = root / 'captures'; captures.mkdir()
        entries = []
        for number, request in enumerate(requests):
            if number == 2:
                continue
            if number == 3:
                entries.append({'request_id': request['request_id'], 'status': 'failed', 'error_code': 'authored_failure'})
                continue
            name = f'{number}.json'
            if number == 0:
                authored = response(request, request['source_text'][:10])
                event = authored['events'][0]
                def located(value, quote, start=None):
                    start = request['source_text'].index(quote) if start is None else start
                    loc = {'page': 1, 'start': start, 'end': start + len(quote), 'quote': quote}
                    return {'state': 'present', 'value': value, 'evidence': [loc], 'alternatives': [], 'reviewed_scope': None, 'reason': ''}
                event['author'] = located('Clerk', 'Clerk authored the report.')
                event['actor'] = located('Committee', 'Committee recommends rejection.')
                event['addressee'] = located('Chamber', 'Chamber placed the proposal on its agenda.')
                event['event'] = located('recommendation', 'Committee recommends rejection.')
                event['outcome'] = located('rejection recommended; no substantive adoption evidenced in this chunk', 'Committee recommends rejection.')
                # A wrong actor with a real quote remains structurally valid and ineligible.
                wrong = copy.deepcopy(event); wrong['candidate_id'] = 'wrong-actor-control'
                wrong['actor']['value'] = 'Invented assembly'
                wrong['event']['value'] = '<img src="https://evil.invalid/?private=data" onerror="alert(1)">'
                quote = 'REPEATED QUOTE.'; second = request['source_text'].rindex(quote)
                wrong['anchors'] = [{'page': 1, 'start': second, 'end': second + len(quote), 'quote': quote}]
                conflict = copy.deepcopy(event); conflict['candidate_id'] = 'conflicting-outcome'
                conflict['outcome'] = {'state': 'conflicting', 'value': None, 'evidence': [], 'reviewed_scope': None, 'reason': 'Authored competing interpretation control.',
                                       'alternatives': [{'state': 'present', 'value': v, 'evidence': event['outcome']['evidence']} for v in ('proposal only', 'agenda decision only')]}
                authored['events'] += [wrong, conflict]
                raw = p.canonical(authored)
            elif number == 1:
                raw = b'{"events": malformed original'
            else:
                raw = p.canonical(response(request))
            (captures / name).write_bytes(raw)
            entries.append({'request_id': request['request_id'], 'status': 'captured', 'response_path': name})
        index = {'profile': p.PROFILE, 'prepare_result_sha256': prep['result_sha256'], 'entries': entries}
        (captures / 'index.json').write_bytes(p.canonical(index))
        imported = p.import_captures(root / 'prepared', captures / 'index.json', root / 'imported', prep['result_sha256'])
        review = p.export_review(root / 'prepared', root / 'imported', root / 'review', imported['result_sha256'])
        return {'selection_id': root.name, 'label': 'Owned authored fixture <script>unsafe</script>',
                'prepared_directory': str(root / 'prepared'), 'imported_directory': str(root / 'imported'),
                'review_directory': str(root / 'review'), 'expected_prepare_sha256': prep['result_sha256'],
                'expected_import_sha256': imported['result_sha256'], 'expected_review_sha256': review['result_sha256']}

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(dir=self.root, prefix='case-'))

    def manifest(self, packets=None, gap=None):
        value = {'profile': w.SELECTION_PROFILE, 'converter_packets': packets if packets is not None else [self.packet], 'frozen_gap_ledger': gap}
        path = self.work / 'selection.json'; path.write_bytes(p.canonical(value)); return path

    def gap(self, families=None):
        root = REPO / 'track_2a_gap_ledger'
        protocol = g.read_json(root, 'protocol.json')
        return {'packet_directory': str(root), 'expected_manifest_sha256': protocol['manifest_sha256'],
                'families': families or ['H03', 'H04', 'H08', 'GenevaM3068', 'Lugano12150']}

    def produce(self, packets=None, gap=None):
        path = self.manifest(packets, gap)
        receipt = w.generate(path, REPO, self.work / 'out')
        result = p.strict_load((self.work / 'out/worksheet.json').read_bytes())
        return receipt, result

    def cloned(self):
        destination = self.work / 'cloned'; shutil.copytree(Path(self.packet['prepared_directory']).parent, destination)
        packet = copy.deepcopy(self.packet)
        for key, name in [('prepared_directory', 'prepared'), ('imported_directory', 'imported'), ('review_directory', 'review')]:
            packet[key] = str(destination / name)
        return packet, destination

    def test_source_preserved_and_no_network_or_provider(self):
        before = digest_tree(Path(self.packet['prepared_directory']).parent)
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            receipt, result = self.produce()
        self.assertEqual(before, digest_tree(Path(self.packet['prepared_directory']).parent))
        self.assertEqual(result['provider_calls'], 0)
        self.assertFalse(receipt['payload']['answer_eligible'])
        copied = self.work / 'out/packets/packet'
        p.verify_result(copied, 'review', self.packet['expected_review_sha256'])

    def test_roles_outcomes_conflicts_and_wrong_actor_stay_separate(self):
        _, result = self.produce()
        candidate = next(r for r in result['rows'] if r['identity'].get('candidate_id') == 'synthetic-1')
        self.assertEqual(candidate['document_author']['value'], 'Clerk')
        self.assertEqual(candidate['actor']['value'], 'Committee')
        self.assertEqual(candidate['addressee']['value'], 'Chamber')
        wrong = next(r for r in result['rows'] if r['identity'].get('candidate_id') == 'wrong-actor-control')
        self.assertEqual(wrong['actor']['value'], 'Invented assembly')
        self.assertFalse(wrong['answer_eligible'])
        conflict = next(r for r in result['rows'] if r['identity'].get('candidate_id') == 'conflicting-outcome')
        self.assertEqual(len(conflict['outcome']['alternatives']), 2)
        self.assertTrue(all(r['manual_review']['status'] == 'not_started' and r['manual_review']['proposed_mappings'] == [] for r in result['rows']))

    def test_repeated_phrase_exact_second_offset_retained(self):
        _, result = self.produce()
        row = next(r for r in result['rows'] if r['identity'].get('candidate_id') == 'wrong-actor-control')
        page = p.strict_load((Path(self.packet['review_directory']) / 'review-queue.json').read_bytes())['pages'][0]
        self.assertEqual(row['provenance'][0]['start'], page['text'].rindex('REPEATED QUOTE.'))
        self.assertNotEqual(row['provenance'][0]['start'], page['text'].index('REPEATED QUOTE.'))

    def test_partial_negative_and_malformed_capture_denominators(self):
        _, result = self.produce()
        coverage = result['coverage']
        self.assertEqual(coverage['converter_requests'], {'planned': 5, 'attempted': 4, 'unattempted': 1, 'structurally_valid': 2, 'rejected': 1, 'failed': 1})
        self.assertEqual(coverage['converter_page_inventory'], 6)
        self.assertEqual(coverage['row_kinds']['unresolved_coverage'], 5)
        self.assertIsNone(coverage['semantic_or_whole_document_coverage'])
        states = {r['source_context']['request_status'] for r in result['rows']}
        self.assertTrue({'no_request', 'unattempted', 'attempt_failed', 'rejected_capture'} <= states)

    def test_zero_text_packet_does_not_claim_no_events(self):
        _, result = self.produce([self.empty])
        self.assertEqual(result['coverage']['converter_requests']['planned'], 0)
        self.assertEqual(len(result['rows']), 2)
        self.assertEqual(result['coverage']['converter_page_statuses']['no_text_unresolved'], 2)
        self.assertFalse(result['answer_eligible'])
        self.assertIn('never evidence of no relevant event', result['rows'][0]['source_context']['coverage_note'])

    def test_xss_and_remote_links_are_inert(self):
        self.produce()
        raw = (self.work / 'out/worksheet.html').read_text()
        parser = Links(); parser.feed(raw)
        self.assertFalse(set(parser.tags) & {'script', 'img', 'iframe', 'object', 'embed', 'form'})
        self.assertFalse(any(k.startswith('on') for k, v in parser.attrs))
        self.assertTrue(all(not link.startswith(('http:', 'https:', 'javascript:', 'data:', 'file:')) for link in parser.links))
        self.assertIn('&lt;img', raw)
        self.assertIn('default-src', raw)

    def test_stable_order_with_reordered_packet_selection(self):
        selected, _ = w.selection(self.manifest([self.empty, self.packet]), p)
        a, _ = w.build(selected, REPO, p, g)
        selected, _ = w.selection(self.manifest([self.packet, self.empty]), p)
        b, _ = w.build(selected, REPO, p, g)
        self.assertEqual(p.canonical(a), p.canonical(b))
        self.assertEqual(w.render(a), w.render(b))

    def test_same_source_selected_twice_keeps_distinct_identity(self):
        packet, _ = self.cloned(); packet['selection_id'] = 'second_selection'
        _, result = self.produce([self.packet, packet])
        rows = [r for r in result['rows'] if r['identity'].get('candidate_id') == 'synthetic-1']
        self.assertEqual(len(rows), 2)
        self.assertEqual(len({r['row_id'] for r in rows}), 2)

    def test_tampered_packet_rejected_before_output(self):
        packet, root = self.cloned()
        (root / 'review/source.pdf').write_bytes(b'tampered')
        with self.assertRaises(p.PipelineError):
            w.generate(self.manifest([packet]), REPO, self.work / 'out')
        self.assertFalse((self.work / 'out').exists())

    def test_rehashed_review_with_promoted_claim_rejected(self):
        packet, root = self.cloned()
        path = root / 'review/review-queue.json'; queue = p.strict_load(path.read_bytes())
        queue['answer_eligible'] = True; path.write_bytes(p.canonical(queue))
        packet['expected_review_sha256'] = pin_again(root / 'review')
        with self.assertRaisesRegex(p.PipelineError, 'review_regeneration_mismatch'):
            w.generate(self.manifest([packet]), REPO, self.work / 'out')
        self.assertFalse((self.work / 'out').exists())

    def test_rehashed_import_cannot_hide_captured_candidates_as_unattempted(self):
        packet, root = self.cloned()
        path = root / 'imported/import-ledger.json'; ledger = p.strict_load(path.read_bytes())
        unit = next(u for u in ledger['units'] if u['candidates'])
        unit.update(status='unattempted', attempted=False, candidates=[], capture_record=None, error=None)
        ledger['denominators']['attempted'] -= 1
        ledger['denominators']['unattempted'] += 1
        ledger['denominators']['structurally_valid'] -= 1
        path.write_bytes(p.canonical(ledger))
        path = root / 'imported/result.json'; receipt = p.strict_load(path.read_bytes())
        receipt['payload']['ledger_sha256'] = p.sha(p.canonical(ledger))
        receipt['payload']['denominators'] = ledger['denominators']
        path.write_bytes(p.canonical(receipt))
        packet['expected_import_sha256'] = pin_again(root / 'imported')
        review = p.export_review(root / 'prepared', root / 'imported', root / 'forged-review', packet['expected_import_sha256'])
        packet['review_directory'] = str(root / 'forged-review')
        packet['expected_review_sha256'] = review['result_sha256']
        with self.assertRaisesRegex(p.PipelineError, 'import_classification_replay_mismatch'):
            w.generate(self.manifest([packet]), REPO, self.work / 'out')
        self.assertFalse((self.work / 'out').exists())

    def test_missing_packet_file_rejected(self):
        packet, root = self.cloned(); (root / 'review/source.pdf').unlink()
        with self.assertRaises(p.PipelineError):
            w.generate(self.manifest([packet]), REPO, self.work / 'out')

    def test_missing_or_wrong_pin_rejected(self):
        for pin in ('', '0' * 64):
            packet = copy.deepcopy(self.packet); packet['expected_review_sha256'] = pin
            with self.assertRaises(p.PipelineError):
                w.generate(self.manifest([packet]), REPO, self.work / ('out-' + str(len(pin))))

    def test_malformed_selection_duplicate_keys_nonfinite_unknown_properties(self):
        for number, raw in enumerate((b'{"profile":1,"profile":2}', b'{"x":NaN}', b'{', p.canonical({'profile': w.SELECTION_PROFILE, 'converter_packets': [], 'frozen_gap_ledger': None, 'extra': True}))):
            path = self.work / f'bad-{number}.json'; path.write_bytes(raw)
            with self.assertRaises(p.PipelineError):
                w.generate(path, REPO, self.work / f'out-{number}')
            self.assertFalse((self.work / f'out-{number}').exists())

    def test_unsupported_converter_version_rejected(self):
        packet, root = self.cloned()
        path = root / 'prepared/bundle.json'; bundle = p.strict_load(path.read_bytes())
        bundle['extractor']['converter_version'] = '0.1.0'; path.write_bytes(p.canonical(bundle))
        path = root / 'prepared/result.json'; result = p.strict_load(path.read_bytes())
        result['payload']['bundle_sha256'] = p.sha(p.canonical(bundle)); path.write_bytes(p.canonical(result))
        packet['expected_prepare_sha256'] = pin_again(root / 'prepared')
        with self.assertRaisesRegex(p.PipelineError, 'extraction_policy_mismatch'):
            w.generate(self.manifest([packet]), REPO, self.work / 'out')

    def test_invalid_preparation_bounds_rejected_before_reconstruction(self):
        packet, root = self.cloned()
        path = root / 'prepared/bundle.json'; bundle = p.strict_load(path.read_bytes())
        bundle['chunk_chars'] = -4000; path.write_bytes(p.canonical(bundle))
        with self.assertRaisesRegex(p.PipelineError, 'chunk_size_limit'):
            w.generate(self.manifest([packet]), REPO, self.work / 'out')

    def test_missing_capture_bytes_keep_declared_rejection_visible(self):
        root = self.work / 'missing-capture'; root.mkdir()
        prepared = self.packet['prepared_directory']
        bundle = p.strict_load((Path(prepared) / 'bundle.json').read_bytes())
        rid = bundle['requests'][0]['request_id']
        index = {'profile': p.PROFILE, 'prepare_result_sha256': self.packet['expected_prepare_sha256'],
                 'entries': [{'request_id': rid, 'status': 'captured', 'response_path': 'never-supplied.json'}]}
        (root / 'index.json').write_bytes(p.canonical(index))
        imported = p.import_captures(prepared, root / 'index.json', root / 'imported', self.packet['expected_prepare_sha256'])
        review = p.export_review(prepared, root / 'imported', root / 'review', imported['result_sha256'])
        packet = copy.deepcopy(self.packet)
        packet.update(imported_directory=str(root / 'imported'), review_directory=str(root / 'review'),
                      expected_import_sha256=imported['result_sha256'], expected_review_sha256=review['result_sha256'])
        _, result = self.produce([packet])
        row = next(r for r in result['rows'] if r['identity']['request_id'] == rid)
        self.assertEqual(row['source_context']['request_status'], 'rejected_capture')
        self.assertEqual(row['source_context']['request_error'], 'required_file_unavailable')
        self.assertEqual(result['coverage']['converter_requests']['attempted'], 1)

    def test_duplicate_capture_index_retained_without_winner(self):
        root = self.work / 'duplicate-capture'; root.mkdir()
        prepared = self.packet['prepared_directory']
        original_index = p.strict_load((Path(self.packet['imported_directory']) / 'original-index.json').read_bytes())
        raw = (Path(self.packet['imported_directory']) / 'original-captures/0000.bin').read_bytes()
        (root / 'original.json').write_bytes(raw)
        entry = {'request_id': original_index['entries'][0]['request_id'], 'status': 'captured', 'response_path': 'original.json'}
        (root / 'index.json').write_bytes(p.canonical({'profile': p.PROFILE, 'prepare_result_sha256': self.packet['expected_prepare_sha256'], 'entries': [entry, entry]}))
        imported = p.import_captures(prepared, root / 'index.json', root / 'imported', self.packet['expected_prepare_sha256'])
        review = p.export_review(prepared, root / 'imported', root / 'review', imported['result_sha256'])
        packet = copy.deepcopy(self.packet)
        packet.update(imported_directory=str(root / 'imported'), review_directory=str(root / 'review'),
                      expected_import_sha256=imported['result_sha256'], expected_review_sha256=review['result_sha256'])
        _, result = self.produce([packet])
        row = next(r for r in result['rows'] if r['identity']['request_id'] == entry['request_id'])
        self.assertEqual(row['source_context']['request_error'], 'duplicate_capture_request')
        self.assertIsNone(row['original_candidate'])
        self.assertEqual(len(result['documents'][0]['rejected_capture_records']), 2)

    def test_output_alias_existing_directory_and_symlink_rejected(self):
        manifest = self.manifest()
        with self.assertRaisesRegex(p.PipelineError, 'output_input_alias'):
            w.generate(manifest, REPO, Path(self.packet['review_directory']) / 'new')
        (self.work / 'out').mkdir()
        with self.assertRaisesRegex(p.PipelineError, 'fresh_output_directory_required'):
            w.generate(manifest, REPO, self.work / 'out')
        link = self.work / 'link'; link.symlink_to(self.packet['review_directory'], target_is_directory=True)
        packet = copy.deepcopy(self.packet); packet['review_directory'] = str(link)
        with self.assertRaisesRegex(p.PipelineError, 'symlink_rejected'):
            w.generate(self.manifest([packet]), REPO, self.work / 'unused')

    def test_real_frozen_ledger_dates_baselines_uninspected_annexes(self):
        _, result = self.produce([], self.gap())
        self.assertEqual(len(result['rows']), 9)
        h03 = next(r for r in result['rows'] if r['identity']['event_id'] == 'H03-chamber-adoption')
        self.assertEqual(h03['event_date']['status'], 'conflict')
        self.assertEqual({a['value'] for a in h03['event_date']['alternatives']}, {'2024-06-14', '2025-06-14'})
        self.assertEqual(h03['document_dates'][0]['field']['value'], '2025-03-25')
        geneva = [r for r in result['rows'] if r['identity']['family_id'] == 'GenevaM3068']
        self.assertNotIn('substantive_affair', {r['source_context']['provisional_decision_scope'] for r in geneva})
        self.assertTrue(any(e['binding_state'] != 'bound_historical_text' for r in geneva for e in r['provenance']))
        self.assertEqual(result['coverage']['API_field_coverage'], 'unknown')
        self.assertTrue(all(not r['answer_eligible'] for r in result['rows']))
        self.assertIn('not_inspected', json.dumps(result))
        h08 = next(d for d in result['documents'] if d['label'] == 'H08')
        self.assertEqual(h08['baseline_gap']['disposition'], 'baseline_metadata_already_available_for_recorded_fields')

    def test_unknown_family_and_tampered_ledger_failclosed(self):
        with self.assertRaisesRegex(p.PipelineError, 'selected_family_unavailable'):
            w.generate(self.manifest([], self.gap(['missing-family'])), REPO, self.work / 'out')
        root = self.work / 'ledger'; shutil.copytree(REPO / 'track_2a_gap_ledger', root)
        with (root / 'data/annotations.jsonl').open('ab') as handle:
            handle.write(b'\n')
        gap = self.gap(); gap['packet_directory'] = str(root)
        with self.assertRaisesRegex(g.LedgerError, 'frozen_input_changed'):
            w.generate(self.manifest([], gap), REPO, self.work / 'out')


if __name__ == '__main__':
    unittest.main()
