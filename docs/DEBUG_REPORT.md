# 網羅的デバッグレポート（kojima-farm-app-v3）

実施日: 2025年2月  
対象: [GitHub - naioki/kojima-farm-app-v3](https://github.com/naioki/kojima-farm-app-v3)

---

## 1. 実施した観点

| 観点 | 内容 |
|------|------|
| テスト・インポート | pytest 実行、`verify_imports.py`、不足インポートの有無 |
| 静的解析 | 未使用変数、bare except、インデント不備、型・依存関係 |
| コードレビュー | 主要モジュールのバグ・境界値・エラーハンドリング |
| 設定・シークレット | Secrets / GCP / 環境変数の参照方法、フォールバック |
| 依存関係 | requirements.txt、非推奨パッケージの警告 |

---

## 2. 修正した不具合・改善

### 2.1 重大: 不足インポート（app.py）

**現象**: 解析結果の確認・編集で「ラベルを生成」や編集保存時に `NameError` が発生する可能性。

**原因**: `normalize_item_name` と `validate_store_name` を `app.py` 内で使用しているが、`order_processing` からインポートしていなかった。

**対応**: `order_processing` のインポートに `normalize_item_name`, `validate_store_name` を追加。

```python
from order_processing import (
    safe_int,
    parse_order_image, parse_order_text, validate_and_fix_order_data,
    normalize_item_name, validate_store_name
)
```

---

### 2.2 テスト失敗: 列名の表記ゆれ（test_delivery_converter.py）

**現象**: `test_v2_result_to_delivery_rows` で「納品日付」のアサーションが失敗。

**原因**: テストで中国語簡体字の「纳品日付」を使用していたが、実装は日本語の「納品日付」でキーを出力している。

**対応**: テストの `row["纳品日付"]` を `row["納品日付"]` に修正。

---

### 2.3 スタイル・堅牢性: bare except（app.py）

**現象**: 出荷日デフォルト取得の `except:` で全ての例外を握りつぶしており、推奨されない。

**対応**: `except (ValueError, TypeError):` に変更し、想定する例外のみ捕捉。

---

### 2.4 インデント不備（app.py）

**現象**: 未確定一覧の「変更を保存」で、`updates["チェック"] = new_check` の行だけインデントが1スペース不足していた。

**対応**: 正しいインデントに修正。

---

### 2.5 テスト実行環境（requirements.txt）

**現象**: リポジトリに `pytest` が含まれておらず、CIやローカルで `python -m pytest` が使えない。

**対応**: `requirements.txt` に `pytest>=7.0.0` を追加。

---

## 3. テスト結果（修正後）

```
tests/test_delivery_converter.py::test_safe_int PASSED
tests/test_delivery_converter.py::test_normalize_date PASSED
tests/test_delivery_converter.py::test_v2_result_to_delivery_rows PASSED
tests/test_delivery_converter.py::test_v2_result_to_ledger_rows PASSED
tests/test_delivery_converter.py::test_ledger_rows_to_v2_format_with_units PASSED
tests/test_order_processing.py::test_safe_int PASSED
tests/test_order_processing.py::test_validate_store_name PASSED
tests/test_order_processing.py::test_normalize_item_name PASSED
tests/test_order_processing.py::test_validate_and_fix_order_data PASSED
```

**9 passed**, 1 warning（後述の非推奨パッケージ）。

---

## 4. 残存する注意点・推奨

### 4.1 非推奨パッケージ（google-generativeai）

`order_processing.py` および `app.py` で `import google.generativeai as genai` を使用しています。  
公式では `google-genai` への移行が案内されています。

- 現状: 動作するが FutureWarning が出る
- 推奨: 余裕があるタイミングで [google-genai](https://github.com/google-gemini/deprecated-generative-ai-python/blob/main/README.md) へ移行

### 4.2 verify_imports.py と app の読み込み

`verify_imports.py` が `import app` すると、`app.py` のトップレベルで Streamlit / Gemini が実行され、時間がかかったり環境によっては失敗することがあります。  
インポート検証のみ行う場合は、`app` をインポートしないオプションや、軽量なモジュールだけを検証する方法を検討するとよいです。

### 4.3 その他の bare except

以下のファイルに `except:` が残っています（ユーティリティ・デバッグ用のため優先度は低いです）。

- `get_service_email.py`
- `show_cloud_secrets.py`

必要に応じて `except Exception:` などに限定することを推奨します。

### 4.4 台帳シート名のデフォルト

- 未確定一覧の「変更を保存」では `ledger_sheet_fetch or "シート1"` をフォールバックにしていますが、表示用のデフォルトは「台帳データ」です。  
  実際のシート名が「台帳データ」の場合は、保存時も「台帳データ」が使われるよう、`(ledger_sheet_fetch or "台帳データ").strip() or "台帳データ"` のように揃えると安全です。

---

## 5. 変更ファイル一覧

| ファイル | 変更内容 |
|----------|----------|
| `app.py` | 不足インポート追加、bare except 修正、インデント修正 |
| `tests/test_delivery_converter.py` | 「納品日付」の表記修正 |
| `requirements.txt` | pytest 追加 |
| `docs/DEBUG_REPORT.md` | 本レポート（新規） |

---

## 6. 今後のチェック例

- `streamlit run app.py` で起動し、画像解析・メール取得・未確定一覧・台帳からPDF・設定の各タブを一通り操作する
- `.streamlit/secrets.toml` に `[gcp]` を設定した状態で、納品データ追記・台帳取得ができることを確認する
- 新しい Python 環境で `pip install -r requirements.txt` の後に `python -m pytest tests/` が通ることを確認する

以上で網羅的デバッグの実施内容と修正・推奨事項をまとめています。
