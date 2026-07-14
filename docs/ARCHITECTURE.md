# Physical Media Tracker — Build Plan

**Goal:** A Raspberry Pi 4 box that sits near your CD player (and later, turntable), identifies what's playing, logs it to a collection database, and shows friends your collection + current listen on a shareable web page.

**Identification approach:** hybrid — microphone audio fingerprinting for automatic "now playing" detection, plus barcode/manual entry for building out the full collection catalog and as a fallback when fingerprinting fails.

---

## 1. System overview

```
                    ┌─────────────────────────┐
   USB mic  ───────▶│  Listener daemon        │
   (near speakers)   │  (records 10s clips,    │──▶ SQLite DB
                     │   fingerprints, IDs      │      ├─ collection
                     │   track)                 │      ├─ now_playing
                     └─────────────────────────┘      └─ history
                                                          ▲
   USB barcode ─────▶┌─────────────────────────┐         │
   scanner (HID)      │  Catalog service         │────────┘
                       │  (barcode → metadata →   │
                       │   add to collection)     │
                       └─────────────────────────┘
                                                          │
                                                          ▼
                                                ┌─────────────────────┐
                                                │  Web app (FastAPI)  │
                                                │  - collection view  │
                                                │  - now playing      │
                                                └─────────────────────┘
                                                          │
                                          ┌───────────────┴───────────────┐
                                          ▼                               ▼
                                 Local network access           Cloudflare Tunnel
                                 (same wifi)                    (public URL, friends
                                                                 anywhere)
```

Everything runs on the Pi. Nothing needs a separate cloud server.

---

## 2. Hardware

You already have: Raspberry Pi 4, standard CD player.

Still need:

- **USB microphone** — a basic USB desk/conference mic is enough to start. Cost: ~$10–20.
- **USB barcode scanner** — any cheap one works; they emulate a keyboard, so no drivers needed. Cost: ~$15–25.
- **MicroSD card** (32GB+) if the Pi doesn't already have one set up with Raspberry Pi OS.
- *Optional, later:* a USB audio interface with a line-in (e.g. Behringer UCA202, ~$30) to capture line-level audio directly from the CD player's headphone/RCA output instead of through a mic. Much cleaner signal, especially useful once you add a turntable — room-mic fingerprinting on quiet vinyl passages is unreliable.
- *Optional:* small case/enclosure once the build is stable.

No physical display is required for the MVP — "now playing" is meant to be seen by friends on the web, not on the box itself. If you want a local screen later, a small e-ink or SPI display can be bolted on without touching the rest of the architecture.

---

## 3. Audio identification pipeline

1. A background daemon on the Pi continuously samples audio from the mic (or line-in) in short windows (e.g., 12–15 seconds every couple of minutes, or continuously if CPU allows).
2. Each clip is fingerprinted with **Chromaprint** (`fpcalc`), the same open-source library behind AcoustID/MusicBrainz.
3. The fingerprint is sent to the **AcoustID API** (free, open), which returns a MusicBrainz recording match: artist, track, album.
4. If matched and different from the current "now playing" row, update the `now_playing` table and append to `history`.
5. If no match (silence, vinyl surface noise, an obscure pressing), fall back to whatever was last identified, or prompt for manual entry via the web UI.

This is well-trodden ground — Chromaprint/`fpcalc` and `pyacoustid` (Python bindings) run fine on a Pi 4; people have been doing exactly this kind of stream monitoring since the library was built for that use case.

Realistic expectations: fingerprinting works best on well-known, mastered recordings. Live bootlegs, rare pressings, or spoken-word records may not match — that's what the barcode/manual path is for.

---

## 4. Barcode cataloging pipeline

This is how the *collection* (not just "now playing") gets built, and it's the more reliable of the two identification paths.

1. Barcode scanner acts as a keyboard — scanning a UPC on a CD or record sleeve just "types" the number into a listening input field.
2. The catalog service looks up the barcode via the **Discogs API** `/database/search?barcode=...` endpoint (no auth needed for basic search), which is strong for music releases including obscure/regional pressings, and returns cover art.
3. Fall back to **MusicBrainz**'s barcode search if Discogs has no match.
4. Matched release gets written into the `collection` table. If nothing matches automatically, you get a quick manual-entry form (title/artist/format) so the catalog stays complete even for oddballs.

Practically: this becomes your one-time "shelf scanning session" to seed the collection, then an occasional step whenever you buy something new.

---

## 5. Data model (SQLite)

- **collection** — id, artist, album, format (CD/vinyl/etc.), barcode, cover_art_url, musicbrainz_id, date_added
- **now_playing** — single row: collection_id (nullable), track_title, started_at, source (fingerprint/manual)
- **history** — id, collection_id, track_title, played_at

SQLite is enough here — single device, low write volume, zero maintenance.

---

## 6. Backend

- **OS:** Raspberry Pi OS Lite (headless — no need for a desktop environment since this runs unattended).
- **Two long-running services**, each as a `systemd` unit so they survive reboots/crashes:
  - `listener.service` — the mic-capture + fingerprint loop.
  - `webapp.service` — a small FastAPI (or Flask) app serving both the JSON API and the friend-facing pages.
- Barcode scanning can be handled by the same web app (a page with a focused text input that "catches" the scanner's keystrokes) rather than a separate always-on service.

---

## 7. Sharing with friends — how to think about the trade-offs

You asked me to help you decide here, so walking through it:

**A. Pi-hosted, local network only.** Simplest possible setup — the web app just runs on the Pi, reachable at `http://<pi-ip>:8000` on your home wifi. Zero cost, zero extra setup. The catch: it only works for friends physically on your network, which defeats "show your friends your collection" unless they're literally in your apartment.

**B. Fully cloud-hosted.** The Pi pushes now-playing/collection data out to a hosted service (e.g. a free-tier deployment on Fly.io/Render/Vercel + a hosted Postgres). Friends can always reach it, even if your Pi is off — they'd just see the last known state. But now you're maintaining a second deployment, a sync mechanism between Pi and cloud, and possibly a monthly cost once you're past free tiers.

**C. Hybrid — Pi-hosted, exposed via Cloudflare Tunnel (recommended).** The web app still runs entirely on the Pi (one system, one database, no sync logic), but `cloudflared` gives it a real public HTTPS URL without port-forwarding or exposing your home IP. This is free for personal use with no traffic limit, sets up in well under an hour, and runs as a `systemd` service so it survives reboots. The only real downside is that if the Pi is off, the site is unreachable — but for a "what's currently spinning" tracker, that's an acceptable failure mode (it can just show "offline" or the last session).

Recommendation: start with **A** (local only) to get the core working, then layer in **C** (Cloudflare Tunnel) once the app is stable enough to expose. Skip **B** — the added infrastructure isn't worth it for a single-user hobby project.

---

## 8. Suggested build order

1. **Catalog MVP:** barcode scanner → Discogs/MusicBrainz lookup → SQLite `collection` table → basic web page listing the collection. No audio yet. This alone makes the shelf-scanning session worthwhile and gives you something to look at immediately.
2. **Now-playing MVP:** mic capture → `fpcalc` → AcoustID → update `now_playing` → show it on the same web page. Test with the CD player only first, tune sampling interval/clip length.
3. **Polish the web UI:** cover art grid, now-playing banner, recently-played history.
4. **Expose it:** set up Cloudflare Tunnel, get friends a real URL.
5. **Vinyl support:** add the turntable, evaluate mic accuracy, add the line-in USB audio interface if fingerprinting on vinyl is unreliable via mic alone.
6. *(Optional)* physical display, LED "now playing" indicator, better enclosure.

---

## 9. Open questions to settle before/while building

- Sampling cadence for the listener daemon (continuous vs. periodic) — affects Pi CPU load and API call volume to AcoustID.
- Whether you want authentication on the public page at all, or fully open (anyone with the link can view).
- How much history to retain / whether to eventually add stats (most-played artist, etc.) — easy to bolt on later since `history` is already structured for it.
