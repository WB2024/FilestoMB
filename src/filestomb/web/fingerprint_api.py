"""HTTP endpoints for AcoustID fingerprinting, with progress the page can poll."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .. import fingerprint, tags


class StartIn(BaseModel):
    path: str


def register(app: FastAPI, resolve: Callable[[str], Path], refuse_during_batch: Callable[[], None]) -> None:
    jobs: dict[str, dict] = {}
    running: set[asyncio.Task] = set()

    @app.get("/api/fingerprint/status")
    async def status(path: str | None = None) -> dict:
        job = jobs.get(path.strip("/")) if path else None
        return {"available": fingerprint.find_fpcalc() is not None, "job": job}

    async def work(key: str, files: list[Path], fpcalc: str) -> None:
        job = jobs[key]
        for file in files:
            try:
                fp = await asyncio.to_thread(fingerprint.calculate, file, fpcalc)
                await asyncio.to_thread(fingerprint.write_tag, file, fp)
            except fingerprint.FingerprintError as error:
                job["errors"].append(str(error))
            job["done"] += 1
        job["state"] = "done"

    @app.post("/api/fingerprint/start")
    async def start(body: StartIn) -> dict:
        refuse_during_batch()
        fpcalc = fingerprint.find_fpcalc()
        if not fpcalc:
            raise HTTPException(422, "fpcalc isn't installed in this container, so fingerprints can't be generated.")
        folder = resolve(body.path)
        if not folder.is_dir():
            raise HTTPException(404, "Not a directory.")
        key = body.path.strip("/")
        if jobs.get(key, {}).get("state") == "running":
            raise HTTPException(409, "Already fingerprinting this album.")
        album = await asyncio.to_thread(tags.scan_directory, folder, False)
        if album is None:
            raise HTTPException(404, "No readable audio files were found in that folder.")
        files = [Path(t.path) for t in album.tracks]
        jobs[key] = {"state": "running", "total": len(files), "done": 0, "errors": []}
        task = asyncio.create_task(work(key, files, fpcalc))
        running.add(task)
        task.add_done_callback(running.discard)
        return jobs[key]
