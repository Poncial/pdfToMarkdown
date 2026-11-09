"""Post-traitement du Markdown produit par pymupdf4llm, pour le rendre lisible par une IA.

Étapes : nettoyage typographique, suppression des numéros de page et en-têtes/pieds
de page répétés, normalisation des niveaux de titre, fusion des lignes d'un même
paragraphe, promotion des sous-titres isolés.
"""
import re
from collections import Counter

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
LIST_RE = re.compile(r"^\s*([-*+\u2022]|\d+[.)])\s+")
PAGE_NUM_RE = re.compile(r"^(\d{1,4}|[ivxlcdm]{1,7}|[IVXLCDM]{1,7})$")
CONNECTORS = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "à", "au", "aux", "en", "dans",
              "pour", "sur", "par", "un", "une", "ou", "avec", "of", "the", "and", "to", "in", "for", "und", "oder"}
TERMINAL = (".", "!", "?", ":", ";")
SENTENCE_END = (".", "!", "?", ":", ";", ",")


def _is_structural(line: str) -> bool:
    s = line.lstrip()
    return bool(
        HEADING_RE.match(line)
        or LIST_RE.match(line)
        or s.startswith(("|", "![", "```", ">"))
    )


def _clean_heading_text(text: str) -> str:
    text = text.replace("**", "").replace("__", "")
    text = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    # Astérisque de note de bas de page laissé en fin de titre
    return re.sub(r"\s*\*+$", "", text)


def _remove_page_noise(lines: list[str]) -> list[str]:
    def key(ln: str) -> str:
        m = HEADING_RE.match(ln)
        txt = _clean_heading_text(m.group(2)) if m else ln.strip().strip("*_ ")
        # Ignore le numéro de page collé au début ou à la fin de l'en-tête/pied de page
        return re.sub(r"^\d+\s+|\s+\d+$", "", txt).lower()

    # Numéro de page de chaque ligne (les pages sont séparées par des lignes "-----")
    page_of, page = [], 0
    for ln in lines:
        if re.fullmatch(r"-{3,}", ln.strip()):
            page += 1
        page_of.append(page)
    n_pages = page + 1

    pages_with: dict[str, set[int]] = {}
    for ln, pg in zip(lines, page_of):
        if (ln.strip() and len(ln) < 140 and not LIST_RE.match(ln)
                and not ln.lstrip().startswith("|")):
            pages_with.setdefault(key(ln), set()).add(pg)
    # En-tête/pied de page : ligne courte présente sur au moins 25 % des pages (minimum 3)
    min_pages = max(3, 0.25 * n_pages)
    noise = {k for k, pgs in pages_with.items() if k and len(pgs) >= min_pages}

    out = []
    for ln in lines:
        stripped = ln.strip()
        if re.fullmatch(r"-{3,}", stripped) or PAGE_NUM_RE.match(stripped.strip("*_ ")):
            continue
        if stripped and key(ln) in noise:
            continue
        out.append(ln)
    return out


def _normalize_heading_levels(lines: list[str]) -> list[str]:
    levels = sorted({len(m.group(1)) for ln in lines if (m := HEADING_RE.match(ln))})
    remap = {lvl: i + 1 for i, lvl in enumerate(levels)}
    out = []
    for ln in lines:
        m = HEADING_RE.match(ln)
        if m:
            text = _clean_heading_text(m.group(2))
            out.append(f"{'#' * remap[len(m.group(1))]} {text}" if text else "")
        else:
            out.append(ln)
    return out


BOLD_LINE_RE = re.compile(r"^\*\*(?!\*)(.+?)\*\*$")
LETTERED_RE = re.compile(r"^[A-Z]\.\s")


def _promote_bold_headings(lines: list[str]) -> list[str]:
    """Un bloc de 1 à 3 lignes entièrement en gras, isolé entre deux lignes vides, est un titre.

    Les titres du type "A. Mesures générales" passent un niveau sous le plus bas titre
    existant ; les autres (ex. "Réserves") un niveau en dessous.
    """
    max_level = max([len(m.group(1)) for ln in lines if (m := HEADING_RE.match(ln))], default=0)

    # Blocs de lignes consécutives non vides : (indice de début, lignes)
    blocks, start = [], None
    for i, ln in enumerate(lines + [""]):
        if ln.strip() and start is None:
            start = i
        elif not ln.strip() and start is not None:
            blocks.append((start, lines[start:i]))
            start = None

    # Si presque toutes les lignes sont isolées (une ligne vide entre chaque ligne), l'isolement
    # ne dit rien sur la structure : on ne promeut rien
    nonblank = [b for _, blk in blocks for b in blk]
    isolated = sum(1 for _, blk in blocks if len(blk) == 1)
    if nonblank and isolated / len(blocks) > 0.6 and len(blocks) > 20:
        return lines

    candidates = []  # (début, fin exclue, texte)
    for start, block in blocks:
        inners = []
        for ln in block:
            m = BOLD_LINE_RE.match(ln.strip())
            if not m or "**" in m.group(1) or LIST_RE.match(ln):
                break
            inners.append(m.group(1).strip())
        else:
            # Un titre en gras tient sur 1 à 3 lignes (titres longs coupés par la mise en page)
            text = " ".join(inners)
            if (len(inners) <= 3 and len(text) <= 220
                    and not text.endswith(TERMINAL + (",",)) and not PAGE_NUM_RE.match(text)):
                candidates.append((start, start + len(block), text))

    has_lettered = any(LETTERED_RE.match(t) for _, _, t in candidates)
    lettered_level = min(max_level + 1, 6)
    out = list(lines)
    for start, end, text in candidates:
        level = lettered_level if LETTERED_RE.match(text) else max_level + (2 if has_lettered else 1)
        out[start] = f"{'#' * min(level, 6)} {text}"
        for j in range(start + 1, end):
            out[j] = ""

    # Titres lettrés ("J. Suite donnée…") déjà détectés par la police : même niveau que "A.", "B."
    last_letter = ""
    for i, ln in enumerate(out):
        m = HEADING_RE.match(ln)
        mm = m and re.match(r"^([A-Z])\.\s", m.group(2))
        if not mm:
            continue
        letter = mm.group(1)
        # "I." est un chiffre romain, sauf s'il suit "H."
        if letter in "IVX" and not (letter == "I" and last_letter == "H"):
            continue
        last_letter = letter
        if has_lettered:
            out[i] = f"{'#' * lettered_level} {m.group(2)}"
    return out


def _wrap_threshold(lines: list[str]) -> float:
    lengths = sorted(len(ln) for ln in lines
                     if ln.strip() and not _is_structural(ln) and len(ln) > 20)
    if not lengths:
        return float("inf")
    return 0.8 * lengths[int(0.9 * (len(lengths) - 1))]


def _join(prev: str, nxt: str) -> str:
    # Les césures ("mot- suite") sont résolues plus tard par _fix_hyphenation
    return prev + " " + nxt.lstrip()


WORD_RE = re.compile(r"[a-zà-ÿœ]+", re.IGNORECASE)


def _fix_hyphenation(text: str) -> str:
    """Recolle les mots coupés en fin de ligne, en s'appuyant sur le vocabulaire du document."""
    vocab = Counter(w.lower() for w in WORD_RE.findall(text))
    letters = "a-zà-ÿœ"

    # 1) "hiérar- chiquement", "bien- être", "socio-<br>éducatifs"
    def hyphen(m: re.Match) -> str:
        a, sep, b = m.group(1), m.group(2), m.group(3)
        if b.lower() in CONNECTORS:
            return m.group(0)
        if vocab[(a + b).lower()] > 0:
            return a + b
        if vocab[f"{a}-{b}".lower()] > 0 or "<br>" in sep:
            return f"{a}-{b}"
        # Autres cas : césure de fin de ligne ordinaire
        return a + b

    hyph_pat = re.compile(rf"([{letters}]{{2,}})-(\s+|<br>)([{letters}]{{2,}})", re.IGNORECASE)
    text = hyph_pat.sub(hyphen, text)

    # 2) "péda gogiques", "l’éla boration" : le mot recollé existe ailleurs dans le document
    pair_pat = re.compile(rf"(?<![{letters}])([{letters}]{{2,}}) ([{letters}]{{2,}})(?![{letters}])",
                          re.IGNORECASE)

    def pair(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        joined = (a + b).lower()
        if (vocab[joined] > 0 and vocab[a.lower()] < vocab[joined]
                and a.lower() not in CONNECTORS and b.lower() not in CONNECTORS):
            return a + b
        return m.group(0)

    return pair_pat.sub(pair, text)


def _merge_paragraphs(lines: list[str]) -> list[str]:
    thr = _wrap_threshold(lines)

    # Lignes non vides avec le nombre de lignes vides qui les précèdent
    items: list[tuple[str, int]] = []
    blanks = 0
    for ln in lines:
        if ln.strip():
            items.append((ln.rstrip(), blanks))
            blanks = 0
        else:
            blanks += 1

    # Mode du document : une ligne vide sépare-t-elle deux lignes d'un même paragraphe ?
    n0 = n1 = 0
    for (prev, _), (cur, bb) in zip(items, items[1:]):
        if len(prev) >= thr and not _is_structural(prev) and not _is_structural(cur):
            n1 += bb > 0
            n0 += bb == 0
    blank_breaks = n0 > n1

    out: list[str] = []
    para: str | None = None
    prev_len = 0
    prev_line = ""
    list_open = False
    last_level = 1
    in_code = False

    def flush():
        nonlocal para
        if para is not None:
            out.extend([para, ""])
            para = None

    for i, (ln, bb) in enumerate(items):
        if in_code or ln.lstrip().startswith("```"):
            flush()
            if ln.lstrip().startswith("```"):
                in_code = not in_code
            out.append(ln)
            prev_len = 0
            continue
        if _is_structural(ln):
            flush()
            m = HEADING_RE.match(ln)
            if m:
                last_level = len(m.group(1))
                out.extend(["", ln, ""])
            else:
                if bb > 0 and out and out[-1] != "":
                    out.append("")
                out.append(ln)
            list_open = bool(LIST_RE.match(ln))
            prev_len = 0
            continue

        # Puce coupée sur deux lignes : la suite en minuscule est recollée à la puce
        if (list_open and out and LIST_RE.match(out[-1]) and ln.lstrip()[:1].islower()
                and not out[-1].endswith(TERMINAL)):
            out[-1] = out[-1] + " " + ln.strip()
            continue
        list_open = False

        # Suite évidente : la ligne précédente n'est pas terminée et celle-ci commence en minuscule
        continues = (not prev_line.rstrip("*_ ").endswith(TERMINAL)
                     and ln.lstrip("*_ ")[:1].islower() and prev_len > 0)
        # Paragraphe coupé par un saut de page : ligne vide, mais phrase manifestement inachevée
        page_break_continuation = continues and prev_len >= thr
        join = (para is not None and (prev_len >= thr or continues)
                and (not (blank_breaks and bb > 0) or page_break_continuation))
        if join:
            para = _join(para, ln)
        elif para is not None and bb == 0:
            # Lignes courtes consécutives (liste d'items, sommaire) : on garde le retour à la ligne
            para = para + chr(10) + ln.strip()
        else:
            flush()
            nxt = items[i + 1] if i + 1 < len(items) else None
            # Sous-titre isolé : ligne courte sans ponctuation suivie d'un paragraphe
            if (blank_breaks and nxt and nxt[1] == 0 and not _is_structural(nxt[0])
                    and len(nxt[0]) >= thr and len(ln) < 70 and ln[:1].isupper()
                    and not ln.endswith(SENTENCE_END) and not ln[-1:].isdigit()):
                out.extend(["", f"{'#' * min(last_level + 1, 6)} {ln.strip()}", ""])
                prev_len = 0
                continue
            para = ln.strip()
        prev_len = len(ln)
        prev_line = ln.rstrip()
    flush()
    return out


def _merge_headings(lines: list[str]) -> list[str]:
    """Fusionne les titres consécutifs de même niveau (titre coupé) et supprime les doublons."""
    out: list[str] = []
    prev_heading_idx = None
    for ln in lines:
        m = HEADING_RE.match(ln)
        if m and prev_heading_idx is not None:
            pm = HEADING_RE.match(out[prev_heading_idx])
            same_level = len(pm.group(1)) == len(m.group(1))
            if pm.group(2).lower() == m.group(2).lower():
                continue
            # Titre coupé : même niveau, ou début qui se termine par un mot de liaison,
            # ou suite qui commence par une minuscule
            last_word = re.sub(r"\W+$", "", pm.group(2)).split(" ")[-1].lower()
            dangling = last_word in CONNECTORS or pm.group(2).lower().endswith(("l’", "d’", "l'", "d'"))
            # Jamais de fusion avec un titre numéroté ("I. Introduction", "A. …", "3.1 …")
            numbered = bool(re.match(r"^([IVX]+|[A-Z]|\d+(\.\d+)*)[.)]?\s", m.group(2)))
            if not numbered and (same_level or dangling or m.group(2)[:1].islower()):
                out[prev_heading_idx] = f"{pm.group(1)} {pm.group(2)} {m.group(2)}"
                continue
        if m:
            prev_heading_idx = len(out)
        elif ln.strip():
            prev_heading_idx = None
        out.append(ln)
    return out


def postprocess_markdown(text: str) -> str:
    text = text.replace("\u00ad ", "").replace("\u00ad", "")
    text = text.replace("** **", " ").replace("\u00a0", " ")
    # Exposants d'ordinaux : "2512 [e]" -> "2512e", "n [os]" -> "nos"
    text = re.sub(r"(?<=\w) ?\[(e|er|re|es|os|o|ème|d|nd)\]", r"\1", text)
    lines = text.splitlines()
    lines = _remove_page_noise(lines)
    lines = _normalize_heading_levels(lines)
    lines = _promote_bold_headings(lines)
    lines = _merge_paragraphs(lines)
    lines = _merge_headings(lines)
    result = "\n".join(lines)
    # Gras/italique coupés d'une ligne à l'autre : "**a** **b**" -> "**a b**"
    result = re.sub(r"\*\*\s+\*\*", " ", result)
    result = re.sub(r"_\s+_", " ", result)
    result = _fix_hyphenation(result)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result + "\n"
