# Поиск квартир

Следит за объявлениями об аренде квартир на [kleinanzeigen.de](https://www.kleinanzeigen.de/)
сразу по семи городам NRW (Mülheim an der Ruhr, Neuss, Köln, Düsseldorf,
Essen, Hilden, Münster) и шлёт в Telegram новые объявления, которые
укладываются в лимиты по цене и площади, допустимые джобцентром для одного
человека.

## Логика фильтра

1. **Площадь** — не больше `MAX_WOHNFLAECHE_QM` (по умолчанию 55 м²: 50 —
   норма, до 55 — согласованный запас).
2. **Цена** — сравнивается только **Kaltmiete** (холодная аренда, без
   коммунальных). У каждого объявления на Kleinanzeigen эта цифра доступна
   по-разному:
   - иногда указана прямо (поле «Kaltmiete» в характеристиках объявления);
   - иногда объявление даёт только «Warmmiete» и «Nebenkosten» отдельно —
     тогда Kaltmiete = Warmmiete − Nebenkosten;
   - иногда (особенно у комнат в WG) указана только «Warmmiete» без
     разбивки — точную Kaltmiete в этом случае посчитать нельзя, и такое
     объявление не попадает в уведомления (но не теряется — сохраняется в
     базе как просмотренное, чтобы не проверять его повторно).

   Логика реализована в `scraper.compute_kaltmiete()` и покрыта тестами в
   `tests/test_scraper.py`.
3. Итоговая Kaltmiete сравнивается с лимитом города (`max_kaltmiete` в
   `config.py`).

### Откуда взяты лимиты по городам

Цифры — это допустимая **Bruttokaltmiete** (Kaltmiete + холодные
коммунальные) для домохозяйства из 1 человека по официальным документам
джобцентра/города, ответственного за каждый город. Площадь для 1 человека
везде принята за 50 м².

| Город | Лимит, € | Действует с | Источник |
|---|---|---|---|
| Mülheim an der Ruhr | 440,50 | 01.10.2024 | [Amtsblatt Mülheim an der Ruhr](https://amtsblatt.muelheim-ruhr.de/node/4447) |
| Neuss | 590,00 (460 Nettokaltmiete + 130 Nebenkosten) | 01.05.2025 | Sitzungsvorlage 50/5228/XVII/2024, Rhein-Kreis Neuss (Vergleichsraum 2 „Mitte“: Neuss/Kaarst/Dormagen) |
| Köln | 677,00 | 01.01.2025 | [Richtlinie 50 01 035a, Stadt Köln](https://www.wiku-koeln.de/) |
| Düsseldorf | 565,00 | 01.07.2026 | [Jobcenter Düsseldorf](https://www.jobcenter-duesseldorf.de/finanzen/rund-ums-wohnen/geld-fuer-wohnung-und-heizung/) |
| Essen | 482,50 | 01.04.2026 | [essen.de, Pressemeldung](https://www.essen.de/meldungen/pressemeldung_1590039.de.html) |
| Oberhausen | 433,50 (316,50 Grundmiete + 117,00 Betriebskosten) | 01.01.2025 | [Jobcenter Oberhausen, обзор Bürgergeld-Anwalt](https://mein-hartz4-anwalt.de/miete-jobcenter-oberhausen/) |
| Hilden (Kreis Mettmann) | 551,50 | 01.04.2026 | [Angemessenheitsrichtwerte, jobcenter ME-aktiv](https://www.jobcenter-me-aktiv.de/) |
| Münster | 594,00 | 01.09.2025 | [Stadt Münster, Jobcenter](https://www.stadt-muenster.de/jobcenter/leistungen-lebensunterhalt/kosten-unterkunft) |

Эти значения периодически пересматриваются (обычно раз в год) — если
проходит много времени с даты выше, стоит свериться с источником и обновить
`config.py`.

**По договорённости с пользователем фильтр сравнивает Kaltmiete именно с
этими цифрами напрямую** (без добавления Nebenkosten сверху) — это немного
строже официального правила (там Nebenkosten входят в лимит), то есть
скорее пропустит меньше вариантов, чем больше.

## Как работает поиск на Kleinanzeigen

Проверено вручную (см. `config.py`, `scraper.py`): фильтрация по городу
работает через query-параметры `locationStr` и `radius`, а не через слаг в
пути URL (слаг без верного внутреннего ID локации сайт молча игнорирует и
отдаёт объявления со всей Германии). Пример рабочего URL:

```
https://www.kleinanzeigen.de/s-wohnung-mieten/preis:0:880/c203?locationStr=Köln&radius=0&sortingField=SORTING_DATE
```

Бот на каждом цикле проверки:
1. Загружает первую страницу поиска (отсортированную по дате, новые
   сверху) для каждого города, с ценой в URL — с запасом
   `SEARCH_PRICE_BUFFER` от лимита, потому что в шапке объявления
   Kleinanzeigen иногда показывает Warmmiete вместо Kaltmiete (она выше).
2. Для объявлений, которых ещё не было в базе (`listings.db`), открывает
   страницу самого объявления и считает точную Kaltmiete и площадь.
3. Если Kaltmiete ≤ лимита города и площадь ≤ `MAX_WOHNFLAECHE_QM` — шлёт
   уведомление в Telegram со ссылкой на объявление.
4. Объявление помечается как просмотренное независимо от результата — при
   следующей проверке оно уже не откроется повторно.

## Установка

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Настройка (.env)

Скопировать `.env.example` в `.env` и заполнить:

1. **BOT_TOKEN** — создать бота через [@BotFather](https://t.me/BotFather),
   команда `/newbot`. Этот бот только шлёт уведомления.
2. **CHAT_ID** — написать что-нибудь новому боту, затем открыть в браузере
   `https://api.telegram.org/bot<TOKEN>/getUpdates` и взять
   `message.chat.id` из ответа.
3. Остальные параметры (периодичность проверки, макс. площадь, радиус
   поиска, буфер цены) — по умолчанию разумные, менять не обязательно.

Города и лимиты цены заданы прямо в `config.py` (список `CITIES`) — их
можно поправить там же, если лимит для какого-то города обновился.

## Запуск

```
.venv\Scripts\python main.py
```

Дальше бот раз в `POLL_INTERVAL_MINUTES` минут (по умолчанию 15) проверяет
все семь городов и шлёт уведомления в чат с ботом.

## Структура

- `models.py` — модель `City` (без зависимости от `.env`, чтобы её могли
  импортировать `scraper.py`/`tracker.py` без настроенного окружения)
- `config.py` — чтение настроек из `.env`, список городов и их лимитов
- `scraper.py` — поиск объявлений на Kleinanzeigen, разбор карточки
  объявления, расчёт Kaltmiete
- `storage.py` — SQLite: какие объявления уже видели (`listings.db`)
- `tracker.py` — логика одной проверки города: найти новые объявления,
  отфильтровать, отправить уведомления
- `notifier.py` — отправка сообщения через Telegram Bot API
- `logger.py` — настройка ротируемого лога (`bot.log`)
- `errors.py` — классификация ошибок (временная сетевая / реальная)
- `main.py` — бесконечный цикл опроса всех городов
- `tests/` — юнит-тесты (расчёт Kaltmiete, дедупликация, фильтрация)

## Тесты

```
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

Покрыто: разбор характеристик объявления и расчёт Kaltmiete по всем трём
сценариям (`scraper.py`), разбор карточек в выдаче поиска с реальной
разметкой Kleinanzeigen, дедупликация по `ad_id` (`storage.py`), вся логика
одной проверки города — совпадение по цене/площади, отсев неподходящих,
объявления без точной Kaltmiete, повторный пропуск уже виденных
(`tracker.py`) — с лёгкими заглушками вместо реальных HTTP-запросов и
Telegram.

## Логи

`bot.log` рядом с проектом, ротация раз в сутки, хранится
`LOG_RETENTION_DAYS` дней (по умолчанию 14). `INFO` — какие объявления
найдены и отправлены, `WARNING` — временная сетевая проблема (само
пройдёт на следующем цикле), `ERROR` — что-то реально сломалось, с
traceback.
