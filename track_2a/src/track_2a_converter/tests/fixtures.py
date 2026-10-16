"""Explicitly synthetic engineering PDF/response fixtures; never semantic gold."""
from __future__ import annotations
import copy
import json
from pathlib import Path


def pdf_bytes(pages, *, malformed_pages=()):
    """Tiny deterministic PDF writer, avoiding a new test-only dependency."""
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'']
    font_id = 3
    objects.append(b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>')
    page_ids = []
    for number, text in enumerate(pages, 1):
        page_id, stream_id = len(objects) + 1, len(objects) + 2
        page_ids.append(page_id)
        escaped = text.encode('ascii').replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
        stream = b'BT /F1 11 Tf 50 700 Td (' + escaped + b') Tj ET' if text else b''
        if number in malformed_pages:
            # Owned content stream with an invalid one-operand text-position
            # instruction. Its page exists, but native text extraction fails.
            stream = b'BT /F1 11 Tf (synthetic malformed operand) Td ET'
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {stream_id} 0 R >>'.encode())
        objects.append(b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream')
    objects[1] = ('<< /Type /Pages /Kids [' + ' '.join(f'{n} 0 R' for n in page_ids) + f'] /Count {len(page_ids)} >>').encode()
    result, offsets = b'%PDF-1.4\n', [0]
    for number, obj in enumerate(objects, 1):
        offsets.append(len(result)); result += f'{number} 0 obj\n'.encode() + obj + b'\nendobj\n'
    xref = len(result)
    result += f'xref\n0 {len(objects) + 1}\n0000000000 65535 f \n'.encode()
    for offset in offsets[1:]:
        result += f'{offset:010d} 00000 n \n'.encode()
    return result + f'trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n'.encode()


def encrypted_pdf_bytes(pages, *, password_required=False):
    """Author a NEW owned fixture; fake test values are never used for reading.

    This does not alter any imported/real PDF. Default writer permissions are
    unchanged. Production code neither supplies credentials nor calls decrypt.
    """
    import io
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    source = PdfReader(io.BytesIO(pdf_bytes(pages)), strict=True)
    for page in source.pages:
        writer.add_page(page)
    writer.add_metadata({'/Title': 'SYNTHETIC ENGINEERING FIXTURE - owned test content'})
    writer.encrypt('synthetic-fixture-not-a-real-credential' if password_required else '',
                   owner_password='synthetic-fixture-owner-not-a-real-credential', algorithm='RC4-128')
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def unassessed():
    return {'state': 'unassessed', 'value': None, 'evidence': [], 'alternatives': [], 'reviewed_scope': None, 'reason': ''}


def response(request, text=None):
    from track_2a_converter.pipeline import FIELDS
    result = {key: copy.deepcopy(request[key]) for key in ('request_id', 'binding', 'reviewed_scope')}
    result['events'] = []
    if text is not None:
        start = request['reviewed_scope']['start']
        loc = {'page': request['reviewed_scope']['page'], 'start': start, 'end': start + len(text), 'quote': text}
        fields = {name: unassessed() for name in FIELDS}
        fields['event'] = {'state': 'present', 'value': 'synthetic candidate only', 'evidence': [loc], 'alternatives': [], 'reviewed_scope': None, 'reason': ''}
        result['events'] = [{'candidate_id': 'synthetic-1', 'anchors': [loc], **fields}]
    return result
