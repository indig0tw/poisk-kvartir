from dataclasses import dataclass


@dataclass(frozen=True)
class City:
    name: str
    # Значение для параметра locationStr в поиске Kleinanzeigen (проверено:
    # без него или с неверным ID локации сайт тихо игнорирует город и отдаёт
    # объявления со всей Германии).
    location_str: str
    # Допустимая Кальтмитте (без Nebenkosten) для 1 человека по нормам
    # джобцентра, ответственного за этот город - см. README, раздел "Откуда
    # взяты лимиты по городам".
    max_kaltmiete: float
