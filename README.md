# kojima-farm-app-v3

出荷ラベル・納品データ連携アプリ v3

- **現場用**: 画像／メールから注文を解析 → ラベルPDF・納品データ・台帳追記・一括確定
- **事務用**: 台帳の行を日付・納品先・品目で絞り込み、単価・金額を一括更新

## 主な機能

- 出荷ラベル印刷（PDF）
- 納品データ変換・スプレッドシート（台帳）追記
- メール自動読み取り・注文解析
- 事務用：台帳の単価・金額一括適用（1回読み＋1回書きで高速）

## セットアップ

1. `pip install -r requirements.txt`
2. `.streamlit/secrets.toml` に以下を設定（例）
   - `GEMINI_API_KEY`: Gemini API キー
   - `[gcp]`: 台帳用 Google サービスアカウント（JSON の中身を TOML 形式で）
   - `DELIVERY_SPREADSHEET_ID`: 台帳のスプレッドシートID（任意・未設定時は画面で入力）
3. 必要に応じて `ipaexg.ttf`（日本語フォント）を配置

## 実行（ローカル）

```bash
streamlit run app.py
```

## プロジェクト構成（抜粋）

- `app.py` … メインUI（現場用／事務用メニュー、タブ）
- `config_manager.py` … 店舗・品目・規格マスタ（`config/*.json`）
- `order_processing.py` … 画像／テキスト解析（Gemini）、検証
- `delivery_sheet_writer.py` … 台帳の取得・追記・一括更新
- `delivery_converter.py` … 解析結果→納品データ変換
- `pdf_generator.py` … ラベルPDF生成
- `error_display_util.py` … エラー表示（日本語理由＋技術詳細）

`config/` の JSON は店舗名・品目名・品目別規格・入数などです。本番と検証で同じ設定を使う場合はバックアップして運用してください。

## Streamlit Cloud で公開する

GitHub にプッシュしたリポジトリを Streamlit Cloud に接続すると、ブラウザからどこでもアクセスできます。  
**手順の詳細は [DEPLOY.md](DEPLOY.md) を参照してください。**

- Secrets で `GEMINI_API_KEY` と `[gcp]`（台帳用）を設定
- 必要なら `DELIVERY_SPREADSHEET_ID` も Secrets に設定すると、各タブで台帳IDを再入力しなくてよい
- 台帳スプレッドシートをサービスアカウントのメールで「編集者」共有
- リポジトリに `ipaexg.ttf` が含まれていること

## 改善の視点

多方面からの評価・改善の方向性は [docs/網羅的改善レビュー.md](docs/網羅的改善レビュー.md) にまとめています。
