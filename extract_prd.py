import pymupdf
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

doc = pymupdf.open(r'c:\Users\Administrator\Downloads\CALL E\calle-hackathon-prd.pdf')
for page in doc:
    print(page.get_text())
