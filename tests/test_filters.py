import filters


def test_tauschwohnung_title_is_excluded():
    assert filters.is_title_excluded("Suche Tauschwohnung 3 gegen 2 Zimmer") is True


def test_normal_title_is_not_excluded():
    assert filters.is_title_excluded("Schöne 2-Zimmer-Wohnung") is False


def test_monteurwohnung_title_is_excluded():
    assert filters.is_title_excluded("Ferien-Monteur - Wohnung") is True


def test_seeking_title_with_sucht_is_excluded():
    # "sucht" - это встречный поиск ("ищу квартиру"), не предложение аренды.
    assert filters.is_title_excluded("Ruhiges Rentnerehepaar sucht schöne Wohnung") is True


def test_gesucht_offer_title_is_not_excluded():
    # "gesucht" (не "sucht") - легитимная формулировка предложения аренды,
    # например "ищем нового жильца" = сдают квартиру.
    assert filters.is_title_excluded("Nachmieter gesucht für 1-Zi-Wohnung in Köln Ossendorf") is False


def test_buergergeld_exclusion_phrase_is_detected():
    assert filters.is_buergergeld_excluded("Bürgergeldempfänger nicht gewünscht!") is True


def test_alternative_buergergeld_exclusion_phrasing_is_detected():
    assert filters.is_buergergeld_excluded("Keine Transferleistungen, bitte nur Berufstätige.") is True


def test_description_without_exclusion_is_not_flagged():
    assert filters.is_buergergeld_excluded("Schöne Wohnung, Bürgergeld willkommen.") is False
