"""処理結果のメール通知。認証情報はログに出さない。"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from config import settings
from src.utils import now_iso

logger = logging.getLogger("base_wp_ja_auto")


def notify_success(payload: dict) -> None:
    name = payload.get("plugin_name") or ""
    version = payload.get("plugin_version") or ""
    subject = f"【BASE商品登録完了】{name} {version}"
    body = (
        f"プラグイン名: {name}\n"
        f"バージョン: {version}\n"
        f"WordPress公式URL: {payload.get('plugin_url')}\n"
        f"翻訳文字列数: {payload.get('translated_count')}\n"
        f"未翻訳数: {payload.get('untranslated_count')}\n"
        f"BASE商品名: {payload.get('base_title')}\n"
        f"販売価格: {payload.get('price')}\n"
        f"BASE商品URL: {payload.get('base_product_url') or '(DRY RUNのため未登録)'}\n"
        f"販売用ZIP保存場所: {payload.get('output_zip')}\n"
        f"処理日時: {now_iso()}\n"
        f"モード: {'DRY RUN' if payload.get('dry_run') else '本番'}\n"
    )
    _send(subject, body)


def notify_error(payload: dict) -> None:
    name = payload.get("plugin_name") or payload.get("slug") or ""
    subject = f"【BASE商品登録エラー】{name}"
    body = (
        f"エラーが発生した工程: {payload.get('stage')}\n"
        f"エラー内容: {payload.get('error')}\n"
        f"ログファイルの場所: {payload.get('log_path')}\n"
        f"スクリーンショットの場所: {payload.get('screenshot_dir') or '(なし)'}\n"
        f"再実行方法: python app.py \"{payload.get('plugin_url') or payload.get('url')}\" --resume\n"
        f"処理日時: {now_iso()}\n"
    )
    _send(subject, body)


def notify_review(payload: dict) -> None:
    subject = "【要確認】BASE商品登録処理"
    body = (
        f"プラグイン名: {payload.get('plugin_name')}\n"
        f"工程: {payload.get('stage')}\n"
        f"内容: {payload.get('error')}\n"
        f"ログファイルの場所: {payload.get('log_path')}\n"
        f"スクリーンショットの場所: {payload.get('screenshot_dir') or '(なし)'}\n"
        f"再実行方法: python app.py \"{payload.get('plugin_url')}\" --resume\n"
        f"処理日時: {now_iso()}\n"
    )
    _send(subject, body)


def _send(subject: str, body: str) -> None:
    logger.info("メール送信: %s", subject)
    if not settings.smtp_host or not settings.notify_email:
        logger.info("SMTP または NOTIFY_EMAIL が未設定のためメールは送信せずログのみ残します")
        Path(settings.logs_dir).mkdir(parents=True, exist_ok=True)
        (settings.logs_dir / "last-mail.txt").write_text(f"{subject}\n\n{body}", encoding="utf-8")
        return
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.mail_from or settings.smtp_user
    msg["To"] = settings.notify_email
    msg.set_content(body)
    try:
        if settings.smtp_port == 465:
            with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        logger.info("メール送信完了")
    except Exception as exc:  # noqa: BLE001
        logger.info("メール送信に失敗しました（処理自体は継続）: %s", exc)
        (settings.logs_dir / "last-mail.txt").write_text(f"{subject}\n\n{body}", encoding="utf-8")
