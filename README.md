# 🎸 Chordbook

App web para crear, editar y exportar letras con acordes posicionados sobre la sílaba correcta. Estilo Songbook Pro. PDF imprimible. Setlists. Transpose.

## Features

- Editor con click-to-place de acordes (pixel-aligned sobre sílabas)
- Secciones: Verso, Coro, Puente, Intro, Outro, Pre-coro
- Transpose ±N semitonos con un click
- Capo position
- Setlists (lista de canciones para tocar en vivo)
- Export PDF profesional con tipografía musical
- Auto-save cada 800ms
- Tema oscuro
- Mobile-first / PWA-ready
- REST API completa

## Stack

- Flask 3.1 + SQLite
- WeasyPrint 69 (PDF generation)
- Vanilla JS (sin frameworks — más rápido en mobile)
- nginx reverse proxy

## URLs

- App: http://173.249.3.113:8104
- Health: http://173.249.3.113:8104/health
- API: ver `app/main.py`

## API

- `GET /` — lista canciones
- `GET /song/<id>` — editor
- `GET /song/<id>/preview` — vista limpia para tocar
- `GET /new` — nueva canción
- `POST /api/songs` — crear
- `PUT /api/songs/<id>` — actualizar
- `DELETE /api/songs/<id>` — eliminar
- `POST /api/songs/<id>/transpose` — transponer
- `GET /api/songs/<id>/pdf` — descargar PDF
- `GET /api/setlists/<id>/pdf` — PDF setlist completo

## Run local

```bash
pip install flask weasyprint
python -m app.main
# → http://127.0.0.1:5101
```

## Roadmap

- [ ] APK Android (PWA → TWA con PWABuilder)
- [ ] Import lyrics desde URL (scraping Genius/Letras)
- [ ] Metronome en preview
- [ ] Auto-scroll durante performance
- [ ] Multi-usuario con auth
