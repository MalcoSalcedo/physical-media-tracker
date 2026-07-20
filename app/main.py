from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import catalog
from app.db import get_connection, init_db

load_dotenv()

APP_DIR = Path(__file__).resolve().parent


def _global_now_playing(request: Request) -> dict:
    """Injected into every template's context so the banner can show on any page."""
    with get_connection() as conn:
        current = catalog.get_now_playing(conn)
    return {"global_now_playing": current}


def _timeago(value: str | None) -> str:
    """Format a SQLite UTC datetime string ('YYYY-MM-DD HH:MM:SS') as '3m ago'."""
    if not value:
        return ""
    then = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    seconds = int((datetime.utcnow() - then).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


templates = Jinja2Templates(
    directory=str(APP_DIR / "templates"), context_processors=[_global_now_playing]
)
templates.env.filters["timeago"] = _timeago

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Physical Media Tracker", lifespan=lifespan)


@app.get("/collection")
def view_collection(request: Request, sort: str = catalog.DEFAULT_SORT, format: str | None = None):
    with get_connection() as conn:
        items = catalog.list_items(conn, sort=sort, format_filter=format)
        formats = catalog.list_formats(conn)
    return templates.TemplateResponse(
        request,
        "collection.html",
        {"items": items, "sort": sort, "format_filter": format, "formats": formats},
    )


@app.get("/add")
def add_form(request: Request):
    return templates.TemplateResponse(request, "add.html", {})


@app.post("/add")
def add_lookup(request: Request, barcode: str = Form(...)):
    match = catalog.lookup_barcode(barcode)
    if match is None:
        return templates.TemplateResponse(
            request, "add.html", {"barcode": barcode, "no_match": True}
        )
    return templates.TemplateResponse(
        request, "add.html", {"barcode": barcode, "match": match}
    )


@app.post("/collection")
def create_item(
    artist: str = Form(...),
    album: str = Form(...),
    format: str = Form(...),
    barcode: str | None = Form(None),
    cover_art_url: str | None = Form(None),
    musicbrainz_id: str | None = Form(None),
    discogs_id: str | None = Form(None),
):
    with get_connection() as conn:
        catalog.save_item(
            conn,
            artist=artist,
            album=album,
            format=format,
            barcode=barcode or None,
            cover_art_url=cover_art_url or None,
            musicbrainz_id=musicbrainz_id or None,
            discogs_id=discogs_id or None,
        )
    return RedirectResponse("/collection", status_code=303)


@app.get("/listen")
def listen_form(request: Request):
    with get_connection() as conn:
        items = catalog.list_items(conn)
    return templates.TemplateResponse(request, "listen.html", {"items": items})


@app.post("/listen")
def select_album(collection_id: int = Form(...)):
    with get_connection() as conn:
        item = catalog.get_item(conn, collection_id)
        tracks = catalog.get_tracks(conn, collection_id)
        if not tracks:
            tracks = catalog.fetch_tracklist(item)
            if tracks:
                catalog.save_tracks(conn, collection_id, tracks)
        catalog.set_active_album(conn, collection_id)
    return RedirectResponse("/now-playing", status_code=303)


@app.get("/now-playing")
def now_playing(request: Request):
    with get_connection() as conn:
        current = catalog.get_now_playing(conn)
        tracks = catalog.get_tracks(conn, current["collection_id"]) if current else []
        history = catalog.get_recent_history(conn)
    return templates.TemplateResponse(
        request, "now_playing.html", {"current": current, "tracks": tracks, "history": history}
    )
