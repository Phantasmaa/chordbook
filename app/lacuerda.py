"""
LaCuerda.net scraper for Chordbook.
URL format: https://acordes.lacuerda.net/TXT/<artist>/<song>.txt

File structure:
- ASCII art header (====)
- META lines (| ARTISTA: ..., | CANCION: ..., etc.)
- Sections separated by blank lines:
    * Section name + ":" possibly (e.g. "lntro: E F# A E x2")
    * Alternating: chord line / lyric line / chord line / lyric line ...
- The lyrics have chords placed **inline at the column position** of the syllable.
  E.g.
       E                    F#
    Estoy solo y triste acá en este mundo
"""

import re
from typing import Dict, List, Optional, Tuple

# Reasonable browser UA to avoid datacenter flags
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Example known spot-check
SPOTCHECK_URL = "https://acordes.lacuerda.net/TXT/gatos/la_balsa.txt"


def _find_chord_positions(chord_line: str, lyrics_line: str) -> List[Dict]:
    """
    Given a chord line like '       E                    F#' (chord strings
    sitting at specific column positions) and a lyrics line like
    'acá en este mundo abandonado', return a list of
        {symbol: 'E', pos: 0} where pos is the column (0-based) at which the
    chord sits RELATIVE TO THE LYRIC's first non-whitespace character.

    Why: LaCuerda's chord line tracks the *display column* of the lyric.
    When the lyric starts with a leading indent (e.g. "  Estoy muy solo"),
    the chord at column 0 lines up with the first letter "E". So the chord
    column should be measured *relative to the lyric's indent*, not absolute.
    Concretely: `pos = chord_column - leading_indent_of_lyric_line`.
    """
    # Find the lyric's leading indentation
    lyric_lead = len(lyrics_line) - len(lyrics_line.lstrip())
    chords: List[Dict] = []

    for m in re.finditer(r"\S+", chord_line):
        symbol = m.group(0).strip()
        if not symbol or not re.search(r"[A-Za-z]", symbol):
            continue
        # Column-relative to the lyric's first letter
        col = max(0, m.start() - lyric_lead)
        chords.append({"symbol": symbol, "pos": col})
    return chords


def _normalize_section_name(name: str) -> str:
    """
    LaCuerda uses lowercase names like `lntro`, `verso`, `coro`, `puente`,
    `estribillo`, `outro`, etc. We map them to canonical labels.
    """
    n = name.strip().lower().rstrip(":")
    mapping = {
        "lntro": "INTRO",
        "intro": "INTRO",
        "verso": "VERSO",
        "verse": "VERSO",
        "coro": "CORO",
        "estribillo": "CORO",
        "chorus": "CORO",
        "puente": "PUENTE",
        "bridge": "PUENTE",
        "outro": "OUTRO",
        "final": "OUTRO",
        "pre-coro": "PRE-CORO",
        "precoro": "PRE-CORO",
        "precorro": "PRE-CORO",
        "interludio": "INTERLUDIO",
        "solo": "SOLO",
    }
    return mapping.get(n, n.upper())


def parse_lacuerda_txt(raw: str) -> Dict:
    """
    Parse a raw LaCuerda TXT into a Chordbook-ready dict:

        {
            "title": "La Balsa",
            "artist": "los Gatos",
            "blocks": [
                {"name": "VERSO", "lines": [
                    {"text": "...", "chords": [{"symbol":"Am", "pos":5}]},
                    ...
                ]},
                ...
            ],
            "intro_chords": ["E", "F#", "A", "E"],
        }

    Lines without a chord line (only lyrics) get an empty chord list.
    """
    lines = raw.splitlines()

    # 1) Extract header metadata
    title = ""
    artist = ""
    for ln in lines[:30]:
        m_art = re.match(r"\|\s*ARTISTA:\s*(.+?)\s*\|", ln)
        m_sng = re.match(r"\|\s*CANCION:\s*(.+?)\s*\|", ln)
        if m_art:
            artist = m_art.group(1).strip()
        if m_sng:
            title = m_sng.group(1).strip().title()

    # 2) Stop at the footer — many LaCuerda files end with
    # "=========================== lacuerda.net ============================"
    end = len(lines)
    for j, ln in enumerate(lines):
        if "lacuerda.net" in ln and "===" in ln and j > 30:
            end = j
            break

    # 3) Find first content line (skip ASCII decorations & header bar)
    start = 0
    for i in range(min(end, len(lines))):
        ln = lines[i]
        if "|" in ln and ("ARTISTA" in ln or "CANCION" in ln):
            continue
        if ln.strip().startswith(("=", "+", "|")):
            continue
        if not ln.strip():
            continue
        start = i
        break

    # 3) Walk through content lines. Two consecutive lines with the second
    # being "lyrics-only" form a chord-lyric pair. A blank line breaks pairs.
    blocks: List[Dict] = []
    current_block: Dict = {"name": "VERSO", "lines": []}
    intro_chords: List[str] = []

    i = start
    n = end

    while i < n:
        ln = lines[i]
        stripped = ln.strip()

        # Section header? "intro: E F# A E x2" or "verso 1:"
        # Only treat as section header if it has a colon (or known word).
        sec_match = re.match(r"^([a-zA-ZñáéíóúÁÉÍÓÚ\s\-]+)\s*:\s*(.*)$", stripped)
        if sec_match and re.search(r"[a-zA-Z]", sec_match.group(1)):
            name_raw = sec_match.group(1)
            rest = sec_match.group(2).strip()
            # If rest is purely chord-like text (allow 'x 2' suffixes, '(2)' etc),
            # treat as INTRO chord progression
            rest_clean = re.sub(r"x\s*\d+", "", rest)
            rest_clean = re.sub(r"\(\d+\)", "", rest_clean)
            rest_clean = rest_clean.strip()
            chord_tokens = re.findall(
                r"[A-G][#b]?(?:m|maj[7]?|sus[24]?|add[0-9]+|[0-9](?:sus)?)?",
                rest_clean,
            )
            # Reject if rest contains uppercase letters beyond chord tokens
            rest_punct = re.sub(
                r"[A-G][#b]?(?:m|maj[7]?|sus[24]?|add[0-9]+|[0-9](?:sus)?)?",
                "",
                rest_clean,
            )
            rest_punct = re.sub(r"[\s,]", "", rest_punct)
            if (
                rest_clean
                and chord_tokens
                and not rest_punct
                and len(rest_clean) < 80
            ):
                # Detect "x<num>" suffix
                mul = 1
                mul_m = re.search(r"x\s*(\d+)", rest)
                if mul_m:
                    mul = int(mul_m.group(1))
                intro_chords = chord_tokens * mul
                # don't open a new block; these go in song-level intro
                i += 1
                continue
            else:
                # Section name only — open a new block
                new_name = _normalize_section_name(name_raw)
                if current_block["lines"]:
                    blocks.append(current_block)
                current_block = {"name": new_name, "lines": []}
                i += 1
                continue

        # Empty line: block separator
        if not stripped:
            if current_block["lines"]:
                blocks.append(current_block)
                current_block = {"name": "VERSO", "lines": []}
            i += 1
            continue

        # Maybe chord line (no letters outside chord symbols) + lyrics line
        # Heuristic: next line is the lyrics IF:
        #   - current line has chord-like tokens
        #   - next line exists and is not blank
        #   - current line length <= next line length  (so chord 'fits' over lyric)
        # AND the lyrics line is not itself a section header.
        # We are conservative: if current line is ONLY chord-symbol-looking
        # content (no spaces inside words that look like Spanish words),
        # we treat it as a chord line.
        def looks_like_chord_line(s: str) -> bool:
            # Has at least one chord-like token
            tokens = re.findall(r"[A-G][#b]?(?:m|maj|sus[24]?|add[0-9]+|[0-9])?(?:\(.*?\))?",
                                s)
            if not tokens:
                return False
            # If the strip has only those tokens + spaces/indent, it's a chord line
            stripped = s.strip()
            rebuilt = " ".join(tokens)
            return rebuilt.replace(" ", "") == stripped.replace(" ", "")

        # Standalone chord progression line (no lyrics below) — skip
        if looks_like_chord_line(ln) and (i + 1 >= n or not lines[i + 1].strip()):
            i += 1
            continue

        if (
            i + 1 < n
            and looks_like_chord_line(ln)
            and lines[i + 1].strip() != ""
            and not re.match(
                r"^[a-zA-ZñáéíóúÁÉÍÓÚ\s\-]+\s*:",
                lines[i + 1].strip(),
            )
        ):
            chord_line = ln
            lyric_line = lines[i + 1]
            positions = _find_chord_positions(chord_line, lyric_line)
            current_block["lines"].append(
                {"text": lyric_line.rstrip(), "chords": positions}
            )
            i += 2
            continue

        # Otherwise treat as a lyrics-only line with no chord above
        current_block["lines"].append({"text": ln.rstrip(), "chords": []})
        i += 1

    if current_block["lines"]:
        blocks.append(current_block)

    # Filter out empty blocks
    blocks = [b for b in blocks if b["lines"]]

    # If a block contains ONLY an intro progression line (like "E F# A E"),
    # lift that to the song intro_chords list and drop the block.
    cleaned_blocks: List[Dict] = []
    for b in blocks:
        only_intro = (
            len(b["lines"]) == 1
            and not b["lines"][0]["text"].strip()
            and not b["lines"][0]["chords"]
        )
        if only_intro:
            continue
        cleaned_blocks.append(b)

    return {
        "title": title or "Sin título",
        "artist": artist or "",
        "intro_chords": intro_chords,
        "blocks": cleaned_blocks,
    }


def fetch_lacuerda(url: str) -> Dict:
    """
    Fetch the .txt from LaCuerda and return parsed Chordbook dict.
    Accepts:
      * https://acordes.lacuerda.net/TXT/<artist>/<song>.txt
      * https://acordes.lacuerda.net/<artist>/<song> (will rewrite to .txt)
    Raises RuntimeError on failure.
    """
    import requests

    if not url:
        raise RuntimeError("URL vacía")

    # Normalize to .txt endpoint if user pasted a normal page URL
    clean = url.strip()
    if not clean.startswith(("http://", "https://")):
        clean = "https://" + clean

    if "/TXT/" not in clean:
        # Rewrite: https://acordes.lacuerda.net/<artist>/<song>[/]
        # → https://acordes.lacuerda.net/TXT/<artist>/<song>.txt
        parsed = re.match(
            r"^https?://(acordes\.lacuerda\.net)/([^?#]+?)(?:\.shtml)?/?$",
            clean,
        )
        if not parsed:
            raise RuntimeError(
                "URL no parece de LaCuerda (esperado: acordes.lacuerda.net/...)"
            )
        host = parsed.group(1)
        path = parsed.group(2)
        clean = f"https://{host}/TXT/{path}.txt"

    try:
        resp = requests.get(
            clean,
            headers={"User-Agent": USER_AGENT, "Accept": "text/plain,*/*"},
            timeout=15,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Error de red: {e}") from e

    if resp.status_code == 404:
        raise RuntimeError(
            "No se encontró el archivo .txt en LaCuerda. "
            "Verificá que la URL apunta a una canción existente."
        )
    if resp.status_code != 200:
        raise RuntimeError(f"LaCuerda respondió {resp.status_code}")

    raw = resp.text
    if "TABLATURAS Y ACORDES" not in raw and "|" not in raw[:400]:
        raise RuntimeError(
            "La página de LaCuerda no parece tener acordes. "
            "Asegurate de pegar el link de una canción (no de un artista)."
        )

    parsed = parse_lacuerda_txt(raw)
    parsed["source_url"] = clean
    return parsed


def blocks_to_chordbook_blocks(parsed: Dict) -> List[Dict]:
    """
    Convert parsed dict to the shape the Chordbook editor uses, with a
    leading INTRO line if intro_chords exist.
    """
    out: List[Dict] = []
    if parsed.get("intro_chords"):
        intro_text = " ".join(parsed["intro_chords"])
        out.append(
            {
                "name": "INTRO",
                "lines": [
                    {"text": "", "chords": [
                        {"symbol": c, "pos": 0} for c in parsed["intro_chords"]
                    ]}
                ],
            }
        )

    for b in parsed["blocks"]:
        out.append(b)
    return out
