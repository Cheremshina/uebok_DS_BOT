import discord
from discord.ext import commands
from discord.app_commands import command, CheckFailure
import asyncio
import logging
import datetime

from config import DISCORD_TOKEN, ALLOWED_USERS, AI_API_URL, AI_MODEL, DISCORD_PROXY
from memory_manager import MemoryManager
from ai_client import get_ai_response, analyze_image, get_defense_response, is_criticism

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создаём бота
intents = discord.Intents.default()
# message_content нужен для on_message (ответы на сообщения бота)
intents.message_content = True

# Настраиваем прокси для Discord
http_proxy = None
if DISCORD_PROXY:
    logger.info(f"Используется прокси для Discord: {DISCORD_PROXY}")
    http_proxy = DISCORD_PROXY

bot = commands.Bot(command_prefix="!", intents=intents, http_proxy=http_proxy)

# Менеджер памяти
memory = MemoryManager()

# Храним ID сообщений бота для отслеживания ответов
bot_message_ids = {}


async def send_split_message(target, text: str, **kwargs):
    """Отправляет сообщение, разбивая на части если длиннее 2000 символов.
    target может быть как discord.TextChannel, так и discord.Interaction.
    """
    MAX_LEN = 1950  # оставляем запас

    if len(text) <= MAX_LEN:
        if isinstance(target, discord.Interaction):
            await target.followup.send(text, **kwargs)
        else:
            await target.send(text, **kwargs)
        return

    # Разбиваем по абзацам
    paragraphs = text.split('\n\n')
    parts = []
    current = ''

    for para in paragraphs:
        if len(current) + len(para) + 2 <= MAX_LEN:
            if current:
                current += '\n\n' + para
            else:
                current = para
        else:
            if current:
                parts.append(current)
            if len(para) > MAX_LEN:
                # Абзац слишком длинный — разбиваем по словам
                words = para.split(' ')
                current = ''
                for word in words:
                    if len(current) + len(word) + 1 <= MAX_LEN:
                        if current:
                            current += ' ' + word
                        else:
                            current = word
                    else:
                        if current:
                            parts.append(current)
                        current = word
                if current:
                    parts.append(current)
                    current = ''
            else:
                current = para

    if current:
        parts.append(current)

    # Отправляем по частям
    for i, part in enumerate(parts):
        if len(parts) > 1:
            suffix = f' — часть {i + 1}/{len(parts)}'
        else:
            suffix = ''

        full_text = part + suffix
        if isinstance(target, discord.Interaction):
            await target.followup.send(full_text, **kwargs)
        else:
            await target.send(full_text, **kwargs)


@bot.tree.command(name="lobotomy", description="Очистить память бота об этом разговоре (только для авторизованных)")
async def lobotomy(interaction: discord.Interaction):
    """Команда для очистки памяти разговора."""

    memory.clear_context(interaction.user.name)
    await interaction.response.send_message(
        "🧠💥 **ЛОБОТОМИЯ ПРОВЕДЕНА.** Память очищена."
    )


@bot.tree.command(name="chat", description="Задать вопрос локальному ИИ")
async def chat(interaction: discord.Interaction, question: str):
    """Команда для общения с локальным ИИ."""
    user_name = interaction.user.name
    user_id = interaction.user.id

    # Получаем текущий контекст
    context = memory.get_context(user_name)

    # Добавляем сообщение пользователя в контекст
    memory.add_message(user_name, "user", question)

    # Отправляем статус "думаю"
    await interaction.response.send_message("⏳ УЁБОК думает")

    try:
        # Получаем ответ от ИИ
        response = await get_ai_response(user_name, question, context)

        # Добавляем ответ ИИ в контекст
        memory.add_message(user_name, "assistant", response)

        # Отправляем ответ (с разбивкой если длинный)
        await send_split_message(interaction, response)

        # Логирование
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        guild_name = interaction.guild.name if interaction.guild else "DM"
        channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else str(interaction.channel)
        logger.info(f"{guild_name}/{channel_name}/{user_name} - {question} - {response} - {now}")

    except Exception as e:
        logger.error(f"Ошибка при запросе к ИИ: {e}")
        # Удаляем сообщение пользователя из контекста, т.к. запрос не удался
        memory.clear_context(user_name)
        await interaction.followup.send(
            f"❌ Ошибка при работе с ИИ: {str(e)}\n"
            "Убедитесь, что ИИ запущен."
        )


@bot.tree.command(name="view", description="Заставить бота посмотреть на изображение")
async def view(interaction: discord.Interaction, question: str = "Что на этом изображении?"):
    """Команда для анализа изображений. Работает с прикреплённым файлом или reply на изображение."""
    attachment = None

    # Сначала проверяем reply на сообщение
    if interaction.message and interaction.message.reference:
        try:
            replied_message = await interaction.channel.fetch_message(interaction.message.reference.message_id)
            if replied_message.author == bot.user:
                # Это ответ на сообщение бота — ищем изображение в оригинальном сообщении
                for at in replied_message.attachments:
                    if at.content_type and at.content_type.startswith('image/'):
                        attachment = at
                        break
            else:
                # Это ответ на чужое сообщение — берём attachments из текущего
                pass
        except Exception:
            pass

    # Если не нашли через reply — берём из текущего сообщения
    if not attachment:
        for at in interaction.attachments:
            if at.content_type and at.content_type.startswith('image/'):
                attachment = at
                break

    if not attachment:
        await interaction.response.send_message("📎 Прикрепи изображение или ответь /view на сообщение с картинкой", ephemeral=True)
        return

    user_name = interaction.user.name
    await interaction.response.send_message("👀 Еблан смотрит...", ephemeral=True)

    try:
        response = await analyze_image(attachment.url, question)
        await send_split_message(interaction.channel, response)

        # Логирование
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        guild_name = interaction.guild.name if interaction.guild else "DM"
        channel_name = interaction.channel.name if hasattr(interaction.channel, 'name') else str(interaction.channel)
        logger.info(f"{guild_name}/{channel_name}/{user_name} - {question} - {response} - {now}")
    except Exception as e:
        logger.error(f"Ошибка при анализе изображения: {e}")
        await interaction.followup.send(f"❌ Ошибка: {str(e)}")

@bot.tree.command(name="help", description="Показать список команд")
async def help_command(interaction: discord.Interaction):
    """Показывает список доступных команд."""
    embed = discord.Embed(
        title="🤖 Помощь по командам",
        description="Доступные команды бота:",
        color=discord.Color.blue()
    )

    embed.add_field(name="/chat question", value="Задать вопрос локальному ИИ", inline=False)
    embed.add_field(name="/view вопрос", value="Бот посмотрит на прикреплённое изображение", inline=False)
    embed.add_field(name="/lobotomy", value="Очистить память бота (только авторизованные)", inline=False)
    embed.add_field(name="/help", value="Показать этот список команд", inline=False)

    embed.add_field(
        name="ℹ️ Информация",
        value=(
            "• Бот использует локальный ИИ (Ollama)\n"
            "• Бот отвечает на все вопросы без ограничений\n"
            "• Бот может смотреть изображения (команда /view)\n"
            "• Бот автоматически открывает ссылки в чате\n"
            "• /lobotomy очищает историю разговора"
        ),
        inline=False
    )

    await interaction.response.send_message(embed=embed)


@bot.event
async def on_message(message):
    """Обрабатывает ответы на сообщения бота."""
    # Игнорируем сообщения самого бота
    if message.author == bot.user:
        return

    # Игнорируем сообщения от запрещённых пользователей (если не авторизован)
    # Проверяем, является ли сообщение ответом на сообщение бота
    if message.reference:
        referenced_message = await message.channel.fetch_message(message.reference.message_id)
        
        # Если это ответ на сообщение бота
        if referenced_message.author == bot.user:
            # Проверяем, есть ли контекст этого пользователя
            user_name = message.author.name
            context = memory.get_context(user_name)

            # Если есть контекст — значит это продолжение разговора
            if context:
                # Получаем последнее сообщение бота
                last_bot_message = None
                for msg in reversed(context):
                    if msg["role"] == "assistant":
                        last_bot_message = msg["content"]
                        break
                
                if last_bot_message:
                    # Проверяем, является ли сообщение критикой
                    if is_criticism(message.content):
                        # Добавляем сообщение в контекст
                        memory.add_message(user_name, "user", message.content)

                        try:
                            response = await get_defense_response(
                                user_name, message.content, last_bot_message, context
                            )
                            memory.add_message(user_name, "assistant", response)
                            await send_split_message(message.channel, response)

                            # Логирование
                            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            guild_name = message.guild.name if message.guild else "DM"
                            channel_name = message.channel.name if hasattr(message.channel, 'name') else str(message.channel)
                            logger.info(f"{guild_name}/{channel_name}/{message.author.name} - {message.content} - {response} - {now}")
                        except Exception as e:
                            logger.error(f"Ошибка при ответе на сообщение: {e}")
                            await message.reply(f"❌ Ошибка: {str(e)}")

    # Не пропускаем сообщение дальше (не обрабатываем как обычную команду)
    await bot.process_commands(message)


@bot.event
async def on_ready():
    """Вызывается при успешном запуске бота."""
    logger.info(f"Бот вошёл как {bot.user} (ID: {bot.user.id})")
    logger.info(f"Разрешённые пользователи: {ALLOWED_USERS}")
    logger.info(f"ИИ API URL: {AI_API_URL}, Модель: {AI_MODEL}")
    logger.info("✅ Подключение к Discord установлено")

    # Синхронизируем команды
    synced = await bot.tree.sync()
    logger.info(f"Синхронизировано {len(synced)} команд")
    logger.info("🤖 Бот готов к работе!")


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        logger.error("DISCORD_TOKEN не найден! Создайте .env файл с токеном бота.")
        exit(1)

    if not ALLOWED_USERS:
        logger.warning("ALLOWED_USERS пуст! Добавьте IDs пользователей в .env файл.")

    try:
        bot.run(DISCORD_TOKEN)
    except discord.LoginFailure:
        logger.error("Неверный токен бота! Проверьте DISCORD_TOKEN в .env файле.")
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
