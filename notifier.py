import httpx


async def verify_bot_token(bot_token: str) -> None:
    """Проверяет валидность BOT_TOKEN через Telegram getMe - без отправки
    сообщения в чат. Нужно вызывать в начале каждого прогона: если токен
    битый (например, из-за случайно затесавшегося BOM-символа при
    неаккуратной правке секрета), send_message на КАЖДОЕ найденное
    объявление будет молча падать - а без явной проверки на входе это
    легко пропустить, поскольку сам процесс не падает, только отдельные
    попытки отправки (см. инцидент 2026-08-28/29 - сутки битый токен в
    облаке не заметили, пока пользователь сам не сказал, что тишина)."""
    url = f"https://api.telegram.org/bot{bot_token}/getMe"
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(url)
        response.raise_for_status()


async def send_message(bot_token: str, chat_id: str, text: str,
                        buttons: list[tuple[str, str]] | None = None) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if buttons:
        payload["reply_markup"] = {
            "inline_keyboard": [[{"text": label, "url": link}] for label, link in buttons]
        }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
