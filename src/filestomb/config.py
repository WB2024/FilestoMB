"""Local settings, loaded from a .env file (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_API_BASE_URL = "https://musicbrainz.org/ws/2"


@dataclass
class Settings:
    app_name: str
    app_version: str
    contact: str
    api_base_url: str
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    # Root of the music library the web UI is allowed to browse.
    music_root: Path = Path.home()
    # Picard integration (web UI). Both are optional; see compose.yaml.
    picard_pipe_dir: str = ""  # directory holding Picard's remote-command pipe
    picard_url: str = ""  # where you reach Picard's own UI, for the "Open Picard" link
    picard_library_root: str = "/music"  # the library's path as Picard sees it
    picard_dest_root: str = ""  # where Picard saves files (our path); lets batch mode verify they landed

    @property
    def user_agent(self) -> str:
        # MusicBrainz requires a descriptive, contactable User-Agent on every
        # request or it will throttle/block the client.
        return f"{self.app_name}/{self.app_version} ( {self.contact} )"

    @property
    def has_contact(self) -> bool:
        return bool(self.contact.strip())

    @property
    def has_oauth(self) -> bool:
        return bool(self.oauth_client_id.strip() and self.oauth_client_secret.strip())


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_name=os.environ.get("MB_APP_NAME", "FilesToMB"),
        app_version=os.environ.get("MB_APP_VERSION", "0.1.0"),
        contact=os.environ.get("MB_CONTACT", ""),
        api_base_url=os.environ.get("MB_API_BASE_URL", DEFAULT_API_BASE_URL),
        oauth_client_id=os.environ.get("MB_OAUTH_CLIENT_ID", ""),
        oauth_client_secret=os.environ.get("MB_OAUTH_CLIENT_SECRET", ""),
        music_root=Path(os.environ.get("MUSIC_ROOT") or Path.home()).expanduser(),
        picard_pipe_dir=os.environ.get("PICARD_PIPE_DIR", ""),
        picard_url=os.environ.get("PICARD_URL", "").rstrip("/"),
        picard_library_root=os.environ.get("PICARD_LIBRARY_ROOT", "/music"),
        picard_dest_root=os.environ.get("PICARD_DEST_ROOT", ""),
    )
