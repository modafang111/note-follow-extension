WordPress公式プラグイン日本語化 → BASE商品登録 自動化
======================================================

配置場所（想定）
  D:\dev\base-wp-ja-auto

人間が行う作業は、原則として WordPress 公式プラグインの URL を指定することだけに近づけます。
既存 BASE 商品は「正解のテンプレート」として参照専用です。既存商品の変更・削除は行いません。


1. できること
--------------
- WordPress.org Plugin API からプラグイン情報を取得
- 公式ZIPの取得と安全な展開（PHPは実行しない）
- 日本語化状況の事前確認
- 翻訳対象の抽出（同梱 .pot 優先、なければ WP-CLI または内蔵抽出器）
- OpenAI による日本語翻訳（Gemini 等へ差し替え可能な translator.py）
- 翻訳品質チェック
- TextDomain-ja.po / .mo （必要なら JS JSON）生成
- 販売用ZIPと README の作成
- 既存 BASE 商品の命名・価格・説明・カテゴリをテンプレート化
- DRY RUN で登録予定内容を JSON/テキスト出力
- BASE 公式API または Playwright による商品登録
- SQLite による履歴・重複防止・途中再開
- メール通知


2. BASE 公式仕様の切り分け（実装前に公式ドキュメントで確認済み）
--------------------------------------------------------------
確認日: 2026-08-27
公式: https://docs.thebase.in/api/

API で可能なこと
- OAuth2 による認証（access_token 有効期限 約1時間、refresh_token 約30日）
- GET /1/items/detail/:item_id  テンプレート商品の参照
- GET /1/categories
- GET /1/item_categories/detail/:item_id
- POST /1/items/add             商品メタデータ登録（title, detail, price, stock, visible 等）
- POST /1/items/add_image       画像登録（公開URLが必要。jpg/png/gif、4MB以内）
- POST /1/item_categories/add   カテゴリ付与

API ではできないこと
- デジタルコンテンツ販売 App のファイル添付
- ローカル画像ファイルの直接アップロード（image_url のみ）
- デジタルコンテンツ商品の編集（公式エラー: 「デジタルコンテンツの商品は編集できません。」）

そのため
- テンプレート取得・メタデータ登録は公式APIを優先
- 販売ZIPの添付は Playwright（管理画面のロール/ラベル操作）
- CAPTCHA・二段階認証・本人確認は突破しない。停止して「BASEで手動認証が必要です」と通知
- 商品削除 API はコード上も呼び出さない


3. 初期セットアップ（Windows）
------------------------------
1) Python 3.10 以降をインストールする

2) 本フォルダへ移動する
   cd /d D:\dev\base-wp-ja-auto

3) 仮想環境（推奨）
   python -m venv .venv
   .venv\Scripts\activate

4) 依存関係
   python -m pip install -r requirements.txt

5) Playwright ブラウザ（実登録でデジタルファイルを添付する場合のみ）
   python -m playwright install chromium

6) .env.example をコピーして .env を作る
   copy .env.example .env
   パスワードや API キーは .env にだけ書く。.env は Git 対象外。

7) 最低限の確認
   python app.py --help


4. .env のポイント
------------------
DRY_RUN=true
  最初は必ず true。BASE へ実登録しない。登録予定内容だけ生成する。

BASE_PUBLISH_MODE=draft
  draft=非表示(visible=0) / public=表示(visible=1)
  初回の実登録は draft のまま、管理画面で目視確認してから public にする。

CONTINUE_WHEN_JA_COMPLETE=false
  公式日本語翻訳が JA_TRANSLATION_SKIP_PERCENT 以上なら自動登録しない。
  処理したい場合は true、または実行時 --continue-if-translated。

SALE_PACKAGE_MODE=translation_only
  translation_only     販売ZIPは翻訳ファイル+README のみ（推奨の初期値）
  plugin_and_translation  参考用にプラグイン本体も同梱（本体は公式から入れる旨を明記）
  どちらでも、内部の work フォルダでは original と translations を必ず分離する。

BASE_REGISTER_METHOD=playwright_digital
  playwright_digital   デジタルコンテンツとしてファイル添付まで試行
  api_metadata_only    公式APIでメタデータのみ登録。ファイルは手動添付。

TRANSLATOR_PROVIDER=openai
  openai または offline（APIキーなしの試験用。本番品質には使わない）

BASE_TEMPLATE_PRODUCT_URL または BASE_TEMPLATE_PRODUCT_ID
  既存の販売商品を指定する。商品名の命名規則・説明文・価格・カテゴリの正解。

BASE_TEMPLATE_PLUGIN_NAME
  テンプレート商品が扱っているプラグイン名。説明文中の差し替えに使う。
  例: Contact Form 7

OPENAI_API_KEY / OPENAI_MODEL
  初期実装の翻訳エンジン。未設定時は offline へフォールバック（警告ログあり）。

BASE_CLIENT_ID / BASE_CLIENT_SECRET / BASE_ACCESS_TOKEN / BASE_REFRESH_TOKEN
  https://developers.thebase.in でアプリ申請し、write_items と read_items を付与。
  python app.py --base-auth
  表示されたURLで許可し、
  python app.py --base-auth --auth-code 認可コード
  トークンは data/base_tokens.json に保存（Git 対象外）。

SMTP_* / NOTIFY_EMAIL / MAIL_FROM
  未設定ならメールは送らず logs/last-mail.txt に本文を残す。


5. 実行方法
------------
1件
  python app.py "https://wordpress.org/plugins/hello-dolly/"

DRY RUN（推奨・最初はこれ）
  python app.py "https://wordpress.org/plugins/hello-dolly/" --dry-run

公式日本語が十分でも継続
  python app.py "https://wordpress.org/plugins/hello-dolly/" --dry-run --continue-if-translated

複数件（input\plugins.txt に1行1URL）
  python app.py --input input\plugins.txt

URL もファイルも省略し、input\plugins.txt に実URLがある場合はそれを読む。

翻訳まで（BASE登録しない）
  python app.py URL --translate-only

途中再開（翻訳済みなら API を再呼び出ししない）
  python app.py URL --resume

BASE登録のみ再実行
  python app.py URL --base-only

同一バージョンを再処理
  python app.py URL --force

テンプレート商品の取得（参照のみ）
  python app.py --fetch-template

本番登録（.env の DRY_RUN=false でも可）
  python app.py URL --no-dry-run


6. 処理の流れ
--------------
URL解析
→ WordPress情報取得
→ 対象可否判定（公式無料プラグイン以外は停止）
→ ZIPダウンロード
→ ZIP展開
→ 日本語対応状況の事前確認
→ 翻訳対象抽出
→ AI翻訳
→ 品質チェック
→ .po / .mo 生成
→ 販売ZIP生成
→ 商品情報生成（既存商品の形式に合わせる）
→ DRY RUN ならプレビュー出力で停止
→ BASEログイン / 商品登録
→ 登録確認
→ メール通知


7. 成果物の場所
----------------
work\スラッグ\バージョン\
  original\           展開した公式プラグイン（実行しない）
  translations\       自作 .po .mo
  preview.json / preview.txt
  product_image.png

output\
  スラッグ-バージョン-ja.zip
  スラッグ-バージョン-preview.json

data\jobs.sqlite      処理履歴
logs\                 実行ログ（秘密情報はマスク）
screenshots\          BASE操作失敗時
backup\               予備


8. 開発・検証の順番（本番をいきなり大量登録しない）
--------------------------------------------------
第1段階  WordPress URL から情報取得
第2段階  ZIP取得・展開
第3段階  翻訳文字列抽出
第4段階  AI翻訳
第5段階  .po/.mo 生成
第6段階  販売ZIP
第7段階  BASEテンプレート取得（--fetch-template）
第8段階  DRY RUN で登録予定内容を確認
第9段階  テスト商品を draft（非公開）で1件だけ登録
第10段階 人間が BASE 管理画面で確認
第11段階 問題がなければ通常運用


9. エラー時の復旧
------------------
ログを見る
  logs フォルダの最新ファイル。スタックトレースもここに残る。

翻訳後に BASE だけ失敗
  python app.py URL --resume
  または
  python app.py URL --base-only

品質エラーで止まった
  work\...\quality_report.json を確認。重大エラー中は自動登録しない。

「既に十分日本語化されている可能性があります」
  販売しないのが既定。続けるなら
  CONTINUE_WHEN_JA_COMPLETE=true
  または --continue-if-translated

「BASEで手動認証が必要です」
  ブラウザで管理画面にログインし、CAPTCHA/2FA を済ませる。
  その後 --resume または --base-only。
  自動回避機能はない。

同一 slug + バージョンが登録済み
  二重登録しない。新しいバージョンは更新版として記録する。
  UPDATE_MODE=new_product（既定）/ skip / needs_review

メール未設定
  logs\last-mail.txt を見る。


10. 安全対策
------------
- ダウンロードした PHP は実行しない
- ZIP Slip 防止、サイズ・ファイル数の上限
- プラグインZIPは downloads.wordpress.org のみ
- APIキー・パスワードはソースにもログにも出さない
- 既存 BASE 商品は参照のみ。削除機能なし
- 予期しない状態では Fail Safe で停止
- 既定は DRY_RUN=true かつ BASE_PUBLISH_MODE=draft


11. 商品名・説明文について
--------------------------
新しいルールは作らず、指定した既存 BASE 商品を正解にする。

1. .env に BASE_TEMPLATE_PRODUCT_ID または URL を入れる
2. python app.py --fetch-template
3. 取得した商品名から「{plugin_name} ...」形式の命名規則を組み立てる
4. 説明文は既存の改行・構成を維持し、プラグイン名 / バージョン / 公式URL などを差し替える
5. AI でセールスコピーを作り直さない

API 未設定の間は templates\product_name.txt と product_description.txt を使う。
既存商品に合わせてこれらのファイルを編集してよい。
価格の初期値 500 円はプレースホルダ。テンプレート取得後は既存商品の価格を使う。


12. ディレクトリ構成
--------------------
app.py
config.py
.env
.env.example
requirements.txt
README.txt
src\
  wordpress.py
  plugin_downloader.py
  plugin_analyzer.py
  translator.py
  translation_builder.py
  package_builder.py
  base_client.py
  base_template.py
  mailer.py
  logger.py
  database.py
  utils.py
  （内部用）pipeline.py / product_image.py / exceptions.py
input\plugins.txt
work\
output\
logs\
data\
screenshots\
backup\
templates\
