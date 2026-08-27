"""WordPress公式プラグインの日本語化ファイル作成と BASE 商品登録の自動化エントリ。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from config import settings  # noqa: E402
from src.database import init_db  # noqa: E402
from src.exceptions import AlreadyProcessed, NeedHumanReview, SkipPlugin  # noqa: E402
from src.logger import setup_logger  # noqa: E402
from src.pipeline import RunOptions, process_url  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="WordPress公式プラグインの日本語化ファイルを作り、BASEへ商品登録する（DRY RUN 既定）",
    )
    parser.add_argument("url", nargs="?", help="https://wordpress.org/plugins/slug/")
    parser.add_argument("--input", dest="input_file", help="1行1URLのテキストファイル")
    parser.add_argument("--dry-run", action="store_true", help="BASEへ実登録せずプレビューのみ生成")
    parser.add_argument("--no-dry-run", action="store_true", help="DRY_RUN=false 相当。本番登録する")
    parser.add_argument("--resume", action="store_true", help="途中成果を再利用して再開する")
    parser.add_argument("--translate-only", action="store_true", help="翻訳・販売ZIPまでで停止")
    parser.add_argument("--base-only", action="store_true", help="既存成果から BASE 登録のみ行う")
    parser.add_argument("--force", action="store_true", help="同一バージョンの再処理を許可")
    parser.add_argument(
        "--continue-if-translated",
        action="store_true",
        help="公式日本語翻訳が十分でも処理を継続する",
    )
    parser.add_argument("--fetch-template", action="store_true", help="BASEテンプレート商品を取得して保存する")
    parser.add_argument("--base-auth", action="store_true", help="BASE OAuth 認可コードをトークンに交換する")
    parser.add_argument("--auth-code", help="--base-auth と併用する認可コード")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings.ensure_directories()
    init_db()

    if args.fetch_template:
        logger, log_path = setup_logger("fetch-template")
        logger.info("BASEテンプレート取得")
        from src.base_template import fetch_template_only

        rules = fetch_template_only()
        logger.info("取得元: %s / 商品名: %s / 価格: %s", rules.source, rules.title, rules.price)
        logger.info("保存先: %s", settings.template_cache_path)
        logger.info("ログ: %s", log_path)
        return 0

    if args.base_auth:
        logger, log_path = setup_logger("base-auth")
        from src.base_client import exchange_authorization_code, oauth_authorize_url

        if not settings.base_client_id:
            logger.info("BASE_CLIENT_ID が未設定です")
            return 2
        if args.auth_code:
            exchange_authorization_code(args.auth_code)
            logger.info("トークンを data/base_tokens.json に保存しました（Git対象外）")
            return 0
        logger.info("ブラウザで次のURLを開き、許可後の code を --auth-code に渡してください")
        logger.info("%s", oauth_authorize_url())
        logger.info("例: python app.py --base-auth --auth-code 認可コード")
        return 0

    urls = _collect_urls(args)
    if not urls:
        print("プラグインURLを指定するか、--input で一覧ファイルを指定してください。", file=sys.stderr)
        return 2

    dry_run = True if args.dry_run else (False if args.no_dry_run else None)
    options = RunOptions(
        dry_run=dry_run,
        resume=args.resume or args.base_only,
        translate_only=args.translate_only,
        base_only=args.base_only,
        force=args.force,
        continue_if_translated=args.continue_if_translated,
    )

    exit_code = 0
    for url in urls:
        slug_hint = url
        logger, log_path = setup_logger("run")
        logger.info("ログファイル: %s", log_path)
        try:
            result = process_url(url, options, log_path)
            logger.info("成功: %s %s", result.get("plugin_name"), result.get("plugin_version"))
            logger.info("プレビュー: %s", result.get("preview_path"))
            logger.info("販売ZIP: %s", result.get("output_zip"))
        except (SkipPlugin, AlreadyProcessed, NeedHumanReview) as exc:
            logger.info("%s: %s", type(exc).__name__, exc)
            exit_code = 1
        except Exception:
            exit_code = 1
        finally:
            del slug_hint
    return exit_code


def _collect_urls(args: argparse.Namespace) -> list[str]:
    urls: list[str] = []
    if args.url:
        urls.append(args.url.strip())
    input_file = Path(args.input_file) if args.input_file else None
    if input_file is None and not args.url:
        default_input = settings.input_dir / "plugins.txt"
        if default_input.exists() and any(
            line.strip() and not line.strip().startswith("#")
            for line in default_input.read_text(encoding="utf-8").splitlines()
        ):
            input_file = default_input
    if input_file:
        path = input_file if input_file.is_absolute() else (ROOT / input_file)
        if not path.exists():
            path = settings.input_dir / input_file.name
        for line in path.read_text(encoding="utf-8").splitlines():
            text = line.strip()
            if text and not text.startswith("#"):
                urls.append(text)
    # 重複除去（順序維持）
    seen = set()
    unique = []
    for url in urls:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


if __name__ == "__main__":
    raise SystemExit(main())
