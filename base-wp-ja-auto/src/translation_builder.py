"""翻訳品質チェックと .po / .mo / JS JSON 生成。"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import polib

from config import settings
from src.exceptions import QualityError
from src.plugin_analyzer import Analysis, Message
from src.utils import dump_json, html_tags, looks_like_mojibake, placeholders
from src.wordpress import PluginInfo

logger = logging.getLogger("base_wp_ja_auto")


def quality_check(
    messages: list[Message],
    translations: dict[tuple[str, str], str],
    work_dir: Path,
) -> dict:
    logger.info("品質チェック開始")
    issues: list[dict] = []
    by_msgid: dict[str, set[str]] = defaultdict(set)

    for msg in messages:
        msgstr = translations.get(msg.key, "")
        by_msgid[msg.msgid].add(msgstr)
        if msgstr.strip() == "":
            issues.append({"level": "error", "type": "empty", "msgid": msg.msgid})
            continue
        src_ph = placeholders(msg.msgid)
        dst_ph = placeholders(msgstr)
        if src_ph != dst_ph:
            issues.append(
                {
                    "level": "error",
                    "type": "placeholder_mismatch",
                    "msgid": msg.msgid,
                    "msgstr": msgstr,
                    "src": src_ph,
                    "dst": dst_ph,
                }
            )
        src_tags = sorted(html_tags(msg.msgid))
        dst_tags = sorted(html_tags(msgstr))
        if src_tags != dst_tags:
            issues.append(
                {
                    "level": "error",
                    "type": "html_mismatch",
                    "msgid": msg.msgid,
                    "msgstr": msgstr,
                }
            )
        if len(msg.msgid) > 0 and len(msgstr) > max(80, int(len(msg.msgid) * settings.long_translation_ratio) + 40):
            issues.append(
                {
                    "level": "warning",
                    "type": "too_long",
                    "msgid": msg.msgid,
                    "msgstr": msgstr,
                }
            )
        if looks_like_mojibake(msgstr):
            issues.append({"level": "error", "type": "mojibake", "msgid": msg.msgid, "msgstr": msgstr})

    for msgid, variants in by_msgid.items():
        cleaned = {v for v in variants if v}
        if len(cleaned) > 1:
            issues.append(
                {
                    "level": "warning",
                    "type": "inconsistent",
                    "msgid": msgid,
                    "variants": sorted(cleaned),
                }
            )

    errors = [i for i in issues if i["level"] == "error"]
    report = {
        "source_count": len(messages),
        "translated_count": sum(1 for m in messages if translations.get(m.key, "").strip()),
        "untranslated_count": sum(1 for m in messages if not translations.get(m.key, "").strip()),
        "error_count": len(errors),
        "warning_count": sum(1 for i in issues if i["level"] == "warning"),
        "issues": issues[:500],
    }
    dump_json(work_dir / "quality_report.json", report)
    logger.info(
        "品質チェック終了: 原文=%s 翻訳=%s 未翻訳=%s 重大=%s",
        report["source_count"],
        report["translated_count"],
        report["untranslated_count"],
        report["error_count"],
    )
    if errors:
        raise QualityError(
            f"翻訳品質の重大エラーが {len(errors)} 件あります。BASEへ自動登録しません。",
            stage="quality_check",
        )
    if report["source_count"] != report["translated_count"]:
        raise QualityError("原文数と翻訳数が一致しません。", stage="quality_check")
    return report


def build_po_mo(
    info: PluginInfo,
    analysis: Analysis,
    translations: dict[tuple[str, str], str],
    work_dir: Path,
) -> dict[str, Path]:
    logger.info(".po生成")
    lang_dir = work_dir / "translations"
    lang_dir.mkdir(parents=True, exist_ok=True)
    domain = analysis.text_domain or info.slug
    po_path = lang_dir / f"{domain}-ja.po"
    mo_path = lang_dir / f"{domain}-ja.mo"

    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": f"{info.name} {info.version}",
        "Report-Msgid-Bugs-To": info.official_url,
        "POT-Creation-Date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M+0000"),
        "PO-Revision-Date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M+0000"),
        "Last-Translator": "base-wp-ja-auto",
        "Language": "ja",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Plural-Forms": "nplurals=1; plural=0;",
        "X-Domain": domain,
        "X-Generator": "base-wp-ja-auto",
    }
    for msg in analysis.messages:
        msgstr = translations.get(msg.key, "")
        if msg.msgid_plural:
            entry = polib.POEntry(
                msgid=msg.msgid,
                msgid_plural=msg.msgid_plural,
                msgstr_plural={0: msgstr},
                msgctxt=msg.msgctxt or None,
            )
        else:
            entry = polib.POEntry(
                msgid=msg.msgid,
                msgstr=msgstr,
                msgctxt=msg.msgctxt or None,
            )
        if msg.references:
            occ = []
            for ref in msg.references:
                if isinstance(ref, (list, tuple)) and len(ref) >= 1:
                    occ.append((str(ref[0]), str(ref[1]) if len(ref) > 1 else ""))
                else:
                    occ.append((str(ref), ""))
            entry.occurrences = occ
        po.append(entry)

    po.save(str(po_path))
    logger.info(".mo生成")
    po.save_as_mofile(str(mo_path))
    _verify_mo(po_path, mo_path)

    json_paths: list[Path] = []
    if analysis.has_js_i18n:
        json_path = _write_jed_json(lang_dir, domain, po)
        json_paths.append(json_path)
        logger.info("JS翻訳JSONを生成: %s", json_path.name)

    logger.info(".po/.mo生成完了")
    return {"po": po_path, "mo": mo_path, **{f"json{i}": p for i, p in enumerate(json_paths)}}


def _verify_mo(po_path: Path, mo_path: Path) -> None:
    po = polib.pofile(str(po_path))
    mo = polib.mofile(str(mo_path))
    po_ids = {e.msgid for e in po if e.msgid}
    mo_ids = {e.msgid for e in mo if e.msgid}
    if po_ids != mo_ids:
        raise QualityError(".po と .mo の msgid が一致しません。", stage="mo_verify")
    for entry in mo:
        if entry.msgid and not (entry.msgstr or entry.msgstr_plural):
            raise QualityError(f".mo に未翻訳があります: {entry.msgid[:80]}", stage="mo_verify")
    logger.info(".mo検証OK (%s エントリ)", len(mo_ids))


def _write_jed_json(lang_dir: Path, domain: str, po: polib.POFile) -> Path:
    messages = {
        "": {
            "domain": domain,
            "lang": "ja",
            "plural-forms": "nplurals=1; plural=0;",
        }
    }
    for entry in po:
        if not entry.msgid:
            continue
        key = entry.msgid if not entry.msgctxt else f"{entry.msgctxt}\u0004{entry.msgid}"
        messages[key] = [entry.msgstr] if not entry.msgid_plural else [entry.msgstr_plural.get(0, "")]
    payload = {
        "translation-revision-date": datetime.now(timezone.utc).isoformat(),
        "generator": "base-wp-ja-auto",
        "source": f"{domain}-ja.po",
        "domain": domain,
        "locale_data": {domain: messages},
    }
    digest = hashlib.md5(f"{domain}-ja.po".encode("utf-8")).hexdigest()
    path = lang_dir / f"ja-{domain}-{digest}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
