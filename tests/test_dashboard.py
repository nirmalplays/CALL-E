from medai_readback.dashboard import render_dashboard


def _doc(**overrides):
    doc = {
        "call_id": "pat1-2026-09-09-readback",
        "patient_name": "Ravi Kumar",
        "phone_number": "+919876543210",
        "medications": [
            {"name": "Metformin", "dosage": "500mg", "quantity": "1",
             "schedule": ["MORNING"], "duration": "30 days", "instructions": "after food"},
        ],
        "status": "pending",
        "corrections": [],
        "structured_result": None,
    }
    doc.update(overrides)
    return doc


def test_empty_queue_renders_without_error():
    html_out = render_dashboard([])
    assert "<html>" in html_out
    assert "Nothing here." in html_out


def test_patient_name_and_masked_phone_appear():
    html_out = render_dashboard([_doc()])
    assert "Ravi Kumar" in html_out
    assert "+919876543210" not in html_out, "raw phone number must not leak onto the dashboard"
    assert "+91" in html_out and "210" in html_out, "masked phone should still be recognizable"


def test_review_status_shows_correction_verbatim():
    doc = _doc(
        status="review",
        corrections=[{"name_as_read": "Metformin", "status": "corrected", "correction_text": "it's 50mg not 5mg"}],
    )
    html_out = render_dashboard([doc])
    assert "it&#x27;s 50mg not 5mg" in html_out or "it's 50mg not 5mg" in html_out


def test_html_special_characters_in_patient_name_are_escaped():
    doc = _doc(patient_name="<script>alert(1)</script>")
    html_out = render_dashboard([doc])
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out


def test_review_and_fallback_sort_before_scheduled():
    docs = [_doc(status="scheduled", patient_name="Scheduled Patient"),
            _doc(status="review", patient_name="Review Patient")]
    html_out = render_dashboard(docs)
    assert html_out.index("Review Patient") < html_out.index("Scheduled Patient")


def test_patient_notes_are_shown_when_present():
    doc = _doc(structured_result={"patient_notes": "please call after 6pm"})
    html_out = render_dashboard([doc])
    assert "please call after 6pm" in html_out
