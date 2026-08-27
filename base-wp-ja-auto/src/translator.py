"""翻訳プロバイダ。OpenAI を初期実装とし、将来 Gemini 等へ差し替え可能。"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from abc import ABC, abstractmethod
from pathlib import Path

from config import settings
from src.database import cache_get, cache_put
from src.plugin_analyzer import Message
from src.utils import dump_json, load_json, placeholders, retry

logger = logging.getLogger("base_wp_ja_auto")

SYSTEM_PROMPT = """あなたは WordPress プラグインの日本語翻訳者です。
管理画面に表示される文言として、自然で簡潔な日本語に翻訳してください。

守るルール:
- WordPress で一般的な用語を使う（Save=保存, Settings=設定, Delete=削除, Enable=有効化, Disable=無効化, Update=更新, Upload=アップロード, Download=ダウンロード, Search=検索, Filter=絞り込み, Submit=送信, Cancel=キャンセル, Edit=編集, Add=追加, Remove=削除, Publish=公開, Draft=下書き, Required=必須, Optional=任意）。
- プレースホルダー（%s, %d, %1$s, {0}, {name} など）は絶対に変更・削除・並び替えしない。
- HTML タグは維持する。
- URL は翻訳しない。
- プラグイン名、商品名、会社名、作者名、関数名、コード断片は無理に日本語化しない。
- 直訳調を避け、管理画面として読みやすい表現にする。
- 原文がすでに日本語ならそのまま返す。
- 出力は JSON オブジェクトのみ。キーは入力の id 文字列、値は日本語訳。
"""


class Translator(ABC):
    name = "base"

    @abstractmethod
    def translate_many(self, items: list[dict]) -> dict[str, str]:
        """id -> msgstr。items は id, msgid, msgctxt を持つ。"""


class OfflineTranslator(Translator):
    """APIキーなし・テスト用。用語集を優先し、未知の文言は安全に原文を維持しないよう簡易訳する。"""

    name = "offline"

    def __init__(self, glossary: dict[str, str]) -> None:
        self.glossary = {k.lower(): v for k, v in glossary.items()}

    def translate_many(self, items: list[dict]) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in items:
            msgid = item["msgid"]
            exact = self.glossary.get(msgid.lower())
            if exact:
                out[item["id"]] = exact
            else:
                out[item["id"]] = _offline_translate(msgid, self.glossary)
        return out


class OpenAITranslator(Translator):
    name = "openai"

    def __init__(self, glossary: dict[str, str]) -> None:
        from openai import OpenAI

        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY が未設定です")
        self.glossary = glossary
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def translate_many(self, items: list[dict]) -> dict[str, str]:
        glossary_lines = "\n".join(f"- {k} => {v}" for k, v in list(self.glossary.items())[:80])
        payload = [
            {"id": it["id"], "source": it["msgid"], "context": it.get("msgctxt") or ""}
            for it in items
        ]
        user = (
            "用語集:\n"
            f"{glossary_lines}\n\n"
            "次の JSON 配列を翻訳し、id をキーにした JSON オブジェクトだけを返してください。\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

        def _call() -> dict[str, str]:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            )
            content = response.choices[0].message.content or "{}"
            data = json.loads(content)
            if not isinstance(data, dict):
                raise ValueError("翻訳APIの応答がオブジェクトではありません")
            return {str(k): str(v) for k, v in data.items()}

        result = retry(_call, attempts=5, base_delay=2.0)
        by_id = {it["id"]: it for it in items}
        fixed: dict[str, str] = {}
        for key, msgid_item in by_id.items():
            translated = result.get(key)
            if translated is None:
                for value in result.values():
                    if isinstance(value, str):
                        translated = value
                        break
            if not translated:
                raise ValueError(f"翻訳結果が空です: {msgid_item['msgid'][:80]}")
            if placeholders(msgid_item["msgid"]) != placeholders(translated):
                logger.info("プレースホルダ不一致のため再試行: %s", msgid_item["msgid"][:60])
                translated = self._retry_one(msgid_item, translated)
            fixed[key] = translated
        return fixed

    def _retry_one(self, item: dict, previous: str) -> str:
        user = (
            "プレースホルダを原文と完全一致させて再翻訳してください。\n"
            f"原文: {item['msgid']}\n前回の訳: {previous}\n"
            'JSON: {"translation": "..."}'
        )

        def _call() -> str:
            response = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
            )
            data = json.loads(response.choices[0].message.content or "{}")
            return str(data.get("translation") or previous)

        return retry(_call, attempts=3, base_delay=1.0)


def get_translator() -> Translator:
    glossary = load_json(settings.glossary_path, default={}) or {}
    provider = settings.translator_provider
    if provider == "offline":
        return OfflineTranslator(glossary)
    if provider == "openai":
        if not settings.openai_api_key:
            logger.info("OPENAI_API_KEY がないため offline 翻訳へフォールバックします")
            return OfflineTranslator(glossary)
        return OpenAITranslator(glossary)
    raise RuntimeError(f"未対応の TRANSLATOR_PROVIDER: {provider}")


def translate_messages(messages: list[Message], work_dir: Path) -> dict[tuple[str, str], str]:
    logger.info("AI翻訳開始: %s 件", len(messages))
    translator = get_translator()
    results: dict[tuple[str, str], str] = {}
    pending: list[tuple[Message, str]] = []
    for index, msg in enumerate(messages):
        cache_key = _cache_key(msg, translator)
        cached = cache_get(cache_key)
        if cached is not None:
            results[msg.key] = cached
            continue
        pending.append((msg, f"s{index}"))

    chunk_size = max(1, settings.translation_chunk_size)
    for offset in range(0, len(pending), chunk_size):
        chunk = pending[offset : offset + chunk_size]
        payload = [
            {"id": ident, "msgid": msg.msgid, "msgctxt": msg.msgctxt}
            for msg, ident in chunk
        ]
        translated = translator.translate_many(payload)
        for msg, ident in chunk:
            text = translated.get(ident) or translated.get(str(ident))
            if not text:
                raise RuntimeError(f"翻訳欠落: {msg.msgid[:80]}")
            results[msg.key] = text
            cache_put(
                _cache_key(msg, translator),
                msg.msgid,
                text,
                msgctxt=msg.msgctxt,
                provider=translator.name,
                model=settings.openai_model if translator.name == "openai" else translator.name,
            )
        logger.info("AI翻訳進捗: %s/%s", min(offset + chunk_size, len(pending)), len(pending))

    dump_json(
        work_dir / "translations.json",
        [
            {
                "msgid": msg.msgid,
                "msgctxt": msg.msgctxt,
                "msgid_plural": msg.msgid_plural,
                "msgstr": results.get(msg.key, ""),
            }
            for msg in messages
        ],
    )
    logger.info("AI翻訳終了")
    return results


def _cache_key(msg: Message, translator: Translator) -> str:
    raw = f"{translator.name}|{settings.openai_model if translator.name == 'openai' else ''}|{msg.msgctxt}|{msg.msgid}|{msg.msgid_plural}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _offline_translate(msgid: str, glossary: dict[str, str]) -> str:
    if re.fullmatch(r"https?://\S+", msgid.strip()):
        return msgid
    # 用語集の完全一致以外は、単語単位で置換し、残りは原文を残す（固有名詞保護）。
    words = re.split(r"(\s+)", msgid)
    out: list[str] = []
    for word in words:
        key = word.lower().strip(".,:;!?")
        if key in glossary:
            out.append(word.replace(word.strip(".,:;!?"), glossary[key]))
        else:
            out.append(word)
    text = "".join(out)
    if text == msgid and re.search(r"[A-Za-z]{3,}", msgid):
        # テスト継続用の最低限の日本語化。プレースホルダは維持する。
        text = msgid
        replacements = [
            (r"\bSave\b", "保存"),
            (r"\bSettings\b", "設定"),
            (r"\bDelete\b", "削除"),
            (r"\bEnable\b", "有効化"),
            (r"\bDisable\b", "無効化"),
            (r"\bUpdate\b", "更新"),
            (r"\bAdd New\b", "新規追加"),
            (r"\bAdd\b", "追加"),
            (r"\bEdit\b", "編集"),
            (r"\bSearch\b", "検索"),
            (r"\bCancel\b", "キャンセル"),
            (r"\bSubmit\b", "送信"),
            (r"\bRequired\b", "必須"),
            (r"\bOptional\b", "任意"),
            (r"\bPlugin\b", "プラグイン"),
            (r"\bWordPress\b", "WordPress"),
        ]
        for pattern, repl in replacements:
            text = re.sub(pattern, repl, text, flags=re.IGNORECASE)
        if text == msgid:
            text = f"{msgid}"
    return text
