"""
Chordbook — letra + acordes + PDF

Backend Flask para gestión de canciones con acordes posicionados
sobre la letra, transposición, setlists, y export a PDF profesional.
"""
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import (
    Flask, abort, jsonify, render_template,
    request, send_file, url_for,
)

from app.chord_engine import (
    transpose_chord, transpose_song, validate_chord,
    parse_chord_line, format_chord_display,
)

# ---------- Config ----------

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = BASE_DIR / "uploads"
DB_PATH = DATA_DIR / "chordbook.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Sharp keys + flat keys for transpose
KEYS_SHARP = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
KEYS_FLAT  = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]
# map sharp→flat for display
SHARP_TO_FLAT = {"C#": "Db", "D#": "Eb", "F#": "Gb", "G#": "Ab", "A#": "Bb"}
FLAT_TO_SHARP = {v: k for k, v in SHARP_TO_FLAT.items()}

app = Flask(__name__, template_folder=str(BASE_DIR / "templates"), static_folder=str(BASE_DIR / "static"))
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5MB upload cap


def _chord_alignment(chords, text):
    """Render chord line for PDF: spaces + chord symbol at each position."""
    if not chords:
        return ""
    max_pos = max(c["position"] for c in chords)
    width = max(max_pos + len(max((c["symbol"] for c in chords), key=len)) + 1, len(text) + 4)
    out = [" "] * width
    for c in chords:
        sym = c["symbol"]
        pos = c["position"]
        for i, ch in enumerate(sym):
            if pos + i < width:
                out[pos + i] = ch
    return "".join(out).rstrip()


app.jinja_env.globals["_chord_alignment"] = _chord_alignment


# ---------- DB ----------

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db():
    """Create schema if not exists."""
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS songs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        artist TEXT,
        album TEXT,
        key TEXT DEFAULT 'C',
        capo INTEGER DEFAULT 0,
        tempo INTEGER DEFAULT 120,
        time_signature TEXT DEFAULT '4/4',
        content TEXT NOT NULL,
        tags TEXT,                       -- comma-separated
        notes TEXT,
        source_url TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS setlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS setlist_songs (
        setlist_id INTEGER NOT NULL,
        song_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        transposed_key TEXT,
        PRIMARY KEY (setlist_id, song_id),
        FOREIGN KEY (setlist_id) REFERENCES setlists(id) ON DELETE CASCADE,
        FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_songs_title ON songs(title);
    CREATE INDEX IF NOT EXISTS idx_songs_artist ON songs(artist);
    CREATE INDEX IF NOT EXISTS idx_songs_key ON songs(key);
    """)
    db.commit()
    db.close()


init_db()


# ---------- Helpers ----------

def row_to_song(row, include_content=True):
    """Convert DB row to dict, parsing JSON content."""
    d = dict(row)
    if include_content and d.get("content"):
        try:
            d["content"] = json.loads(d["content"])
        except (json.JSONDecodeError, TypeError):
            d["content"] = {"blocks": []}
    else:
        d["content"] = {"blocks": []}
    if d.get("tags"):
        d["tags"] = [t.strip() for t in d["tags"].split(",") if t.strip()]
    else:
        d["tags"] = []
    return d


def get_song_or_404(song_id):
    db = get_db()
    row = db.execute("SELECT * FROM songs WHERE id = ?", (song_id,)).fetchone()
    db.close()
    if not row:
        abort(404)
    return row_to_song(row)


# ---------- Routes: pages ----------

@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "").strip()
    key_filter = request.args.get("key", "").strip()
    tag_filter = request.args.get("tag", "").strip()

    sql = "SELECT id, title, artist, key, tempo, updated_at FROM songs WHERE 1=1"
    params = []
    if q:
        sql += " AND (title LIKE ? OR artist LIKE ? OR tags LIKE ?)"
        like = f"%{q}%"
        params.extend([like, like, like])
    if key_filter:
        sql += " AND key = ?"
        params.append(key_filter)
    if tag_filter:
        sql += " AND tags LIKE ?"
        params.append(f"%{tag_filter}%")
    sql += " ORDER BY updated_at DESC"

    rows = db.execute(sql, params).fetchall()
    db.close()
    songs = [dict(r) for r in rows]
    return render_template("index.html", songs=songs, q=q, key_filter=key_filter,
                          tag_filter=tag_filter, keys_sharp=KEYS_SHARP, keys_flat=KEYS_FLAT)


@app.route("/song/<int:song_id>")
def song_editor(song_id):
    song = get_song_or_404(song_id)
    return render_template("editor.html", song=song, keys_sharp=KEYS_SHARP, keys_flat=KEYS_FLAT)


@app.route("/song/<int:song_id>/preview")
def song_preview(song_id):
    song = get_song_or_404(song_id)
    transpose = request.args.get("transpose", 0, type=int)
    if transpose != 0:
        song = transpose_song(song, transpose)
    return render_template("preview.html", song=song)


@app.route("/new")
def new_song():
    return render_template("editor.html", song={
        "id": None,
        "title": "Nueva canción",
        "artist": "",
        "album": "",
        "key": "C",
        "capo": 0,
        "tempo": 120,
        "time_signature": "4/4",
        "content": {"blocks": [{
            "type": "verse", "name": "Verso 1", "lines": [{"chords": [], "text": ""}]
        }]},
        "tags": [],
        "notes": "",
        "source_url": "",
    }, keys_sharp=KEYS_SHARP, keys_flat=KEYS_FLAT)


@app.route("/setlists")
def setlists_index():
    db = get_db()
    rows = db.execute("SELECT * FROM setlists ORDER BY created_at DESC").fetchall()
    db.close()
    return render_template("setlists.html", setlists=[dict(r) for r in rows])


@app.route("/setlist/<int:setlist_id>")
def setlist_view(setlist_id):
    db = get_db()
    sl = db.execute("SELECT * FROM setlists WHERE id = ?", (setlist_id,)).fetchone()
    if not sl:
        abort(404)
    songs = db.execute("""
        SELECT s.*, ss.position, ss.transposed_key
        FROM setlist_songs ss
        JOIN songs s ON s.id = ss.song_id
        WHERE ss.setlist_id = ?
        ORDER BY ss.position
    """, (setlist_id,)).fetchall()
    db.close()
    return render_template("setlist.html", setlist=dict(sl), songs=[dict(r) for r in songs])


# ---------- Routes: API ----------

@app.route("/api/songs", methods=["POST"])
def create_song():
    data = request.get_json(force=True)
    if not data.get("title"):
        return jsonify({"error": "title required"}), 400

    db = get_db()
    cur = db.execute("""
        INSERT INTO songs (title, artist, album, key, capo, tempo, time_signature,
                           content, tags, notes, source_url)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["title"].strip(),
        data.get("artist", "").strip(),
        data.get("album", "").strip(),
        data.get("key", "C"),
        int(data.get("capo", 0) or 0),
        int(data.get("tempo", 120) or 120),
        data.get("time_signature", "4/4"),
        json.dumps(data.get("content", {"blocks": []})),
        ",".join(data.get("tags", [])),
        data.get("notes", ""),
        data.get("source_url", ""),
    ))
    db.commit()
    song_id = cur.lastrowid
    db.close()
    return jsonify({"id": song_id}), 201


@app.route("/api/songs/<int:song_id>", methods=["PUT"])
def update_song(song_id):
    data = request.get_json(force=True)
    db = get_db()
    existing = db.execute("SELECT id FROM songs WHERE id = ?", (song_id,)).fetchone()
    if not existing:
        db.close()
        return jsonify({"error": "not found"}), 404

    db.execute("""
        UPDATE songs SET
            title = ?, artist = ?, album = ?, key = ?, capo = ?, tempo = ?,
            time_signature = ?, content = ?, tags = ?, notes = ?, source_url = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (
        data.get("title", "").strip(),
        data.get("artist", "").strip(),
        data.get("album", "").strip(),
        data.get("key", "C"),
        int(data.get("capo", 0) or 0),
        int(data.get("tempo", 120) or 120),
        data.get("time_signature", "4/4"),
        json.dumps(data.get("content", {"blocks": []})),
        ",".join(data.get("tags", [])) if isinstance(data.get("tags"), list) else data.get("tags", ""),
        data.get("notes", ""),
        data.get("source_url", ""),
        song_id,
    ))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/songs/<int:song_id>", methods=["DELETE"])
def delete_song(song_id):
    db = get_db()
    db.execute("DELETE FROM songs WHERE id = ?", (song_id,))
    db.commit()
    db.close()
    return jsonify({"ok": True})


@app.route("/api/songs/<int:song_id>/transpose", methods=["POST"])
def api_transpose(song_id):
    """Return song with all chords transposed by N semitones."""
    data = request.get_json(force=True) or {}
    n = int(data.get("semitones", 0))
    song = get_song_or_404(song_id)
    transposed = transpose_song(song, n)
    return jsonify(transposed)


# ---------- Routes: PDF export ----------

@app.route("/api/songs/<int:song_id>/pdf")
def export_pdf(song_id):
    song = get_song_or_404(song_id)
    transpose = request.args.get("transpose", 0, type=int)
    if transpose != 0:
        song = transpose_song(song, transpose)

    # Render HTML for PDF
    html = render_template("pdf.html", song=song)

    # Generate PDF
    from weasyprint import HTML
    from weasyprint.text.fonts import FontConfiguration

    pdf_bytes = HTML(string=html, base_url=str(BASE_DIR)).write_pdf(
        font_config=FontConfiguration()
    )

    safe_title = re.sub(r"[^\w-]+", "_", song["title"]).strip("_")
    fname = f"{safe_title}_{song['key']}.pdf"
    return send_file(
        __import__("io").BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=fname,
    )


@app.route("/api/setlists", methods=["POST"])
def create_setlist():
    data = request.get_json(force=True)
    if not data.get("name"):
        return jsonify({"error": "name required"}), 400
    db = get_db()
    cur = db.execute("INSERT INTO setlists (name, description) VALUES (?, ?)",
                    (data["name"].strip(), data.get("description", "")))
    db.commit()
    db.close()
    return jsonify({"id": cur.lastrowid}), 201


@app.route("/api/setlists/<int:setlist_id>/pdf")
def export_setlist_pdf(setlist_id):
    db = get_db()
    sl = db.execute("SELECT * FROM setlists WHERE id = ?", (setlist_id,)).fetchone()
    if not sl:
        abort(404)
    songs = db.execute("""
        SELECT s.*, ss.transposed_key
        FROM setlist_songs ss
        JOIN songs s ON s.id = ss.song_id
        WHERE ss.setlist_id = ?
        ORDER BY ss.position
    """, (setlist_id,)).fetchall()
    db.close()

    songs_data = []
    for row in songs:
        s = row_to_song(row)
        if row["transposed_key"]:
            s = transpose_song(s, _key_diff(s["key"], row["transposed_key"]))
        songs_data.append(s)

    html = render_template("pdf_setlist.html", setlist=dict(sl), songs=songs_data)
    from weasyprint import HTML
    from io import BytesIO
    pdf_bytes = HTML(string=html, base_url=str(BASE_DIR)).write_pdf()
    safe_name = re.sub(r"[^\w-]+", "_", sl["name"]).strip("_")
    return send_file(BytesIO(pdf_bytes), mimetype="application/pdf", as_attachment=True,
                    download_name=f"setlist_{safe_name}.pdf")


def _key_diff(from_key, to_key):
    """Compute semitone difference between two keys."""
    if from_key in KEYS_SHARP and to_key in KEYS_SHARP:
        return (KEYS_SHARP.index(to_key) - KEYS_SHARP.index(from_key)) % 12
    if from_key in KEYS_SHARP and to_key in KEYS_FLAT:
        return (KEYS_FLAT.index(to_key) - KEYS_SHARP.index(from_key)) % 12
    return 0


# ---------- Lyrics import (paste from internet) ----------

@app.route("/api/songs/import", methods=["POST"])
def import_lyrics():
    """Parse raw lyrics text, optionally with chords above."""
    data = request.get_json(force=True)
    raw = data.get("text", "")
    title = data.get("title", "Importado")
    artist = data.get("artist", "")

    blocks = parse_lyrics_text(raw)
    return jsonify({
        "title": title,
        "artist": artist,
        "key": "C",
        "tempo": 120,
        "content": {"blocks": blocks},
        "tags": [],
        "notes": "",
        "source_url": "",
    })


def parse_lyrics_text(raw):
    """
    Parse plain text into blocks.
    Recognizes section markers like [Verso 1], [Coro], etc.
    Lines that look like chords (Am, F#m, C7, etc.) get parsed separately.
    """
    lines = raw.split("\n")
    blocks = []
    current = {"type": "verse", "name": "Verso 1", "lines": []}
    pending_chord_line = None

    SECTION_PAT = re.compile(r"^\s*\[(.+?)\]\s*$")

    for line in lines:
        stripped = line.strip()

        # Section marker
        m = SECTION_PAT.match(line)
        if m:
            if current["lines"]:
                blocks.append(current)
            name = m.group(1).strip()
            current = {
                "type": _infer_section_type(name),
                "name": name,
                "lines": [],
            }
            pending_chord_line = None
            continue

        # Empty line = break between lines
        if not stripped:
            pending_chord_line = None
            continue

        # Check if this line is all chords (heuristic)
        tokens = stripped.split()
        if tokens and all(_looks_like_chord(t) for t in tokens):
            pending_chord_line = tokens
            continue

        # Regular lyrics line
        if pending_chord_line:
            # Map chord positions to text
            chars = list(stripped)
            chord_positions = _align_chords_to_text(pending_chord_line, stripped)
            current["lines"].append({
                "chords": chord_positions,
                "text": stripped,
            })
            pending_chord_line = None
        else:
            current["lines"].append({"chords": [], "text": stripped})

    if current["lines"]:
        blocks.append(current)
    if not blocks:
        blocks.append({"type": "verse", "name": "Verso 1", "lines": []})
    return blocks


def _infer_section_type(name):
    n = name.lower()
    if "coro" in n or "chorus" in n or "estribillo" in n:
        return "chorus"
    if "puente" in n or "bridge" in n:
        return "bridge"
    if "intro" in n:
        return "intro"
    if "outro" in n or "final" in n:
        return "outro"
    if "pre" in n:
        return "pre-chorus"
    return "verse"


def _looks_like_chord(token):
    """Heuristic: token looks like a chord."""
    return bool(re.match(r"^[A-G][#b]?(m|maj|min|dim|aug|sus|add)?\d*(\/[A-G][#b]?)?$", token))


def _align_chords_to_text(chords, text):
    """Best-effort: place each chord at the next whitespace position."""
    positions = []
    cursor = 0
    for ch in chords:
        # find next non-space position
        while cursor < len(text) and text[cursor] == " ":
            cursor += 1
        if cursor >= len(text):
            cursor = len(text) - 1
        positions.append({"symbol": ch, "position": cursor})
        # advance past next word
        while cursor < len(text) and text[cursor] != " ":
            cursor += 1
    return positions


# ---------- Health ----------

@app.route("/health")
def health():
    db = get_db()
    n = db.execute("SELECT COUNT(*) FROM songs").fetchone()[0]
    db.close()
    return jsonify({"status": "ok", "songs": n})


# ---------- Main ----------

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5101, debug=False)
