"""Conservative text-to-draft extraction. Never a clinical approval or lookup."""
import re

STRENGTH = re.compile(r'(?<![\w.])\d+(?:\.\d+)?\s*(?:mcg|mg|g|ml|mL|IU|units)(?:\s*/\s*(?:\d+(?:\.\d+)?\s*)?(?:ml|mL))?\b', re.I)


def medication_drafts(pages):
    drafts = []
    for page in pages:
        for line in page.get('lines', []):
            text = line['text'].strip()
            match = STRENGTH.search(text)
            if not match:
                continue
            prefix = text[:match.start()].strip(' :-|')
            prefix = re.sub(r'^\s*(?:\d+[.)]\s*|[-•]\s*)', '', prefix)
            prefix = re.sub(r'^(?:tablet|tablets|tab\.?|capsule|cap\.?|syrup|medicine\s*:)\s+', '', prefix, flags=re.I)
            if not prefix or not re.search(r'[A-Za-z]', prefix):
                continue
            # These are literal transcriptions, not instructions inferred from
            # frequency abbreviations, strengths, or a drug dictionary.
            fields = {}
            for key in ('quantity', 'schedule', 'duration', 'instructions'):
                found = re.search(r'(?:^|[;|])\s*'+key+r'\s*:\s*([^;|]+)', text, re.I)
                fields[key] = found.group(1).strip() if found else ''
            drafts.append(dict(name=prefix, dosage=match.group(), quantity=fields['quantity'],
                schedule=[fields['schedule']] if fields['schedule'] else [],
                duration=fields['duration'], instructions=fields['instructions'],
                source_text=text, source_page=page['page'], confidence=line.get('confidence'),
                review_required=True))
    return drafts
