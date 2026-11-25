import asyncio

import aiohttp
import pytest
from aiohttp import web

from app.exceptions import DownloadUserCanceledException
from app.utils import media_transfer


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["ranges", "retry", "ignore", "short", "wrong-offset", "cancel"])
async def test_http_transfer(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(media_transfer, "RANGE_SIZE", 1024)
    data = bytes(range(251)) * 43
    active = peak = 0
    retried = False

    async def serve(request):
        nonlocal active, peak, retried
        if mode == "ignore":
            return web.Response(body=data)
        start, end = map(int, request.headers["Range"].removeprefix("bytes=").split("-"))
        end = min(end, len(data) - 1)
        if mode == "retry" and start == 1024 and not retried:
            retried = True
            return web.Response(status=503)
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.005)
            body = data[start:end + 1]
            if mode == "short" and start:
                body = body[:-1]
            reported_start = 0 if mode == "wrong-offset" else start
            return web.Response(status=206, body=body, headers={
                "Content-Range": f"bytes {reported_start}-{end}/{len(data)}"
            })
        finally:
            active -= 1

    class Progress:
        total = 0
        received = 0

        async def advance(self, count, *, force=False):
            self.received += count
            if mode == "cancel" and self.received > 1024:
                raise DownloadUserCanceledException()

    app = web.Application()
    app.router.add_get("/media", serve)
    runner = web.AppRunner(app)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        url = f"http://127.0.0.1:{runner.addresses[0][1]}/media"
        progress = Progress()
        path = tmp_path / "media"
        async with aiohttp.ClientSession() as session:
            transfer = media_transfer.download_http_file(session, url, path, progress)
            if mode in ("short", "wrong-offset", "cancel"):
                with pytest.raises(DownloadUserCanceledException if mode == "cancel" else ValueError):
                    await transfer
            else:
                await transfer
                assert path.read_bytes() == data
                assert progress.received == progress.total == len(data)
                if mode == "ranges":
                    assert 1 < peak <= media_transfer.CONNECTIONS
                if mode == "retry":
                    assert retried
    finally:
        await runner.cleanup()
