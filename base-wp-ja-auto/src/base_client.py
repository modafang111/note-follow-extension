"""BASE 公式APIクライアントと、APIではできないデジタルコンテンツ添付用 Playwright。

公式仕様（https://docs.thebase.in/api/ 2026-08-27 確認）:
- 商品メタデータ登録: POST /1/items/add （title, detail, price, stock, visible 等）
- 商品取得: GET /1/items/detail/:item_id
- 画像: POST /1/items/add_image （公開URLが必要。ローカルファイル直アップロードは非対応）
- カテゴリ: GET /1/categories , POST /1/item_categories/add
- デジタルコンテンツのファイル添付APIは公開されていない
- デジタルコンテンツ商品は API から編集できない（add_image エラー文言より）
- 商品削除 API は存在するが、本プログラムでは絶対に呼び出さない
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from config import settings
from src.exceptions import BaseApiUnavailable, NeedHumanReview, PipelineError
from src.utils import ALLOWED_BASE_API_HOSTS, assert_allowed_host, dump_json, load_json, retry

logger = logging.getLogger("base_wp_ja_auto")

AUTH_HINTS = [
    "認証コード",
    "二段階認証",
    "2段階認証",
    "two-factor",
    "two factor",
    "totp",
    "recaptcha",
    "hcaptcha",
    "captcha",
    "本人確認",
    "セキュリティチェック",
]


def _token_store() -> dict[str, str]:
    data = load_json(settings.token_store_path, default={}) or {}
    return data if isinstance(data, dict) else {}


def _save_tokens(access: str, refresh: str) -> None:
    dump_json(
        settings.token_store_path,
        {"access_token": access, "refresh_token": refresh},
    )


def current_access_token() -> str:
    stored = _token_store()
    return stored.get("access_token") or settings.base_access_token


def current_refresh_token() -> str:
    stored = _token_store()
    return stored.get("refresh_token") or settings.base_refresh_token


def has_api_credentials() -> bool:
    return bool(current_access_token() or (settings.base_client_id and current_refresh_token()))


def refresh_access_token() -> str:
    if not (settings.base_client_id and settings.base_client_secret and current_refresh_token()):
        raise BaseApiUnavailable("BASE リフレッシュトークンまたはクライアント情報が不足しています。")
    url = f"{settings.base_api_base_url}/1/oauth/token"
    assert_allowed_host(url, ALLOWED_BASE_API_HOSTS, "BASE OAuth")
    resp = requests.post(
        url,
        data={
            "grant_type": "refresh_token",
            "client_id": settings.base_client_id,
            "client_secret": settings.base_client_secret,
            "refresh_token": current_refresh_token(),
            "redirect_uri": settings.base_redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=settings.http_timeout,
    )
    data = resp.json()
    if "access_token" not in data:
        raise BaseApiUnavailable(f"トークン更新に失敗しました: {data.get('error_description') or data}")
    _save_tokens(data["access_token"], data.get("refresh_token") or current_refresh_token())
    return data["access_token"]


def _api(method: str, path: str, *, data: dict | None = None, params: dict | None = None) -> dict[str, Any]:
    url = f"{settings.base_api_base_url}{path}"
    assert_allowed_host(url, ALLOWED_BASE_API_HOSTS, "BASE API")
    if path.rstrip("/").endswith("delete") or "/delete" in path:
        raise PipelineError("BASE商品削除APIは実装・呼び出し禁止です。", stage="base_api")

    def _do() -> dict[str, Any]:
        token = current_access_token()
        if not token:
            token = refresh_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        if method == "POST":
            headers["Content-Type"] = "application/x-www-form-urlencoded"
            resp = requests.post(url, data=data or {}, headers=headers, timeout=settings.http_timeout)
        else:
            resp = requests.get(url, params=params, headers=headers, timeout=settings.http_timeout)
        payload = resp.json() if resp.content else {}
        if resp.status_code == 400 and payload.get("error") == "invalid_request":
            desc = str(payload.get("error_description") or "")
            if "アクセストークン" in desc:
                refresh_access_token()
                raise requests.RequestException("token refreshed, retry")
        if resp.status_code != 200 or "error" in payload:
            raise BaseApiUnavailable(
                f"BASE API エラー {path}: {payload.get('error_description') or payload or resp.status_code}"
            )
        return payload

    return retry(_do, attempts=3, base_delay=1.5, retry_on=(requests.RequestException,))


def get_item(item_id: str) -> dict[str, Any]:
    logger.info("BASEテンプレート商品取得: item_id=%s", item_id)
    data = _api("GET", f"/1/items/detail/{item_id}")
    return data.get("item") or data


def list_categories() -> list[dict[str, Any]]:
    data = _api("GET", "/1/categories")
    return data.get("categories") or []


def get_item_categories(item_id: str) -> list[dict[str, Any]]:
    data = _api("GET", f"/1/item_categories/detail/{item_id}")
    return data.get("item_categories") or []


def add_item(payload: dict[str, Any]) -> dict[str, Any]:
    """メタデータのみ登録。削除は行わない。デジタルファイルはこのAPIでは添付できない。"""
    logger.info("BASE API 商品登録 (メタデータ)")
    data = _api("POST", "/1/items/add", data=payload)
    return data.get("item") or data


def add_item_image_from_url(item_id: str, image_url: str, image_no: int = 1) -> dict[str, Any]:
    return _api(
        "POST",
        "/1/items/add_image",
        data={"item_id": item_id, "image_no": str(image_no), "image_url": image_url},
    )


def add_item_category(item_id: str, category_id: str) -> dict[str, Any]:
    return _api(
        "POST",
        "/1/item_categories/add",
        data={"item_id": item_id, "category_id": category_id},
    )


def oauth_authorize_url() -> str:
    params = {
        "response_type": "code",
        "client_id": settings.base_client_id,
        "redirect_uri": settings.base_redirect_uri,
        "scope": "read_users read_items write_items",
    }
    return f"{settings.base_api_base_url}/1/oauth/authorize?{urlencode(params)}"


def exchange_authorization_code(code: str) -> dict[str, Any]:
    url = f"{settings.base_api_base_url}/1/oauth/token"
    assert_allowed_host(url, ALLOWED_BASE_API_HOSTS, "BASE OAuth")
    resp = requests.post(
        url,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.base_client_id,
            "client_secret": settings.base_client_secret,
            "code": code,
            "redirect_uri": settings.base_redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=settings.http_timeout,
    )
    data = resp.json()
    if "access_token" not in data:
        raise BaseApiUnavailable(f"認可コード交換に失敗: {data}")
    _save_tokens(data["access_token"], data.get("refresh_token") or "")
    return data


def register_via_api(preview: dict[str, Any]) -> dict[str, Any]:
    visible = 0 if preview.get("publish_mode") == "draft" else 1
    item = add_item(
        {
            "title": preview["title"],
            "detail": preview["detail"],
            "price": str(preview["price"]),
            "stock": str(preview.get("stock") or 10000),
            "visible": str(visible),
            "identifier": preview.get("identifier") or "",
        }
    )
    item_id = str(item.get("item_id") or "")
    for cat_id in preview.get("category_ids") or []:
        try:
            add_item_category(item_id, str(cat_id))
        except BaseApiUnavailable as exc:
            logger.info("カテゴリ付与をスキップ: %s", exc)
    image_url = preview.get("image_public_url")
    if image_url:
        try:
            add_item_image_from_url(item_id, image_url)
        except BaseApiUnavailable as exc:
            logger.info("API画像登録は見送り（手動確認へ）: %s", exc)
    return {
        "item_id": item_id,
        "raw": item,
        "file_attached": False,
        "note": "公式APIはデジタルコンテンツファイル添付に非対応。ファイルは管理画面で手動または Playwright 経路を使用。",
    }


def register_via_playwright(preview: dict[str, Any], zip_path: Path, screenshot_dir: Path) -> dict[str, Any]:
    """デジタルコンテンツ商品として登録する。CAPTCHA/2FA は突破しない。"""
    if not settings.base_login_email or not settings.base_login_password:
        raise NeedHumanReview("BASEログイン情報が .env にありません。", stage="base_login")
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeout
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise BaseApiUnavailable("Playwright がインストールされていません。") from exc

    screenshot_dir.mkdir(parents=True, exist_ok=True)
    state_path = settings.playwright_state_path
    state_path.parent.mkdir(parents=True, exist_ok=True)

    logger.info("BASEログイン（Playwright）")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context_kwargs: dict[str, Any] = {"locale": "ja-JP"}
        if state_path.exists():
            context_kwargs["storage_state"] = str(state_path)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()
        try:
            page.goto(f"{settings.base_admin_base_url}/login", wait_until="domcontentloaded", timeout=60000)
            if _needs_manual_auth(page):
                _shot(page, screenshot_dir / "base-auth-required.png")
                raise NeedHumanReview("BASEで手動認証が必要です", stage="base_login")
            if _looks_like_login(page):
                _fill_login(page)
                page.wait_for_timeout(1500)
                if _needs_manual_auth(page) or _looks_like_login(page):
                    _shot(page, screenshot_dir / "base-login-blocked.png")
                    raise NeedHumanReview("BASEで手動認証が必要です", stage="base_login")
            context.storage_state(path=str(state_path))

            logger.info("BASE商品情報生成後のデジタルコンテンツ登録")
            if not page.get_by_text(re.compile("商品")).first.count() and not page.get_by_role(
                "link", name=re.compile("商品")
            ).count():
                page.goto(f"{settings.base_admin_base_url}/items", wait_until="domcontentloaded", timeout=60000)

            created = _try_create_digital_item(page, preview, zip_path, screenshot_dir)
            context.storage_state(path=str(state_path))
            return created
        except NeedHumanReview:
            raise
        except PlaywrightTimeout as exc:
            _shot(page, screenshot_dir / "base-timeout.png")
            raise NeedHumanReview("BASE管理画面の操作がタイムアウトしました。手動確認が必要です。", stage="base_register") from exc
        except Exception as exc:  # noqa: BLE001
            _shot(page, screenshot_dir / "base-error.png")
            raise NeedHumanReview(
                f"BASE管理画面の自動操作を安全のため停止しました: {exc}",
                stage="base_register",
            ) from exc
        finally:
            context.close()
            browser.close()


def _looks_like_login(page) -> bool:
    html = page.content().lower()
    return "password" in html or "パスワード" in page.content() or "login" in page.url.lower()


def _needs_manual_auth(page) -> bool:
    content = page.content()
    lowered = content.lower()
    return any(hint.lower() in lowered or hint in content for hint in AUTH_HINTS)


def _fill_login(page) -> None:
    email_box = page.get_by_label(re.compile("メール"))
    if email_box.count() == 0:
        email_box = page.locator('input[type="email"], input[name="email"], input[name="mail"]')
    pass_box = page.get_by_label(re.compile("パスワード"))
    if pass_box.count() == 0:
        pass_box = page.locator('input[type="password"]')
    if email_box.count() == 0 or pass_box.count() == 0:
        raise NeedHumanReview("BASEで手動認証が必要です（ログイン欄を特定できません）", stage="base_login")
    email_box.first.fill(settings.base_login_email)
    pass_box.first.fill(settings.base_login_password)
    button = page.get_by_role("button", name=re.compile("ログイン|Sign in|サインイン"))
    if button.count() == 0:
        button = page.locator('button[type="submit"], input[type="submit"]')
    button.first.click()
    page.wait_for_load_state("domcontentloaded")


def _try_create_digital_item(page, preview: dict[str, Any], zip_path: Path, screenshot_dir: Path) -> dict[str, Any]:
    """ラベル・ロール中心。ボタン座標や nth-child には依存しない。"""
    new_item = page.get_by_role("link", name=re.compile("商品を登録"))
    if new_item.count() == 0:
        new_item = page.get_by_text(re.compile("商品を登録する"))
    if new_item.count() == 0:
        _shot(page, screenshot_dir / "base-no-new-item.png")
        raise NeedHumanReview("商品登録画面への導線が見つかりません。BASEで手動確認が必要です。", stage="base_register")
    new_item.first.click()
    page.wait_for_load_state("domcontentloaded")

    digital = page.get_by_role("link", name=re.compile("デジタルコンテンツ"))
    if digital.count() == 0:
        digital = page.get_by_text("デジタルコンテンツ", exact=False)
    if digital.count() == 0:
        _shot(page, screenshot_dir / "base-no-digital.png")
        raise NeedHumanReview(
            "デジタルコンテンツ作成画面が見つかりません。Apps の導入状態を確認してください。",
            stage="base_register",
        )
    digital.first.click()
    page.wait_for_load_state("domcontentloaded")

    _fill_by_label(page, re.compile("商品名"), preview["title"])
    detail_box = page.get_by_label(re.compile("商品説明|説明"))
    if detail_box.count():
        detail_box.first.fill(preview["detail"])
    _fill_by_label(page, re.compile("価格"), str(preview["price"]))
    stock_box = page.get_by_label(re.compile("在庫"))
    if stock_box.count():
        stock_box.first.fill(str(preview.get("stock") or 10000))

    file_input = page.locator('input[type="file"]')
    if file_input.count() == 0:
        _shot(page, screenshot_dir / "base-no-file-input.png")
        raise NeedHumanReview("デジタルコンテンツのファイル選択欄が見つかりません。", stage="base_register")
    file_input.first.set_input_files(str(zip_path))

    image_path = preview.get("image_path")
    if image_path and Path(image_path).exists() and file_input.count() > 1:
        file_input.nth(1).set_input_files(str(image_path))

    if preview.get("publish_mode") == "draft":
        vis = page.get_by_label(re.compile("非公開|非表示|下書き"))
        if vis.count():
            vis.first.check()

    submit = page.get_by_role("button", name=re.compile("登録する"))
    if submit.count() == 0:
        submit = page.get_by_role("button", name=re.compile("更新する|保存"))
    if submit.count() == 0:
        _shot(page, screenshot_dir / "base-no-submit.png")
        raise NeedHumanReview("登録ボタンが見つかりません。", stage="base_register")
    submit.first.click()
    page.wait_for_timeout(2000)
    _shot(page, screenshot_dir / "base-registered.png")
    item_id = ""
    match = re.search(r"/items/(\d+)", page.url)
    if match:
        item_id = match.group(1)
    return {
        "item_id": item_id,
        "product_url": page.url,
        "file_attached": True,
        "note": "Playwright によりデジタルコンテンツとして登録を試行しました。管理画面で内容を確認してください。",
    }


def _fill_by_label(page, pattern, value: str) -> None:
    loc = page.get_by_label(pattern)
    if loc.count():
        loc.first.fill(value)


def _shot(page, path: Path) -> None:
    try:
        page.screenshot(path=str(path), full_page=True)
        logger.info("スクリーンショット: %s", path)
    except Exception:  # noqa: BLE001
        logger.info("スクリーンショットの保存に失敗しました")
