# Streamlit Cloud Deployment Guide

このアプリをStreamlit Cloudで公開するための手順です。

## 1. 準備

### 1.1. 必要なファイル
以下のファイルが揃っていることを確認してください（自動的に作成されています）。
- `app.py`: メインアプリケーション
- `requirements.txt`: 依存ライブラリリスト
- `ipaexg.ttf`: 日本語フォントファイル
- `pdf_generator.py`, `order_processing.py` など関連モジュール
- `config/`: 設定ファイルフォルダ

### 1.2. GitHubへのプッシュ
1. GitHubで新しいリポジトリ（例: `farm-label-app`）を作成します。
2. このプロジェクトフォルダをリポジトリとしてプッシュします。
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   # 以下は自分のリポジトリURLに書き換えてください
   git remote add origin https://github.com/YOUR_USERNAME/farm-label-app.git
   git push -u origin main
   ```

## 2. Streamlit Cloudでの設定

1. [Streamlit Cloud](https://share.streamlit.io/) にログインします。
2. "New app" をクリックし、GitHubリポジトリを選択します。
   - Repository: `YOUR_USERNAME/farm-label-app`
   - Branch: `main`
   - Main file path: `app.py`
3. **Advanced settings** を開きます（ここが重要です）。

### 2.1. Secrets (環境変数) の設定
ローカルの `.streamlit/secrets.toml` の内容を、Streamlit Cloudの **Secrets** 入力欄にコピー＆ペーストします。

必要なキー:
- `GEMINI_API_KEY`: Google Gemini APIキー
- `[gcp]`: Google Sheets API認証情報（SERVICE_ACCOUNT_JSONの中身など）
- `[email]`: メール設定（imap_server, email_address など）

例:
```toml
GEMINI_API_KEY = "your-api-key"

[email]
email_address = "your-email@gmail.com"
imap_server = "imap.gmail.com"
sender_email = "order@example.com"

[gcp]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "..."
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."
```

※ Google Cloud Credentials (`[gcp]`セクション) は、JSONファイルの中身をそのままTOML形式に変換して貼り付けるか、または `st.secrets` の辞書形式に合わせて記述する必要があります。

## 3. デプロイ

"Deploy!" ボタンを押すと、数分でアプリが起動します。

## 注意点
- **フォント**: `ipaexg.ttf` がリポジトリに含まれている必要があります。これがないと日本語が出力されません。
- **メモリ**: 画像解析はメモリを使用するため、大きな画像を連続で処理するとリソース制限にかかる可能性があります。
