#!/usr/bin/env python3
"""
Упрощенный тестовый скрипт для проверки интегрированного VK парсера
"""

import asyncio
import re
import ssl
import aiohttp

class VkParser:
    def __init__(self, url):
        self.url = url
        self.is_vk_com = "vk.com" in url
        self.is_vkvideo_ru = "vkvideo.ru" in url
        
        if self.is_vk_com:
            match = re.search(r"video(\d+_\d+)", url)
            if not match:
                raise ValueError("Неверный формат URL VK видео")
            self.owner_id, self.video_id = match.group(1).split("_")
        elif self.is_vkvideo_ru:
            match = re.search(r"video-(\d+_\d+)", url)
            if not match:
                raise ValueError("Неверный формат URL VKVideo")
            self.owner_id, self.video_id = match.group(1).split("_")
        else:
            raise ValueError("Неподдерживаемый URL")
        
        self._headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 YaBrowser/25.6.0.0 Safari/537.36",
        }
        
        if self.is_vkvideo_ru:
            self._headers.update({
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"https://vkvideo.ru/video-{self.owner_id}_{self.video_id}",
            })
        
        self._ssl_context = ssl.create_default_context()
        self._ssl_context.check_hostname = False
        self._ssl_context.verify_mode = ssl.CERT_NONE

    async def test_vk_com(self, session: aiohttp.ClientSession):
        """Тестирует парсинг vk.com"""
        print("Тестируем vk.com...")
        
        # Получаем страницу видео
        async with session.get(self.url, ssl=self._ssl_context) as response:
            html = await response.text()
        
        # Извлекаем hash
        hash_match = re.search(r'og:video" content="[^"]*hash=([^&"]+)', html)
        if hash_match:
            video_hash = hash_match.group(1)
            print(f"Найден hash: {video_hash}")
        else:
            print("Hash не найден")
            return False
        
        # Извлекаем название
        title_match = re.search(r'og:title" content="([^"]+)"', html)
        if title_match:
            title = title_match.group(1)
            print(f"Название: {title}")
        else:
            print("Название не найдено")
            return False
        
        # Получаем embed страницу
        embed_url = f"https://vk.com/video_ext.php?oid={self.owner_id}&id={self.video_id}&hash={video_hash}"
        print(f"Embed URL: {embed_url}")
        
        embed_headers = self._headers.copy()
        embed_headers.update({
            "Referer": self.url,
            "Origin": "https://vk.com"
        })
        
        async with session.get(embed_url, headers=embed_headers, ssl=self._ssl_context) as response:
            embed_html = await response.text()
        
        # Извлекаем URL видео
        video_urls = {}
        for quality in ['144', '240', '360', '480']:
            url_match = re.search(f'"url{quality}":"([^"]+)"', embed_html)
            if url_match:
                video_urls[quality] = url_match.group(1).replace('\\/', '/')
        
        print(f"Найдено URL: {list(video_urls.keys())}")
        return len(video_urls) > 0

    async def test_vkvideo_ru(self, session: aiohttp.ClientSession):
        """Тестирует парсинг vkvideo.ru"""
        print("Тестируем vkvideo.ru...")
        
        data = {
            "al": 1,
            "is_video_page": True,
            "video": f"-{self.owner_id}_{self.video_id}",
        }
        
        async with session.post("https://vkvideo.ru/al_video.php?act=show", 
                               data=data, ssl=self._ssl_context) as response:
            response_json = await response.json()
        
        print(f"Получен ответ с ключами: {list(response_json.keys())}")
        
        # Проверяем структуру ответа
        if 'payload' in response_json and len(response_json['payload']) > 1:
            video_info = response_json['payload'][1][4]['player']['params'][0]
            print(f"Видео информация получена")
            return True
        else:
            print("Неожиданная структура ответа")
            return False

    async def test(self):
        """Тестирует парсер"""
        async with aiohttp.ClientSession(headers=self._headers) as session:
            if self.is_vk_com:
                return await self.test_vk_com(session)
            elif self.is_vkvideo_ru:
                return await self.test_vkvideo_ru(session)
            else:
                return False

async def test_parser(url: str):
    """Тестирует парсер с указанным URL"""
    print(f"\n{'='*60}")
    print(f"Тестируем URL: {url}")
    print(f"{'='*60}")
    
    try:
        parser = VkParser(url)
        print(f"Тип URL: {'vk.com' if parser.is_vk_com else 'vkvideo.ru'}")
        print(f"Owner ID: {parser.owner_id}")
        print(f"Video ID: {parser.video_id}")
        
        success = await parser.test()
        
        if success:
            print(f"\n✅ Парсер успешно работает с {url}")
        else:
            print(f"\n❌ Парсер не смог обработать {url}")
        
        return success
        
    except Exception as e:
        print(f"❌ Ошибка при работе с {url}: {e}")
        return False

async def main():
    """Основная функция тестирования"""
    test_urls = [
        "https://vk.com/video335482664_456239334",      # Новый VK
        "https://vkvideo.ru/video-212496568_456248024"  # Старый VKVideo
    ]
    
    print("Тестирование интегрированного VK парсера")
    
    results = []
    
    for url in test_urls:
        result = await test_parser(url)
        results.append((url, result))
    
    # Итоговый отчет
    print(f"\n{'='*60}")
    print("ИТОГОВЫЙ ОТЧЕТ")
    print(f"{'='*60}")
    
    for url, success in results:
        status = "✅ УСПЕХ" if success else "❌ ОШИБКА"
        print(f"{status}: {url}")
    
    success_count = sum(1 for _, success in results if success)
    total_count = len(results)
    
    print(f"\nРезультат: {success_count}/{total_count} тестов прошли успешно")
    
    if success_count == total_count:
        print("🎉 Все тесты прошли успешно! Парсер готов к использованию.")
    else:
        print("⚠️  Некоторые тесты не прошли. Требуется доработка.")

if __name__ == "__main__":
    asyncio.run(main()) 