# config.py
import os
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------
# Discord
# -------------------------------------------------
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Пользователи, которым разрешено использовать /lobotomy
ALLOWED_USERS = {
    os.getenv("ALLOWED_USER_1"),
    os.getenv("ALLOWED_USER_2"),
    os.getenv("ALLOWED_USER_3"),
}
ALLOWED_USERS = {uid for uid in ALLOWED_USERS if uid}

# -------------------------------------------------
# Groq (OpenAI‑совместимый) API
# -------------------------------------------------
# Токен, полученный в личном кабинете https://console.groq.com/keys
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Базовый URL Groq (по‑умолчанию – OpenAI‑совместимый эндпоинт)
GROQ_API_URL = os.getenv(
    "GROQ_API_URL", "https://api.groq.com/openai/v1"
)  # можно переопределить, если нужен прокси

# Модель, которую вы хотите использовать. Примеры:
#   "mixtral-8x7b-32768", "llama3-70b-8192", "gemma-7b-it"
GROQ_MODEL = os.getenv("GROQ_MODEL", "mixtral-8x7b-32768")

# -------------------------------------------------
# Прокси (опционально)
# -------------------------------------------------
DISCORD_PROXY = os.getenv("DISCORD_PROXY", "")
AI_PROXY = os.getenv("AI_PROXY", "")      # будет использоваться для запросов к Groq

# -------------------------------------------------
# Прочие настройки
# -------------------------------------------------
MAX_CONTEXT_MESSAGES = 20