#!/usr/bin/env python3
"""Extract text from PDF using pdfminer.six"""
import sys
try:
    from pdfminer.high_level import extract_text
except ImportError:
    # Try pip installing
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pdfminer.six", "-q"])
    from pdfminer.high_level import extract_text

pdf_path = sys.argv[1]
text = extract_text(pdf_path)
print(text)
