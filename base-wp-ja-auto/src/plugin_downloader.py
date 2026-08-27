"""WordPress公式配布元からのZIP取得。PHPは実行しない。"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import requests

from config import settings
from src.exceptions import PipelineError
from src.utils import (
    ALLOWED_DOWNLOAD_HOSTS,
    assert_allowed_host,
    dump_json,
    retry,
    safe_extract_zip,
)
from src.wordpress import PluginInfo

logger = logging.getLogger("base_wp_ja_auto")


def download_plugin(info: PluginInfo, work_dir: Path) -> dict:
    logger.info("ZIPダウンロード開始: %s", info.download_url)
    assert_allowed_host(info.download_url, ALLOWED_DOWNLOAD_HOSTS, "プラグインZIP")
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / f"{info.slug}-{info.version}.zip"

    def _do() -> None:
        with requests.get(
            info.download_url,
            stream=True,
            timeout=settings.http_timeout,
            headers={"User-Agent": settings.user_agent},
        ) as resp:
            resp.raise_for_status()
            max_bytes = settings.max_zip_size_mb * 1024 * 1024
            written = 0
            tmp = zip_path.with_suffix(".zip.part")
            with tmp.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue
                    written += len(chunk)
                    if written > max_bytes:
                        raise PipelineError(
                            f"ダウンロードサイズが上限を超えました ({written} bytes)",
                            stage="download",
                        )
                    fh.write(chunk)
            tmp.replace(zip_path)

    retry(_do, attempts=4, retry_on=(requests.RequestException, PipelineError))
    meta = {
        "slug": info.slug,
        "version": info.version,
        "downloaded_at": datetime.now().replace(microsecond=0).isoformat(sep=" "),
        "download_url": info.download_url,
        "zip_path": str(zip_path),
        "size_bytes": zip_path.stat().st_size,
    }
    dump_json(work_dir / "download_meta.json", meta)
    logger.info("ZIPダウンロード完了: %s (%s bytes)", zip_path.name, meta["size_bytes"])
    return meta


def extract_plugin(zip_path: Path, work_dir: Path) -> Path:
    logger.info("ZIP展開: %s", zip_path)
    dest = work_dir / "original"
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    safe_extract_zip(
        zip_path,
        dest,
        max_zip_bytes=settings.max_zip_size_mb * 1024 * 1024,
        max_files=settings.max_zip_files,
        max_file_bytes=settings.max_single_file_mb * 1024 * 1024,
    )
    logger.info("ZIP展開完了: %s", dest)
    return dest
