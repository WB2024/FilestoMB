#!/usr/bin/env python3
"""Convenience launcher: `python3 main.py [path]` runs the TUI directly from
a checkout without installing the package.

For everyday use, prefer installing it properly instead (see README):

    pipx install -e .

That puts a `filestomb` command on your PATH that works from any directory
and picks up code changes immediately, since it's an editable install.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from filestomb.app import run

if __name__ == "__main__":
    run()
