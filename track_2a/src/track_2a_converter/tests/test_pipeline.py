"""Engineering conformance only. Synthetic inputs are not human/model evaluation."""
import copy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from track_2a_converter import pipeline as p
from fixtures import pdf_bytes, response, unassessed


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pdf = self.root / 'new-unseen-name.pdf'
        self.pdf.write_bytes(pdf_bytes(['The council proposed a bridge. ' * 20, '', 'The committee postponed discussion.']))
        self.socket = patch.object(socket, 'socket', side_effect=AssertionError('network forbidden'))
        self.socket.start()
        self.addCleanup(self.socket.stop)
        self.addCleanup(self.tmp.cleanup)
        self.prepared = self.root / 'prepared'
        self.result = p.prepare(self.pdf, self.prepared, chunk_chars=256)
        self.bundle = p.strict_load((self.prepared / 'bundle.json').read_bytes())
        self.requests = [p.strict_load((self.prepared / spec['path']).read_bytes()) for spec in self.bundle['requests']]
        self.captures = self.root / 'captures'; self.captures.mkdir()

    def index(self, entries, **extra):
        path = self.captures / 'index.json'
        path.write_bytes(p.canonical({'profile': p.PROFILE, 'prepare_result_sha256': self.result['result_sha256'], 'entries': entries, **extra}))
        return path

    def capture(self, req=None, body=None, name='response.json'):
        req = req or self.requests[0]
        body = response(req, req['source_text'][:20]) if body is None else body
        (self.captures / name).write_bytes(body if isinstance(body, bytes) else p.canonical(body))
        return {'request_id': req['request_id'], 'status': 'captured', 'response_path': name}

    def do_import(self, entries):
        out = self.root / 'imported'
        result = p.import_captures(self.prepared, self.index(entries), out, self.result['result_sha256'])
        ledger = p.strict_load((out / 'import-ledger.json').read_bytes())
        return out, result, ledger

    def test_generic_prepare_deterministic_and_all_pages_explicit(self):
        second = self.root / 'second'
        result = p.prepare(self.pdf, second, 256)
        self.assertEqual((self.prepared / 'bundle.json').read_bytes(), (second / 'bundle.json').read_bytes())
        self.assertNotEqual(self.result['invocation_id'], result['invocation_id'])
        self.assertEqual([p['status'] for p in self.bundle['pages']], ['text_extracted', 'no_text_unresolved', 'text_extracted'])
        self.assertEqual(self.bundle['source_sha256'], p.sha(self.pdf.read_bytes()))
        self.assertTrue(all(len(r['source_text']) <= 256 for r in self.requests))
        self.assertTrue(all(page['ocr_status'] == 'not_attempted' for page in self.bundle['pages']))
        for page in self.bundle['pages']:
            chunks = [r['source_text'] for r in self.requests if r['reviewed_scope']['page'] == page['page']]
            self.assertEqual(''.join(chunks), page['text'])

    def test_prepare_import_review_source_first_integration(self):
        entries = [self.capture(), {'request_id': self.requests[1]['request_id'], 'status': 'failed', 'error_code': 'offline_capture_failed'}]
        imported, result, ledger = self.do_import(entries)
        reviewed = self.root / 'reviewed'
        r = p.export_review(self.prepared, imported, reviewed, result['result_sha256'])
        p.verify_result(reviewed, 'review', r['result_sha256'])
        queue = p.strict_load((reviewed / 'review-queue.json').read_bytes())
        self.assertEqual(len(queue['pages']), 3)
        self.assertEqual(queue['denominators']['planned'], len(self.requests))
        self.assertEqual(queue['denominators']['attempted'], 2)
        self.assertEqual(queue['denominators']['failed'], 1)
        self.assertEqual(queue['denominators']['unattempted'], len(self.requests) - 2)
        self.assertFalse(queue['answer_eligible']); self.assertFalse(queue['human_reference'])
        candidate = queue['pages'][0]['requests'][0]['candidates'][0]
        self.assertEqual(candidate['adjudication'], 'unadjudicated'); self.assertFalse(candidate['answer_eligible'])
        self.assertEqual((reviewed / 'source.pdf').read_bytes(), self.pdf.read_bytes())
        self.assertEqual((reviewed / 'original-captures/0000.bin').read_bytes(), (self.captures / 'response.json').read_bytes())
        self.assertIn('Source text first', (reviewed / 'review.html').read_text())

    def test_malformed_original_preserved_and_denominator_retained(self):
        raw = b'{"request_id":"x","request_id":"y"} trailing'
        out, result, ledger = self.do_import([self.capture(body=raw)])
        self.assertEqual((out / 'original-captures/0000.bin').read_bytes(), raw)
        self.assertEqual(ledger['denominators']['attempted'], 1)
        self.assertEqual(ledger['denominators']['rejected'], 1)
        self.assertEqual(ledger['denominators']['structurally_valid'], 0)

    def test_strict_json_boundaries(self):
        for raw in (b'{"x":1,"x":2}', b'{}[]', b'{"x":NaN}', b'{"x":1e999}', b'"\\ud800"', b'\xef\xbb\xbf{}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaises(p.PipelineError):
                p.strict_load(raw)

    def test_malformed_index_retained_no_complete_result(self):
        index = self.captures / 'index.json'; index.write_bytes(b'{"entries":[],"entries":[]}')
        out = self.root / 'bad-index'
        with self.assertRaises(p.PipelineError):
            p.import_captures(self.prepared, index, out, self.result['result_sha256'])
        self.assertEqual((out / 'original-index.json').read_bytes(), index.read_bytes())
        self.assertFalse((out / 'result.json').exists()); self.assertTrue((out / 'failure.json').exists())

    def test_binding_and_unknown_location_rejection(self):
        cases = []
        base = response(self.requests[0], self.requests[0]['source_text'][:20])
        wrong = copy.deepcopy(base); wrong['binding']['source_sha256'] = 'a' * 64; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['binding']['schema_sha256'] = 'a' * 64; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['binding']['prompt_sha256'] = 'a' * 64; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['request_id'] = self.requests[1]['request_id']; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['events'][0]['anchors'][0]['page'] = 999; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['events'][0]['anchors'][0]['start'] += 1; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['events'][0]['adjudication'] = 'HUMAN'; cases.append(wrong)
        wrong = copy.deepcopy(base); wrong['reviewer_kind'] = 'HUMAN'; cases.append(wrong)
        schema = p.strict_load((self.prepared / 'response.schema.json').read_bytes())
        for value in cases:
            with self.subTest(value=value), self.assertRaises(p.PipelineError):
                p.validate_candidate(value, self.requests[0], self.bundle, schema)

    def test_typed_missingness_and_conflicts(self):
        req = self.requests[0]; value = response(req, req['source_text'][:20]); event = value['events'][0]
        loc = event['anchors'][0]
        event['author'] = {'state': 'not_stated_within_reviewed_scope', 'value': None, 'evidence': [], 'alternatives': [], 'reviewed_scope': req['reviewed_scope'], 'reason': 'Synthetic scoped missingness example only.'}
        event['actor'] = {'state': 'explicit_absence', 'value': None, 'evidence': [loc], 'alternatives': [], 'reviewed_scope': None, 'reason': 'Synthetic schema-only example; no truth claim.'}
        event['outcome'] = {'state': 'conflicting', 'value': None, 'evidence': [], 'alternatives': [{'state': 'present', 'value': 'proposed', 'evidence': [loc]}, {'state': 'explicit_absence', 'value': None, 'evidence': [loc]}], 'reviewed_scope': None, 'reason': 'Synthetic conflicting alternatives.'}
        schema = p.strict_load((self.prepared / 'response.schema.json').read_bytes())
        p.validate_candidate(value, req, self.bundle, schema)
        event['author']['reviewed_scope'] = None
        with self.assertRaises(p.PipelineError): p.validate_candidate(value, req, self.bundle, schema)

    def test_duplicate_and_unknown_capture_entries_retained(self):
        entry = self.capture()
        unknown = self.capture(body=b'{}', name='unknown.json'); unknown['request_id'] = 'a' * 64
        out, result, ledger = self.do_import([entry, copy.deepcopy(entry), unknown])
        self.assertEqual(len(ledger['capture_records']), 3)
        self.assertEqual(ledger['denominators']['attempted'], 1)
        self.assertEqual(ledger['denominators']['planned'], len(self.requests))
        self.assertEqual(ledger['denominators']['structurally_valid'], 0)
        self.assertEqual(len(list((out / 'original-captures').iterdir())), 3)

    def test_status_contradiction_does_not_hide_attempt(self):
        entry = self.capture(); entry['status'] = 'unattempted'
        _, _, ledger = self.do_import([entry])
        self.assertEqual(ledger['denominators']['structurally_valid'], 0)
        self.assertEqual(ledger['units'][0]['status'], 'rejected_capture')

    def test_failure_and_missing_capture_count_attempted(self):
        entry = {'request_id': self.requests[0]['request_id'], 'status': 'captured', 'response_path': 'missing.json'}
        _, _, ledger = self.do_import([entry])
        self.assertEqual(ledger['denominators']['attempted'], 1)
        self.assertEqual(ledger['denominators']['unattempted'], len(self.requests) - 1)
        self.assertEqual(ledger['units'][0]['status'], 'rejected_capture')

    def test_reuse_output_and_stale_pins_rejected(self):
        with self.assertRaises(p.PipelineError): p.prepare(self.pdf, self.prepared)
        with self.assertRaises(p.PipelineError): p.load_prepared(self.prepared, 'a' * 64)
        index = self.index([])
        with self.assertRaises(p.PipelineError): p.import_captures(self.prepared, index, self.root / 'bad', 'a' * 64)

    def test_tampered_prepared_and_imported_artifacts_rejected(self):
        out, result, ledger = self.do_import([self.capture()])
        (out / 'original-captures/0000.bin').write_bytes(b'{}')
        with self.assertRaises(p.PipelineError):
            p.export_review(self.prepared, out, self.root / 'reviewed', result['result_sha256'])
        request_path = self.prepared / self.bundle['requests'][0]['path']
        request_path.write_bytes(b'{}')
        with self.assertRaises(p.PipelineError): p.load_prepared(self.prepared, self.result['result_sha256'])

    @unittest.skip("Filesystem-only verification is outside the current functional suite.")
    def test_unsafe_capture_paths_and_symlink_parent_rejected(self):
        link = self.root / 'linked'; link.symlink_to(self.captures, target_is_directory=True)
        self.capture()
        for path in ('../captures/response.json', '/etc/passwd', './response.json', 'sub/../response.json'):
            with self.subTest(path=path), self.assertRaises(p.PipelineError): p.relative_file(self.captures, path)
        with self.assertRaises(p.PipelineError): p.read_bytes(link / 'response.json')

    @unittest.skip("Filesystem-only verification is outside the current functional suite.")
    def test_fifo_nonblocking_rejection(self):
        fifo = self.root / 'fifo'; os.mkfifo(fifo)
        with self.assertRaises(p.PipelineError): p.read_bytes(fifo)

    def test_interrupted_prepare_has_no_success_manifest(self):
        out = self.root / 'interrupted'
        with patch.object(p, 'extract', side_effect=p.PipelineError('injected_parser_failure')):
            with self.assertRaises(p.PipelineError): p.prepare(self.pdf, out)
        self.assertFalse((out / 'result.json').exists())
        self.assertTrue((out / 'failure.json').exists())
        with self.assertRaises(p.PipelineError): p.verify_result(out, 'prepare', 'a' * 64)

    def test_all_blank_pdf_has_page_status_no_false_empty_success(self):
        path = self.root / 'blank.pdf'; path.write_bytes(pdf_bytes(['', '']))
        out = self.root / 'blank-prepared'; result = p.prepare(path, out)
        self.assertEqual(result['payload']['planned_requests'], 0)
        bundle = p.strict_load((out / 'bundle.json').read_bytes())
        self.assertEqual([x['status'] for x in bundle['pages']], ['no_text_unresolved'] * 2)

    def test_html_source_and_candidate_are_escaped(self):
        out, result, ledger = self.do_import([self.capture()])
        reviewed = self.root / 'reviewed'; p.export_review(self.prepared, out, reviewed, result['result_sha256'])
        queue = p.strict_load((reviewed / 'review-queue.json').read_bytes())
        queue['pages'][0]['text'] = '<script>alert(1)</script>'
        rendered = p.render_review(queue, ledger)
        self.assertNotIn('<script>', rendered); self.assertIn('&lt;script&gt;', rendered)

    def test_cli_errors_no_success_stdout(self):
        proc = subprocess.run([sys.executable, str(p.ROOT / 'pipeline.py'), 'prepare', '--pdf', str(self.pdf), '--out', str(self.prepared)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 1); self.assertEqual(proc.stdout, '')
        self.assertEqual(json.loads(proc.stderr)['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
