"""Extract text from Doc13 PDF."""
import subprocess
import sys
from pathlib import Path

pdf = Path(r"C:\Users\silwa\Downloads\Non-real case sample doc\Non-real case sample doc\NR Doc13-Insurancepolicy.pdf")
print(f"PDF size: {pdf.stat().st_size} bytes")

# Try pdftotext first (poppler)
try:
    out = subprocess.check_output(["pdftotext", "-layout", str(pdf), "-"], stderr=subprocess.STDOUT, text=True)
    print("=== pdftotext output (first 2000 chars) ===")
    print(out[:2000])
except Exception as e:
    print("pdftotext failed:", e)
    # Fallback: try pypdf
    try:
        import pypdf
        r = pypdf.PdfReader(str(pdf))
        for i, page in enumerate(r.pages):
            text = page.extract_text() or ""
            print(f"=== page {i+1} ===")
            print(text)
            if i >= 0: break
    except Exception as e2:
        print("pypdf failed too:", e2)
