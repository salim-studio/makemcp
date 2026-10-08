"""STDIO transport helpers (used by server.run internally)."""
from __future__ import annotations
import asyncio


async def run_stdio_server(app, reader=None, writer=None):
    from .. import _json as J
    import sys
    loop = asyncio.get_running_loop()
    if reader is None:
        reader = asyncio.StreamReader()
        await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin.buffer)
    if writer is None:
        tr, pr = await loop.connect_write_pipe(asyncio.BaseProtocol, sys.stdout.buffer)
        writer = asyncio.StreamWriter(tr, pr, reader, loop)
    while True:
        line = await reader.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            msg = J.loads(line)
        except Exception:
            continue
        resp = await app.handle(msg)
        if resp is not None:
            writer.write(J.dumps(resp) + b"\n")
            await writer.drain()
