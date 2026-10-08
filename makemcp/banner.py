"""Visual identity for makemcp: ASCII banner, tagline and copyright."""
from __future__ import annotations

TAGLINE = "Build MCP servers and clients — dependency-free."
COPYRIGHT = "Copyright (c) 2026 salim-slimani"

BANNER = r"""
 _ __ ___   __ _| | _____| | _____ _ __
| '_ ` _ \ / _` | |/ / _ \ |/ / __| '_ \
| | | | | | (_| |   <  __/   < (__| |_) |
|_| |_| |_|\__,_|_|\_\___|_|\_\___| .__/
                                  |_|
""".rstrip("\n")

FULL_BANNER = f"{BANNER}\n  {TAGLINE}\n  {COPYRIGHT} · MIT\n"


def show() -> None:
    print(FULL_BANNER)
