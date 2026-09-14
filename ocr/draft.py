"""Conservative text-to-draft extraction. Never a clinical approval or lookup."""
import re

STRENGTH = re.compile(r'(?<![\w.])\d+(?:\.\d+)?\s*(?:mcg|mg|g|ml|mL|IU|units)(?:\s*/\s*(?:\d+(?:\.\d+)?\s*)?(?:ml|mL))?\b', re.I)

# Map recognised labels (case-insensitive) to canonical field names.
_FIELD_ALIASES = {
    'quantity': 'quantity', 'qty': 'quantity',
    'schedule': 'schedule', 'timing': 'schedule',
    'duration': 'duration',
    'instructions': 'instructions', 'instruction': 'instructions',
}
_FIELD_LINE = re.compile(
    r'^\s*(' + '|'.join(_FIELD_ALIASES) + r')\s*:\s*(.+)', re.I,
)


def medication_drafts(pages):
    drafts = []
    for page in pages:
        lines = page.get('lines', [])
        i = 0
        while i < len(lines):
            text = lines[i]['text'].strip()
            match = STRENGTH.search(text)
            if not match:
                i += 1
                continue
            prefix = text[:match.start()].strip(' :-|')
            prefix = re.sub(r'^\s*(?:\d+[.)]\s*|[-•]\s*)', '', prefix)
            prefix = re.sub(r'^(?:tablet|tablets|tab\.?|capsule|cap\.?|syrup|medicine\s*:)\s+', '', prefix, flags=re.I)
            if not prefix or not re.search(r'[A-Za-z]', prefix):
                i += 1
                continue
            # These are literal transcriptions, not instructions inferred from
            # frequency abbreviations, strengths, or a drug dictionary.
            fields = {}
            # Pass 1: inline fields on the same line (e.g. "Aspirin 100mg | quantity: 30")
            for key in ('quantity', 'schedule', 'timing', 'duration', 'instructions'):
                found = re.search(r'(?:^|[;|])\s*'+key+r'\s*:\s*([^;|]+)', text, re.I)
                if found:
                    canon = _FIELD_ALIASES.get(key, key)
                    if not fields.get(canon):
                        fields[canon] = found.group(1).strip()
            # Pass 2: look at following lines for "Key: value" patterns
            j = i + 1
            while j < len(lines):
                following = lines[j]['text'].strip()
                fmatch = _FIELD_LINE.match(following)
                if not fmatch:
                    break
                canon = _FIELD_ALIASES.get(fmatch.group(1).lower())
                if canon and not fields.get(canon):
                    fields[canon] = fmatch.group(2).strip()
                j += 1
            drafts.append(dict(name=prefix, dosage=match.group(),
                quantity=fields.get('quantity', ''),
                schedule=[fields['schedule']] if fields.get('schedule') else [],
                duration=fields.get('duration', ''),
                instructions=fields.get('instructions', ''),
                source_text=text, source_page=page['page'],
                confidence=lines[i].get('confidence'),
                review_required=True))
            i = j  # skip past the consumed field lines
    return drafts

