import asyncio
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

from fastapi import HTTPException
from pytubefix import Stream, YouTube, StreamQuery, Search
from bs4 import BeautifulSoup

from app.config import settings
from app.exceptions import DownloadUserCanceledException
from app.models.cache import redis_cache
from app.models.post_process import PostPrecess
from app.models.status import VideoDownloadStatus
from app.models.types import DownloadTask
from app.parsers.base import BaseParser
from app.schemas.main import SVideoFormat, SVideoResponse, SVideoDownload, SYoutubeSearchItem
from app.utils.validators_utils import fallback_background_task
from app.utils.video_utils import save_preview_on_s3, combine_audio_and_video, convert_to_mp3



class YouTubeParser(BaseParser):

    def __init__(self, url):
        self.url = url
        self._yt = YouTube(self.url)

    @classmethod
    async def search_videos(cls, query: str) -> list[SYoutubeSearchItem]:

        # def sync_search():
        #     result_items = []
        #     upload_jobs = []
        #     search = Search(query)
        #     video: YouTube
        #     for video in search.results:
        #         result_items.append(SYoutubeSearchItem(
        #             video_url=video.watch_url,
        #             title=video.title,
        #             author=video.author,
        #             duration=timedelta(milliseconds=int(video.streams.first().durationMs)).seconds,
        #             thumbnail_url=video.thumbnail_url,
        #         ))
        #
        #         if video.thumbnail_url:
        #             upload_jobs.append(save_preview_on_s3(video.thumbnail_url, video.title, video.author))
        #     return result_items, upload_jobs
        #
        # result_items, upload_jobs = await asyncio.to_thread(sync_search)
        #
        # if upload_jobs:
        #     uploaded_urls = await asyncio.gather(*upload_jobs, return_exceptions=True)
        #     idx = 0
        #     for i, item in enumerate(result_items):
        #         if item.thumbnail_url:
        #             new_url = uploaded_urls[idx]
        #             idx += 1
        #             if isinstance(new_url, str) and new_url:
        #                 item.thumbnail_url = new_url
        #
        # return result_items

        try:
            search_url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"

            async with aiohttp.ClientSession(headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ru,en;q=0.9",
            }) as session:
                async with session.get(search_url) as resp:
                    resp.raise_for_status()
                    html = await resp.text()

            yt_initial_json = None
            m = re.search(r"ytInitialData\s*=\s*(\{[\s\S]*?\});", html)
            if m:
                try:
                    yt_initial_json = _json.loads(m.group(1))
                except Exception:
                    yt_initial_json = None

            search_items: list[dict] = []
            if yt_initial_json:
                # Walk through contents to find videoRenderer entries
                def walk(obj):
                    if isinstance(obj, dict):
                        if "videoRenderer" in obj:
                            search_items.append(obj["videoRenderer"])
                        for v in obj.values():
                            walk(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            walk(v)

                walk(yt_initial_json)
            else:
                soup = BeautifulSoup(html, "lxml")
                for a in soup.select("a#video-title[href^='/watch']"):
                    search_items.append({
                        "navigationEndpoint": {"commandMetadata": {"webCommandMetadata": {"url": a.get("href")}}},
                        "title": {"runs": [{"text": a.get("title") or a.get_text(strip=True)}]},
                    })

            result_items: list[SYoutubeSearchItem] = []

            upload_jobs = []
            for item in search_items:
                url_path = (
                    item.get("navigationEndpoint", {})
                    .get("commandMetadata", {})
                    .get("webCommandMetadata", {})
                    .get("url")
                )
                if isinstance(url_path, str) and url_path.startswith("/watch"):
                    url = f"https://www.youtube.com{url_path}"
                else:
                    continue

                title = "".join(run.get("text", "") for run in item.get("title", {}).get("runs"))

                author = "".join(run.get("text", "") for run in (
                        item.get("longBylineText", {}).get("runs") or item.get("ownerText",{}).get("runs")
                ))

                thumbnail_url = None
                thumbs = item.get("thumbnail", {}).get("thumbnails", [])
                if thumbs:
                    thumbnail_url = thumbs[-1].get("url")


                duration_seconds = None
                duration_text = item.get("lengthText", {}).get("simpleText")
                if duration_text:
                    parts = duration_text.split(":")
                    secs = 0
                    for p in parts:
                        secs = secs * 60 + int(p)
                    duration_seconds = secs

                result_items.append(SYoutubeSearchItem(
                    video_url=url,
                    title=title or url,
                    author=author,
                    duration=duration_seconds,
                    thumbnail_url=thumbnail_url,
                ))

                if thumbnail_url:
                    upload_jobs.append(save_preview_on_s3(thumbnail_url, title or url, (author or "youtube")))

                if len(result_items) >= 30:
                    break

            if upload_jobs:
                uploaded_urls = await asyncio.gather(*upload_jobs, return_exceptions=True)
                idx = 0
                for i, item in enumerate(result_items):
                    if item.thumbnail_url:
                        new_url = uploaded_urls[idx]
                        idx += 1
                        if isinstance(new_url, str) and new_url:
                            item.thumbnail_url = new_url

            return result_items
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"YouTube search failed: {e}")


    @fallback_background_task
    async def download(self, task_id: str, download_video: SVideoDownload):
        task: DownloadTask = await redis_cache.get_download_task(task_id)

        download_path = Path(settings.DOWNLOAD_FOLDER) / self._yt.author
        event_loop = asyncio.get_event_loop()

        def post_process_hook(stream_: Stream, chunk: bytes, bytes_remaining: int):
            bytes_received = stream_.filesize - bytes_remaining
            percent = round(100.0 * bytes_received / float(stream_.filesize), 1)
            task.video_status.percent = float(percent)
            async def _update_and_check():
                await redis_cache.set_download_task(task_id, task)
                if await redis_cache.is_task_canceled(task_id):
                    raise DownloadUserCanceledException()
            event_loop.create_task(_update_and_check())

        self._yt.register_on_progress_callback(post_process_hook)
        try:
            if not download_video.video_format_id:
                task.video_status.description = "Downloading audio track"
                await redis_cache.set_download_task(task_id, task)
                audio_path = Path(await asyncio.to_thread(
                    self._yt.streams.get_by_itag(download_video.audio_format_id).download,
                    output_path=download_path.as_posix(),
                    filename_prefix=f"{task_id}_audio_"
                ))

                task.video_status.description = "Converting to MP3"
                await redis_cache.set_download_task(task_id, task)
                out_path = audio_path.with_suffix('.mp3')
                await asyncio.to_thread(convert_to_mp3,
                                    audio_path.as_posix(),
                                    out_path.as_posix()
                                    )
                audio_path.unlink(missing_ok=True)
                task.filepath = out_path
                
            else:
                # Стандартная логика для видео
                task.video_status.description = "Downloading video track"
                await redis_cache.set_download_task(task_id, task)
                video_path = Path(await asyncio.to_thread(
                    self._yt.streams.get_by_itag(download_video.video_format_id).download,
                    output_path=download_path.as_posix(),
                    filename_prefix=f"{task_id}_video_"
                ))
                if download_video.audio_format_id != download_video.video_format_id:
                    task.video_status.description = "Downloading audio track"
                    await redis_cache.set_download_task(task_id, task)
                    audio_path = Path(await asyncio.to_thread(
                        self._yt.streams.get_by_itag(download_video.audio_format_id).download,
                        output_path=download_path.as_posix(),
                        filename_prefix=f"{task_id}_audio_"
                    ))
                    task.video_status.description = "Merging tracks"
                    await redis_cache.set_download_task(task_id, task)
                    out_path = video_path.with_name(video_path.stem + "_out.mp4")
                    await asyncio.to_thread(combine_audio_and_video,
                                            video_path.as_posix(),
                                            audio_path.as_posix(),
                                            out_path.as_posix()
                                            )
                    audio_path.unlink(missing_ok=True)
                    video_path.unlink(missing_ok=True)
                    video_path = out_path
                task.filepath = video_path

            post_process = PostPrecess(task, download_video)
            await post_process.process()

            task.video_status.status = VideoDownloadStatus.COMPLETED
            task.video_status.description = VideoDownloadStatus.COMPLETED
            await redis_cache.set_download_task(task_id, task)

        except Exception as e:
            task.video_status.status = VideoDownloadStatus.ERROR
            task.video_status.description = str(e)
            await redis_cache.set_download_task(task_id, task)


    @staticmethod
    def _format_filter(stream: Stream):
        return (
            stream.type == "video" and
            stream.video_codec.startswith("avc1") and
            stream.height > settings.MIN_VIDEO_HEIGHT
        )


    @staticmethod
    def _get_audio_stream(streams: StreamQuery) -> Stream:
        main_stream = next(
            (s for s in streams if s.includes_audio_track and s.includes_video_track),
            None
        ) or streams.filter(only_audio=True).order_by('abr').first()
        return main_stream


    async def get_formats(self) -> SVideoResponse:
        streams = await asyncio.to_thread(lambda: self._yt.streams.fmt_streams)
        audio = await asyncio.to_thread(self._get_audio_stream, streams)

        preview_url = await save_preview_on_s3(self._yt.thumbnail_url,self._yt.title, self._yt.author)
        duration = timedelta(milliseconds=int(audio.durationMs)).seconds
        
        # Get video formats
        available_formats = [
            SVideoFormat(
                **{
                    "quality": v_format.resolution,
                    "video_format_id": str(v_format.itag),
                    "audio_format_id": str(audio.itag),
                    "filesize": round(v_format.filesize + audio.filesize, 2),
                }
            ) for v_format in filter(self._format_filter, streams)
        ]
        
        # Add audio-only format
        audio_format = SVideoFormat(
            quality="Audio only",
            video_format_id="",
            audio_format_id=str(audio.itag),
            filesize=round(audio.filesize, 2)
        )
        available_formats.append(audio_format)
        
        return SVideoResponse(
            url=self.url,
            title=self._yt.title,
            preview_url=preview_url,
            duration=duration,
            formats=available_formats,
            author=self._yt.author,
        )