import os
from dotenv import load_dotenv

load_dotenv()

# Токен Discord бота (получить на https://discord.com/developers/applications)
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# IDs пользователей, которым разрешено использовать /lobotomy
# Получить ID: Настройки Discord → Продвинутые → Режим разработчика → ПКМ по пользователю → Копировать ID
ALLOWED_USERS = {os.getenv("ALLOWED_USER_1"), os.getenv("ALLOWED_USER_2"), os.getenv("ALLOWED_USER_3")}

# Убрать пустые значения из ALLOWED_USERS
ALLOWED_USERS = {uid for uid in ALLOWED_USERS if uid}

# Настройки локального ИИ
# Ollama: http://localhost:11434
# OpenAI compatible: http://localhost:11434/v1
AI_API_URL = os.getenv("AI_API_URL", "http://localhost:11434")
AI_MODEL = os.getenv("AI_MODEL", "qwen2.5vl")

# Максимальное количество сообщений в контексте (для экономии памяти)
MAX_CONTEXT_MESSAGES = 20

# Прокси для Discord и ИИ (если за прокси/корпоративной сетью)
# Формат: http://host:port или http://user:pass@host:port
DISCORD_PROXY = os.getenv("DISCORD_PROXY", "")
AI_PROXY = os.getenv("AI_PROXY", "")  # ИИ без прокси (локальный)