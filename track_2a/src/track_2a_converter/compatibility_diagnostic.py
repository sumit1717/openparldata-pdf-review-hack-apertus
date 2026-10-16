"""Read-only PDF compatibility diagnostic; print counts/hashes, never source text.

No source copying, credentials, explicit decryption, OCR, network/provider call,
candidate import, rights clearance or semantic evaluation is performed.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import json
import os
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from track_2a_converter import pipeline as p


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf', required=True)
    parser.add_argument('--expected-sha256', required=True)
    args = parser.parse_args()
    try:
        p.require(bool(p.DIGEST.fullmatch(args.expected_sha256)), 'expected_source_pin_required')
        raw = p.read_bytes(args.pdf, p.PDF_CAP)
        p.require(p.sha(raw) == args.expected_sha256, 'source_pin_mismatch')
        # This command is its own resource-bounded process. Only summary fields
        # reach stdout; extracted text stays in memory and is never persisted.
        with open(os.devnull, 'w') as diagnostics, redirect_stderr(diagnostics):
            extracted = p._extract_pdf(args.pdf)
        p.require(p.sha(p.read_bytes(args.pdf, p.PDF_CAP)) == args.expected_sha256, 'source_changed_during_diagnostic')
        summary = {
            'diagnostic_kind': 'read_only_ordinary_reader_compatibility',
            'converter_version': p.CONVERTER_VERSION, 'status': 'complete',
            'source_sha256': args.expected_sha256, 'source_bytes': len(raw), 'source_unchanged': True,
            'source_access': extracted['source_access'], 'extractor': extracted['extractor'],
            'page_count': len(extracted['pages']), 'page_status_counts': extracted['page_status_counts'],
            'pages': [{key: page[key] for key in ('page', 'status', 'error', 'text_sha256', 'ocr_status')} |
                      {'text_chars': len(page['text']), 'text_utf8_bytes': len(page['text'].encode('utf-8'))}
                      for page in extracted['pages']],
            'planned_requests_at_4000_chars': sum(len(p.chunks_for(page, 4000)) for page in extracted['pages']),
            'network_calls': 0, 'provider_calls': 0, 'ocr_status': 'not_attempted',
            'answer_eligible': False, 'human_reference': False, 'semantic_accuracy': None,
            'redistribution_rights': 'not_established',
        }
        print(json.dumps(summary, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc) if isinstance(exc, p.PipelineError) else 'diagnostic_failed'}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
