"""環境変数と安全なデフォルト値。認証情報は .env からのみ読み込む。"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    return int(value)


def _as_float(value: str | None, default: float) -> float:
    if value is None or value.strip() == "":
        return default
    return float(value)


class Settings:
    def __init__(self) -> None:
        self.root_dir = ROOT_DIR
        self.input_dir = ROOT_DIR / "input"
        self.work_dir = ROOT_DIR / "work"
        self.output_dir = ROOT_DIR / "output"
        self.logs_dir = ROOT_DIR / "logs"
        self.data_dir = ROOT_DIR / "data"
        self.screenshots_dir = ROOT_DIR / "screenshots"
        self.backup_dir = ROOT_DIR / "backup"
        self.templates_dir = ROOT_DIR / "templates"

        self.dry_run = _as_bool(os.getenv("DRY_RUN"), True)
        self.base_publish_mode = (os.getenv("BASE_PUBLISH_MODE") or "draft").strip().lower()
        if self.base_publish_mode not in {"draft", "public"}:
            self.base_publish_mode = "draft"

        self.base_login_email = os.getenv("BASE_LOGIN_EMAIL") or ""
        self.base_login_password = os.getenv("BASE_LOGIN_PASSWORD") or ""
        self.base_template_product_url = os.getenv("BASE_TEMPLATE_PRODUCT_URL") or ""
        self.base_template_product_id = os.getenv("BASE_TEMPLATE_PRODUCT_ID") or ""
        self.base_template_plugin_name = os.getenv("BASE_TEMPLATE_PLUGIN_NAME") or ""
        self.base_client_id = os.getenv("BASE_CLIENT_ID") or ""
        self.base_client_secret = os.getenv("BASE_CLIENT_SECRET") or ""
        self.base_access_token = os.getenv("BASE_ACCESS_TOKEN") or ""
        self.base_refresh_token = os.getenv("BASE_REFRESH_TOKEN") or ""
        self.base_redirect_uri = os.getenv("BASE_REDIRECT_URI") or "http://127.0.0.1:8765/callback"
        self.base_admin_base_url = (os.getenv("BASE_ADMIN_BASE_URL") or "https://admin.thebase.in").rstrip("/")
        self.base_api_base_url = "https://api.thebase.in"

        self.openai_api_key = os.getenv("OPENAI_API_KEY") or ""
        self.openai_model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.translator_provider = (os.getenv("TRANSLATOR_PROVIDER") or "openai").strip().lower()

        self.smtp_host = os.getenv("SMTP_HOST") or ""
        self.smtp_port = _as_int(os.getenv("SMTP_PORT"), 587)
        self.smtp_user = os.getenv("SMTP_USER") or ""
        self.smtp_password = os.getenv("SMTP_PASSWORD") or ""
        self.smtp_use_tls = _as_bool(os.getenv("SMTP_USE_TLS"), True)
        self.notify_email = os.getenv("NOTIFY_EMAIL") or ""
        self.mail_from = os.getenv("MAIL_FROM") or self.smtp_user

        self.sale_package_mode = (os.getenv("SALE_PACKAGE_MODE") or "translation_only").strip().lower()
        if self.sale_package_mode not in {"translation_only", "plugin_and_translation"}:
            self.sale_package_mode = "translation_only"

        self.base_register_method = (
            os.getenv("BASE_REGISTER_METHOD") or "playwright_digital"
        ).strip().lower()
        if self.base_register_method not in {"playwright_digital", "api_metadata_only"}:
            self.base_register_method = "playwright_digital"

        self.continue_when_ja_complete = _as_bool(os.getenv("CONTINUE_WHEN_JA_COMPLETE"), False)
        self.ja_translation_skip_percent = _as_float(os.getenv("JA_TRANSLATION_SKIP_PERCENT"), 95.0)
        self.update_mode = (os.getenv("UPDATE_MODE") or "new_product").strip().lower()
        if self.update_mode not in {"new_product", "skip", "needs_review"}:
            self.update_mode = "new_product"

        self.max_zip_size_mb = _as_int(os.getenv("MAX_ZIP_SIZE_MB"), 80)
        self.max_zip_files = _as_int(os.getenv("MAX_ZIP_FILES"), 5000)
        self.max_single_file_mb = _as_int(os.getenv("MAX_SINGLE_FILE_MB"), 30)
        self.translation_chunk_size = _as_int(os.getenv("TRANSLATION_CHUNK_SIZE"), 25)
        self.long_translation_ratio = _as_float(os.getenv("LONG_TRANSLATION_RATIO"), 3.0)

        self.http_timeout = _as_int(os.getenv("HTTP_TIMEOUT"), 60)
        self.user_agent = os.getenv("HTTP_USER_AGENT") or (
            "base-wp-ja-auto/1.0 (WordPress.org Plugin API client; personal shop automation)"
        )

        self.db_path = self.data_dir / "jobs.sqlite"
        self.token_store_path = self.data_dir / "base_tokens.json"
        self.playwright_state_path = self.data_dir / "playwright_state" / "state.json"
        self.template_cache_path = self.data_dir / "base_template.json"
        self.glossary_path = self.templates_dir / "glossary.json"
        self.product_name_template_path = self.templates_dir / "product_name.txt"
        self.product_description_template_path = self.templates_dir / "product_description.txt"
        self.sale_readme_template_path = self.templates_dir / "sale_readme.txt"

    def ensure_directories(self) -> None:
        for path in (
            self.input_dir,
            self.work_dir,
            self.output_dir,
            self.logs_dir,
            self.data_dir,
            self.screenshots_dir,
            self.backup_dir,
            self.templates_dir,
            self.playwright_state_path.parent,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def secret_values(self) -> list[str]:
        values = [
            self.base_login_password,
            self.base_client_secret,
            self.base_access_token,
            self.base_refresh_token,
            self.openai_api_key,
            self.smtp_password,
        ]
        return [v for v in values if v]


settings = Settings()
