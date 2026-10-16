"""HTTP endpoints for the ReplayGain (rsgain) section. Logic lives in filestomb.replaygain."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .. import integrations, replaygain

# Stored as strings in integrations.json so the last-used choices are remembered.
DEFAULTS = {"rsgain_album": "1", "rsgain_true_peak": "1", "rsgain_reference": "1", "rsgain_target": "-18", "rsgain_clip": "p", "rsgain_max_peak": "0", "rsgain_opus": "d"}


class OptionsIn(BaseModel):
    album: bool = True
    true_peak: bool = True
    reference_tag: bool = True
    target: float = -18.0
    clip_mode: str = "p"
    max_peak: float = 0.0
    opus_mode: str = "d"


class RunIn(BaseModel):
    path: str  # the album folder Picard saved to, relative to the library
    release_mbid: str | None = None
    write: bool = False
    options: OptionsIn = OptionsIn()


def remembered() -> dict:
    g = lambda k: integrations.get(k) or DEFAULTS[k]  # noqa: E731
    return {
        "album": g("rsgain_album") == "1",
        "true_peak": g("rsgain_true_peak") == "1",
        "reference_tag": g("rsgain_reference") == "1",
        "target": float(g("rsgain_target")),
        "clip_mode": g("rsgain_clip"),
        "max_peak": float(g("rsgain_max_peak")),
        "opus_mode": g("rsgain_opus"),
    }


def remember(o: replaygain.Options) -> None:
    integrations.update({
        "rsgain_album": "1" if o.album else "0",
        "rsgain_true_peak": "1" if o.true_peak else "0",
        "rsgain_reference": "1" if o.reference_tag else "0",
        "rsgain_target": f"{o.target:g}",
        "rsgain_clip": o.clip_mode,
        "rsgain_max_peak": f"{o.max_peak:g}",
        "rsgain_opus": o.opus_mode,
    })


def register(app: FastAPI, root: Path, resolve: Callable[[str], Path], refuse_during_batch: Callable[[], None]) -> None:
    @app.get("/api/replaygain/status")
    async def status() -> dict:
        try:
            replaygain.check_binary(integrations.get("rsgain_path"))
            ok = True
        except replaygain.ReplayGainError:
            ok = False
        return {"configured": ok, "options": remembered()}

    @app.post("/api/replaygain/run")
    async def run(body: RunIn) -> dict:
        refuse_during_batch()
        folder = resolve(body.path)
        if not folder.is_dir():
            raise HTTPException(404, "Not a directory.")
        options = replaygain.Options(**body.options.model_dump())
        try:
            binary = replaygain.check_binary(integrations.get("rsgain_path"))
            options.validate()
            files = await asyncio.to_thread(replaygain.audio_files_for_release, folder, body.release_mbid)
            result = await asyncio.to_thread(replaygain.run, binary, options, files, body.write)
        except replaygain.ReplayGainError as error:
            raise HTTPException(422, str(error)) from error
        remember(options)
        return {
            "wrote": result.wrote,
            "verified": result.verified,
            "notes": result.notes,
            "tracks": [vars(r) for r in result.tracks],
            "album": vars(result.album) if result.album else None,
        }
