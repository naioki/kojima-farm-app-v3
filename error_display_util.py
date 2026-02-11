"""
エラー表示用ユーティリティ。
利用者向けに日本語の理由を上に、修正用に技術詳細を下に表示する。
"""
def _reason_ja(e: Exception, context: str) -> str:
    """例外内容から日本語の理由文を推測する。"""
    s = (str(e) or "").lower()
    if "429" in s or "too many request" in s or "quota" in s or "rate limit" in s:
        return "リクエスト回数が多すぎます。しばらく時間をおいてからお試しください。"
    if "connection" in s or "connect" in s or "network" in s or "接続" in s or "refused" in s:
        return "接続に失敗しました。ネットワークまたはサーバー設定をご確認ください。"
    if "permission" in s or "権限" in s or "403" in s or "forbidden" in s:
        return "権限がありません。設定または共有をご確認ください。"
    if "spreadsheet" in s or "gspread" in s or "スプレッドシート" in s or "404" in s:
        return "スプレッドシートへのアクセスに失敗しました。ID・シート名・共有設定・認証をご確認ください。"
    if "json" in s or "parse" in s or "解析" in s or "decode" in s:
        return "データの解析に失敗しました。入力内容またはAPIの応答をご確認ください。"
    if "imap" in s or "mail" in s or "メール" in s or "smtp" in s or "authentication" in s:
        return "メールの接続・取得に失敗しました。アドレス・パスワード・IMAP設定をご確認ください。"
    if "pdf" in s or "font" in s or "ファイル" in s:
        return "PDFの生成に失敗しました。ファイルまたはフォントの設定をご確認ください。"
    if "api" in s or "key" in s or "invalid" in s:
        return "APIの呼び出しに失敗しました。APIキーまたはリクエスト内容をご確認ください。"
    if context:
        return f"{context}の処理中にエラーが発生しました。"
    return "予期しないエラーが発生しました。"


def format_error_display(e: Exception, context: str = "") -> str:
    """
    利用者向けに表示するエラー文を組み立てる。
    上に日本語の理由、下に「詳細（修正用）」として技術メッセージを残す。
    """
    reason = _reason_ja(e, context)
    detail = str(e).strip() or "(詳細なし)"
    return f"{reason}\n\n詳細（修正用）: {detail}"
