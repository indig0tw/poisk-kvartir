import re

# Tauschwohnung - это обмен квартирами между жильцами, а не аренда у
# арендодателя (часто у соцжилья с фиксированной привязкой к квартире) -
# пользователю такое не подходит, отсеиваем по названию.
# Monteur(wohnung/zimmer) - посуточное жильё для командированных рабочих,
# ценник совсем другой природы (не помесячная Kaltmiete), для долгосрочной
# аренды не годится (реальный пример: "Ferien-Monteur - Wohnung" за 30 €
# оказался посуточной ценой, а не месячной Kaltmiete).
# Zwischenmiete - временная субаренда на несколько недель/месяцев с чётким
# сроком окончания, не долгосрочная аренда, которую ищет пользователь
# (реальный пример: 2 из 5 объявлений на WG-Gesucht оказались такими).
_EXCLUDED_TITLE_KEYWORDS = ("tausch", "monteur", "zwischenmiete")

# "sucht" (не "gesucht"!) в начале заголовка - типичная формулировка
# объявления "ищу квартиру" (например "Rentnerehepaar sucht schöne
# Wohnung") - это не предложение аренды, а встречный поиск. "gesucht" не
# трогаем - это распространённая легитимная формулировка предложений вроде
# "Nachmieter gesucht" ("ищем нового жильца" = это предложение сдать).
_SEEKING_TITLE_RE = re.compile(r"\bsucht\b", re.IGNORECASE)

# Некоторые арендодатели прямо пишут в описании, что не готовы сдавать
# получателям Bürgergeld/социальных выплат - подходящих по цене и площади
# вариантов у такого объявления для пользователя всё равно нет, отсеиваем.
# Порядок слов в реальных объявлениях разный - "kein Bürgergeld" (отрицание
# перед словом), но не реже встречается "Bürgergeldempfänger nicht
# gewünscht" (отрицание после) - поэтому ищем отрицание в окне в несколько
# слов вокруг ключевого слова, а не в жёстком порядке.
_BUERGERGELD_KEYWORD_RE = re.compile(r"b[üu]rgergeld\w*|transferleistung\w*|sozialleistung\w*|hartz\s*4|hartz-4",
                                      re.IGNORECASE)
_NEGATION_RE = re.compile(r"\bkein[e]?\b|\bnicht\b", re.IGNORECASE)
_NEGATION_WINDOW_CHARS = 25


def is_title_excluded(title: str) -> bool:
    lowered = title.lower()
    if any(keyword in lowered for keyword in _EXCLUDED_TITLE_KEYWORDS):
        return True
    return bool(_SEEKING_TITLE_RE.search(title))


def is_buergergeld_excluded(text: str) -> bool:
    for match in _BUERGERGELD_KEYWORD_RE.finditer(text):
        window_start = max(0, match.start() - _NEGATION_WINDOW_CHARS)
        window_end = min(len(text), match.end() + _NEGATION_WINDOW_CHARS)
        if _NEGATION_RE.search(text[window_start:window_end]):
            return True
    return False
