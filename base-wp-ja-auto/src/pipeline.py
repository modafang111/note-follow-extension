"""処理パイプライン。段階ごとに SQLite へ保存し、途中再開できる。"""

from __future__ import annotations

import logging
import traceback
from pathlib import Path
from typing import Any

from config import settings
from src import base_client, base_template, database, mailer
from src.exceptions import (
    AlreadyProcessed,
    NeedHumanReview,
    PipelineError,
    QualityError,
    SkipPlugin,
)
from src.package_builder import build_sale_package
from src.plugin_analyzer import analyze_plugin, maybe_skip_already_translated
from src.plugin_downloader import download_plugin, extract_plugin
from src.translation_builder import build_po_mo, quality_check
from src.translator import translate_messages
from src.utils import dump_json, load_json, now_iso
from src.wordpress import PluginInfo, fetch_plugin_info, parse_url

logger = logging.getLogger("base_wp_ja_auto")

DONE_REGISTERED = {"completed", "base_registered"}


class RunOptions:
    def __init__(
        self,
        *,
        dry_run: bool | None = None,
        resume: bool = False,
        translate_only: bool = False,
        base_only: bool = False,
        force: bool = False,
        continue_if_translated: bool = False,
    ) -> None:
        self.dry_run = settings.dry_run if dry_run is None else dry_run
        self.resume = resume
        self.translate_only = translate_only
        self.base_only = base_only
        self.force = force
        self.continue_if_translated = continue_if_translated


def process_url(url: str, options: RunOptions, log_path: Path) -> dict[str, Any]:
    logger.info("処理開始: %s", url)
    slug = parse_url(url)
    info: PluginInfo | None = None
    work_dir: Path | None = None
    screenshot_dir = settings.screenshots_dir / slug
    try:
        info = _stage_info(url, slug)
        work_dir = settings.work_dir / info.slug / info.version
        work_dir.mkdir(parents=True, exist_ok=True)
        dump_json(work_dir / "plugin.json", info.to_dict())

        existing = database.get_job(info.slug, info.version)
        previous = database.latest_job_for_slug(info.slug)
        is_update = bool(previous and previous.get("plugin_version") != info.version)
        if is_update:
            logger.info(
                "更新版を検出: %s %s -> %s (将来の商品更新に備えて is_update=1)",
                info.slug,
                previous.get("plugin_version") if previous else "",
                info.version,
            )
            if settings.update_mode == "skip" and not options.force:
                raise SkipPlugin("UPDATE_MODE=skip のため更新版を自動登録しません。", stage="duplicate")
            if settings.update_mode == "needs_review" and not options.force:
                raise NeedHumanReview("更新版です。人間確認後に --force で実行してください。", stage="duplicate")

        database.upsert_job(
            info.slug,
            info.version,
            plugin_name=info.name,
            wordpress_url=info.official_url,
            download_url=info.download_url,
            work_dir=str(work_dir),
            log_path=str(log_path),
            is_update=1 if is_update else 0,
            status="running",
            stage="wordpress_info",
        )

        if (
            existing
            and existing.get("status") in DONE_REGISTERED
            and not options.force
            and not options.dry_run
        ):
            raise AlreadyProcessed(
                f"同一 slug+バージョンは登録済みです: {info.slug} {info.version} "
                f"(BASE {existing.get('base_product_id')})",
                stage="duplicate",
            )

        if options.base_only:
            result = _resume_base(info, work_dir, options, screenshot_dir)
        else:
            result = _run_full(info, work_dir, options, screenshot_dir)

        mailer.notify_success(
            {
                **result,
                "plugin_name": info.name,
                "plugin_version": info.version,
                "plugin_url": info.official_url,
                "dry_run": options.dry_run,
            }
        )
        logger.info("処理終了")
        return result
    except SkipPlugin as exc:
        logger.info("対象外: %s", exc)
        if info:
            database.mark_error(info.slug, info.version, exc.stage or "skip", str(exc))
        mailer.notify_error(
            {
                "plugin_name": info.name if info else slug,
                "slug": slug,
                "stage": exc.stage or "skip",
                "error": str(exc),
                "log_path": str(log_path),
                "plugin_url": url,
                "screenshot_dir": str(screenshot_dir),
            }
        )
        raise
    except NeedHumanReview as exc:
        logger.info("要確認: %s", exc)
        if info:
            database.upsert_job(
                info.slug,
                info.version,
                status="needs_review",
                stage=exc.stage or "review",
                error_message=str(exc)[:4000],
            )
        mailer.notify_review(
            {
                "plugin_name": info.name if info else slug,
                "stage": exc.stage or "review",
                "error": str(exc),
                "log_path": str(log_path),
                "plugin_url": url,
                "screenshot_dir": str(screenshot_dir),
            }
        )
        raise
    except Exception as exc:
        logger.info("エラー: %s", exc)
        logger.info("スタックトレース:\n%s", traceback.format_exc())
        if info:
            database.mark_error(info.slug, info.version, getattr(exc, "stage", "") or "error", str(exc))
        mailer.notify_error(
            {
                "plugin_name": info.name if info else slug,
                "slug": slug,
                "stage": getattr(exc, "stage", "") or "error",
                "error": str(exc),
                "log_path": str(log_path),
                "plugin_url": url,
                "screenshot_dir": str(screenshot_dir),
            }
        )
        raise


def _stage_info(url: str, slug: str) -> PluginInfo:
    return fetch_plugin_info(slug)


def _run_full(info: PluginInfo, work_dir: Path, options: RunOptions, screenshot_dir: Path) -> dict[str, Any]:
    zip_meta = _ensure_download(info, work_dir, options.resume)
    extracted = work_dir / "original"
    if not extracted.exists() or not options.resume:
        extract_plugin(Path(zip_meta["zip_path"]), work_dir)
    database.upsert_job(info.slug, info.version, stage="unzip", download_url=info.download_url)

    analysis = analyze_plugin(info, extracted, work_dir)
    info.text_domain = analysis.text_domain
    if analysis.license and not info.license:
        info.license = analysis.license
    dump_json(work_dir / "plugin.json", info.to_dict())
    database.upsert_job(info.slug, info.version, plugin_name=info.name, stage="analyzed")
    maybe_skip_already_translated(analysis, options.continue_if_translated)

    translations_path = work_dir / "translations.json"
    if options.resume and translations_path.exists():
        logger.info("翻訳キャッシュ/成果を再利用します（API再呼び出しを避けます）")
        translations = _load_translations(translations_path, analysis.messages)
    else:
        translations = translate_messages(analysis.messages, work_dir)
    database.upsert_job(info.slug, info.version, stage="translated", translation_date=now_iso())

    report = quality_check(analysis.messages, translations, work_dir)
    if report["source_count"] == 0:
        raise NeedHumanReview("翻訳対象文字列が 0 件でした。販売対象か確認してください。", stage="quality_check")

    files = build_po_mo(info, analysis, translations, work_dir)
    database.upsert_job(info.slug, info.version, stage="po_built")

    sale_zip = build_sale_package(info, analysis, files, work_dir)
    database.upsert_job(info.slug, info.version, stage="packaged", output_zip=str(sale_zip))

    preview = base_template.build_listing(info, sale_zip, work_dir / "product_image.png", work_dir)
    base_template.validate_preview(preview)
    database.upsert_job(info.slug, info.version, stage="preview_generated")

    if options.translate_only:
        database.upsert_job(info.slug, info.version, status="translated_only", stage="translate_only")
        return _result(info, report, preview, sale_zip, dry_run=True)

    return _register_or_dry_run(info, preview, sale_zip, report, options, screenshot_dir)


def _resume_base(info: PluginInfo, work_dir: Path, options: RunOptions, screenshot_dir: Path) -> dict[str, Any]:
    preview = load_json(work_dir / "preview.json")
    report = load_json(work_dir / "quality_report.json") or {}
    sale_zip = Path(preview["sale_file"]) if preview and preview.get("sale_file") else None
    if not preview or not sale_zip or not sale_zip.exists():
        raise PipelineError("--base-only には既存の販売ZIPと preview.json が必要です。先に本処理を実行してください。", stage="resume")
    base_template.validate_preview(preview)
    return _register_or_dry_run(info, preview, sale_zip, report, options, screenshot_dir)


def _register_or_dry_run(
    info: PluginInfo,
    preview: dict[str, Any],
    sale_zip: Path,
    report: dict[str, Any],
    options: RunOptions,
    screenshot_dir: Path,
) -> dict[str, Any]:
    if options.dry_run:
        logger.info("DRY RUN: BASEへ実際の商品登録はしません")
        database.upsert_job(
            info.slug,
            info.version,
            status="dry_run_complete",
            stage="dry_run",
            output_zip=str(sale_zip),
        )
        return _result(info, report, preview, sale_zip, dry_run=True)

    logger.info("BASE商品登録")
    if settings.base_register_method == "api_metadata_only":
        if not base_client.has_api_credentials():
            raise NeedHumanReview("BASE API 認証がありません。", stage="base_register")
        registered = base_client.register_via_api(preview)
    else:
        registered = base_client.register_via_playwright(preview, sale_zip, screenshot_dir)

    product_url = registered.get("product_url") or ""
    item_id = str(registered.get("item_id") or "")
    if item_id and not product_url:
        product_url = f"{settings.base_admin_base_url}/items/{item_id}"
    database.upsert_job(
        info.slug,
        info.version,
        status="completed",
        stage="registered",
        base_product_id=item_id,
        base_product_url=product_url,
        output_zip=str(sale_zip),
    )
    logger.info("登録確認: item_id=%s url=%s", item_id, product_url)
    preview["base_product_id"] = item_id
    preview["base_product_url"] = product_url
    dump_json(Path(preview.get("sale_file", ".")).parent.parent / "preview.json", preview) if False else None
    dump_json((settings.work_dir / info.slug / info.version) / "preview.json", preview)
    return _result(info, report, preview, sale_zip, dry_run=False, registered=registered)


def _ensure_download(info: PluginInfo, work_dir: Path, resume: bool) -> dict[str, Any]:
    meta_path = work_dir / "download_meta.json"
    zip_path = work_dir / f"{info.slug}-{info.version}.zip"
    if resume and meta_path.exists() and zip_path.exists():
        logger.info("ダウンロード済みZIPを再利用します")
        return load_json(meta_path)
    return download_plugin(info, work_dir)


def _load_translations(path: Path, messages) -> dict:
    rows = load_json(path) or []
    mapping = {}
    for row in rows:
        mapping[(row.get("msgctxt") or "", row.get("msgid") or "")] = row.get("msgstr") or ""
    for msg in messages:
        if msg.key not in mapping:
            raise PipelineError("保存済み翻訳が不足しています。--force で翻訳からやり直してください。", stage="translate")
    return mapping


def _result(
    info: PluginInfo,
    report: dict[str, Any],
    preview: dict[str, Any],
    sale_zip: Path,
    *,
    dry_run: bool,
    registered: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "plugin_name": info.name,
        "plugin_version": info.version,
        "plugin_url": info.official_url,
        "translated_count": report.get("translated_count"),
        "untranslated_count": report.get("untranslated_count"),
        "base_title": preview.get("title"),
        "price": preview.get("price"),
        "base_product_url": (registered or {}).get("product_url") or preview.get("base_product_url"),
        "base_product_id": (registered or {}).get("item_id") or preview.get("base_product_id"),
        "output_zip": str(sale_zip),
        "preview_path": str(settings.work_dir / info.slug / info.version / "preview.json"),
        "dry_run": dry_run,
        "detail": preview.get("detail"),
        "image_path": preview.get("image_path"),
    }
