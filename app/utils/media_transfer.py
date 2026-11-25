import asyncio
import re
import time
from pathlib import Path

import aiofiles
import aiohttp

from app.exceptions import DownloadUserCanceledException
from app.models.cache import redis_cache
from app.models.types import DownloadTask


RANGE_SIZE = 4 * 1024 * 1024
CONNECTIONS = 4
BUFFER_SIZE = 256 * 1024


class TransferProgress:
    def __init__(self, task: DownloadTask, total: int = 0):
        self.task = task
        self.total = total
        self.received = 0
        self.started = time.monotonic()
        self.last_update = self.started

    async def advance(self, count: int, *, force: bool = False):
        self.received += count
        now = time.monotonic()
        if not force and now - self.last_update < 0.4:
            return
        self.last_update = now
        if await redis_cache.is_task_canceled(self.task.id_):
            raise DownloadUserCanceledException()
        status = self.task.video_status
        speed = self.received / max(0.001, now - self.started)
        status.speed_bps = speed
        if self.total:
            status.percent = min(100, round(100 * self.received / self.total, 1))
            status.eta_seconds = int(max(0, self.total - self.received) / speed) if speed else None
        await redis_cache.set_download_task(self.task)


async def download_http_file(session: aiohttp.ClientSession, url, path: Path,
                             progress: TransferProgress, expected_size: int = 0):
    """Write verified HTTP ranges directly to their offsets in a private staging file."""
    def request(start, end):
        return session.get(url, headers={"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"})

    async def copy(response, output, length):
        written = 0
        async for chunk in response.content.iter_chunked(BUFFER_SIZE):
            written += len(chunk)
            if length is not None and written > length:
                raise ValueError("Media response exceeds requested size")
            await output.write(chunk)
            await progress.advance(len(chunk))
        if not written or (length is not None and written != length):
            raise ValueError("Incomplete media response")

    first_end = min(expected_size or RANGE_SIZE, RANGE_SIZE) - 1
    async with request(0, first_end) as first, aiofiles.open(path, "wb") as output:
        first.raise_for_status()
        if first.status == 200:
            size = expected_size or first.content_length
            progress.total = progress.total or size or 0
            await copy(first, output, size)
            await progress.advance(0, force=True)
            return
        match = re.fullmatch(r"bytes 0-(\d+)/(\d+)", first.headers.get("Content-Range", ""))
        if first.status != 206 or not match:
            raise ValueError("Invalid initial media range")
        end, size = map(int, match.groups())
        if size <= 0 or end != min(first_end, size - 1) or (expected_size and size != expected_size):
            raise ValueError("Media size changed")
        progress.total = progress.total or size
        await copy(first, output, end + 1)
        etag = first.headers.get("ETag")

    starts = iter(range(end + 1, size, RANGE_SIZE))

    async def fetch_ranges():
        # Each writer has its own file position. The iterator is shared on one event loop.
        async with aiofiles.open(path, "r+b") as output:
            for start in starts:
                stop = min(start + RANGE_SIZE, size) - 1
                await output.seek(start)
                for attempt in range(2):
                    offset = await output.tell()
                    try:
                        async with request(offset, stop) as response:
                            response.raise_for_status()
                            if (response.status != 206 or
                                    response.headers.get("Content-Range") != f"bytes {offset}-{stop}/{size}" or
                                    (etag and response.headers.get("ETag") != etag)):
                                raise ValueError("Unexpected media range")
                            await copy(response, output, stop - offset + 1)
                        break
                    except aiohttp.ClientResponseError as exc:
                        if attempt or exc.status not in (500, 502, 503, 504):
                            raise
                    except (aiohttp.ClientConnectionError, aiohttp.ClientPayloadError, asyncio.TimeoutError):
                        if attempt or await output.tell() > stop:
                            raise
                    await asyncio.sleep(0.3)

    remaining = size - end - 1
    count = min(CONNECTIONS, (remaining + RANGE_SIZE - 1) // RANGE_SIZE)
    workers = [asyncio.create_task(fetch_ranges()) for _ in range(count)]
    try:
        await asyncio.gather(*workers)
    finally:
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)
    await progress.advance(0, force=True)
