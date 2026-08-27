"""既存BASE商品を参照専用テンプレートとして扱う。既存商品は変更しない。"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from config import settings
from src import base_client
from src.exceptions import NeedHumanReview
from src.product_image import generate_product_image
from src.utils import dump_json, extract_base_item_id, load_json, sanitize_identifier, strip_4byte_chars
from src.wordpress import PluginInfo

logger = logging.getLogger("base_wp_ja_auto")

DEFAULT_NAME_TEMPLATE = "{plugin_name} WordPressプラグイン 日本語化ファイル"


@dataclass
class TemplateRules:
    source: str
    item_id: str
    title: str
    detail: str
    price: int
    stock: int
    visible: int
    category_ids: list[str]
    category_names: list[str]
    image_urls: list[str]
    identifier: str
    name_template: str
    plugin_name_in_template: str
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_or_fetch_template() -> TemplateRules:
    cached = load_json(settings.template_cache_path)
    if isinstance(cached, dict) and cached.get("title"):
        logger.info("保存済みBASEテンプレートを利用します（参照専用）")
        return _from_dict(cached)

    item_id = settings.base_template_product_id.strip()
    if not item_id and settings.base_template_product_url.strip():
        try:
            item_id = extract_base_item_id(settings.base_template_product_url)
        except Exception:  # noqa: BLE001
            item_id = ""

    if item_id and base_client.has_api_credentials():
        item = base_client.get_item(item_id)
        categories = []
        category_ids = []
        try:
            cats = base_client.get_item_categories(item_id)
            all_cats = {str(c.get("category_id")): c for c in base_client.list_categories()}
            for row in cats:
                cid = str(row.get("category_id") or "")
                if cid:
                    category_ids.append(cid)
                    name = (all_cats.get(cid) or {}).get("name")
                    if name:
                        categories.append(str(name))
        except Exception as exc:  # noqa: BLE001
            logger.info("テンプレートのカテゴリ取得をスキップ: %s", exc)
        images = [str(item.get(f"img{i}_origin")) for i in range(1, 6) if item.get(f"img{i}_origin")]
        title = str(item.get("title") or "")
        plugin_in_title = settings.base_template_plugin_name or _guess_plugin_name(title)
        name_template = _name_template_from_title(title, plugin_in_title)
        rules = TemplateRules(
            source="base_api",
            item_id=str(item.get("item_id") or item_id),
            title=title,
            detail=str(item.get("detail") or ""),
            price=int(item.get("price") or 0),
            stock=int(item.get("stock") or 10000),
            visible=int(item.get("visible") or 0),
            category_ids=category_ids,
            category_names=categories,
            image_urls=images,
            identifier=str(item.get("identifier") or ""),
            name_template=name_template,
            plugin_name_in_template=plugin_in_title,
            notes=["テンプレート商品は参照のみ。編集・削除は行っていません。"],
        )
        dump_json(settings.template_cache_path, rules.to_dict())
        return rules

    logger.info("BASE API 未設定のため、ローカルテンプレートを使用します")
    return _local_fallback()


def fetch_template_only() -> TemplateRules:
    settings.template_cache_path.unlink(missing_ok=True)
    return load_or_fetch_template()


def build_listing(info: PluginInfo, sale_zip: Path, image_path: Path | None, work_dir: Path) -> dict[str, Any]:
    logger.info("商品情報生成")
    rules = load_or_fetch_template()
    name = _apply_name(rules, info.name)
    detail = _apply_detail(rules, info)
    resolved_image: Path | None = None
    if image_path and Path(image_path).exists():
        resolved_image = Path(image_path)
    else:
        generated = generate_product_image(info.name, work_dir / "product_image.png")
        resolved_image = generated if generated and generated.exists() else None

    publish_mode = settings.base_publish_mode
    visible = 1 if publish_mode == "public" else 0
    identifier = sanitize_identifier(f"{info.slug}-ja-{info.version}")
    preview = {
        "title": strip_4byte_chars(name),
        "detail": strip_4byte_chars(detail),
        "price": rules.price if rules.price > 0 else 500,
        "stock": rules.stock if rules.stock > 0 else 10000,
        "category_ids": rules.category_ids,
        "category_names": rules.category_names,
        "image_path": str(resolved_image) if resolved_image else None,
        "image_public_url": None,
        "sale_file": str(sale_zip),
        "publish_mode": publish_mode,
        "visible": visible,
        "identifier": identifier,
        "plugin_name": info.name,
        "plugin_version": info.version,
        "plugin_url": info.official_url,
        "template_item_id": rules.item_id,
        "template_source": rules.source,
        "sale_package_mode": settings.sale_package_mode,
        "base_register_method": settings.base_register_method,
        "notes": [
            "既存テンプレート商品は変更していません。",
            "本商品は日本語化ファイルであり、オリジナルプラグイン本体ではありません。",
            *rules.notes,
        ],
    }
    dump_json(work_dir / "preview.json", preview)
    (work_dir / "preview.txt").write_text(_preview_text(preview), encoding="utf-8")
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    dump_json(settings.output_dir / f"{info.slug}-{info.version}-preview.json", preview)
    logger.info("登録内容プレビューを生成しました")
    return preview


def validate_preview(preview: dict[str, Any]) -> None:
    missing = [k for k in ("title", "detail", "price", "sale_file") if not preview.get(k)]
    if missing:
        raise NeedHumanReview(f"BASE登録前の必須項目が不足: {', '.join(missing)}", stage="precheck")
    if int(preview["price"]) <= 0:
        raise NeedHumanReview("価格が 0 以下です。", stage="precheck")
    if not Path(preview["sale_file"]).exists():
        raise NeedHumanReview("販売用ZIPが見つかりません。", stage="precheck")


def _local_fallback() -> TemplateRules:
    name_tmpl = DEFAULT_NAME_TEMPLATE
    if settings.product_name_template_path.exists():
        name_tmpl = settings.product_name_template_path.read_text(encoding="utf-8").strip() or name_tmpl
    detail = ""
    if settings.product_description_template_path.exists():
        detail = settings.product_description_template_path.read_text(encoding="utf-8")
    return TemplateRules(
        source="local_templates",
        item_id=settings.base_template_product_id or "",
        title=name_tmpl.replace("{plugin_name}", "TEMPLATE_PLUGIN"),
        detail=detail,
        price=500,
        stock=10000,
        visible=0,
        category_ids=[],
        category_names=[],
        image_urls=[],
        identifier="",
        name_template=name_tmpl,
        plugin_name_in_template=settings.base_template_plugin_name,
        notes=[
            "BASE API 未接続のため templates/ のローカル雛形を使用しています。",
            "python app.py --fetch-template で実商品を取り込んでください。",
        ],
    )


def _from_dict(data: dict[str, Any]) -> TemplateRules:
    return TemplateRules(
        source=str(data.get("source") or "cache"),
        item_id=str(data.get("item_id") or ""),
        title=str(data.get("title") or ""),
        detail=str(data.get("detail") or ""),
        price=int(data.get("price") or 0),
        stock=int(data.get("stock") or 10000),
        visible=int(data.get("visible") or 0),
        category_ids=list(data.get("category_ids") or []),
        category_names=list(data.get("category_names") or []),
        image_urls=list(data.get("image_urls") or []),
        identifier=str(data.get("identifier") or ""),
        name_template=str(data.get("name_template") or DEFAULT_NAME_TEMPLATE),
        plugin_name_in_template=str(data.get("plugin_name_in_template") or ""),
        notes=list(data.get("notes") or []),
    )


def _guess_plugin_name(title: str) -> str:
    match = re.match(r"^(.+?)\s*WordPressプラグイン", title)
    if match:
        return match.group(1).strip()
    match = re.match(r"^(.+?)\s+日本語化", title)
    if match:
        return match.group(1).strip()
    return ""


def _name_template_from_title(title: str, plugin_name: str) -> str:
    if plugin_name and plugin_name in title:
        return title.replace(plugin_name, "{plugin_name}", 1)
    guessed = _guess_plugin_name(title)
    if guessed:
        return title.replace(guessed, "{plugin_name}", 1)
    if settings.product_name_template_path.exists():
        text = settings.product_name_template_path.read_text(encoding="utf-8").strip()
        if text:
            return text
    return DEFAULT_NAME_TEMPLATE


def _apply_name(rules: TemplateRules, plugin_name: str) -> str:
    tmpl = rules.name_template or DEFAULT_NAME_TEMPLATE
    if settings.product_name_template_path.exists():
        file_tmpl = settings.product_name_template_path.read_text(encoding="utf-8").strip()
        if file_tmpl:
            tmpl = file_tmpl
    return tmpl.replace("{plugin_name}", plugin_name)


def _apply_detail(rules: TemplateRules, info: PluginInfo) -> str:
    created = date.today().isoformat()
    replacements = {
        "{plugin_name}": info.name,
        "{plugin_version}": info.version,
        "{plugin_url}": info.official_url,
        "{plugin_short_description}": info.short_description or info.description[:300],
        "{plugin_description}": info.description[:1500],
        "{text_domain}": info.text_domain or info.slug,
        "{created_date}": created,
        "{author}": info.author,
        "{requires_wordpress}": info.requires_wordpress or "不明",
        "{requires_php}": info.requires_php or "不明",
        "{license}": info.license or "プラグイン本体のライセンスおよび利用条件を守ってください",
    }
    if rules.detail.strip() and rules.source == "base_api":
        text = rules.detail
        old_name = rules.plugin_name_in_template or settings.base_template_plugin_name
        if old_name:
            text = text.replace(old_name, info.name)
        version_match = re.search(r"(\d+\.\d+(?:\.\d+)*)", rules.title + "\n" + rules.detail)
        if version_match and info.version:
            text = text.replace(version_match.group(1), info.version, 1)
        url_match = re.search(r"https?://(?:www\.)?wordpress\.org/plugins/[a-z0-9\-]+/?", text)
        if url_match:
            text = text.replace(url_match.group(0), info.official_url, 1)
        text = _ensure_not_plugin_body_notice(text)
        return text

    template = ""
    if settings.product_description_template_path.exists():
        template = settings.product_description_template_path.read_text(encoding="utf-8")
    if not template.strip():
        template = _default_description()
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template


def _ensure_not_plugin_body_notice(text: str) -> str:
    notice = "本商品は日本語化ファイルであり、オリジナルのWordPressプラグイン本体ではありません。"
    if notice not in text and "プラグイン本体ではありません" not in text:
        return notice + "\n\n" + text
    return text


def _default_description() -> str:
    return (
        "{plugin_name} WordPressプラグイン 日本語化ファイル\n\n"
        "本商品は、WordPress公式ディレクトリで公開されている無料プラグイン\n"
        "「{plugin_name}」の日本語翻訳ファイルです。\n\n"
        "※本商品はプラグイン本体ではありません。\n"
        "※オリジナルのプラグインは公式サイトから入手してください。\n\n"
        "【対象】\n"
        "プラグイン名: {plugin_name}\n"
        "対象バージョン: {plugin_version}\n"
        "公式URL: {plugin_url}\n"
        "作者: {author}\n\n"
        "【概要】\n"
        "{plugin_short_description}\n\n"
        "【日本語化対象】\n"
        "{text_domain}-ja.po / {text_domain}-ja.mo\n\n"
        "【導入方法】\n"
        "1. 公式URLからプラグイン本体をインストールする。\n"
        "2. 本商品のZIPを展開する。\n"
        "3. languages 内の翻訳ファイルを wp-content/languages/plugins/ またはプラグインの languages フォルダへ配置する。\n"
        "4. サイト言語が日本語であることを確認する。\n\n"
        "【注意事項】\n"
        "- 対象バージョン以外では未翻訳が残る場合があります。\n"
        "- 本ファイルは非公式の日本語化支援です。\n"
        "- プラグインのライセンス（{license}）を守ってください。\n"
        "- WordPress / PHP 要件: WP {requires_wordpress} / PHP {requires_php}\n\n"
        "【更新日】\n"
        "{created_date}\n"
    )


def _preview_text(preview: dict[str, Any]) -> str:
    cats = ", ".join(preview.get("category_names") or []) or "(テンプレート未取得)"
    return (
        f"商品名: {preview['title']}\n"
        f"価格: {preview['price']}\n"
        f"公開状態: {preview['publish_mode']}\n"
        f"カテゴリ: {cats}\n"
        f"販売ファイル: {preview['sale_file']}\n"
        f"画像: {preview.get('image_path') or '未生成（手動確認待ち）'}\n\n"
        f"---- 商品説明 ----\n{preview['detail']}\n"
    )
