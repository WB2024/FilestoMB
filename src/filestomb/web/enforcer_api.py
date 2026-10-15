"""HTTP endpoints that front Music Genre Enforcer. Thin proxies: the enforcer does the work."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .. import enforcer, integrations
from ..config import Settings


class GenreIn(BaseModel):
    name: str
    genre: str
    apply: bool = True


def configured() -> bool:
    return bool(integrations.get("enforcer_url"))


def make_client() -> enforcer.EnforcerClient:
    if not configured():
        raise HTTPException(422, "Set the Music Genre Enforcer URL in Settings first.")
    return enforcer.EnforcerClient(integrations.get("enforcer_url"))


def register(app: FastAPI, settings: Settings, root: Path, resolve: Callable[[str], Path]) -> Callable[[], object]:
    async def with_client(action):
        client = make_client()
        try:
            return await action(client)
        except enforcer.EnforcerError as error:
            raise HTTPException(502, str(error)) from error
        finally:
            await client.aclose()

    async def notify() -> None:
        await with_client(lambda c: c.notify())

    @app.get("/api/enforcer/status")
    async def status() -> dict:
        if not configured():
            return {"configured": False}

        async def go(c):
            state = await c.state()
            return {
                "configured": True,
                "reachable": True,
                "url": integrations.get("enforcer_url"),
                "auto": integrations.get("enforcer_auto") == "1",
                "counts": state["counts"],
                "dry_run": state["config"]["dry_run"],
                "lastfm": state["config"]["lastfm_configured"],
                "auto_apply": state["config"]["auto_apply"],
                "job": state.get("job"),
            }

        try:
            return await with_client(go)
        except HTTPException as error:
            return {"configured": True, "reachable": False, "url": integrations.get("enforcer_url"), "error": error.detail}

    @app.post("/api/settings/test-enforcer")
    async def test() -> dict:
        async def go(c):
            state = await c.state()
            return {"ok": True, "artists": state["counts"]["artists"], "undefined": state["counts"]["undefined"], "library_exists": state["library_exists"]}

        return await with_client(go)

    @app.post("/api/enforcer/notify")
    async def notify_endpoint() -> dict:
        await notify()
        return {"ok": True}

    @app.get("/api/enforcer/queue")
    async def queue() -> dict:
        """Artists on disk that still need a genre, plus the genres in use (for the chips)."""
        data = await with_client(lambda c: c.artists())
        pending = [a for a in data["artists"] if a["on_disk"] and not a["genre"]]
        return {"artists": pending, "genres": data["genres"]}

    @app.get("/api/enforcer/artist")
    async def artist(name: str = Query(...)) -> dict:
        data = await with_client(lambda c: c.artists())
        found = next((a for a in data["artists"] if a["name"] == name), None)
        return {"name": name, "known": found is not None and found["on_disk"], "genre": found["genre"] if found else "", "genres": data["genres"]}

    @app.get("/api/enforcer/for-folder")
    async def for_folder(path: str = Query(...)) -> dict:
        """Which enforcer artist does this album folder belong to?"""
        if not settings.picard_dest_root:
            raise HTTPException(422, "PICARD_DEST_ROOT isn't set, so the artist folder can't be worked out.")
        folder = resolve(path)
        try:
            rel = folder.relative_to(Path(settings.picard_dest_root).resolve()).as_posix()
        except ValueError:
            raise HTTPException(422, "That folder isn't inside Picard's destination.")
        state = await with_client(lambda c: c.state())
        name = enforcer.artist_for_folder(rel, state["config"]["flat_folders"])
        if not name:
            raise HTTPException(422, "Couldn't work out the artist for that folder.")
        return {"name": name}

    @app.get("/api/enforcer/peek")
    async def peek(name: str = Query(...)) -> dict:
        return await with_client(lambda c: c.peek_tags(name))

    @app.get("/api/enforcer/lastfm")
    async def lastfm(name: str = Query(...)) -> dict:
        return await with_client(lambda c: c.lastfm(name))

    @app.put("/api/enforcer/genre")
    async def set_genre(body: GenreIn) -> dict:
        async def go(c):
            await c.set_genre(body.name, body.genre)
            job = await c.apply_selected([body.name]) if body.apply else None
            return {"ok": True, "job": job}

        return await with_client(go)

    @app.get("/api/enforcer/job")
    async def job() -> dict:
        return {"job": await with_client(lambda c: c.job())}

    return notify
