import asyncio
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import aiohttp
from bs4 import BeautifulSoup

from app.config import settings
from app.exceptions import DownloadUserCanceledException
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoResponse, SVideoDownload, SVideoFormat
from app.utils.helpers import remove_all_spec_chars
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import (
    save_preview_on_s3,
    convert_to_mp3,
    download_hls_to_file,
)


BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}


@dataclass
class RutubeVideo:
    title: str
    author: str
    duration: int
    preview_url: str
    master_m3u8_url: str
    variants: Dict[str, Dict[str, str]]  # height -> {"video": url, "audio"?: url, "video_bw"?: str}


class RutubeParser(BaseParser):
    OPTIONS_URL = "https://rutube.ru/api/play/options/{video_id}/?no_404=true"
    VIDEO_META_URL = "https://rutube.ru/api/video/{video_id}/?format=json"

    def __init__(self, url: str):
        self.url = url
        self.video_id = self._extract_video_id(url)
        self._headers = {**BASE_HEADERS, "Referer": url}

    @staticmethod
    def _extract_video_id(url: str) -> str:
        # Supported forms:
        #  - https://rutube.ru/video/<id>/
        #  - https://rutube.ru/play/embed/<id>
        #  - https://rutube.ru/play/private/<id>
        #  - https://rutube.ru/embed/<id>
        #  - sometimes as query ?v=<id>
        patterns = [
            r"rutube\.ru/video/([a-zA-Z0-9\-]+)/?",
            r"rutube\.ru/(?:play/embed|play/private|embed)/([a-zA-Z0-9\-]+)/?",
            r"[?&]v=([a-zA-Z0-9\-]+)",
        ]
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        raise ValueError("Unsupported RuTube URL format")

    @staticmethod
    def _parse_master_m3u8(master_text: str, base_url: str) -> Dict[str, Dict[str, str]]:
        from urllib.parse import urljoin
        variants: Dict[str, Dict[str, str]] = {}
        lines = [line.strip() for line in master_text.splitlines() if line.strip()]

        audio_groups: Dict[str, str] = {}
        audio_groups_default: Dict[str, str] = {}

        attr_re = re.compile(r"(\w+)=('([^']*)'|\"([^\"]*)\"|[^,]*)")

        for i, line in enumerate(lines):
            if line.startswith('#EXT-X-MEDIA') and 'TYPE=AUDIO' in line:
                attrs = {k: (v.strip('"\'') if v else v) for k, v, *_ in attr_re.findall(line)}
                group_id = attrs.get('GROUP-ID')
                uri = attrs.get('URI')
                is_default = (attrs.get('DEFAULT') or '').upper() == 'YES'
                if uri and group_id:
                    full_uri = urljoin(base_url, uri)
                    # Prefer DEFAULT if available
                    if is_default:
                        audio_groups_default[group_id] = full_uri
                    elif group_id not in audio_groups:
                        audio_groups[group_id] = full_uri

        for i, line in enumerate(lines):
            if line.startswith("#EXT-X-STREAM-INF"):
                resolution_match = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
                height = None
                if resolution_match:
                    height = resolution_match.group(2)
                # Extract AUDIO group
                audio_group_match = re.search(r'AUDIO="([^"]+)"', line)
                audio_group = audio_group_match.group(1) if audio_group_match else None
                # Extract video bandwidth (avg preferred)
                bw_match = re.search(r"AVERAGE-BANDWIDTH=(\d+)", line) or re.search(r"BANDWIDTH=(\d+)", line)
                video_bw = bw_match.group(1) if bw_match else None

                if i + 1 < len(lines):
                    url_line = lines[i + 1]
                    video_url = urljoin(base_url, url_line)
                    audio_url = None
                    if audio_group:
                        audio_url = audio_groups_default.get(audio_group) or audio_groups.get(audio_group)

                    key = height if height else str(len(variants))
                    variants[key] = {"video": video_url}
                    if audio_url:
                        variants[key]["audio"] = audio_url
                    if video_bw:
                        variants[key]["video_bw"] = video_bw
        return variants

    @staticmethod
    def _find_first_m3u8_in_json(obj) -> Optional[str]:
        try:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        found = RutubeParser._find_first_m3u8_in_json(v)
                        if found:
                            return found
                    elif isinstance(v, str) and ".m3u8" in v:
                        return v
            elif isinstance(obj, list):
                for item in obj:
                    found = RutubeParser._find_first_m3u8_in_json(item)
                    if found:
                        return found
        except Exception:
            pass
        return None

    async def _fetch_rutube_video(self) -> RutubeVideo:
        async with aiohttp.ClientSession(headers=self._headers) as session:
            # 1) Play options -> HLS master and preview
            async with session.get(self.OPTIONS_URL.format(video_id=self.video_id)) as resp:
                resp.raise_for_status()
                options_json = await resp.json()

            # Some responses place m3u8 under video_balancer or under streams
            master_m3u8 = None
            preview_url = None
            duration = 0
            title = ""
            author = ""

            # Try multiple common shapes
            video_balancer = options_json.get("video_balancer") or {}
            if isinstance(video_balancer, dict):
                data = video_balancer.get("data") or {}
                if isinstance(data, dict):
                    master_m3u8 = data.get("m3u8") or data.get("url")
                preview_url = video_balancer.get("thumbnail_url") or data.get("thumbnail_url")
                duration = int(float(data.get("duration"))) if data.get("duration") else 0
                title = data.get("title") or ""
                author = data.get("author") or ""

            if not master_m3u8:
                # Try generic search in JSON
                master_m3u8 = self._find_first_m3u8_in_json(options_json)
                if not master_m3u8:
                    streams = options_json.get("streams") or []
                    for s in streams:
                        if s.get("type") == "hls" and s.get("url"):
                            master_m3u8 = s["url"]
                            break

            # 2) Fallback meta for title/author/preview
            if not title or not author or not preview_url:
                try:
                    async with session.get(self.VIDEO_META_URL.format(video_id=self.video_id)) as meta_resp:
                        meta_resp.raise_for_status()
                        meta_json = await meta_resp.json()
                        title = title or meta_json.get("title") or ""
                        author = author or (meta_json.get("author") or {}).get("name", "")
                        preview_url = preview_url or meta_json.get("thumbnail_url")
                        if not duration:
                            duration = int(meta_json.get("duration", 0))
                except Exception:
                    pass

            if not master_m3u8:
                # 3) Fallback: scrape HTML for m3u8
                async with session.get(self.url, headers={**self._headers, "Accept": "text/html,application/xhtml+xml"}) as page_resp:
                    page_resp.raise_for_status()
                    html = await page_resp.text()
                # Look for any .m3u8 URL
                m = re.search(r"https?://[^'\"\s]+\.m3u8[^'\"\s]*", html)
                if m:
                    master_m3u8 = m.group(0)
                # Fallback preview from og:image
                if not preview_url:
                    try:
                        soup = BeautifulSoup(html, "lxml")
                        og_img = soup.select_one("meta[property='og:image']")
                        if og_img and og_img.get("content"):
                            preview_url = og_img["content"]
                        if not title:
                            og_title = soup.select_one("meta[property='og:title']")
                            if og_title and og_title.get("content"):
                                title = og_title["content"]
                    except Exception:
                        pass

            if not master_m3u8:
                raise ValueError("RuTube: HLS playlist not found")

            # 3) Parse master m3u8
            async with session.get(master_m3u8, headers=self._headers) as m3u8_resp:
                m3u8_resp.raise_for_status()
                master_text = await m3u8_resp.text()
                base_url = str(m3u8_resp.url)

            variants = self._parse_master_m3u8(master_text, base_url)

            # thumbnail -> s3
            preview_s3_url = None
            if preview_url:
                preview_s3_url = await save_preview_on_s3(preview_url, title or self.video_id, author or "rutube")

            return RutubeVideo(
                title=title or f"rutube_{self.video_id}",
                author=author or "rutube",
                duration=duration,
                preview_url=preview_s3_url,
                master_m3u8_url=master_m3u8,
                variants=variants,
            )

    async def get_formats(self) -> SVideoResponse:
        video = await self._fetch_rutube_video()

        available_formats: list[SVideoFormat] = []
        for height in sorted(video.variants.keys(), key=lambda x: int(re.sub("[^0-9]", "", x))):
            variant = video.variants[height]
            estimated_size = 0
            if video.duration:
                try:
                    v_bw = int(variant.get("video_bw") or 0)  # bits per second
                    a_bw = 128000 if "audio" in variant else 0  # assume 128 kbps if separate audio
                    total_bps = v_bw + a_bw
                    if total_bps > 0:
                        estimated_size = int((total_bps / 8) * int(video.duration))
                except Exception:
                    estimated_size = 0
            available_formats.append(
                SVideoFormat(
                    **{
                        "quality": f"{height}p",
                        "video_format_id": height,
                        "audio_format_id": height,
                        "filesize": estimated_size,
                    }
                )
            )

        if video.variants:
            min_h = min(video.variants.keys(), key=lambda x: int(re.sub("[^0-9]", "", x)))
            available_formats.append(
                SVideoFormat(
                    **{
                        "quality": "Audio only",
                        "video_format_id": "",
                        "audio_format_id": str(min_h),
                        "filesize": int(((128000) / 8) * int(video.duration)) if video.duration else 0,
                    }
                )
            )

        return SVideoResponse(
            url=self.url,
            title=video.title,
            author=video.author,
            preview_url=video.preview_url,
            duration=video.duration,
            formats=available_formats,
        )

    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)
        video = await self._fetch_rutube_video()

        is_audio_only = not download_video.video_format_id
        chosen_id = download_video.audio_format_id if is_audio_only else download_video.video_format_id
        if chosen_id not in video.variants:
            # fallback to closest available: pick max or min
            if video.variants:
                if is_audio_only:
                    chosen_id = min(video.variants.keys(), key=lambda x: int(re.sub("[^0-9]", "", x)))
                else:
                    chosen_id = max(video.variants.keys(), key=lambda x: int(re.sub("[^0-9]", "", x)))
            else:
                raise ValueError("No available HLS variants for this video")

        chosen_variant = video.variants[chosen_id]

        extension = ".mp3" if is_audio_only else ".mp4"
        author_dir_name = remove_all_spec_chars(video.author or "rutube")
        file_name = f"{task_id}_{remove_all_spec_chars(video.title or 'rutube')}{extension}"
        download_path = Path(settings.DOWNLOAD_FOLDER) / author_dir_name / file_name
        download_path.parent.mkdir(parents=True, exist_ok=True)

        temp_path = download_path.with_suffix(".temp.mp4") if is_audio_only else download_path
        task.video_status.description = "Downloading audio track" if is_audio_only else "Downloading video track"
        task.filepath = temp_path
        await redis_cache.set_download_task(task)

        event_loop = asyncio.get_running_loop()

        def on_progress(seconds_done: float, percent: float):
            task.video_status.percent = float(percent)
            asyncio.run_coroutine_threadsafe(redis_cache.set_download_task(task), event_loop)

        is_cancel = False
        async def check_redis_cancel():
            nonlocal is_cancel
            is_cancel = await redis_cache.is_task_canceled(task_id)

        def check():
            asyncio.run_coroutine_threadsafe(check_redis_cancel(), event_loop)
            return is_cancel

        audio_hls = chosen_variant.get("audio") or chosen_variant.get("video")
        video_hls = None

        if not is_audio_only:
            video_hls = chosen_variant["video"]

        await asyncio.to_thread(
            download_hls_to_file,
            audio_hls,
            temp_path.as_posix(),
            int(video.duration) if video.duration else 0,
            video_hls,
            on_progress,
            self._headers,
            check
        )

        if is_audio_only:
            task.video_status.description = "Converting to MP3"
            await redis_cache.set_download_task(task)
            await asyncio.to_thread(
                convert_to_mp3,
                temp_path.as_posix(),
                download_path.as_posix(),
            )
            temp_path.unlink(missing_ok=True)
            task.filepath = download_path
        else:
            task.filepath = temp_path

        post_process = PostPrecess(task, download_video)
        await post_process.process()

        task.video_status.status = VideoDownloadStatus.COMPLETED
        task.video_status.description = VideoDownloadStatus.COMPLETED
        await redis_cache.set_download_task(task)


