#!/usr/bin/env python3
"""
VK Video Parser - Полное решение для скачивания видео с VK.com

Алгоритм работы:
1. Получаем страницу видео для извлечения hash и названия
2. Используем hash для получения embed страницы
3. Извлекаем URL видео из embed страницы
4. Скачиваем видео в максимальном качестве с названием из VK

Использование:
python final_vk_parser.py "https://vk.com/video335482664_456239334"
"""

import asyncio
import aiohttp
import ssl
import re
import aiofiles
import json
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlencode

class VKVideoParser:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1"
        }
        
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE

    def extract_video_ids(self, url: str) -> tuple:
        """Извлекает owner_id и video_id из URL"""
        match = re.search(r"video(\d+_\d+)", url)
        if not match:
            raise ValueError("Неверный формат URL VK видео")
        
        owner_id, video_id = match.group(1).split("_")
        return owner_id, video_id

    def extract_video_hash(self, html: str) -> str:
        """Извлекает hash видео из HTML страницы"""
        hash_match = re.search(r'og:video" content="[^"]*hash=([^&"]+)', html)
        if hash_match:
            return hash_match.group(1)
        return None

    def extract_video_title(self, html: str) -> str:
        """Извлекает название видео из HTML страницы"""
        title_match = re.search(r'og:title" content="([^"]+)"', html)
        if title_match:
            title = title_match.group(1)
            # Очищаем название от недопустимых символов для имени файла
            return self.sanitize_filename(title)
        return None

    def sanitize_filename(self, filename: str) -> str:
        """Очищает название файла от недопустимых символов"""
        # Удаляем или заменяем недопустимые символы
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # Заменяем множественные пробелы на один
        filename = re.sub(r'\s+', ' ', filename)
        # Убираем пробелы в начале и конце
        filename = filename.strip()
        # Ограничиваем длину
        if len(filename) > 100:
            filename = filename[:100]
        return filename

    def extract_video_urls(self, html: str) -> dict:
        """Извлекает URL видео из embed страницы"""
        video_urls = {}
        
        # HLS URL
        hls_match = re.search(r'"hls":"([^"]+)"', html)
        if hls_match:
            video_urls['hls'] = hls_match.group(1).replace('\\/', '/')
        
        # DASH URL
        dash_match = re.search(r'"dash_sep":"([^"]+)"', html)
        if dash_match:
            video_urls['dash'] = dash_match.group(1).replace('\\/', '/')
        
        # Прямые URL для разных качеств
        for quality in ['144', '240', '360', '480']:
            url_match = re.search(f'"url{quality}":"([^"]+)"', html)
            if url_match:
                video_urls[f'url{quality}'] = url_match.group(1).replace('\\/', '/')
        
        return video_urls

    def select_best_quality(self, video_urls: dict) -> tuple:
        """Выбирает лучшее доступное качество"""
        preferred_qualities = ['url480', 'url360', 'url240', 'url144', 'hls', 'dash']
        
        for quality in preferred_qualities:
            if quality in video_urls:
                return video_urls[quality], quality
        
        return None, None

    async def download_video(self, url: str, output_path: str) -> str:
        """Основная функция для скачивания видео"""
        try:
            owner_id, video_id = self.extract_video_ids(url)
            print(f"Video ID: {owner_id}_{video_id}")
            
            async with aiohttp.ClientSession(headers=self.headers) as session:
                # 1. Получаем страницу видео для извлечения hash и названия
                print(f"1. Получаем страницу видео: {url}")
                async with session.get(url, ssl=self.ssl_context) as response:
                    html = await response.text()
                
                # 2. Извлекаем hash и название
                video_hash = self.extract_video_hash(html)
                video_title = self.extract_video_title(html)
                
                if video_hash:
                    print(f"2. Найден hash: {video_hash}")
                else:
                    print("2. Hash не найден, пробуем без hash")
                
                if video_title:
                    print(f"3. Название видео: {video_title}")
                else:
                    print("3. Название видео не найдено")
                    video_title = f"video_{owner_id}_{video_id}"
                
                # 4. Получаем embed страницу
                if video_hash:
                    embed_url = f"https://vk.com/video_ext.php?oid={owner_id}&id={video_id}&hash={video_hash}"
                else:
                    embed_url = f"https://vk.com/video_ext.php?oid={owner_id}&id={video_id}"
                
                print(f"4. Получаем embed страницу: {embed_url}")
                
                embed_headers = self.headers.copy()
                embed_headers.update({
                    "Referer": url,
                    "Origin": "https://vk.com"
                })
                
                async with session.get(embed_url, headers=embed_headers, ssl=self.ssl_context) as response:
                    embed_html = await response.text()
                    print(f"5. Embed ответ получен, размер: {len(embed_html)} байт")
                
                # 5. Извлекаем URL видео
                video_urls = self.extract_video_urls(embed_html)
                print(f"6. Найдено URL видео: {list(video_urls.keys())}")
                
                if not video_urls:
                    raise Exception("URL видео не найдены")
                
                # 6. Выбираем лучшее качество
                download_url, quality_name = self.select_best_quality(video_urls)
                if not download_url:
                    raise Exception("Подходящий URL видео не найден")
                
                print(f"7. Скачиваем видео в качестве: {quality_name}")
                print(f"   URL: {download_url}")
                
                # 7. Скачиваем видео
                async with session.get(download_url, ssl=self.ssl_context) as video_response:
                    if video_response.status != 200:
                        raise Exception(f"Ошибка скачивания: {video_response.status}")
                    
                    # Определяем расширение файла
                    if quality_name == 'hls':
                        ext = '.m3u8'
                    elif quality_name == 'dash':
                        ext = '.mpd'
                    else:
                        ext = '.mp4'
                    
                    # Формируем имя файла с названием видео
                    quality_suffix = quality_name.replace('url', '') if quality_name.startswith('url') else quality_name
                    filename = f"{output_path}/{video_title}_{quality_suffix}{ext}"
                    
                    # Создаем директорию если нужно
                    Path(output_path).mkdir(parents=True, exist_ok=True)
                    
                    # Скачиваем файл
                    async with aiofiles.open(filename, "wb") as f:
                        total_size = 0
                        async for chunk in video_response.content.iter_chunked(8192):
                            await f.write(chunk)
                            total_size += len(chunk)
                    
                    print(f"8. Видео успешно скачано: {filename}")
                    print(f"   Размер: {total_size} байт")
                    
                    # Если это HLS, также сохраняем содержимое m3u8
                    if quality_name == 'hls':
                        m3u8_content = await video_response.text()
                        m3u8_filename = f"{output_path}/{video_title}_hls_content.m3u8"
                        async with aiofiles.open(m3u8_filename, "w") as f:
                            await f.write(m3u8_content)
                        print(f"   HLS содержимое сохранено: {m3u8_filename}")
                    
                    return filename
                    
        except Exception as e:
            print(f"Ошибка: {e}")
            raise

async def main():
    if len(sys.argv) != 2:
        print("Использование: python final_vk_parser.py <URL_VK_VIDEO>")
        print("Пример: python final_vk_parser.py https://vk.com/video335482664_456239334")
        return
    
    url = sys.argv[1]
    output_path = "output"
    
    parser = VKVideoParser()
    try:
        filename = await parser.download_video(url, output_path)
        print(f"\n✅ Видео успешно скачано: {filename}")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 