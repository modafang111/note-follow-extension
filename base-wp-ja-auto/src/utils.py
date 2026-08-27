"""共通ユーティリティ。ZIP Slip 防止、URL許可、slug抽出など。"""

from __future__ import annotations

import html
import json
import re
import time
import zipfile
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, TypeVar
from urllib.parse import urlparse

from src.exceptions import PipelineError

T = TypeVar("T")

WP_PLUGIN_URL_RE = re.compile(
    r"^https?://(?:www\.)?wordpress\.org/plugins/([a-z0-9\-]+)/?",
    re.IGNORECASE,
)
BASE_ITEM_ID_RE = re.compile(r"(?:/items/|/item_id/|item_id=)(\d+)", re.IGNORECASE)

ALLOWED_WP_API_HOSTS = {
    "api.wordpress.org",
    "downloads.wordpress.org",
    "ps.w.org",
    "ts.w.org",
    "s.w.org",
    "translate.wordpress.org",
}
ALLOWED_DOWNLOAD_HOSTS = {"downloads.wordpress.org"}
ALLOWED_BASE_API_HOSTS = {"api.thebase.in"}
ALLOWED_OPENAI_HOSTS = {"api.openai.com"}

EMOJI_RE = re.compile(r"[\U00010000-\U0010ffff]", flags=re.UNICODE)
PLACEHOLDER_RE = re.compile(
    r"%\d+\$[sd]|%[sd]|%%|%\([^)]+\)[sd]|\{[0-9a-zA-Z_\.]+\}|\{\{[^{}]+\}\}"
)
HTML_TAG_RE = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def extract_plugin_slug(url: str) -> str:
    text = (url or "").strip()
    match = WP_PLUGIN_URL_RE.match(text)
    if not match:
        raise PipelineError(
            f"WordPress公式プラグインURLではありません: {url}",
            stage="url_parse",
        )
    return match.group(1).lower()


def canonical_plugin_url(slug: str) -> str:
    return f"https://wordpress.org/plugins/{slug}/"


def extract_base_item_id(url_or_id: str) -> str:
    text = (url_or_id or "").strip()
    if text.isdigit():
        return text
    match = BASE_ITEM_ID_RE.search(text)
    if match:
        return match.group(1)
    raise PipelineError(f"BASE商品IDをURLから抽出できません: {url_or_id}", stage="base_template")


def assert_allowed_host(url: str, allowed_hosts: Iterable[str], purpose: str) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in set(allowed_hosts):
        raise PipelineError(
            f"{purpose} の宛先が許可されていません: {host or url}",
            stage="network_guard",
        )


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", "", str(value))
    return html.unescape(text).strip()


def strip_4byte_chars(value: str) -> str:
    """BASE API は title/detail に4byte文字（絵文字等）を受け付けない。"""
    return EMOJI_RE.sub("", value or "")


def sanitize_identifier(value: str) -> str:
    return re.sub(r"[^\w\-\.]+", "-", value, flags=re.ASCII).strip("-")[:80]


def placeholders(text: str) -> list[str]:
    return PLACEHOLDER_RE.findall(text or "")


def html_tags(text: str) -> list[str]:
    return [m.group(1).lower() for m in HTML_TAG_RE.finditer(text or "")]


def looks_like_mojibake(text: str) -> bool:
    if not text:
        return False
    if "\ufffd" in text:
        return True
    suspicious = ["Ã", "Â ", "ãƒ", "æ—¥æœ¬"]
    return any(token in text for token in suspicious) and not any(
        ch in text for ch in "あいうえおかきくけこさしすせそたちつてと"
    )


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(data) if is_dataclass(data) and not isinstance(data, type) else data
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 5,
    base_delay: float = 1.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return fn()
        except retry_on as exc:
            last = exc
            if i == attempts - 1:
                break
            time.sleep(base_delay * (2**i))
    assert last is not None
    raise last


def safe_extract_zip(
    zip_path: Path,
    dest_dir: Path,
    *,
    max_zip_bytes: int,
    max_files: int,
    max_file_bytes: int,
) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    size = zip_path.stat().st_size
    if size > max_zip_bytes:
        raise PipelineError(
            f"ZIPが大きすぎます ({size} bytes / 上限 {max_zip_bytes})",
            stage="unzip",
        )
    with zipfile.ZipFile(zip_path) as zf:
        infos = zf.infolist()
        if len(infos) > max_files:
            raise PipelineError(
                f"ZIP内のファイル数が多すぎます ({len(infos)} / 上限 {max_files})",
                stage="unzip",
            )
        dest_root = dest_dir.resolve()
        for info in infos:
            if info.file_size > max_file_bytes:
                raise PipelineError(
                    f"ZIP内ファイルが大きすぎます: {info.filename} ({info.file_size} bytes)",
                    stage="unzip",
                )
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or re.match(r"^[A-Za-z]:/", name):
                raise PipelineError(f"ZIP Slipの疑い（絶対パス）: {info.filename}", stage="unzip")
            target = (dest_dir / name).resolve()
            if dest_root not in target.parents and target != dest_root:
                raise PipelineError(f"ZIP Slipの疑い（ディレクトリトラバーサル）: {info.filename}", stage="unzip")
            if info.is_dir() or name.endswith("/"):
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                remaining = info.file_size
                while remaining > 0:
                    chunk = src.read(min(1024 * 64, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    out.write(chunk)


def find_plugin_root(extracted_dir: Path) -> Path:
    """展開後、プラグイン本体ディレクトリを特定する。"""
    php_with_header = []
    for path in extracted_dir.rglob("*.php"):
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:8192]
        except OSError:
            continue
        if re.search(r"Plugin Name\s*:", head):
            php_with_header.append(path)
    if php_with_header:
        php_with_header.sort(key=lambda p: len(p.parts))
        return php_with_header[0].parent
    children = [p for p in extracted_dir.iterdir() if p.is_dir() and p.name not in {"__MACOSX"}]
    if len(children) == 1:
        return children[0]
    return extracted_dir


def parse_plugin_headers(plugin_root: Path) -> dict[str, str]:
    headers: dict[str, str] = {}
    keys = [
        "Plugin Name",
        "Plugin URI",
        "Description",
        "Version",
        "Author",
        "Author URI",
        "Text Domain",
        "Domain Path",
        "Network",
        "Requires at least",
        "Requires PHP",
        "License",
        "License URI",
    ]
    for path in sorted(plugin_root.glob("*.php")):
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:16384]
        except OSError:
            continue
        if "Plugin Name" not in head:
            continue
        for key in keys:
            match = re.search(rf"^[ \t\/*#@]*{re.escape(key)}\s*:\s*(.+)$", head, re.MULTILINE)
            if match:
                headers[key] = match.group(1).strip()
        headers["_main_file"] = str(path)
        break
    return headers
