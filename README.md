# kojima-farm-app-v3

出荷ラベル・納品データ連携アプリ v3

- 出荷ラベル印刷（PDF）
- 納品データ変換・スプレッドシート追記
- メール設定・送信

## セットアップ

1. `pip install -r requirements.txt`
2. `.streamlit/secrets.toml` に GCP 認証情報などを設定
3. 必要に応じて `G:\マイドライブ\00_CursorProject\01_Project\0209Kojima farm app v3` から `email_reader.py`, `pdf_generator.py`, `ipaexg.ttf` をコピー

## 実行（ローカル）

```bash
streamlit run app.py
```

## Streamlit Cloud で公開する

GitHub にプッシュしたリポジトリを Streamlit Cloud に接続すると、ブラウザからどこでもアクセスできます。  
**手順の詳細は [DEPLOY.md](DEPLOY.md) を参照してください。**

- Secrets で `GEMINI_API_KEY` と `[gcp]`（台帳用）を設定
- 台帳スプレッドシートをサービスアカウントのメールで「編集者」共有
- リポジトリに `ipaexg.ttf` が含まれていること
