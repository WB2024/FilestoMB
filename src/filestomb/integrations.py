"""Optional third-party service settings (fanart.tv, Lidarr).

Values entered in the web UI are stored in /config/integrations.json (mode
600); an environment variable of the same purpose is used when nothing has
been saved. Secrets are never sent back to the browser, only whether they're set.
"""

from __future__ import annotations

import json
import os

from .paths import config_dir

SECRET_FIELDS = {"fanart_api_key", "lidarr_api_key"}
ENV_NAMES = {
    "fanart_api_key": "FANART_API_KEY",
    "lidarr_url": "LIDARR_URL",
    "lidarr_api_key": "LIDARR_API_KEY",
    # The Lidarr root folder as Lidarr sees it, e.g. /data/Media/Audio/Music/Sources/Clean
    "lidarr_root_folder": "LIDARR_ROOT_FOLDER",
    # Where Lidarr mounts the same library FilesToMB mounts at its music root, e.g. /data
    "lidarr_library_path": "LIDARR_LIBRARY_PATH",
    # "1" = batch mode sends each finished album to Lidarr automatically
    "lidarr_auto": "LIDARR_AUTO",
    # Music Genre Enforcer's address, e.g. http://192.168.1.110:8320
    "enforcer_url": "ENFORCER_URL",
    # "1" = batch mode tells the enforcer about each finished album
    "enforcer_auto": "ENFORCER_AUTO",
}
FIELDS = tuple(ENV_NAMES)


def _path():
    return config_dir() / "integrations.json"


def _stored() -> dict[str, str]:
    try:
        data = json.loads(_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if k in FIELDS and isinstance(v, str)} if isinstance(data, dict) else {}


def get(field: str) -> str:
    if field not in FIELDS:
        raise KeyError(field)
    return (_stored().get(field) or os.environ.get(ENV_NAMES[field], "")).strip()


def update(values: dict[str, str | None]) -> None:
    """Set fields (empty string clears one); unknown fields and None are ignored."""
    data = _stored()
    for field, value in values.items():
        if field in FIELDS and value is not None:
            if value.strip():
                data[field] = value.strip()
            else:
                data.pop(field, None)
    path = _path()
    path.write_text(json.dumps(data, indent=2))
    try:
        path.chmod(0o600)
    except OSError:
        pass


def public_view() -> dict:
    """What the browser may see: whether each field is set, never the secret."""
    out = {}
    for f in FIELDS:
        entry = {"set": bool(get(f)), "from_env": bool(os.environ.get(ENV_NAMES[f])) and f not in _stored()}
        if f not in SECRET_FIELDS:
            entry["value"] = get(f)
        out[f] = entry
    return out
