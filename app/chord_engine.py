"""
Chord transposition engine for Chordbook.

Supports:
- Root note with optional sharp/flat
- Quality: m, maj7, m7, 7, sus4, dim, aug, add9, 6, etc.
- Bass note: C/G, Am/E, etc.
- Slash chords: D/F#, Bm/D
"""
import re

# 12-tone chromatic scale
SHARP_KEYS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_KEYS  = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

# Note→index map
NOTE_TO_INDEX = {}
for i, n in enumerate(SHARP_KEYS):
    NOTE_TO_INDEX[n] = i
for i, n in enumerate(FLAT_KEYS):
    if n not in NOTE_TO_INDEX:
        NOTE_TO_INDEX[n] = i

# Regex to parse chord: root + quality + optional /bass
CHORD_RE = re.compile(r"^([A-G][#b]?)(.*?)(?:\/([A-G][#b]?))?$")


def parse_chord(chord):
    """Split chord into (root, quality, bass)."""
    m = CHORD_RE.match(chord.strip())
    if not m:
        return None
    root, quality, bass = m.groups()
    return root, quality or "", bass or ""


def transpose_note(note, semitones, prefer="sharp"):
    """Transpose a single note by N semitones."""
    if note not in NOTE_TO_INDEX:
        return note
    idx = NOTE_TO_INDEX[note]
    new_idx = (idx + semitones) % 12
    return SHARP_KEYS[new_idx] if prefer == "sharp" else FLAT_KEYS[new_idx]


def transpose_chord(chord, semitones, prefer="sharp"):
    """Transpose a chord symbol by N semitones."""
    parsed = parse_chord(chord)
    if not parsed:
        return chord
    root, quality, bass = parsed
    new_root = transpose_note(root, semitones, prefer)
    new_bass = transpose_note(bass, semitones, prefer) if bass else ""
    if new_bass:
        return f"{new_root}{quality}/{new_bass}"
    return f"{new_root}{quality}"


def transpose_song(song, semitones):
    """Transpose every chord in the song data structure."""
    if semitones == 0:
        return song

    prefer = "flat" if "b" in song.get("key", "") else "sharp"
    out = dict(song)
    out["content"] = {"blocks": []}
    if song.get("key"):
        out["key"] = transpose_chord(song["key"], semitones, prefer)

    for block in song.get("content", {}).get("blocks", []):
        new_block = dict(block)
        new_block["lines"] = []
        for line in block.get("lines", []):
            new_line = dict(line)
            new_line["chords"] = [
                {**c, "symbol": transpose_chord(c["symbol"], semitones, prefer)}
                for c in line.get("chords", [])
            ]
            new_block["lines"].append(new_line)
        out["content"]["blocks"].append(new_block)
    return out


def validate_chord(chord):
    """Return True if chord parses."""
    return parse_chord(chord) is not None


def parse_chord_line(line):
    """Parse 'Am    F    C    G' → ['Am', 'F', 'C', 'G']."""
    return [t for t in line.split() if t]


def format_chord_display(chord):
    """Pretty-print a chord symbol."""
    return chord.strip()
