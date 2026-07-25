// Chordbook — editor logic
// Maneja: render de bloques, edición de letra, click-to-place acordes,
// auto-save, transpose, export.

const SONG = JSON.parse(document.getElementById('song-data').textContent);
let SONG_ID = SONG.id;  // null for new songs, set after first POST
const container = document.getElementById('blocks-container');
const statusEl = document.getElementById('save-status');
let saveTimer = null;
let dirty = false;

const SECTION_LABELS = {
  verse: 'Verso',
  chorus: 'Coro',
  bridge: 'Puente',
  intro: 'Intro',
  outro: 'Outro',
  'pre-chorus': 'Pre-coro',
};

// ---------- Render ----------

function render() {
  container.innerHTML = '';
  SONG.content.blocks.forEach((block, bi) => {
    container.appendChild(renderBlock(block, bi));
  });
}

function renderBlock(block, bi) {
  const wrap = document.createElement('div');
  wrap.className = 'block';
  wrap.dataset.blockIdx = bi;

  // Header
  const header = document.createElement('div');
  header.className = 'block-header';
  header.innerHTML = `
    <input type="text" class="block-name" value="${escapeHtml(block.name || '')}" data-block-idx="${bi}">
    <span class="block-type-tag">${SECTION_LABELS[block.type] || block.type}</span>
    <div class="block-controls">
      <button title="Mover arriba" data-action="up" data-block-idx="${bi}">↑</button>
      <button title="Mover abajo" data-action="down" data-block-idx="${bi}">↓</button>
      <button title="Duplicar" data-action="dup" data-block-idx="${bi}">⎘</button>
      <button title="Eliminar" class="danger" data-action="del" data-block-idx="${bi}">🗑</button>
    </div>
  `;
  wrap.appendChild(header);

  // Lines container
  const linesEl = document.createElement('div');
  linesEl.className = 'lines-container';
  block.lines.forEach((line, li) => {
    linesEl.appendChild(renderLine(line, bi, li));
  });

  // Bulk-paste button (mobile-friendly: large tap target)
  const pasteBtn = document.createElement('button');
  pasteBtn.className = 'paste-lyrics-btn';
  pasteBtn.textContent = '📋 Pegar letra';
  pasteBtn.dataset.blockIdx = bi;
  pasteBtn.dataset.action = 'paste-block';
  linesEl.appendChild(pasteBtn);

  // Add line button
  const addLineBtn = document.createElement('button');
  addLineBtn.className = 'add-line-btn';
  addLineBtn.textContent = '+ Agregar línea';
  addLineBtn.dataset.blockIdx = bi;
  addLineBtn.dataset.action = 'add-line';
  addLineBtn.dataset.lineIdx = '-1';  // signal: add at end
  linesEl.appendChild(addLineBtn);

  wrap.appendChild(linesEl);
  return wrap;
}

function renderLine(line, bi, li) {
  const wrap = document.createElement('div');
  wrap.className = 'line';
  wrap.dataset.lineIdx = li;

  // Chord line
  const chordLine = document.createElement('div');
  chordLine.className = 'line-chords';
  chordLine.style.position = 'relative';

  // Render chords as absolute spans
  if (line.chords) {
    line.chords.forEach((c, ci) => {
      const span = document.createElement('span');
      span.className = 'chord';
      span.textContent = c.symbol;
      span.style.left = c.position + 'ch';
      span.dataset.chordIdx = ci;
      span.dataset.blockIdx = bi;
      span.dataset.lineIdx = li;
      span.addEventListener('click', (e) => {
        e.stopPropagation();
        editChord(bi, li, ci, span);
      });
      chordLine.appendChild(span);
    });
  }
  wrap.appendChild(chordLine);

  // Text line
  const textEl = document.createElement('div');
  textEl.className = 'line-text';
  textEl.contentEditable = 'true';
  textEl.dataset.placeholder = 'Click para escribir letra…';
  textEl.spellcheck = false;
  textEl.autocapitalize = 'none';
  textEl.autocorrect = 'off';
  textEl.textContent = line.text || '';
  textEl.addEventListener('input', () => {
    line.text = textEl.innerText;
    dirty = true;
    scheduleAutoSave();
  });
  textEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      addLineAfter(bi, li);
    }
    if (e.key === 'Backspace' && textEl.innerText === '') {
      e.preventDefault();
      removeLine(bi, li);
    }
  });
  // Smart paste: split multi-line paste into separate lines
  textEl.addEventListener('paste', (e) => {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    if (!text) return;
    // If only one line, let default paste happen
    if (!/\r?\n/.test(text)) return;
    e.preventDefault();
    bulkPasteIntoBlock(bi, text, li);
  });
  // Click on text → place chord at click position
  textEl.addEventListener('click', (e) => {
    if (window.getSelection().toString()) return;
    if (e.target.classList.contains('chord')) return;
    const range = document.caretRangeFromPoint
      ? document.caretRangeFromPoint(e.clientX, e.clientY)
      : null;
    if (!range) return;
    const offset = textEl.innerText.slice(0, range.startOffset).length;
    openChordInput(bi, li, offset, e.clientX, e.clientY);
  });
  wrap.appendChild(textEl);

  // Line actions
  const actions = document.createElement('div');
  actions.className = 'line-actions';
  actions.innerHTML = `
    <button title="Agregar acorde" data-action="add-chord" data-block-idx="${bi}" data-line-idx="${li}">♪</button>
    <button title="Eliminar línea" class="danger" data-action="del-line" data-block-idx="${bi}" data-line-idx="${li}">×</button>
  `;
  wrap.appendChild(actions);

  return wrap;
}

// ---------- Block operations ----------

function addBlock(type) {
  const labels = {verse:'Verso', chorus:'Coro', bridge:'Puente', intro:'Intro', outro:'Outro', 'pre-chorus':'Pre-coro'};
  const baseName = labels[type] || type;
  // Find next number
  const existing = SONG.content.blocks.filter(b => b.type === type).length + 1;
  const name = existing === 1 ? baseName : `${baseName} ${existing}`;
  SONG.content.blocks.push({
    type,
    name,
    lines: [{chords: [], text: ''}],
  });
  dirty = true;
  render();
  scheduleAutoSave();
}

function moveBlock(bi, dir) {
  const blocks = SONG.content.blocks;
  const newIdx = bi + dir;
  if (newIdx < 0 || newIdx >= blocks.length) return;
  [blocks[bi], blocks[newIdx]] = [blocks[newIdx], blocks[bi]];
  dirty = true; render(); scheduleAutoSave();
}

function duplicateBlock(bi) {
  const blocks = SONG.content.blocks;
  const copy = JSON.parse(JSON.stringify(blocks[bi]));
  copy.name = copy.name + ' (copia)';
  blocks.splice(bi + 1, 0, copy);
  dirty = true; render(); scheduleAutoSave();
}

function deleteBlock(bi) {
  if (!confirm('¿Eliminar esta sección?')) return;
  SONG.content.blocks.splice(bi, 1);
  if (SONG.content.blocks.length === 0) {
    SONG.content.blocks.push({type: 'verse', name: 'Verso 1', lines: [{chords: [], text: ''}]});
  }
  dirty = true; render(); scheduleAutoSave();
}

// ---------- Bulk paste: split text into lines and append to a block ----------

function splitLyricsIntoLines(text) {
  // First try: split by newlines
  let parts = text.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
  if (parts.length > 1) return parts;
  // No newlines: split by sentence-ending punctuation followed by space
  parts = text.split(/(?<=[.!?…])\s+/).map(s => s.trim()).filter(Boolean);
  if (parts.length > 1) return parts;
  // No punctuation either: split by length (~50 chars per line)
  parts = [];
  const words = text.split(/\s+/);
  let cur = '';
  for (const w of words) {
    if (cur && (cur.length + 1 + w.length) > 50) {
      parts.push(cur);
      cur = w;
    } else {
      cur = cur ? cur + ' ' + w : w;
    }
  }
  if (cur) parts.push(cur);
  return parts.length > 0 ? parts : [text.trim()];
}

function bulkPasteIntoBlock(bi, text, afterLi) {
  const lines = splitLyricsIntoLines(text);
  const block = SONG.content.blocks[bi];
  let insertAt;
  if (afterLi === undefined) {
    // If the block has only one empty line, replace it instead of appending
    if (block.lines.length === 1 && !block.lines[0].text.trim()) {
      block.lines = lines.map(t => ({chords: [], text: t}));
      dirty = true;
      render();
      scheduleAutoSave();
      flashSave(`✓ ${lines.length} línea${lines.length>1?'s':''} pegada${lines.length>1?'s':''}`);
      return;
    }
    insertAt = block.lines.length;
  } else {
    insertAt = afterLi + 1;
  }
  const newLines = lines.map(t => ({chords: [], text: t}));
  block.lines.splice(insertAt, 0, ...newLines);
  dirty = true;
  render();
  scheduleAutoSave();
  flashSave(`✓ ${lines.length} línea${lines.length>1?'s':''} pegada${lines.length>1?'s':''}`);
}

function flashSave(msg) {
  statusEl.textContent = msg;
  statusEl.className = 'save-status';
  setTimeout(() => { if (!dirty) statusEl.textContent = '✓ Guardado'; }, 2000);
}

function openPasteModal(bi) {
  // Remove any existing modal
  closePasteModal();
  const overlay = document.createElement('div');
  overlay.id = 'paste-modal-overlay';
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal-card paste-modal">
      <div class="modal-header">
        <h2>📋 Pegar letra</h2>
        <button class="modal-close" aria-label="Cerrar">×</button>
      </div>
      <p class="modal-hint">Pegá la letra completa. Las líneas se separan automáticamente:</p>
      <ul class="paste-rules">
        <li>Si hay saltos de línea, cada una es una línea de la canción</li>
        <li>Si no los hay, se separa por puntos/contrato</li>
        <li>Si tampoco, se corta cada ~50 caracteres</li>
      </ul>
      <textarea id="paste-textarea" placeholder="Pegá acá la letra copiada de Genius, Letras.com, etc." rows="10" autofocus></textarea>
      <div class="paste-preview-info">
        <span id="paste-line-count">0</span> líneas detectadas
        <button type="button" class="paste-clear">Borrar</button>
      </div>
      <div class="modal-actions">
        <button type="button" class="btn-secondary modal-cancel">Cancelar</button>
        <button type="button" class="btn-primary paste-confirm">Pegar y separar</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const ta = overlay.querySelector('#paste-textarea');
  const counter = overlay.querySelector('#paste-line-count');
  const clear = overlay.querySelector('.paste-clear');
  const confirm = overlay.querySelector('.paste-confirm');
  const cancel = overlay.querySelector('.modal-cancel');
  const close = overlay.querySelector('.modal-close');

  function updateCount() {
    const lines = splitLyricsIntoLines(ta.value || '');
    counter.textContent = lines.length;
    confirm.disabled = lines.length === 0;
    confirm.textContent = lines.length === 0
      ? 'Pegar y separar'
      : `Pegar ${lines.length} línea${lines.length>1?'s':''}`;
  }
  ta.addEventListener('input', updateCount);
  clear.addEventListener('click', () => { ta.value = ''; updateCount(); ta.focus(); });
  const closeFn = () => closePasteModal();
  cancel.addEventListener('click', closeFn);
  close.addEventListener('click', closeFn);
  overlay.addEventListener('click', e => { if (e.target === overlay) closeFn(); });
  confirm.addEventListener('click', () => {
    if (!ta.value.trim()) return;
    bulkPasteIntoBlock(bi, ta.value);
    closeFn();
  });

  // Mobile paste gesture: tap-and-hold on textarea usually opens native paste on Android
  // Add a "Paste from clipboard" button using Clipboard API
  if (navigator.clipboard && navigator.clipboard.readText) {
    const clipBtn = document.createElement('button');
    clipBtn.type = 'button';
    clipBtn.className = 'btn-secondary paste-from-clip';
    clipBtn.textContent = '📥 Pegar del portapapeles';
    clipBtn.addEventListener('click', async () => {
      try {
        const t = await navigator.clipboard.readText();
        ta.value = t;
        updateCount();
      } catch (e) {
        alert('No se pudo leer del portapapeles. Pegá manualmente con Ctrl+V / botón Pegar del teclado.');
      }
    });
    overlay.querySelector('.modal-actions').insertBefore(clipBtn, cancel);
  }

  setTimeout(() => ta.focus(), 50);
  updateCount();
}

function closePasteModal() {
  const m = document.getElementById('paste-modal-overlay');
  if (m) m.remove();
}

function addLineAfter(bi, li) {
  SONG.content.blocks[bi].lines.splice(li + 1, 0, {chords: [], text: ''});
  dirty = true; render(); scheduleAutoSave();
  // Focus the new line
  setTimeout(() => {
    const newLine = container.querySelector(`.line[data-line-idx="${li + 1}"] .line-text`);
    if (newLine) newLine.focus();
  }, 50);
}

function removeLine(bi, li) {
  const block = SONG.content.blocks[bi];
  if (block.lines.length <= 1) {
    block.lines[0] = {chords: [], text: ''};
  } else {
    block.lines.splice(li, 1);
  }
  dirty = true; render(); scheduleAutoSave();
}

// ---------- Chord operations ----------

function openChordInput(bi, li, position, screenX, screenY) {
  const popup = document.getElementById('chord-input-popup');
  const field = document.getElementById('chord-input-field');
  popup.style.display = 'block';
  // Position popup above click point
  const pw = popup.offsetWidth || 240;
  const ph = popup.offsetHeight || 280;
  let left = Math.min(screenX, window.innerWidth - pw - 8);
  let top = screenY - ph - 12;
  if (top < 12) top = Math.min(screenY + 32, window.innerHeight - ph - 12);
  if (left < 8) left = 8;
  popup.style.left = left + 'px';
  popup.style.top = top + 'px';
  field.value = '';
  field.focus();
  field.dataset.editing = '';
  field.dataset.blockIdx = bi;
  field.dataset.lineIdx = li;
  field.dataset.position = position;
  // Reset preview indicator
  const prev = popup.querySelector('#chord-preview');
  if (prev) prev.textContent = '';
}

function editChord(bi, li, ci, span) {
  const popup = document.getElementById('chord-input-popup');
  const field = document.getElementById('chord-input-field');
  const chord = SONG.content.blocks[bi].lines[li].chords[ci];
  popup.style.display = 'block';
  const rect = span.getBoundingClientRect();
  popup.style.left = Math.min(rect.left, window.innerWidth - 200) + 'px';
  popup.style.top = (rect.bottom + 8) + 'px';
  field.value = chord.symbol;
  field.focus();
  field.select();
  field.dataset.editing = '1';
  field.dataset.blockIdx = bi;
  field.dataset.lineIdx = li;
  field.dataset.chordIdx = ci;
}

function commitChord() {
  const field = document.getElementById('chord-input-field');
  const sym = field.value.trim();
  const bi = +field.dataset.blockIdx;
  const li = +field.dataset.lineIdx;
  if (!sym) {
    // Delete chord if editing existing
    if (field.dataset.editing) {
      const ci = +field.dataset.chordIdx;
      SONG.content.blocks[bi].lines[li].chords.splice(ci, 1);
    }
  } else {
    if (field.dataset.editing) {
      const ci = +field.dataset.chordIdx;
      SONG.content.blocks[bi].lines[li].chords[ci].symbol = sym;
    } else {
      const pos = +field.dataset.position;
      SONG.content.blocks[bi].lines[li].chords.push({symbol: sym, position: pos});
    }
  }
  closeChordInput();
  dirty = true;
  render();
  scheduleAutoSave();
}

function closeChordInput() {
  document.getElementById('chord-input-popup').style.display = 'none';
}

// ---------- Auto-save ----------

function scheduleAutoSave() {
  if (saveTimer) clearTimeout(saveTimer);
  statusEl.textContent = '...';
  statusEl.className = 'save-status saving';
  saveTimer = setTimeout(saveNow, 800);
}

async function saveNow() {
  if (SONG_ID === null) {
    // First save → create new song
    try {
      SONG.title = document.getElementById('song-title').value || 'Sin título';
      SONG.artist = document.getElementById('song-artist').value;
      SONG.key = document.getElementById('song-key').value;
      SONG.capo = +document.getElementById('song-capo').value || 0;
      SONG.tempo = +document.getElementById('song-tempo').value || 120;
      SONG.time_signature = document.getElementById('song-time').value;
      SONG.tags = document.getElementById('song-tags').value.split(',').map(t => t.trim()).filter(Boolean);

      const resp = await fetch('/api/songs', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(SONG),
      });
      if (!resp.ok) throw new Error(await resp.text());
      const j = await resp.json();
      SONG.id = j.id;
      SONG_ID = j.id;
      window.history.replaceState({}, '', '/song/' + j.id);
      statusEl.textContent = '✓ Guardado';
      statusEl.className = 'save-status';
      dirty = false;
    } catch (e) {
      console.error(e);
      statusEl.textContent = '✗ Error';
      statusEl.className = 'save-status error';
    }
    return;
  }

  // Update existing
  try {
    SONG.title = document.getElementById('song-title').value || 'Sin título';
    SONG.artist = document.getElementById('song-artist').value;
    SONG.key = document.getElementById('song-key').value;
    SONG.capo = +document.getElementById('song-capo').value || 0;
    SONG.tempo = +document.getElementById('song-tempo').value || 120;
    SONG.time_signature = document.getElementById('song-time').value;
    SONG.tags = document.getElementById('song-tags').value.split(',').map(t => t.trim()).filter(Boolean);

    const resp = await fetch('/api/songs/' + SONG_ID, {
      method: 'PUT',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(SONG),
    });
    if (!resp.ok) throw new Error(await resp.text());
    statusEl.textContent = '✓ Guardado ' + new Date().toLocaleTimeString();
    statusEl.className = 'save-status';
    dirty = false;
  } catch (e) {
    console.error(e);
    statusEl.textContent = '✗ Error';
    statusEl.className = 'save-status error';
  }
}

// ---------- Transpose ----------

async function transpose(dir) {
  const n = parseInt(dir, 10);
  if (SONG_ID === null) {
    await saveNow();
  }
  try {
    const resp = await fetch('/api/songs/' + (SONG_ID || 0) + '/transpose', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({semitones: n}),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const data = await resp.json();
    SONG.content = data.content;
    SONG.key = data.key;
    document.getElementById('song-key').value = data.key;
    render();
  } catch (e) {
    console.error(e);
    alert('Error al transponer');
  }
}

// ---------- Helpers ----------

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, c => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  })[c]);
}

// ---------- Event delegation ----------

container.addEventListener('click', (e) => {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const action = btn.dataset.action;
  const bi = +btn.dataset.blockIdx;
  const li = +btn.dataset.lineIdx;
  if (action === 'up') moveBlock(bi, -1);
  else if (action === 'down') moveBlock(bi, 1);
  else if (action === 'dup') duplicateBlock(bi);
  else if (action === 'del') deleteBlock(bi);
  else if (action === 'add-line') {
    const afterLi = +btn.dataset.lineIdx;
    if (afterLi === -1) {
      const lastIdx = SONG.content.blocks[bi].lines.length - 1;
      addLineAfter(bi, lastIdx);
    } else {
      addLineAfter(bi, afterLi);
    }
  }
  else if (action === 'paste-block') {
    openPasteModal(bi);
  }
  else if (action === 'add-chord') {
    const textEl = btn.closest('.line').querySelector('.line-text');
    textEl.focus();
    openChordInput(bi, li, 0, e.clientX, e.clientY);
  }
  else if (action === 'del-line') removeLine(bi, li);
});

container.addEventListener('input', (e) => {
  if (e.target.classList.contains('block-name')) {
    const bi = +e.target.dataset.blockIdx;
    SONG.content.blocks[bi].name = e.target.value;
    dirty = true;
    scheduleAutoSave();
  }
});

document.querySelectorAll('.btn-section').forEach(btn => {
  btn.addEventListener('click', () => addBlock(btn.dataset.type));
});

document.querySelectorAll('.btn-transpose').forEach(btn => {
  btn.addEventListener('click', () => transpose(btn.dataset.dir));
});

document.getElementById('btn-preview').addEventListener('click', async () => {
  // Cancel any pending debounced save and save immediately
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
  await saveNow();
  if (SONG_ID) window.location = '/song/' + SONG_ID + '/preview';
});

document.getElementById('btn-pdf').addEventListener('click', async () => {
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
  await saveNow();
  if (SONG_ID) window.location = '/api/songs/' + SONG_ID + '/pdf';
});

document.getElementById('btn-delete').addEventListener('click', async () => {
  if (SONG_ID === null) { window.location = '/'; return; }
  if (!confirm('¿Eliminar esta canción?')) return;
  await fetch('/api/songs/' + SONG_ID, {method: 'DELETE'});
  window.location = '/';
});

// Header fields trigger save
['song-title', 'song-artist', 'song-key', 'song-capo', 'song-tempo', 'song-time', 'song-tags'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => { dirty = true; scheduleAutoSave(); });
});

// Chord popup input
const chordField = document.getElementById('chord-input-field');
chordField.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); commitChord(); }
  if (e.key === 'Escape') { closeChordInput(); }
});
chordField.addEventListener('input', () => {
  const prev = document.getElementById('chord-preview');
  if (prev) prev.textContent = chordField.value;
});

// Confirm / Cancel buttons
document.getElementById('chord-confirm-btn').addEventListener('mousedown', (e) => {
  e.preventDefault();
  commitChord();
});
document.getElementById('chord-cancel-btn').addEventListener('mousedown', (e) => {
  e.preventDefault();
  chordField.value = '';
  closeChordInput();
});

// Tap on a suggestion fills field + commits
document.querySelectorAll('.chord-suggestions button').forEach(btn => {
  btn.addEventListener('mousedown', (e) => {
    e.preventDefault();
    chordField.value = btn.dataset.chord;
    commitChord();
  });
});

// Tap outside popup closes it
document.addEventListener('mousedown', (e) => {
  const popup = document.getElementById('chord-input-popup');
  if (!popup || popup.style.display === 'none') return;
  if (popup.contains(e.target)) return;
  // Don't close if clicking the line text (re-position popup)
  if (e.target.closest('.line-text')) return;
  if (e.target.classList && e.target.classList.contains('chord')) return;
  closeChordInput();
});

// Warn before leaving
window.addEventListener('beforeunload', (e) => {
  if (dirty) {
    e.preventDefault();
    e.returnValue = '';
  }
});

// ---------- Boot ----------
render();
