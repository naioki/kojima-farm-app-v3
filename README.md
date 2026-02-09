# kojima-farm-app-v3

出荷ラベル・納品データ連携アプリ v3

- 出荷ラベル印刷（PDF）
- 納品データ変換・スプレッドシート追記
- メール設定・送信

## セットアップ

1. `pip install -r requirements.txt`
2. `.streamlit/secrets.toml` に GCP 認証情報などを設定
3. 必要に応じて `G:\マイドライブ\00_CursorProject\01_Project\0209Kojima farm app v3` から `email_reader.py`, `pdf_generator.py`, `ipaexg.ttf` をコピー

## 実行

```bash
streamlit run app.py
```
