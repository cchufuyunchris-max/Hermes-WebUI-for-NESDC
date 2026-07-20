#!/usr/bin/env python3
import subprocess, importlib
# Check pdftotext
r = subprocess.run(["which", "pdftotext"], capture_output=True, text=True)
print("pdftotext:", r.stdout.strip() or "NOT FOUND")

# Check pypdf2/pdfminer/pdfplumber
for mod in ["PyPDF2", "pdfminer", "pdfminer.high_level", "pdfplumber"]:
    try:
        importlib.import_module(mod)
        print(f"{mod}: OK")
    except ImportError:
        print(f"{mod}: not found")
