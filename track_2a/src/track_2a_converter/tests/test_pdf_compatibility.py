"""Owned PDF-reader compatibility fixtures, never model or human evaluation.

No input-reader credentials, explicit decryption, permissions changes, OCR,
network/provider use, or filesystem race/security checks are exercised.
"""
import io
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pypdf import PdfReader
from pypdf.errors import DependencyError, FileNotDecryptedError, PdfReadError

from track_2a_converter import pipeline as p
from fixtures import encrypted_pdf_bytes, pdf_bytes, response


class PdfCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.network = patch.object(socket, 'socket', side_effect=AssertionError('network forbidden'))
        self.network.start()
        self.addCleanup(self.network.stop)

    def source(self, raw, name='synthetic.pdf'):
        path = self.root / name
        path.write_bytes(raw)
        return path

    def prepared(self, raw):
        path = self.source(raw)
        out = self.root / 'prepared'
        result = p.prepare(path, out)
        bundle = p.strict_load((out / 'bundle.json').read_bytes())
        return path, out, result, bundle

    def review(self, prepared, result, bundle, with_candidate=False):
        entries = []
        if with_candidate:
            request = p.strict_load((prepared / bundle['requests'][0]['path']).read_bytes())
            (self.root / 'authored.json').write_bytes(p.canonical(response(request, request['source_text'][:20])))
            entries.append({'request_id': request['request_id'], 'status': 'captured', 'response_path': 'authored.json'})
        index = self.root / 'index.json'
        index.write_bytes(p.canonical({'profile': p.PROFILE, 'prepare_result_sha256': result['result_sha256'], 'entries': entries}))
        imported = p.import_captures(prepared, index, self.root / 'imported', result['result_sha256'])
        reviewed = p.export_review(prepared, self.root / 'imported', self.root / 'reviewed', imported['result_sha256'])
        p.verify_result(self.root / 'reviewed', 'review', reviewed['result_sha256'])
        return p.strict_load((self.root / 'reviewed/review-queue.json').read_bytes())

    def test_encryption_marker_with_ordinary_access_preserves_source_and_review(self):
        raw = encrypted_pdf_bytes(['SYNTHETIC committee proposes an owned example.', '', 'SYNTHETIC chamber postpones an owned example.'])
        ordinary = PdfReader(io.BytesIO(raw), strict=True)
        self.assertTrue(ordinary.is_encrypted)
        expected_texts = [page.extract_text(extraction_mode='plain') for page in ordinary.pages]
        path, out, result, bundle = self.prepared(raw)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual((out / 'source.pdf').read_bytes(), raw)
        self.assertEqual(bundle['source_sha256'], p.sha(raw))
        self.assertEqual(bundle['source_access'], {'status': 'opened_without_credentials', 'is_encrypted': True})
        self.assertEqual([page['text'] for page in bundle['pages']], expected_texts)
        self.assertEqual(bundle['page_status_counts'], {'text_extracted': 2, 'no_text_unresolved': 1, 'extraction_failed': 0})
        self.assertEqual(result['payload']['planned_requests'], 2)
        repeated = p.prepare(path, self.root / 'repeated')
        self.assertEqual((out / 'bundle.json').read_bytes(), (self.root / 'repeated/bundle.json').read_bytes())
        self.assertNotEqual(result['result_sha256'], repeated['result_sha256'])
        queue = self.review(out, result, bundle, with_candidate=True)
        self.assertEqual(queue['source_access'], bundle['source_access'])
        self.assertEqual(queue['page_status_counts'], bundle['page_status_counts'])
        self.assertEqual([page['page'] for page in queue['pages']], [1, 2, 3])
        self.assertFalse(queue['answer_eligible'])
        self.assertFalse(queue['human_reference'])
        self.assertTrue(all(page['ocr_status'] == 'not_attempted' for page in queue['pages']))
        candidate = queue['pages'][0]['requests'][0]['candidates'][0]
        self.assertFalse(candidate['answer_eligible'])
        self.assertEqual(candidate['adjudication'], 'unadjudicated')
        self.assertEqual((self.root / 'reviewed/source.pdf').read_bytes(), raw)

    def test_actual_password_required_fixture_fails_without_input_credentials(self):
        raw = encrypted_pdf_bytes(['SYNTHETIC inaccessible owned test text.'], password_required=True)
        path = self.source(raw)
        ordinary = PdfReader(io.BytesIO(raw), strict=True)
        self.assertTrue(ordinary.is_encrypted)
        with self.assertRaises(FileNotDecryptedError):
            len(ordinary.pages)
        out = self.root / 'rejected'
        with self.assertRaisesRegex(p.PipelineError, '^pdf_password_required$'):
            p.prepare(path, out)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual((out / 'source.pdf').read_bytes(), raw)
        self.assertEqual(p.strict_load((out / 'failure.json').read_bytes())['error'], 'pdf_password_required')
        self.assertEqual(p.strict_load((out / 'extraction.json').read_bytes()), {'status': 'failed', 'error': 'pdf_password_required'})
        self.assertFalse((out / 'result.json').exists())
        self.assertFalse((out / 'bundle.json').exists())
        self.assertFalse((out / 'requests').exists())

    def test_unreadable_source_has_specific_failure_and_no_success_manifest(self):
        path = self.source(b'%PDF-1.4\nSYNTHETIC incomplete PDF, owned fixture.\n')
        out = self.root / 'rejected'
        with self.assertRaisesRegex(p.PipelineError, '^pdf_unreadable$'):
            p.prepare(path, out)
        self.assertEqual(p.strict_load((out / 'failure.json').read_bytes())['error'], 'pdf_unreadable')
        self.assertFalse((out / 'result.json').exists())

    def test_bad_page_retained_in_order_and_never_gets_a_request(self):
        _, out, result, bundle = self.prepared(pdf_bytes(['SYNTHETIC first page.', 'SYNTHETIC broken page.', 'SYNTHETIC last page.'], malformed_pages=(2,)))
        self.assertEqual([page['status'] for page in bundle['pages']], ['text_extracted', 'extraction_failed', 'text_extracted'])
        failed = bundle['pages'][1]
        self.assertEqual(failed['error'], 'native_text_extraction_failed')
        self.assertEqual(failed['text'], '')
        self.assertEqual(failed['text_sha256'], p.sha(b''))
        self.assertEqual({request['chunk']['page'] for request in bundle['requests']}, {1, 3})
        queue = self.review(out, result, bundle)
        self.assertEqual(queue['pages'][1]['requests'], [])
        self.assertEqual(queue['page_status_counts'], {'text_extracted': 2, 'no_text_unresolved': 0, 'extraction_failed': 1})
        self.assertIn('Page failure: native_text_extraction_failed', (self.root / 'reviewed/review.html').read_text())

    def test_all_failed_pages_have_zero_requests_and_complete_unresolved_inventory(self):
        _, out, result, bundle = self.prepared(pdf_bytes(['SYNTHETIC first.', 'SYNTHETIC second.'], malformed_pages=(1, 2)))
        self.assertEqual(result['payload']['planned_requests'], 0)
        self.assertEqual(bundle['page_status_counts'], {'text_extracted': 0, 'no_text_unresolved': 0, 'extraction_failed': 2})
        queue = self.review(out, result, bundle)
        self.assertEqual(len(queue['pages']), 2)
        self.assertEqual(queue['denominators']['planned'], 0)
        self.assertFalse(queue['answer_eligible'])

    def test_reader_constructor_gets_no_credentials_and_no_explicit_decryption(self):
        source = self.source(pdf_bytes(['SYNTHETIC constructor test.']))
        class Page:
            def extract_text(self, *, extraction_mode):
                self_mode = extraction_mode
                if self_mode != 'plain':
                    raise AssertionError('Unexpected extraction mode')
                return 'SYNTHETIC mock plain text.'
        class Reader:
            is_encrypted = True
            pages = [Page()]
            def decrypt(self, *args, **kwargs):
                raise AssertionError('Explicit decryption forbidden')
        with patch('pypdf.PdfReader', return_value=Reader()) as constructor:
            value = p._read_pdf(source)
        self.assertEqual(constructor.call_count, 1)
        self.assertEqual(len(constructor.call_args.args), 1)
        self.assertEqual(constructor.call_args.kwargs, {'strict': True})
        self.assertEqual(value['extractor']['credential_arguments'], 'none')
        self.assertEqual(value['extractor']['explicit_decryption'], 'not_attempted')
        self.assertEqual(value['extractor']['policy'], p.EXTRACTION_POLICY)
        self.assertEqual(value['extractor']['converter_version'], p.CONVERTER_VERSION)

    def test_reader_and_inventory_failures_do_not_retry_or_guess_from_marker(self):
        source = self.source(pdf_bytes(['SYNTHETIC error classification.']))
        for error, expected in ((FileNotDecryptedError('synthetic'), 'pdf_password_required'),
                                (DependencyError('synthetic'), 'pdf_reader_dependency_unavailable'),
                                (PdfReadError('synthetic'), 'pdf_unreadable')):
            with self.subTest(expected=expected), patch('pypdf.PdfReader', side_effect=error) as constructor:
                with self.assertRaisesRegex(p.PipelineError, '^' + expected + '$'):
                    p._read_pdf(source)
                self.assertEqual(constructor.call_count, 1)
        class BrokenPages:
            def __len__(self):
                raise PdfReadError('synthetic unreadable inventory')
        with patch('pypdf.PdfReader', return_value=SimpleNamespace(is_encrypted=True, pages=BrokenPages())):
            with self.assertRaisesRegex(p.PipelineError, '^pdf_page_inventory_unreadable$'):
                p._read_pdf(source)

    def test_page_access_and_password_failures_preserve_known_denominator(self):
        source = self.source(pdf_bytes(['SYNTHETIC page classification.']))
        class Pages:
            def __len__(self):
                return 3
            def __getitem__(self, index):
                if index == 0:
                    return SimpleNamespace(extract_text=lambda **kwargs: 'SYNTHETIC readable page.')
                if index == 1:
                    raise FileNotDecryptedError('synthetic page requires credentials')
                raise PdfReadError('synthetic unreadable page')
        with patch('pypdf.PdfReader', return_value=SimpleNamespace(is_encrypted=True, pages=Pages())):
            value = p._read_pdf(source)
        self.assertEqual([page['page'] for page in value['pages']], [1, 2, 3])
        self.assertEqual([page['error'] for page in value['pages']], [None, 'page_password_required', 'native_text_extraction_failed'])
        self.assertEqual(value['page_status_counts']['extraction_failed'], 2)
        self.assertEqual(p.chunks_for(value['pages'][1], 4000), [])

    def test_cli_password_failure_exposes_stable_code_without_source_text(self):
        path = self.source(encrypted_pdf_bytes(['SYNTHETIC text must not appear in diagnostics.'], password_required=True))
        proc = subprocess.run([sys.executable, str(p.ROOT / 'pipeline.py'), 'prepare', '--pdf', str(path), '--out', str(self.root / 'rejected')], capture_output=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, b'')
        self.assertEqual(p.strict_load(proc.stderr), {'status': 'failed', 'error': 'pdf_password_required'})

    def test_worker_interruption_is_not_relabelled_as_password_failure(self):
        with patch.object(p.subprocess, 'run', side_effect=subprocess.TimeoutExpired('synthetic', 60)):
            with self.assertRaisesRegex(p.PipelineError, '^pdf_extraction_process_failed$'):
                p.extract(self.root / 'source.pdf', self.root / 'output.json')

    def test_read_only_diagnostic_emits_counts_hashes_and_no_source_text(self):
        text = 'SYNTHETIC diagnostic content must stay out of the receipt.'
        raw = encrypted_pdf_bytes([text, ''])
        path = self.source(raw)
        proc = subprocess.run([sys.executable, str(p.ROOT / 'compatibility_diagnostic.py'),
                               '--pdf', str(path), '--expected-sha256', p.sha(raw)], capture_output=True)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, b'')
        self.assertNotIn(text.encode(), proc.stdout)
        summary = p.strict_load(proc.stdout)
        self.assertEqual(summary['source_sha256'], p.sha(raw))
        self.assertTrue(summary['source_unchanged'])
        self.assertEqual(summary['page_count'], 2)
        self.assertEqual(summary['page_status_counts']['no_text_unresolved'], 1)
        self.assertEqual(summary['planned_requests_at_4000_chars'], 1)
        self.assertFalse(summary['answer_eligible'])
        self.assertEqual(summary['redistribution_rights'], 'not_established')
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_read_only_diagnostic_rejects_wrong_source_pin(self):
        path = self.source(pdf_bytes(['SYNTHETIC pin check.']))
        proc = subprocess.run([sys.executable, str(p.ROOT / 'compatibility_diagnostic.py'),
                               '--pdf', str(path), '--expected-sha256', '0' * 64], capture_output=True)
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(proc.stdout, b'')
        self.assertEqual(p.strict_load(proc.stderr), {'status': 'failed', 'error': 'source_pin_mismatch'})


if __name__ == '__main__':
    unittest.main()
