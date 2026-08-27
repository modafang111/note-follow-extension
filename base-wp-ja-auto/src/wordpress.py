"""WordPress.org 公式 Plugin API / Translations API / GlotPress API クライアント。"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

import requests

from config import settings
from src.exceptions import PipelineError, SkipPlugin
from src.utils import (
    ALLOWED_WP_API_HOSTS,
    assert_allowed_host,
    canonical_plugin_url,
    extract_plugin_slug,
    retry,
    strip_html,
)

logger = logging.getLogger("base_wp_ja_auto")

PLUGIN_API = "https://api.wordpress.org/plugins/info/1.2/"
TRANSLATIONS_API = "https://api.wordpress.org/translations/plugins/1.0/"
GLOTPRESS_STABLE = "https://translate.wordpress.org/api/projects/wp-plugins/{slug}/stable/"
GLOTPRESS_DEV = "https://translate.wordpress.org/api/projects/wp-plugins/{slug}/dev/"


@dataclass
class PluginInfo:
    name: str
    slug: str
    version: str
    author: str
    official_url: str
    download_url: str
    description: str
    short_description: str
    requires_wordpress: str
    tested_up_to: str
    requires_php: str
    last_updated: str
    active_installs: int | None
    rating: float | None
    num_ratings: int | None
    icon_url: str
    banner_url: str
    screenshots: list[dict[str, str]]
    tags: list[str]
    license: str
    license_uri: str
    text_domain: str
    homepage: str
    business_model: str
    language_packs: list[dict[str, Any]] = field(default_factory=list)
    ja_language_pack: dict[str, Any] | None = None
    ja_percent: float | None = None
    ja_current_count: int | None = None
    ja_all_count: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("raw", None)
        return data


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": settings.user_agent, "Accept": "application/json"})
    return session


def _get_json(url: str, *, params: dict[str, Any] | None = None, allowed=ALLOWED_WP_API_HOSTS) -> Any:
    assert_allowed_host(url, allowed, "WordPress/翻訳API")

    def _do() -> Any:
        with _session() as session:
            resp = session.get(url, params=params, timeout=settings.http_timeout)
            resp.raise_for_status()
            return resp.json()

    return retry(_do, attempts=4, retry_on=(requests.RequestException,))


def parse_url(url: str) -> str:
    logger.info("URL解析: %s", url)
    slug = extract_plugin_slug(url)
    logger.info("slug抽出: %s", slug)
    return slug


def fetch_plugin_info(url_or_slug: str) -> PluginInfo:
    slug = url_or_slug if re.fullmatch(r"[a-z0-9\-]+", url_or_slug) else parse_url(url_or_slug)
    logger.info("WordPress情報取得: slug=%s", slug)
    params = {
        "action": "plugin_information",
        "request[slug]": slug,
        "request[locale]": "ja",
        "request[fields][short_description]": "1",
        "request[fields][description]": "1",
        "request[fields][sections]": "1",
        "request[fields][banners]": "1",
        "request[fields][icons]": "1",
        "request[fields][screenshots]": "1",
        "request[fields][active_installs]": "1",
        "request[fields][language_packs]": "1",
        "request[fields][tags]": "1",
        "request[fields][downloaded]": "1",
        "request[fields][rating]": "1",
        "request[fields][ratings]": "1",
        "request[fields][last_updated]": "1",
        "request[fields][homepage]": "1",
        "request[fields][downloadlink]": "1",
        "request[fields][versions]": "0",
    }
    data = _get_json(PLUGIN_API, params=params)
    if not isinstance(data, dict) or data.get("error") or not data.get("slug"):
        raise SkipPlugin(
            f"WordPress.org にプラグインが見つかりません: {slug} ({data})",
            stage="wordpress_info",
        )

    sections = data.get("sections") or {}
    description = strip_html(data.get("description") or sections.get("description") or "")
    short_description = strip_html(data.get("short_description") or "")
    icons = data.get("icons") or {}
    banners = data.get("banners") or {}
    screenshots_raw = data.get("screenshots") or {}
    screenshots: list[dict[str, str]] = []
    if isinstance(screenshots_raw, dict):
        for key, item in screenshots_raw.items():
            if isinstance(item, dict):
                screenshots.append(
                    {
                        "index": str(key),
                        "src": str(item.get("src") or ""),
                        "caption": strip_html(str(item.get("caption") or "")),
                    }
                )
            else:
                screenshots.append({"index": str(key), "src": str(item), "caption": ""})
    tags_raw = data.get("tags") or {}
    if isinstance(tags_raw, dict):
        tags = [str(v) for v in tags_raw.values()]
    elif isinstance(tags_raw, list):
        tags = [str(v) for v in tags_raw]
    else:
        tags = []

    rating_raw = data.get("rating")
    rating = None
    if isinstance(rating_raw, (int, float)):
        rating = round(float(rating_raw) / 20.0, 2) if rating_raw > 5 else float(rating_raw)

    language_packs = data.get("language_packs") or []
    ja_pack = None
    if isinstance(language_packs, list):
        for pack in language_packs:
            if isinstance(pack, dict) and str(pack.get("language") or "").lower() in {"ja", "ja_jp"}:
                ja_pack = pack
                break

    download_url = str(data.get("download_link") or "")
    info = PluginInfo(
        name=strip_html(str(data.get("name") or slug)),
        slug=str(data.get("slug") or slug),
        version=str(data.get("version") or ""),
        author=strip_html(str(data.get("author") or "")),
        official_url=canonical_plugin_url(slug),
        download_url=download_url,
        description=description,
        short_description=short_description,
        requires_wordpress=str(data.get("requires") or ""),
        tested_up_to=str(data.get("tested") or ""),
        requires_php="" if data.get("requires_php") in {None, False} else str(data.get("requires_php")),
        last_updated=str(data.get("last_updated") or ""),
        active_installs=data.get("active_installs") if isinstance(data.get("active_installs"), int) else None,
        rating=rating,
        num_ratings=data.get("num_ratings") if isinstance(data.get("num_ratings"), int) else None,
        icon_url=str(icons.get("2x") or icons.get("1x") or icons.get("svg") or ""),
        banner_url=str(banners.get("high") or banners.get("low") or ""),
        screenshots=screenshots,
        tags=tags,
        license=str(data.get("license") or ""),
        license_uri=str(data.get("license_uri") or ""),
        text_domain="",
        homepage=str(data.get("homepage") or canonical_plugin_url(slug)),
        business_model=str(data.get("business_model") or ""),
        language_packs=language_packs if isinstance(language_packs, list) else [],
        ja_language_pack=ja_pack,
        raw=data,
    )
    _attach_ja_stats(info)
    _assert_free_official(info)
    logger.info(
        "WordPress情報取得完了: %s %s author=%s installs=%s",
        info.name,
        info.version,
        info.author,
        info.active_installs,
    )
    return info


def _attach_ja_stats(info: PluginInfo) -> None:
    for path_tmpl in (GLOTPRESS_STABLE, GLOTPRESS_DEV):
        url = path_tmpl.format(slug=info.slug)
        try:
            data = _get_json(url)
        except Exception as exc:  # noqa: BLE001
            logger.info("GlotPress統計の取得に失敗 (%s): %s", url, exc)
            continue
        sets = data.get("translation_sets") if isinstance(data, dict) else None
        if not sets:
            continue
        for item in sets:
            locale = str(item.get("wp_locale") or item.get("locale") or "").lower()
            if locale == "ja":
                info.ja_percent = float(item.get("percent_translated") or 0)
                info.ja_current_count = int(item.get("current_count") or 0)
                info.ja_all_count = int(item.get("all_count") or 0)
                logger.info(
                    "公式日本語翻訳: %s%% (%s/%s)",
                    info.ja_percent,
                    info.ja_current_count,
                    info.ja_all_count,
                )
                return


def fetch_language_packs(slug: str, version: str) -> list[dict[str, Any]]:
    url = f"{TRANSLATIONS_API}?slug={slug}&version={version}"
    data = _get_json(url)
    translations = data.get("translations") if isinstance(data, dict) else None
    return translations if isinstance(translations, list) else []


def _assert_free_official(info: PluginInfo) -> None:
    if not info.version:
        raise SkipPlugin("バージョン情報が取得できませんでした。", stage="eligibility")
    if not info.download_url:
        raise SkipPlugin(
            "公式ダウンロードURLがありません。有料プラグインまたは外部配布の可能性があります。",
            stage="eligibility",
        )
    from urllib.parse import urlparse

    host = (urlparse(info.download_url).hostname or "").lower()
    if host != "downloads.wordpress.org":
        raise SkipPlugin(
            f"配布元が WordPress 公式ではありません ({host})。自動処理しません。",
            stage="eligibility",
        )
    if not info.download_url.lower().endswith(".zip") and "plugin/" not in info.download_url:
        raise SkipPlugin("ダウンロードURLが公式プラグインZIPではありません。", stage="eligibility")
    model = (info.business_model or "").lower()
    if model in {"commercial", "premium"} and host != "downloads.wordpress.org":
        raise SkipPlugin("有料/商用プラグインのため自動処理しません。", stage="eligibility")
