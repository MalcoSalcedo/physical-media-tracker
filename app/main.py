from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from app import catalog
from app.db import get_connection

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))

app = FastAPI(title="Physical Media Tracker")


@app.get("/collection")
def view_collection(request: Request):
    with get_connection() as conn:
        items = catalog.list_items(conn)
    return templates.TemplateResponse(
        request, "collection.html", {"items": items}
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
        )
    return RedirectResponse("/collection", status_code=303)
