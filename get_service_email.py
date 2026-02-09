import json
import os
import glob

def main():
    print("="*60)
    print(" Google Service Account Email Checker")
    print("="*60)
    
    # Try finding the JSON file (env var > current dir > project glob)
    json_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    email = None

    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                email = data.get("client_email")
        except Exception:
            pass

    if not email:
        # Try local files in project
        files = glob.glob("streamlit-sheets-*.json")
        if files:
            try:
                with open(files[0], 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    email = data.get("client_email")
            except Exception:
                pass

    if email:
        print("\nこのメールアドレスをコピーしてください：\n")
        print(f"   {email}")
        print("\n")
        print("-" * 60)
        print("【手順】")
        print("1. Googleスプレッドシートを開く")
        print("2. 右上の「共有」ボタンを押す")
        print("3. 上記のメールアドレスを貼り付ける")
        print("4. 「編集者」権限になっていることを確認して「送信」")
        print("-" * 60)
    else:
        print("エラー: 認証ファイル（JSON）が見つかりませんでした。")
        print("Downloadsフォルダまたはプロジェクトフォルダに配置してください。")

    print("\nPress Enter to exit...")
    input()

if __name__ == "__main__":
    main()
