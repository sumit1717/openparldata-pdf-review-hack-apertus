"""Create an offline synthetic engineering journey, never a model/human result."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from track_2a_converter import pipeline as p
from track_2a_converter.tests.fixtures import encrypted_pdf_bytes, pdf_bytes, response


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, help='New directory with an existing parent')
    parser.add_argument('--encrypted-readable', action='store_true', help='Author an owned marked-encrypted fixture the ordinary reader opens without credentials')
    args = parser.parse_args()
    root = Path(args.out)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    (root / 'SYNTHETIC_ENGINEERING_ONLY.txt').write_text('Synthetic engineering fixture. No provider output, semantic gold, human review or performance claim.\n')
    pdf = root / 'synthetic-source.pdf'
    create_pdf = encrypted_pdf_bytes if args.encrypted_readable else pdf_bytes
    pdf.write_bytes(create_pdf(['The committee proposed a bridge. The council will discuss it later.', '', 'The chamber postponed the synthetic affair.']))
    prepared = p.prepare(pdf, root / 'prepared')
    bundle = p.strict_load((root / 'prepared/bundle.json').read_bytes())
    requests = [p.strict_load((root / 'prepared' / r['path']).read_bytes()) for r in bundle['requests']]
    captures = root / 'captures'; captures.mkdir(mode=0o700)
    # Deliberately include one structurally valid authored candidate, one malformed
    # capture, and an unresolved blank source page. These are pipeline tests only.
    entries = []
    for number, request in enumerate(requests):
        name = f'{number}.original.json'
        raw = p.canonical(response(request, request['source_text'][:20])) if number == 0 else b'{"events": [ malformed original'
        (captures / name).write_bytes(raw)
        entries.append({'request_id': request['request_id'], 'status': 'captured', 'response_path': name})
    index = {'profile': p.PROFILE, 'prepare_result_sha256': prepared['result_sha256'], 'entries': entries}
    (captures / 'index.json').write_bytes(p.canonical(index))
    imported = p.import_captures(root / 'prepared', captures / 'index.json', root / 'imported', prepared['result_sha256'])
    reviewed = p.export_review(root / 'prepared', root / 'imported', root / 'review', imported['result_sha256'])
    print(json.dumps({'fixture_kind': 'synthetic_engineering_only', 'review_html': str(root / 'review/review.html'),
                      'prepare_result_sha256': prepared['result_sha256'], 'import_result_sha256': imported['result_sha256'],
                      'review_result_sha256': reviewed['result_sha256'], 'denominators': imported['payload']['denominators'],
                      'converter_version': p.CONVERTER_VERSION, 'source_access': bundle['source_access'],
                      'page_status_counts': bundle['page_status_counts'],
                      'human_reference': False, 'provider_calls': 0}, sort_keys=True))


if __name__ == '__main__':
    main()
