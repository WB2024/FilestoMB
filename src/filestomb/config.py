"""Local settings, loaded from a .env file (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

DEFAULT_API_BASE_URL = "https://musicbrainz.org/ws/2"


@dataclass
class Settings:
    app_name: str
    app_version: str
    contact: str
    api_base_url: str

    @property
    def user_agent(self) -> str:
        # MusicBrainz requires a descriptive, contactable User-Agent on every
        # request or it will throttle/block the client.
        return f"{self.app_name}/{self.app_version} ( {self.contact} )"

    @property
    def has_contact(self) -> bool:
        return bool(self.contact.strip())


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_name=os.environ.get("MB_APP_NAME", "FilesToMB"),
        app_version=os.environ.get("MB_APP_VERSION", "0.1.0"),
        contact=os.environ.get("MB_CONTACT", ""),
        api_base_url=os.environ.get("MB_API_BASE_URL", DEFAULT_API_BASE_URL),
    )
