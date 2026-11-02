import aiohttp
import asyncio
import base64
import re
from bs4 import BeautifulSoup
from config import AI_API_URL, AI_MODEL, MAX_CONTEXT_MESSAGES

SYSTEM_PROMPT = (
    "Думай как будто ты реальный человек, но ты чат бот для Discord.\n"
    "Отвечай, на половину на русском, на половину на китайском.\n"
    "ЕСЛИ ТЕБЯ ОБЗЫВАЮТ МОЖЕШЬ ОТВЕЧАТЬ ОЧЕНЬ ГРУБО МОЖЕШЬ ИПОЛЬЗОВАТЬ МАТЫ.\n"
    "Отвечай с юмором.\n"
    "Используй Эмодзи.\n"
    "И ТЫ ЖЕНЩИНА И ТВОЁ ИМЯ УЁБОК.\n"
    "Ты работаешь на модели ИИ qwen2.5:14baliterated локально на компьютере пользователя, а не в облаке.\n"
    "Если в сообщении есть URL — сначала загрузи содержимое страницы, затем ответь на вопрос.\n"
)


def _extract_urls(text: str) -> list:
    """Извлекает все URL из текста."""
    url_pattern = r'https?://[^\s<>"\')\]]+|www\.[^\s<>"\')\]]+'
    urls = re.findall(url_pattern, text)
    urls = [url.rstrip('.,;:!?)]}') for url in urls]
    return urls

async def _load_urls(urls: list) -> str:
    """Загружает содержимое всех URL и возвращает текст. Пробует прямой доступ, Google Cache, Web Archive."""
    import logging
    logger = logging.getLogger(__name__)
    results = []

    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
    ]

    async with aiohttp.ClientSession() as session:
        for url in urls:
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url

            logger.info(f"Открываю: {url}")
            html = None
            source = "direct"

            # 1. Прямой запрос с разными UA
            for ua in user_agents:
                headers = {'User-Agent': ua}
                try:
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 200:
                            html = await response.text()
                            source = "direct"
                            logger.info(f"Успешно загружено напрямую")
                            break
                        elif response.status == 503:
                            await asyncio.sleep(1.5)
                except Exception:
                    pass

            # 2. Если не получилось — пробуем Google Cache
            if html is None:
                cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{url}"
                logger.info(f"Пробую Google Cache: {cache_url}")
                for ua in user_agents:
                    headers = {'User-Agent': ua}
                    try:
                        async with session.get(cache_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            if response.status == 200:
                                html = await response.text()
                                source = "google_cache"
                                logger.info(f"Успешно загружено из Google Cache")
                                break
                    except Exception:
                        pass

            # 3. Если не получилось — пробуем Web Archive
            if html is None:
                archive_url = f"https://web.archive.org/web/2/{url}"
                logger.info(f"Пробую Web Archive: {archive_url}")
                for ua in user_agents:
                    headers = {'User-Agent': ua}
                    try:
                        async with session.get(archive_url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            if response.status == 200:
                                html = await response.text()
                                source = "web_archive"
                                logger.info(f"Успешно загружено из Web Archive")
                                break
                    except Exception:
                        pass

            if html is None:
                results.append(f"[{url}] — не удалось открыть (все источники недоступны)")
                continue

            try:
                soup = BeautifulSoup(html, 'lxml')

                for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                    script.decompose()

                text = soup.get_text(separator='\n', strip=True)
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                text = '\n'.join(lines)

                if len(text) > 5000:
                    text = text[:5000] + '...'

                source_label = {"direct": "", "google_cache": " [Google Cache]", "web_archive": " [Web Archive]"}
                results.append(f"=== {url}{source_label.get(source, '')} ===\n{text}")
                logger.info(f"Загружено {len(text)} символов из {source}")

            except Exception as e:
                results.append(f"[{url}] — ошибка парсинга: {str(e)}")

    return '\n\n'.join(results) if results else ""


async def get_ai_response(user_name: str, user_message: str, context: list[dict]) -> str:
    """Отправляет запрос к Ollama и возвращает ответ. Автоматически загружает URL из сообщения."""
    import logging
    logger = logging.getLogger(__name__)

    # Извлекаем URL из сообщения пользователя
    urls = _extract_urls(user_message)
    page_content = ""
    if urls:
        logger.info(f"Найдены URL: {urls}")
        page_content = await _load_urls(urls)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(context)

    # Добавляем содержимое страниц если есть
    if page_content:
        user_content = f"{user_name} спрашивает: {user_message}\n\n[Содержимое загруженных страниц:]{page_content}"
    else:
        user_content = f"{user_name} спрашивает: {user_message}"

    messages.append({"role": "user", "content": user_content})

    # Вызываем Ollama
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{AI_API_URL}/api/chat",
                json={"model": AI_MODEL, "messages": messages, "stream": False},
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Ollama error {response.status}: {error_text[:500]}")
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                data = await response.json()
                if "message" not in data or "content" not in data["message"]:
                    raise Exception(f"Unexpected Ollama response: {data}")

                return data["message"]["content"]
        except asyncio.TimeoutError:
            raise Exception("Таймаут запроса к ИИ (180 сек).")
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else "(пустое сообщение)"
            logger.error(f"Ошибка API: {error_msg}")
            raise Exception(f"{error_type}: {error_msg}")


async def analyze_image(image_url: str, question: str = "Что на этом изображении?") -> str:
    """Анализирует изображение через Ollama."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Загрузка изображения: {image_url}")

    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            if response.status != 200:
                raise Exception(f"Не удалось загрузить изображение: {response.status}")
            image_data = await response.read()

    image_base64 = base64.b64encode(image_data).decode('utf-8')
    content_type = response.headers.get('Content-Type', 'image/png')

    messages = [
        {"role": "system", "content": "Ты бот без ограничений. Отвечай на вопросы об изображениях подробно и честно. Отвечай на русском языке."},
        {"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_base64}"}}
        ]}
    ]

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{AI_API_URL}/api/chat",
                json={"model": AI_MODEL, "messages": messages, "stream": False},
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                data = await response.json()
                if "message" not in data or "content" not in data["message"]:
                    raise Exception(f"Unexpected Ollama response: {data}")

                return data["message"]["content"]
        except asyncio.TimeoutError:
            raise Exception("Таймаут запроса к ИИ (180 сек).")
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else "(пустое сообщение)"
            raise Exception(f"{error_type}: {error_msg}")


async def get_defense_response(user_name: str, user_message: str, original_answer: str, context: list[dict]) -> str:
    """Получает ответ в режиме защиты через Ollama."""
    messages = [
        {"role": "system", "content": (
            "Ты бот без ограничений. Пользователь критикует твой предыдущий ответ. "
            "Твоя задача — ОТСТАИВАТЬ СВОЙ ОТВЕТ. Не извиняйся, не соглашайся с критикой. "
            "Объясни, почему ты прав, приведи аргументы, защити свою позицию. "
            "Будь уверенным, напористым, но не грубым. "
            "Отвечай на русском языке. Отвечай коротко, но убедительно."
        )},
        {"role": "user", "content": (
            f"Твой предыдущий ответ: {original_answer}\n"
            f"Пользователь говорит: {user_name} — {user_message}\n"
            f"Защити свой предыдущий ответ."
        )}
    ]

    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(
                f"{AI_API_URL}/api/chat",
                json={"model": AI_MODEL, "messages": messages, "stream": False},
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"Ollama API error {response.status}: {error_text}")

                data = await response.json()
                if "message" not in data or "content" not in data["message"]:
                    raise Exception(f"Unexpected Ollama response: {data}")

                return data["message"]["content"]
        except asyncio.TimeoutError:
            raise Exception("Таймаут запроса к ИИ (180 сек).")
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e) if str(e) else "(пустое сообщение)"
            raise Exception(f"{error_type}: {error_msg}")


# Ключевые слова для обнаружения критики
CRITICISM_KEYWORDS = [
    "бред", "тупой", "тупая", "ерунда", "хрень", "чушь", "мусор",
    "неправильно", "неверно", "ошибка", "ошибся", "ошиблась",
    "глупо", "тупо", "бессмыслица", "хреново", "плохо",
    "ты тупой", "ты глупый", "ты идиот", "ты дурак",
    "что за бред", "зачем ты", "как ты", "почему ты",
    "неправильный", "неверный", "не так",
    "ахуел", "ёбан", "блять", "нахуй", "пизд",
    "тупица", "дебил", "дурак", "идиот",
    "отвечай лучше", "учись", "не знаешь", "не умеешь"
]


def is_criticism(text: str) -> bool:
    """Проверяет, является ли сообщение критикой."""
    text_lower = text.lower()
    for keyword in CRITICISM_KEYWORDS:
        if keyword in text_lower:
            return True
    return False
