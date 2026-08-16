import logging
import logging.handlers
import time


def setup_logger(log_path: str, retention_days: int) -> logging.Logger:
    logger = logging.getLogger("apartment_finder")
    logger.setLevel(logging.INFO)

    handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", utc=True, backupCount=retention_days, encoding="utf-8",
    )
    formatter = logging.Formatter("%(asctime)s UTC [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
