"""HTTP endpoints for batch mode. Thin: the logic lives in filestomb.batch."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from ..batch import runner, store
from ..batch.runner import BatchManager


class RootIn(BaseModel):
    path: str = ""


class MatchIn(BaseModel):
    path: str = ""
    rematch: list[str] = Field(default_factory=list)


class ProcessIn(BaseModel):
    path: str = ""
    limit: int = 1
    clear_picard: bool = False


class ResolveIn(BaseModel):
    path: str
    action: str  # use | missing | skip | reset
    release_mbid: str | None = None


def register(app: FastAPI, manager: BatchManager, resolve: Callable[[str], Path]) -> None:
    batch_store = manager.store

    def known_root(path: str) -> str:
        rel = path.strip("/")
        if not rel:
            raise HTTPException(422, "Choose a folder to process, not the whole library.")
        if not resolve(rel).is_dir():
            raise HTTPException(404, "Not a directory.")
        return rel

    def start(action: Callable[[], None]) -> dict:
        try:
            action()
        except RuntimeError as error:
            raise HTTPException(409, str(error))
        return {"started": True}

    @app.get("/api/batch/status")
    async def status(root: str = Query("")) -> dict:
        return manager.status(root.strip("/") or None)

    @app.get("/api/batch/roots")
    async def roots() -> dict:
        with batch_store._conn() as conn:
            rows = conn.execute("SELECT root, COUNT(*) AS n FROM albums GROUP BY root ORDER BY MAX(updated) DESC").fetchall()
        return {"roots": [{"path": r["root"], "albums": r["n"]} for r in rows]}

    @app.post("/api/batch/discover")
    async def discover(body: RootIn) -> dict:
        root = known_root(body.path)
        return start(lambda: manager.start_discovery(root))

    @app.post("/api/batch/match")
    async def match(body: MatchIn) -> dict:
        root = known_root(body.path)
        return start(lambda: manager.start_matching(root, body.rematch))

    @app.post("/api/batch/process")
    async def process(body: ProcessIn) -> dict:
        root = known_root(body.path)
        if not 1 <= body.limit <= 500:
            raise HTTPException(422, "Limit must be between 1 and 500.")
        return start(lambda: manager.start_processing(root, body.limit, body.clear_picard))

    @app.post("/api/batch/stop")
    async def stop() -> dict:
        manager.request_stop()
        return {"ok": True}

    @app.get("/api/batch/albums")
    async def albums(
        root: str = Query(...), status_filter: str | None = Query(None, alias="status"),
        q: str = "", offset: int = 0, limit: int = 100,
    ) -> dict:
        root = root.strip("/")
        if status_filter and status_filter not in store.STATUSES:
            raise HTTPException(422, "Unknown status.")
        rows = await asyncio.to_thread(batch_store.list, root, status_filter, q, max(0, offset), min(max(1, limit), 500))
        return {"albums": rows, "counts": batch_store.counts(root)}

    @app.post("/api/batch/resolve")
    async def resolve_album(body: ResolveIn) -> dict:
        row = batch_store.get(body.path)
        if row is None:
            raise HTTPException(404, "Unknown album.")
        if row["status"] in (store.PROCESSING, store.DONE):
            raise HTTPException(409, "That album is already being processed or finished.")
        if body.action == "skip":
            batch_store.update(body.path, status=store.SKIPPED, message="Skipped by you.")
        elif body.action == "missing":
            batch_store.update(body.path, status=store.MISSING, release_mbid=None, message="Marked as not on MusicBrainz by you.")
        elif body.action == "reset":
            batch_store.update(body.path, status=store.PENDING, message=None)
        elif body.action == "use":
            candidates = (row.get("verdict") or {}).get("candidates", [])
            chosen = next((c for c in candidates if c["mbid"] == body.release_mbid), None)
            if chosen is None:
                raise HTTPException(422, "That release isn't one of the candidates for this album.")
            if not (chosen["confident"] or chosen.get("track_exact")):
                raise HTTPException(
                    422,
                    "That release isn't a complete match (" + "; ".join(chosen["problems"]) + "). Open the album to handle it by hand.",
                )
            # The user vouched for a release whose tracks match exactly but whose title/artist differ.
            verdict = {**(row.get("verdict") or {}), "approved": chosen["mbid"]}
            batch_store.update(
                body.path, status=store.READY, release_mbid=chosen["mbid"], confidence=chosen["rank"],
                verdict=verdict, message="You picked this release.",
            )
        else:
            raise HTTPException(422, "Unknown action.")
        manager.audit("resolved", path=body.path, action=body.action, release=body.release_mbid)
        return {"ok": True}

    @app.post("/api/batch/reconcile")
    async def reconcile(body: RootIn) -> dict:
        root = known_root(body.path)
        if manager.busy:
            raise HTTPException(409, "A batch job is running.")
        return {"changed": await asyncio.to_thread(manager.reconcile, root)}

    @app.post("/api/batch/cleanup")
    async def cleanup(body: RootIn) -> dict:
        """Remove folders that are completely empty (rmdir only; never anything with files in it)."""
        root = known_root(body.path)
        if manager.busy:
            raise HTTPException(409, "A batch job is running.")
        removed = await asyncio.to_thread(runner.cleanup_empty_dirs, resolve(root))
        manager.audit("cleanup_empty_dirs", root=root, removed=len(removed))
        return {"removed": len(removed)}

    @app.get("/api/batch/audit")
    async def audit() -> dict:
        return {"lines": manager.audit_tail(300)}
