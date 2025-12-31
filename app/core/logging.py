from loguru import logger


def setup_logging() -> None:
    # Basic Loguru configuration; can be extended for JSON/structured logging later.
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level="INFO",
        backtrace=True,
        diagnose=True,
    )
