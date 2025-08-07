# VK Video Parser - Полное решение для скачивания видео с VK.com

## Описание

Этот проект содержит полное решение для скачивания видео с VK.com без использования внешних библиотек типа yt-dlp. Решение основано только на HTTP запросах и анализе ответов сервера.

## Алгоритм работы

### 1. Извлечение параметров видео
- Из URL `https://vk.com/video335482664_456239334` извлекаем:
  - `owner_id`: 335482664
  - `video_id`: 456239334

### 2. Получение hash и названия видео
- Делаем GET запрос к странице видео
- Извлекаем hash из meta тега `og:video`
- Извлекаем название из meta тега `og:title`
- Пример: `hash=009607fd6abc1b51`, `title="Синяя птичка Мем"`

### 3. Получение embed страницы
- Используем hash для получения embed страницы:
  ```
  https://vk.com/video_ext.php?oid={owner_id}&id={video_id}&hash={hash}
  ```

### 4. Извлечение URL видео
Из embed страницы извлекаем различные URL видео:

#### Прямые URL для разных качеств:
- `url144`: 144p качество
- `url240`: 240p качество  
- `url360`: 360p качество
- `url480`: 480p качество

#### Потоковые URL:
- `hls`: HLS поток (.m3u8)
- `dash`: DASH поток (.mpd)

### 5. Скачивание видео
- Выбираем лучшее доступное качество (приоритет: 480p → 360p → 240p → 144p → HLS → DASH)
- Скачиваем видео файл с названием из VK

## Структура файлов

```
test/
├── final_vk_parser.py          # Основной скрипт
├── test_vk_parser.py           # Тестовый скрипт
├── Dockerfile.final            # Dockerfile для финального скрипта
├── docker-compose.final.yml    # Docker Compose для финального скрипта
├── Dockerfile.test             # Dockerfile для тестового скрипта
├── docker-compose.test.yml     # Docker Compose для тестового скрипта
├── output/                     # Директория с результатами
│   ├── Синяя птичка Мем_480.mp4  # Скачанные видео файлы с названиями
│   ├── embed_page.html        # Embed страница
│   ├── video_page.html        # Страница видео
│   └── api_response.json      # API ответы
└── README_VK_PARSER.md        # Этот файл
```

## Использование

### Через Docker (рекомендуется)

```bash
# Клонируем репозиторий
cd test

# Запускаем скачивание
docker-compose -f docker-compose.final.yml up --build
```

### Напрямую (требует установки зависимостей)

```bash
# Устанавливаем зависимости
pip install aiohttp aiofiles

# Запускаем скрипт
python final_vk_parser.py "https://vk.com/video335482664_456239334"
```

## Технические детали

### Заголовки запросов
```python
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36...",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9...",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}
```

### SSL настройки
```python
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
```

### Регулярные выражения для извлечения данных

#### Hash видео:
```python
r'og:video" content="[^"]*hash=([^&"]+)'
```

#### Название видео:
```python
r'og:title" content="([^"]+)"'
```

#### URL видео:
```python
# HLS
r'"hls":"([^"]+)"'

# DASH  
r'"dash_sep":"([^"]+)"'

# Прямые URL
r'"url{quality}":"([^"]+)"'
```

### Очистка названия файла
```python
def sanitize_filename(self, filename: str) -> str:
    # Удаляем недопустимые символы
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Заменяем множественные пробелы на один
    filename = re.sub(r'\s+', ' ', filename)
    # Убираем пробелы в начале и конце
    filename = filename.strip()
    # Ограничиваем длину
    if len(filename) > 100:
        filename = filename[:100]
    return filename
```

## Примеры URL видео

### Прямые URL (480p):
```
https://vkvd369.okcdn.ru/?srcIp=81.177.214.141&pr=40&expires=1755017897261&srcAg=CHROME_YA&fromCache=1&ms=185.226.53.204&type=2&subId=8075968973352&sig=-RxBWwifAhs&ct=0&urls=45.136.22.166&clientType=13&appId=512000384397&id=8075968514600
```

### HLS URL:
```
https://vkvd369.okcdn.ru/video.m3u8?srcIp=81.177.214.141&pr=40&expires=1755017897261&srcAg=CHROME_YA&fromCache=1&ms=185.226.53.204&mid=9745117030440&type=2&sig=2MgSkWF0XUA&ct=8&urls=45.136.22.166&clientType=13&cmd=videoPlayerCdn&id=8075968514600
```

## Ограничения

1. **Временные URL**: URL видео содержат временные токены и истекают через некоторое время
2. **Авторизация**: Некоторые видео могут требовать авторизации
3. **Геоблокировка**: Некоторые видео могут быть недоступны в определенных регионах
4. **Частота запросов**: Слишком частые запросы могут привести к блокировке

## Безопасность

- Скрипт не использует авторизацию VK
- Все запросы выполняются анонимно
- SSL проверки отключены для совместимости
- Используются стандартные User-Agent заголовки

## Результат

Успешно скачано видео:
- **Файл**: `Синяя птичка Мем_480.mp4`
- **Размер**: 172,171 байт
- **Качество**: 480p
- **Формат**: MP4
- **Название**: Извлечено из VK

## Заключение

Данное решение демонстрирует, как можно скачивать видео с VK.com, используя только HTTP запросы и анализ ответов сервера, без использования специализированных библиотек. Алгоритм работает путем:

1. Извлечения параметров видео из URL
2. Получения временного hash и названия для доступа к видео
3. Запроса embed страницы с правильными параметрами
4. Извлечения прямых URL видео из ответа
5. Скачивания файла в выбранном качестве с названием из VK

Решение полностью функционально и готово к использованию. 