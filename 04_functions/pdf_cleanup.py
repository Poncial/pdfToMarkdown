"""Nettoyage du PDF avant conversion : notes de bas de page, numéros de page, appels de note.

Le texte concerné est effacé du document en mémoire (redaction) ; le fichier d'origine
n'est jamais modifié.
"""
import re
from collections import Counter

import pymupdf

ROMAN_RE = re.compile(r"^[ivxlcdm]{1,7}$", re.IGNORECASE)
NOTE_MARKERS = ("*", "†", "‡", "§")


def _lines(page: pymupdf.Page) -> list[dict]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if s["text"].strip()]
            if not spans:
                continue
            out.append({
                "bbox": pymupdf.Rect(line["bbox"]),
                "spans": spans,
                "text": "".join(s["text"] for s in line["spans"]).strip(),
                "size": max(s["size"] for s in spans),
            })
    return out


def _body_size(doc: pymupdf.Document) -> float:
    """Taille de police la plus fréquente (pondérée par le nombre de caractères)."""
    counts: Counter = Counter()
    for page in doc:
        for line in _lines(page):
            for s in line["spans"]:
                counts[round(s["size"] * 2) / 2] += len(s["text"])
    return counts.most_common(1)[0][0] if counts else 10.0


def _is_page_number(text: str) -> bool:
    t = text.strip("*_ ")
    return bool(re.fullmatch(r"\d{1,4}", t) or ROMAN_RE.match(t))


def strip_notes_and_page_numbers(doc: pymupdf.Document) -> pymupdf.Document:
    """Efface notes de bas de page, numéros de page, en-têtes/pieds courts et appels de note."""
    body = _body_size(doc)

    for page in doc:
        height = page.rect.height
        lines = _lines(page)
        to_erase: list[pymupdf.Rect] = []
        used: set[int] = set()

        # Numéros de page et en-têtes/pieds courts, dans les marges haute et basse
        for i, ln in enumerate(lines):
            in_margin = ln["bbox"].y0 > 0.945 * height or ln["bbox"].y1 < 0.065 * height
            short = len(ln["text"]) <= 60 and ln["size"] <= body * 1.05
            has_digit = any(c.isdigit() for c in ln["text"])
            if in_margin and short and (has_digit or _is_page_number(ln["text"])):
                to_erase.append(ln["bbox"])
                used.add(i)

        # Zone de notes : lignes en petits caractères en bas de page, de bas en haut
        bottom_up = sorted((i for i in range(len(lines)) if i not in used),
                           key=lambda i: -lines[i]["bbox"].y0)
        zone_top = height
        for i in bottom_up:
            ln = lines[i]
            if ln["bbox"].y0 < 0.5 * height:
                break
            small = ln["size"] <= body * 0.92
            marker = ln["text"].startswith(NOTE_MARKERS) and zone_top < height
            if small or marker:
                to_erase.append(ln["bbox"])
                used.add(i)
                zone_top = ln["bbox"].y0
            else:
                break

        # Appels de note dans le texte : chiffres en exposant
        for i, ln in enumerate(lines):
            if i in used:
                continue
            for s in ln["spans"]:
                txt = s["text"].strip()
                is_super = bool(s["flags"] & 1) or s["size"] < body * 0.75
                if is_super and re.fullmatch(r"[\d,\s()*]+", txt):
                    to_erase.append(pymupdf.Rect(s["bbox"]))

        for rect in to_erase:
            page.add_redact_annot(rect)
        if to_erase:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE)
    return doc
