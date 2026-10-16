"""Create an owned, authored two-packet worksheet; zero provider calls or human gold."""
import argparse
from pathlib import Path
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from track_2a_comparison import worksheet as w


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-root', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    p, _ = w.dependencies(args.repo_root)
    from track_2a_converter.tests.fixtures import pdf_bytes, response
    root = p.safe_path(args.out)
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    p.write_new(root / 'AUTHORED_ENGINEERING_ONLY.txt', b'Owned synthetic sources and authored candidate bytes. No inference, human reference, measured usefulness or rights claim about real sources.\n')
    packets = []
    fixtures = [
        ('recommendation', 'Owned recommendation and unresolved annex',
         ['Clerk authored this report. Committee recommends rejecting the proposal. Annex B is not included.', '', 'A response was not captured for this page.'],
         {'author': ('Clerk', 'Clerk authored this report.'), 'actor': ('Committee', 'Committee recommends rejecting the proposal.'),
          'event': ('recommendation', 'Committee recommends rejecting the proposal.'), 'outcome': ('rejection recommended', 'Committee recommends rejecting the proposal.')}),
        ('agenda', 'Owned agenda decision; substantive outcome remains unassessed',
         ['Secretariat authored this report. Chamber placed the proposal on the agenda. No substantive vote is recorded in this note.', ''],
         {'author': ('Secretariat', 'Secretariat authored this report.'), 'actor': ('Chamber', 'Chamber placed the proposal on the agenda.'),
          'event': ('agenda placement', 'Chamber placed the proposal on the agenda.'), 'outcome': ('placed on agenda', 'Chamber placed the proposal on the agenda.')})]
    for identity, label, pages, fields in fixtures:
        home = root / identity; home.mkdir()
        p.write_new(home / 'source.owned.pdf', pdf_bytes(pages))
        prepared = p.prepare(home / 'source.owned.pdf', home / 'prepared')
        bundle = p.strict_load(p.read_bytes(home / 'prepared/bundle.json'))
        request = p.strict_load(p.read_bytes(home / 'prepared' / bundle['requests'][0]['path']))
        candidate = response(request, request['source_text'][:20])
        event = candidate['events'][0]
        for key, (value, quote) in fields.items():
            start = request['source_text'].index(quote)
            event[key] = {'state': 'present', 'value': value,
                          'evidence': [{'page': 1, 'start': start, 'end': start + len(quote), 'quote': quote}],
                          'alternatives': [], 'reviewed_scope': None, 'reason': ''}
        captures = home / 'captures'; captures.mkdir()
        p.write_new(captures / 'authored.original.json', p.canonical(candidate))
        index = {'profile': p.PROFILE, 'prepare_result_sha256': prepared['result_sha256'],
                 'entries': [{'request_id': request['request_id'], 'status': 'captured', 'response_path': 'authored.original.json'}]}
        p.write_new(captures / 'index.json', p.canonical(index))
        imported = p.import_captures(home / 'prepared', captures / 'index.json', home / 'imported', prepared['result_sha256'])
        review = p.export_review(home / 'prepared', home / 'imported', home / 'review', imported['result_sha256'])
        packets.append({'selection_id': identity, 'label': label, 'prepared_directory': str(home / 'prepared'),
                        'imported_directory': str(home / 'imported'), 'review_directory': str(home / 'review'),
                        'expected_prepare_sha256': prepared['result_sha256'], 'expected_import_sha256': imported['result_sha256'],
                        'expected_review_sha256': review['result_sha256']})
    p.write_new(root / 'selection.json', p.canonical({'profile': w.SELECTION_PROFILE, 'converter_packets': packets, 'frozen_gap_ledger': None}))
    result = w.generate(root / 'selection.json', args.repo_root, root / 'worksheet')
    print(p.canonical({'kind': 'authored_engineering_only', 'worksheet': str(root / 'worksheet/worksheet.html'),
                       'result_sha256': result['result_sha256'], 'provider_calls': 0, 'human_reference': False}).decode())


if __name__ == '__main__':
    main()
