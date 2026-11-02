import json
import os
from datetime import datetime

class MemoryManager:
    """Управление контекстом разговоров для каждого пользователя с сохранением в файл."""

    def __init__(self, max_context=20, history_file="dialog_history.json"):
        # {username: [{"role": "user"/"assistant", "content": "..."}, ...]}
        self._contexts: dict[str, list[dict]] = {}
        self._max_context = max_context
        self._history_file = history_file
        self._load_history()

    def _load_history(self):
        """Загружает историю диалогов из файла."""
        if os.path.exists(self._history_file):
            try:
                with open(self._history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # data: {username: [messages]}
                    self._contexts = data
                print(f"📚 Загружено {len(self._contexts)} диалогов из {self._history_file}")
            except Exception as e:
                print(f"⚠️ Ошибка загрузки истории: {e}")

    def _save_history(self):
        """Сохраняет историю диалогов в файл."""
        try:
            with open(self._history_file, 'w', encoding='utf-8') as f:
                json.dump(self._contexts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Ошибка сохранения истории: {e}")

    def get_context(self, username: str) -> list[dict]:
        """Возвращает историю сообщений пользователя для отправки в ИИ."""
        return self._contexts.get(username, [])

    def add_message(self, username: str, role: str, content: str):
        """Добавляет сообщение в историю пользователя и сохраняет."""
        if username not in self._contexts:
            self._contexts[username] = []

        self._contexts[username].append({
            "role": role,
            "content": content
        })

        # Ограничиваем размер контекста
        if len(self._contexts[username]) > self._max_context:
            self._contexts[username] = self._contexts[username][-self._max_context:]

        # Сохраняем после каждого сообщения
        self._save_history()

    def clear_context(self, username: str):
        """Очищает историю сообщений конкретного пользователя и сохраняет."""
        if username in self._contexts:
            del self._contexts[username]
            self._save_history()

    def clear_all(self):
        """Полная очистка всех контекстов."""
        self._contexts.clear()
        self._save_history()

    def has_context(self, username: str) -> bool:
        """Проверяет, есть ли контекст у пользователя."""
        return username in self._contexts and len(self._contexts[username]) > 0
