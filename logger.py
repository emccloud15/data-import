import logging


def get_logger(name: str | None) -> logging.Logger:
    logger = logging.getLogger(name or "data_import")
    logger.setLevel(logging.DEBUG)


    if not logger.hasHandlers():
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)

        ch_fmt = "%(asctime)s - %(levelname)s - %(message)s"
        ch_formatter = logging.Formatter(ch_fmt)
        ch.setFormatter(ch_formatter)

        logger.addHandler(ch)
    return logger