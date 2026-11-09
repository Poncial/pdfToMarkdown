from pathlib import Path

import pymupdf
import pymupdf4llm

from pdf_cleanup import strip_notes_and_page_numbers
from postprocess_markdown import postprocess_markdown


def pdf_to_markdown(pdf_path: Path, md_path: Path, clean: bool = True) -> Path:
    """Convertit un PDF en Markdown avec pymupdf4llm, puis nettoie le résultat."""
    doc = pymupdf.open(str(pdf_path))
    if clean:
        # Retire notes de bas de page, numéros de page et appels de note (en mémoire seulement)
        strip_notes_and_page_numbers(doc)
    chunks = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)
    doc.close()
    # Séparateur de page requis par le post-traitement (détection des en-têtes/pieds répétés)
    md_text = (chr(10) * 2 + "-----" + chr(10) * 2).join(c["text"] for c in chunks)
    if clean:
        md_text = postprocess_markdown(md_text)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_text, encoding="utf-8")
    return md_path
