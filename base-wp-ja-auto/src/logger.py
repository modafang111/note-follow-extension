"""実行ログ。パスワード・APIキーは絶対に出さない。"""

from __future__ import annotations

import logging
import re
import sys
from datetime import datetime
from pathlib import Path

from config import settings

SECRET_PATTERNS = [
    re.compile(r"(sk-[A-Za-z0-9_-]{10,})"),
    re.compile(r"(Bearer\s+[A-Za-z0-9._\-]+)", re.IGNORECASE),
]


class RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self.secrets = [s for s in secrets if s and len(s) >= 4]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._redact(str(v)) for k, v in record.args.items()}
            else:
                record.args = tuple(self._redact(str(a)) for a in record.args)
        return True

    def _redact(self, text: str) -> str:
        for secret in self.secrets:
            text = text.replace(secret, "[REDACTED]")
        for pattern in SECRET_PATTERNS:
            text = pattern.sub("[REDACTED]", text)
        return text


def setup_logger(slug: str | None = None) -> tuple[logging.Logger, Path]:
    settings.ensure_directories()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = slug or "run"
    safe_name = re.sub(r"[^a-zA-Z0-9._-]+", "_", name)
    log_path = settings.logs_dir / f"{stamp}-{safe_name}.log"

    logger = logging.getLogger("base_wp_ja_auto")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    redactor = RedactingFilter(settings.secret_values())

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redactor)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger, log_path


def log_exception(logger: logging.Logger, exc: BaseException) -> None:
    logger.exception("スタックトレース:\n%s", exc)
