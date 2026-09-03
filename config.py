import os

from dotenv import load_dotenv

from models import City

load_dotenv()


# Радиус поиска вокруг locationStr, в км. 0 - только сам город (без соседних
# населённых пунктов), можно переопределить в .env через SEARCH_RADIUS_KM.
SEARCH_RADIUS_KM = int(os.environ.get("SEARCH_RADIUS_KM", "0"))

CITIES = [
    # locationStr специально "Mülheim (Ruhr)", а не "Mülheim an der Ruhr" -
    # проверено вручную: с полным названием Kleinanzeigen путает город с
    # районом Кёльна "Mülheim" (почтовые индексы 5106x вместо настоящих
    # 454xx) и отдаёт объявления не оттуда.
    City("Mülheim an der Ruhr", "Mülheim (Ruhr)", 440.50),
    City("Wuppertal", "Wuppertal", 466.00),
    City("Moers", "Moers", 460.50),
    # Тот же Vergleichsraum и тот же лимит, что у Moers - Jobcenter Kreis
    # Wesel ведёт Kamp-Lintfort/Moers/Neukirchen-Vluyn единой таблицей
    # (подтверждено на jobcenter-kreis-wesel.de).
    City("Neukirchen-Vluyn", "Neukirchen-Vluyn", 460.50),
    # Kreis Recklinghausen с 2025 года - единый Vergleichsraum на весь округ
    # (раньше было по городам отдельно): 350 Nettokaltmiete + 106 медиана
    # холодных коммунальных для ~50 м² (отчёт empirica "Mietobergrenzen im
    # Kreis Recklinghausen - Aktualisierung 2025", Stand Februar 2025).
    City("Gladbeck", "Gladbeck", 456.00),
    City("Bottrop", "Bottrop", 436.00),
]

# Жёсткий потолок площади (м²) - выше не показываем, даже если цена
# подходит. 50 - норма джобцентра для одного человека, до 55 - допустимый
# запас по договорённости с пользователем.
MAX_WOHNFLAECHE_QM = float(os.environ.get("MAX_WOHNFLAECHE_QM", "55"))

# Верхняя граница цены для самого поиска на сайте - берётся с запасом от
# max_kaltmiete, потому что в шапке объявления Kleinanzeigen иногда
# показывает не Kaltmiete, а Warmmiete (она выше на размер Nebenkosten).
# Точный расчёт Kaltmiete делается уже по карточке конкретного объявления.
SEARCH_PRICE_BUFFER = float(os.environ.get("SEARCH_PRICE_BUFFER", "1.3"))

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

# GitHub PAT (repo) для синхронизации "уже видел" между локальным ботом и
# облачным workflow через commit/push в cloud_seen.json - без него оба
# работают независимо и могут задублировать уведомление об одном и том же
# объявлении. Необязателен: если не задан, синхронизация просто выключена.
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

POLL_INTERVAL_MINUTES = float(os.environ.get("POLL_INTERVAL_MINUTES", "15"))
# Сколько объявлений с первой страницы поиска рассматривать за один цикл на
# город. Первая страница отсортирована по дате (новые сверху), этого с
# запасом хватает между двумя проверками при разумном POLL_INTERVAL_MINUTES.
MAX_LISTINGS_PER_CITY = int(os.environ.get("MAX_LISTINGS_PER_CITY", "50"))

DB_PATH = "listings.db"

LOG_PATH = "bot.log"
LOG_RETENTION_DAYS = int(os.environ.get("LOG_RETENTION_DAYS", "14"))

# Kleinanzeigen отдаёт обычный HTML без JS - не нужен headless-браузер,
# достаточно representative User-Agent, иначе некоторые запросы блокируются.
HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
