#!/usr/bin/env python3
"""
Тестовый скрипт для проверки интегрированного VK парсера
Проверяет работу как с vk.com, так и с vkvideo.ru
"""

import asyncio
import sys
import os

# Добавляем путь к основному приложению
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from app.parsers.vk import VkParser

async def test_parser(url: str):
    """Тестирует парсер с указанным URL"""
    print(f"\n{'='*60}")
    print(f"Тестируем URL: {url}")
    print(f"{'='*60}")
    
    try:
        # Создаем парсер
        parser = VkParser(url)
        print(f"Тип URL: {'vk.com' if parser.is_vk_com else 'vkvideo.ru'}")
        print(f"Owner ID: {parser.owner_id}")
        print(f"Video ID: {parser.video_id}")
        
        # Получаем доступные форматы
        print("\nПолучаем доступные форматы...")
        formats_response = await parser.get_formats()
        
        print(f"Название: {formats_response.title}")
        print(f"Автор: {formats_response.author}")
        print(f"Длительность: {formats_response.duration} сек")
        print(f"Превью: {formats_response.preview_url}")
        print(f"Доступные форматы:")
        
        for i, format_info in enumerate(formats_response.formats, 1):
            print(f"  {i}. {format_info.quality} (ID: {format_info.video_format_id}/{format_info.audio_format_id})")
        
        print(f"\n✅ Парсер успешно работает с {url}")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка при работе с {url}: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Основная функция тестирования"""
    # Тестовые URL
    test_urls = [
        "https://vk.com/video335482664_456239334",      # Новый VK
        "https://vkvideo.ru/video-212496568_456248024"  # Старый VKVideo
    ]
    
    print("Тестирование интегрированного VK парсера")
    print("Проверяем поддержку vk.com и vkvideo.ru")
    
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