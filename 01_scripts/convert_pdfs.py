"""Convertit les PDF de 02_inputfiles en Markdown dans 03_outputFiles.

Prérequis : pip install pymupdf pymupdf4llm==0.3.4
Exécuter depuis la racine du projet : python 01_scripts/convert_pdfs.py
"""
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root / "04_functions"))

from pdf_to_markdown import pdf_to_markdown  # noqa: E402

input_dir = root / "02_inputfiles"
output_dir = root / "03_outputFiles"
output_dir.mkdir(exist_ok=True)

pdfs = sorted(input_dir.glob("*.pdf"))
if not pdfs:
    print(f"Aucun PDF trouvé dans {input_dir}")

for pdf in pdfs:
    md = output_dir / f"{pdf.stem}.md"
    try:
        pdf_to_markdown(pdf, md)
        print(f"OK  {pdf.name} -> {md.name}")
    except Exception as e:
        print(f"ERREUR  {pdf.name} : {e}")
