import httpx


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
