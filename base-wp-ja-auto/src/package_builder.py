"""販売用ZIPと導入READMEを作成する。オリジナルと翻訳成果物は内部で分離する。"""

from __future__ import annotations

import logging
import shutil
import zipfile
from datetime import date
from pathlib import Path

from config import settings
from src.plugin_analyzer import Analysis
from src.utils import dump_json
from src.wordpress import PluginInfo

logger = logging.getLogger("base_wp_ja_auto")


def build_sale_package(
    info: PluginInfo,
    analysis: Analysis,
    translation_files: dict[str, Path],
    work_dir: Path,
) -> Path:
    logger.info("販売ZIP生成")
    sale_root = work_dir / "sale"
    if sale_root.exists():
        shutil.rmtree(sale_root)
    inner = sale_root / f"{info.slug}-ja-{info.version}"
    lang_dest = inner / "languages"
    lang_dest.mkdir(parents=True, exist_ok=True)

    copied = []
    for path in translation_files.values():
        if path.exists():
            target = lang_dest / path.name
            shutil.copy2(path, target)
            copied.append(target.name)

    readme = _render_sale_readme(info, analysis, copied)
    (inner / "README.txt").write_text(readme, encoding="utf-8")

    # 内部保管: オリジナルと翻訳を必ず分ける
    original_keep = work_dir / "original"
    translations_keep = work_dir / "translations"
    dump_json(
        work_dir / "package_layout.json",
        {
            "original_dir": str(original_keep),
            "translations_dir": str(translations_keep),
            "sale_mode": settings.sale_package_mode,
            "sale_includes_plugin": settings.sale_package_mode == "plugin_and_translation",
        },
    )

    if settings.sale_package_mode == "plugin_and_translation":
        plugin_dest = inner / "original-plugin"
        if original_keep.exists():
            shutil.copytree(original_keep, plugin_dest, dirs_exist_ok=True)
            notice = (
                "この original-plugin フォルダは参考用です。\n"
                "公開運用では WordPress.org から公式プラグインを導入してください。\n"
            )
            (plugin_dest / "NOTICE-公式プラグインと混同しないでください.txt").write_text(
                notice, encoding="utf-8"
            )

    zip_name = f"{info.slug}-{info.version}-ja.zip"
    out_zip = settings.output_dir / zip_name
    if out_zip.exists():
        out_zip.unlink()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in inner.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(sale_root).as_posix())
    logger.info("販売ZIP生成完了: %s", out_zip)
    return out_zip


def _render_sale_readme(info: PluginInfo, analysis: Analysis, files: list[str]) -> str:
    template_path = settings.sale_readme_template_path
    mapping = {
        "plugin_name": info.name,
        "plugin_version": info.version,
        "plugin_url": info.official_url,
        "created_date": date.today().isoformat(),
        "text_domain": analysis.text_domain,
        "domain_path": analysis.domain_path or "/languages",
        "translation_files": "\n".join(f"- {name}" for name in files) or "- (なし)",
        "author": info.author,
        "requires_wordpress": info.requires_wordpress or "不明",
        "requires_php": info.requires_php or "不明",
        "license": analysis.license or info.license or "プラグイン本体のライセンスに従ってください",
    }
    if template_path.exists():
        text = template_path.read_text(encoding="utf-8")
        for key, value in mapping.items():
            text = text.replace("{" + key + "}", str(value))
        return text
    return _default_readme(mapping)


def _default_readme(mapping: dict[str, str]) -> str:
    return f"""{mapping['plugin_name']} 日本語化ファイル

対象プラグイン名: {mapping['plugin_name']}
対象バージョン: {mapping['plugin_version']}
作成日: {mapping['created_date']}
公式プラグインURL: {mapping['plugin_url']}
作者: {mapping['author']}
Text Domain: {mapping['text_domain']}

【重要】
本ZIPは日本語翻訳ファイルです。オリジナルの WordPress プラグイン本体ではありません。
プラグイン本体は必ず公式URLから入手・インストールしてください。

【同梱ファイル】
{mapping['translation_files']}

【翻訳ファイルの配置方法】
1. WordPress公式ディレクトリから「{mapping['plugin_name']}」をインストールする。
2. 本ZIPを展開する。
3. languages フォルダ内の .po / .mo を、次のいずれかに配置する。
   - wp-content/languages/plugins/{mapping['text_domain']}-ja.mo
   - またはプラグインフォルダ{mapping['domain_path']} 配下
4. WordPress のサイト言語が「日本語」であることを確認する。

【注意事項】
- 対象バージョン以外では表示が崩れる、未翻訳が残る場合があります。
- プラグインのライセンス（{mapping['license']}）および公式の利用条件を守ってください。
- 本ファイルは非公式の日本語化支援です。プラグイン作者・WordPress.org 公式の翻訳プロジェクトとは別物です。
- WordPress / PHP の動作要件: WP {mapping['requires_wordpress']} / PHP {mapping['requires_php']}

【更新日】
{mapping['created_date']}
"""
