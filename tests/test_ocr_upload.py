import io
import pytest
from PIL import Image, ImageDraw, ImageFont
from tests.test_local_api import client, MED
from medai_readback.local_api import workflow


def document(fmt='PNG', blank=False):
    im = Image.new('RGB', (1400, 600), 'white')
    if not blank:
        font = ImageFont.load_default(size=48)
        ImageDraw.Draw(im).text((50, 50), 'OCR TEST DOCUMENT\nMedicine Alpha 500 mg\nDuration 5 days', fill='black', font=font, spacing=20)
    b = io.BytesIO()
    im.save(b, format=fmt)
    return b.getvalue()


@pytest.mark.parametrize('fmt', ['PNG', 'PDF'])
def test_real_local_upload_and_saved_review(client, fmt):
    response = client.post('/local/ocr/extract', content=document(fmt))
    assert response.status_code == 200, response.text
    doc = response.json()
    assert '500' in doc['text'] and '5 days' in doc['text']
    assert doc['review_required'] and doc['medications'] == []
    assert client.get('/local/ocr/' + doc['scan_id']).json() == doc
    assert workflow().list('confirmation') == [] and workflow().budget() == 0
    response = client.post('/local/intakes', json={'patient_id': 'p', 'source_id': doc['scan_id'], 'medications': [MED]})
    assert response.status_code == 422


def test_upload_rejects_unauthenticated_and_oversize(client):
    assert client.post('/local/ocr/extract', content=b'x', headers={'Authorization': ''}).status_code == 401
    assert client.post('/local/ocr/extract', content=b'x' * (10*1024*1024+1)).status_code == 413


@pytest.mark.parametrize('data', [b'', b'not an image'])
def test_invalid_file_does_not_create_records(client, data):
    assert client.post('/local/ocr/extract', content=data).status_code == 422
    assert workflow().list('ocr') == []


def test_blank_image_is_not_fake_extraction(client):
    assert client.post('/local/ocr/extract', content=document(blank=True)).status_code == 422
