# Local OCR

Install with `python -m pip install -r requirements-ocr.txt` using the same Python as the server, then restart it.

In New prescription, upload a PNG/JPEG/WebP image or a PDF and select Extract text locally. Staff can load source-derived medicine draft fields, compare every value with the retained original, fill missing fields, and acknowledge review before saving. Draft extraction uses conservative text patterns, not a clinical model or a drug dictionary. Unrecognized formats require manual entry. Saved scans can be reopened. The scan reference links the intake to the stored original OCR text and confidence values. Recognition does not place calls or interpret prescriptions automatically.

Authenticated API: POST /local/ocr/extract with raw file bytes; GET /local/ocr/{scan_id} retrieves the stored extraction. Limit: 10 MB, 3 PDF pages, 16 million pixels per rendered page, one OCR worker per server process, 90-second processing timeout. Temporary processing files are deleted afterward. Original uploaded bytes, extracted text, draft fields, and source hash are stored in the tenant's local SQLite database. Original downloads require staff authentication. Storage and backups therefore contain prescription files and must follow the clinic's retention policy.

The worker blocks outbound Python socket requests. Model weights ship with the installed RapidOCR package. No CALL-E or other paid API is used. This is text recognition with manual medication structuring; handwritten prescription accuracy, non-English prescription support, and automatic clinical field extraction are not validated. Never infer unreadable medication details.

Legacy ocr/main.py fixtures remain isolated to offline demos/tests; the upload endpoint uses ocr/extract.py.
