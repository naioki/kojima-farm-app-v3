import json
import glob
import os

def main():
    print("="*50)
    print(" Streamlit Cloud用 Secrets生成ツール")
    print("="*50)
    print("以下の内容をコピーして、Streamlit Cloudの 'Secrets' 設定に貼り付けてください。")
    print("-" * 50)
    print()

    # 1. GEMINI_API_KEY
    # Try to find it in existing secrets.toml or environment
    api_key = "ここにAPIキーを貼り付けてください"
    try:
        if os.path.exists(".streamlit/secrets.toml"):
            with open(".streamlit/secrets.toml", "r", encoding="utf-8") as f:
                for line in f:
                    if "GEMINI_API_KEY" in line:
                        print(line.strip())
                        api_key = None # Already printed
                        break
    except:
        pass
    
    if api_key:
        print(f'GEMINI_API_KEY = "{api_key}"')

    print()

    # 2. Email Config
    print("[email]")
    print('email_address = "your-email@gmail.com"')
    print('imap_server = "imap.gmail.com"')
    print('sender_email = "order@example.com"')
    print('# days_back = 3  # (Optional)')
    
    print()

    # 3. Google Cloud Credentials
    # Try looking in Downloads first as per user request
    json_path = r"C:\Users\naiok\Downloads\streamlit-sheets-486912-5dd20ca660e9.json"
    
    if os.path.exists(json_path):
        # Found the file
        pass
    else:
        # Fallback to local files
        json_files = glob.glob("streamlit-sheets-*.json")
        if json_files:
            json_path = json_files[0]
        else:
            json_path = None

    if json_path:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                creds = json.load(f)
            
            print("[gcp]")
            for key, value in creds.items():
                # Escape newlines for TOML strings if necessary, though usually not needed for simple keys
                if "\n" in str(value):
                    print(f'{key} = """{value}"""')
                else:
                    print(f'{key} = "{value}"')
                    
        except Exception as e:
            print(f"# エラー: JSONファイルの読み込みに失敗しました: {e}")
    else:
        print("# [gcp] 設定用のJSONファイルが見つかりませんでした。")
        print("# 手動で設定してください。")

    print()
    print("-" * 50)
    print("コピー完了後、Streamlit Cloudの App Settings -> Secrets に貼り付けてください。")
    print("="*50)

if __name__ == "__main__":
    main()
