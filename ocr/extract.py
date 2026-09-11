"""Local-only image/PDF recognition; isolated worker prevents outbound sockets."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_BYTES = 10 * 1024 * 1024


def extract(data: bytes):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Upload a nonempty file no larger than 10 MB.')
    with tempfile.TemporaryDirectory(prefix='medai-ocr-') as folder:
        source = Path(folder) / 'source'
        target = Path(folder) / 'result.json'
        source.write_bytes(data)
        try:
            proc = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()),
                                   str(source), str(target)], capture_output=True, timeout=90,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except subprocess.TimeoutExpired:
            raise ValueError('OCR exceeded 90 seconds. Try one smaller, clearer page.') from None
        if not target.exists():
            raise ValueError('Local OCR could not start. Install requirements-ocr.txt and check the local engine.')
        result = json.loads(target.read_text(encoding='utf-8'))
        if proc.returncode or 'error' in result:
            raise ValueError(result.get('error', 'OCR failed.'))
        return result


def recognize(path):
    import warnings
    from PIL import Image, ImageOps, UnidentifiedImageError
    import numpy as np
    from rapidocr import RapidOCR
    Image.MAX_IMAGE_PIXELS = 16_000_000
    warnings.simplefilter('error', Image.DecompressionBombWarning)
    engine = RapidOCR()
    pages = []

    def read(image, number):
        if image.width * image.height > 16_000_000:
            raise ValueError('Page exceeds 16 million pixels. Resize it before uploading.')
        result = engine(np.asarray(image.convert('RGB')))
        texts = result.txts or ()
        scores = result.scores if result.scores is not None else [0.0] * len(texts)
        lines = [{'text': str(t), 'confidence': float(s)} for t, s in zip(texts, scores)]
        pages.append({'page': number, 'lines': lines, 'text': '\n'.join(texts)})

    if path.read_bytes()[:5] == b'%PDF-':
        import pypdfium2 as pdfium
        with pdfium.PdfDocument(path) as pdf:
            if not 1 <= len(pdf) <= 3:
                raise ValueError('Upload a PDF with 1 to 3 pages.')
            for i in range(len(pdf)):
                page = pdf[i]
                try:
                    w, h = page.get_size()
                    if w * h * 4 > 16_000_000:
                        raise ValueError('PDF page is too large to render safely.')
                    bitmap = page.render(scale=2)
                    try:
                        read(bitmap.to_pil(), i + 1)
                    finally:
                        bitmap.close()
                finally:
                    page.close()
    else:
        try:
            with Image.open(path) as image:
                if image.format not in {'PNG', 'JPEG', 'WEBP'} or getattr(image, 'n_frames', 1) != 1:
                    raise ValueError('Use a single PNG, JPEG, WebP image or a PDF.')
                read(ImageOps.exif_transpose(image), 1)
        except UnidentifiedImageError:
            raise ValueError('File is not a readable PNG, JPEG, WebP image or PDF.') from None
    text = '\n\n'.join(p['text'] for p in pages)
    if not text.strip():
        raise ValueError('No readable text found. Try a clearer scan or enter the prescription manually.')
    return {'engine': 'RapidOCR local', 'text': text, 'pages': pages,
            'review_required': True, 'medications': [], 'calls_placed': 0}


if __name__ == '__main__':
    def offline(event, args):
        if event in {'socket.connect', 'socket.getaddrinfo', 'socket.sendto'}:
            raise RuntimeError('Network access is disabled in prescription OCR.')
    sys.addaudithook(offline)
    try:
        output = recognize(Path(sys.argv[1]))
        code = 0
    except ValueError as exc:
        output, code = {'error': str(exc)}, 1
    except Exception:
        output, code = {'error': 'Local OCR failed. Check engine installation or try a clearer, unencrypted file.'}, 1
    Path(sys.argv[2]).write_text(json.dumps(output), encoding='utf-8')
    sys.exit(code)
