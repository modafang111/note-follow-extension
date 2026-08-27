"""プラグイン解析: 有料判定、日本語化状況、翻訳対象抽出。PHPは読み取り専用。"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

import polib

from config import settings
from src.exceptions import SkipPlugin
from src.utils import dump_json, find_plugin_root, parse_plugin_headers
from src.wordpress import PluginInfo

logger = logging.getLogger("base_wp_ja_auto")

I18N_FUNCS = {
    "__": {"msgid": 0, "domain": 1},
    "_e": {"msgid": 0, "domain": 1},
    "_x": {"msgid": 0, "msgctxt": 1, "domain": 2},
    "_ex": {"msgid": 0, "msgctxt": 1, "domain": 2},
    "_n": {"msgid": 0, "msgid_plural": 1, "domain": 3},
    "_nx": {"msgid": 0, "msgid_plural": 1, "msgctxt": 3, "domain": 4},
    "_n_noop": {"msgid": 0, "msgid_plural": 1, "domain": 2},
    "_nx_noop": {"msgid": 0, "msgid_plural": 1, "msgctxt": 2, "domain": 3},
    "esc_html__": {"msgid": 0, "domain": 1},
    "esc_html_e": {"msgid": 0, "domain": 1},
    "esc_html_x": {"msgid": 0, "msgctxt": 1, "domain": 2},
    "esc_attr__": {"msgid": 0, "domain": 1},
    "esc_attr_e": {"msgid": 0, "domain": 1},
    "esc_attr_x": {"msgid": 0, "msgctxt": 1, "domain": 2},
    "esc_html_n": {"msgid": 0, "msgid_plural": 1, "domain": 3},
    "esc_attr_n": {"msgid": 0, "msgid_plural": 1, "domain": 3},
    "translate": {"msgid": 0, "domain": 1},
    "translate_with_gettext_context": {"msgid": 0, "msgctxt": 1, "domain": 2},
}

FUNC_NAME_RE = re.compile(r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)\s*\(")
JS_I18N_RE = re.compile(
    r"""(?:wp\.i18n\.|i18n\.)?(__|_x|_n|_nx)\(\s*(['"`])((?:\\.|(?!\2).)*)\2""",
    re.MULTILINE,
)


@dataclass
class Message:
    msgid: str
    msgid_plural: str = ""
    msgctxt: str = ""
    domain: str = ""
    references: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        return (self.msgctxt, self.msgid)


@dataclass
class Analysis:
    plugin_root: str
    text_domain: str
    domain_path: str
    license: str
    pot_path: str | None
    messages: list[Message]
    has_js_i18n: bool
    bundled_po: list[str]
    bundled_mo: list[str]
    bundled_json: list[str]
    bundled_pot: list[str]
    ja_files: list[str]
    ja_pack_exists: bool
    ja_percent: float | None
    skip_reason: str | None
    source: str

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


def analyze_plugin(info: PluginInfo, extracted_dir: Path, work_dir: Path) -> Analysis:
    logger.info("翻訳対象抽出の準備（日本語対応状況の事前確認）")
    plugin_root = find_plugin_root(extracted_dir)
    headers = parse_plugin_headers(plugin_root)
    text_domain = headers.get("Text Domain") or info.slug
    domain_path = headers.get("Domain Path") or "/languages"
    license_name = headers.get("License") or info.license
    info.text_domain = text_domain
    if not info.license:
        info.license = license_name

    languages_dir = _resolve_domain_path(plugin_root, domain_path)
    bundled_po = [str(p.relative_to(plugin_root)) for p in plugin_root.rglob("*.po")]
    bundled_mo = [str(p.relative_to(plugin_root)) for p in plugin_root.rglob("*.mo")]
    bundled_json = [str(p.relative_to(plugin_root)) for p in plugin_root.rglob("*.json") if "node_modules" not in str(p)]
    bundled_pot = [str(p.relative_to(plugin_root)) for p in plugin_root.rglob("*.pot")]
    ja_files = [
        rel
        for rel in bundled_po + bundled_mo + bundled_json
        if re.search(r"[-_.]ja([_.]|$)", Path(rel).name, re.IGNORECASE)
    ]

    pot_path = _pick_pot(plugin_root, bundled_pot)
    source = "pot" if pot_path else "generated"
    messages: list[Message] = []
    if pot_path:
        logger.info("同梱 .pot を優先利用: %s", pot_path)
        messages = _messages_from_pot(Path(pot_path))
    else:
        generated = _try_wp_cli_make_pot(plugin_root, work_dir, text_domain)
        if generated:
            source = "wp-cli"
            messages = _messages_from_pot(generated)
            pot_path = str(generated)
        else:
            logger.info(".pot がないため、読み取り専用の抽出器で翻訳対象を収集します")
            messages = extract_messages(plugin_root, text_domain)
            source = "extractor"
            pot_path = str(_write_generated_pot(work_dir, text_domain, info, messages))

    has_js = _has_js_i18n(plugin_root)
    skip_reason = None
    ja_percent = info.ja_percent
    ja_pack_exists = bool(info.ja_language_pack) or bool(ja_files)
    if ja_percent is not None and ja_percent >= settings.ja_translation_skip_percent:
        skip_reason = (
            f"既に十分日本語化されている可能性があります"
            f"（公式翻訳 {ja_percent:.0f}% / しきい値 {settings.ja_translation_skip_percent:.0f}%）"
        )
    elif ja_pack_exists and ja_percent is None and not settings.continue_when_ja_complete:
        skip_reason = "既に十分日本語化されている可能性があります（言語パックまたは ja ファイルを検出）"

    analysis = Analysis(
        plugin_root=str(plugin_root),
        text_domain=text_domain,
        domain_path=domain_path,
        license=license_name,
        pot_path=str(pot_path) if pot_path else None,
        messages=messages,
        has_js_i18n=has_js,
        bundled_po=bundled_po,
        bundled_mo=bundled_mo,
        bundled_json=bundled_json,
        bundled_pot=bundled_pot,
        ja_files=ja_files,
        ja_pack_exists=ja_pack_exists,
        ja_percent=ja_percent,
        skip_reason=skip_reason,
        source=source,
    )
    dump_json(
        work_dir / "analysis.json",
        {
            **{k: v for k, v in asdict(analysis).items() if k != "messages"},
            "message_count": len(messages),
            "languages_dir": str(languages_dir) if languages_dir else None,
        },
    )
    dump_json(
        work_dir / "extracted_strings.json",
        [asdict(m) for m in messages],
    )
    logger.info("翻訳対象抽出: %s 件 (source=%s, domain=%s)", len(messages), source, text_domain)
    return analysis


def maybe_skip_already_translated(analysis: Analysis, continue_anyway: bool) -> None:
    if not analysis.skip_reason:
        return
    if continue_anyway or settings.continue_when_ja_complete:
        logger.info("日本語化済みの可能性がありますが、設定により処理を継続します: %s", analysis.skip_reason)
        return
    raise SkipPlugin(analysis.skip_reason, stage="ja_precheck")


def extract_messages(plugin_root: Path, default_domain: str) -> list[Message]:
    collected: dict[tuple[str, str], Message] = {}
    skip_dirs = {".git", "node_modules", "vendor", "tests", "Test", "__MACOSX"}
    for path in plugin_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        rel = str(path.relative_to(plugin_root)).replace("\\", "/")
        if path.suffix.lower() == ".php":
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for msg in _extract_php(source, rel, default_domain):
                _merge_message(collected, msg)
        elif path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx"}:
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for msg in _extract_js(source, rel, default_domain):
                _merge_message(collected, msg)
    return list(collected.values())


def _merge_message(collected: dict[tuple[str, str], Message], msg: Message) -> None:
    if not msg.msgid or msg.msgid.strip() == "":
        return
    existing = collected.get(msg.key)
    if existing:
        if msg.references:
            existing.references.extend(msg.references)
        if msg.msgid_plural and not existing.msgid_plural:
            existing.msgid_plural = msg.msgid_plural
        return
    collected[msg.key] = msg


def _extract_php(source: str, rel: str, default_domain: str) -> list[Message]:
    messages: list[Message] = []
    i = 0
    length = len(source)
    while i < length:
        ch = source[i]
        if ch == "/" and i + 1 < length:
            nxt = source[i + 1]
            if nxt == "/":
                i = source.find("\n", i)
                if i < 0:
                    break
                continue
            if nxt == "*":
                end = source.find("*/", i + 2)
                i = length if end < 0 else end + 2
                continue
        if ch == "#":
            i = source.find("\n", i)
            if i < 0:
                break
            continue
        if ch in {'"', "'"}:
            _, i = _read_php_string(source, i)
            continue
        match = FUNC_NAME_RE.match(source, i)
        if not match:
            i += 1
            continue
        name = match.group(1)
        spec = I18N_FUNCS.get(name)
        i = match.end()
        if not spec:
            continue
        args, i = _read_php_args(source, i)
        msgid = _literal_at(args, spec.get("msgid", 0))
        if msgid is None:
            continue
        msg = Message(
            msgid=msgid,
            msgid_plural=_literal_at(args, spec["msgid_plural"]) if "msgid_plural" in spec else "",
            msgctxt=_literal_at(args, spec["msgctxt"]) if "msgctxt" in spec else "",
            domain=_literal_at(args, spec["domain"]) if "domain" in spec else default_domain,
            references=[rel],
        )
        if not msg.domain:
            msg.domain = default_domain
        if "msgid_plural" in spec:
            plural = _literal_at(args, spec["msgid_plural"])
            msg.msgid_plural = plural or ""
        messages.append(msg)
    return messages


def _literal_at(args: list[str | None], index: int) -> str | None:
    if index >= len(args):
        return None
    return args[index]


def _read_php_args(source: str, i: int) -> tuple[list[str | None], int]:
    """関数呼び出し開始直後（開き括弧の次）から引数リストを読む。"""
    args: list[str | None] = []
    current: list[str] = []
    depth = 1
    length = len(source)
    is_literal_arg = True
    while i < length and depth > 0:
        ch = source[i]
        if ch in {'"', "'"}:
            value, i = _read_php_string(source, i)
            if depth == 1 and is_literal_arg:
                current.append(value)
            continue
        if ch == "/" and i + 1 < length and source[i + 1] in {"/", "*"}:
            if source[i + 1] == "/":
                nl = source.find("\n", i)
                i = length if nl < 0 else nl
                continue
            end = source.find("*/", i + 2)
            i = length if end < 0 else end + 2
            continue
        if ch == "(":
            depth += 1
            is_literal_arg = False
            i += 1
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(current) if current and is_literal_arg else None)
                i += 1
                break
            is_literal_arg = False
            i += 1
            continue
        if ch == "," and depth == 1:
            args.append("".join(current) if current and is_literal_arg else None)
            current = []
            is_literal_arg = True
            i += 1
            continue
        if ch == "." and depth == 1:
            is_literal_arg = False
            i += 1
            continue
        if not ch.isspace() and ch not in {")", ","} and depth == 1 and not current:
            if ch not in {'"', "'"}:
                is_literal_arg = False
        i += 1
    return args, i


def _read_php_string(source: str, i: int) -> tuple[str, int]:
    quote = source[i]
    i += 1
    chars: list[str] = []
    length = len(source)
    while i < length:
        ch = source[i]
        if ch == "\\" and i + 1 < length:
            nxt = source[i + 1]
            escapes = {"n": "\n", "r": "\r", "t": "\t", "\\": "\\", quote: quote}
            chars.append(escapes.get(nxt, nxt))
            i += 2
            continue
        if ch == quote:
            return "".join(chars), i + 1
        chars.append(ch)
        i += 1
    return "".join(chars), i


def _extract_js(source: str, rel: str, default_domain: str) -> list[Message]:
    messages: list[Message] = []
    for match in JS_I18N_RE.finditer(source):
        msgid = bytes(match.group(3), "utf-8").decode("unicode_escape")
        messages.append(Message(msgid=msgid, domain=default_domain, references=[rel]))
    return messages


def _has_js_i18n(plugin_root: Path) -> bool:
    for path in plugin_root.rglob("*"):
        if path.suffix.lower() not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        if "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "wp.i18n" in text or "@wordpress/i18n" in text:
            return True
    return False


def _pick_pot(plugin_root: Path, bundled: list[str]) -> str | None:
    if not bundled:
        return None
    preferred = [p for p in bundled if "languages" in p.replace("\\", "/").lower()]
    rel = preferred[0] if preferred else bundled[0]
    return str(plugin_root / rel)


def _messages_from_pot(path: Path) -> list[Message]:
    po = polib.pofile(str(path))
    messages = []
    for entry in po:
        if not entry.msgid or entry.obsolete:
            continue
        messages.append(
            Message(
                msgid=entry.msgid,
                msgid_plural=entry.msgid_plural or "",
                msgctxt=entry.msgctxt or "",
                domain="",
                references=list(entry.occurrences) if entry.occurrences else [],
            )
        )
    return messages


def _try_wp_cli_make_pot(plugin_root: Path, work_dir: Path, text_domain: str) -> Path | None:
    wp = shutil.which("wp")
    if not wp:
        return None
    out = work_dir / "generated.pot"
    cmd = [
        wp,
        "i18n",
        "make-pot",
        str(plugin_root),
        str(out),
        f"--domain={text_domain}",
        "--allow-root",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.info("WP-CLI make-pot を実行できませんでした: %s", exc)
        return None
    if result.returncode != 0 or not out.exists():
        logger.info("WP-CLI make-pot が失敗したため内蔵抽出器へフォールバックします")
        return None
    logger.info("WP-CLI i18n make-pot で .pot を生成しました")
    return out


def _write_generated_pot(work_dir: Path, domain: str, info: PluginInfo, messages: list[Message]) -> Path:
    po = polib.POFile()
    po.metadata = {
        "Project-Id-Version": f"{info.name} {info.version}",
        "MIME-Version": "1.0",
        "Content-Type": "text/plain; charset=UTF-8",
        "Content-Transfer-Encoding": "8bit",
        "Language": "",
        "X-Domain": domain,
    }
    for msg in messages:
        if msg.msgid_plural:
            po.append(
                polib.POEntry(
                    msgid=msg.msgid,
                    msgid_plural=msg.msgid_plural,
                    msgctxt=msg.msgctxt or None,
                    msgstr_plural={0: "", 1: ""},
                )
            )
        else:
            po.append(
                polib.POEntry(
                    msgid=msg.msgid,
                    msgctxt=msg.msgctxt or None,
                    msgstr="",
                )
            )
    path = work_dir / f"{domain}.pot"
    po.save(str(path))
    return path


def _resolve_domain_path(plugin_root: Path, domain_path: str) -> Path | None:
    rel = domain_path.strip().lstrip("/\\")
    if not rel:
        return None
    path = plugin_root / rel
    return path if path.exists() else None
