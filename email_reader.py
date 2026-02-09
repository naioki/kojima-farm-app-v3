"""
メール自動読み取りモジュール
IMAPを使用してメールを取得し、画像を抽出
"""
import imaplib
import email
from email.header import decode_header
from email.utils import parsedate_to_datetime
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from PIL import Image
import io
import base64

def decode_mime_words(s):
    """MIMEエンコードされた文字列をデコード"""
    if not s:
        return ""
    decoded_fragments = decode_header(s)
    decoded_str = ""
    for fragment, encoding in decoded_fragments:
        if isinstance(fragment, bytes):
            if encoding:
                decoded_str += fragment.decode(encoding)
            else:
                decoded_str += fragment.decode('utf-8', errors='ignore')
        else:
            decoded_str += fragment
    return decoded_str

def extract_images_from_email(msg) -> List[Dict]:
    """メールから画像を抽出"""
    images = []
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            
            # 画像の添付ファイルを探す
            if "image" in content_type and "attachment" in content_disposition:
                filename = part.get_filename()
                if filename:
                    filename = decode_mime_words(filename)
                    image_data = part.get_payload(decode=True)
                    if image_data:
                        try:
                            image = Image.open(io.BytesIO(image_data))
                            images.append({
                                'filename': filename,
                                'image': image,
                                'data': image_data
                            })
                        except Exception as e:
                            print(f"画像読み込みエラー: {e}")
            
            # インライン画像も探す
            elif "image" in content_type:
                image_data = part.get_payload(decode=True)
                if image_data:
                    try:
                        image = Image.open(io.BytesIO(image_data))
                        images.append({
                            'filename': part.get_filename() or 'inline_image',
                            'image': image,
                            'data': image_data
                        })
                    except Exception as e:
                        print(f"画像読み込みエラー: {e}")
    else:
        # シンプルなメールの場合
        content_type = msg.get_content_type()
        if "image" in content_type:
            image_data = msg.get_payload(decode=True)
            if image_data:
                try:
                    image = Image.open(io.BytesIO(image_data))
                    images.append({
                        'filename': msg.get_filename() or 'image',
                        'image': image,
                        'data': image_data
                    })
                except Exception as e:
                    print(f"画像読み込みエラー: {e}")
    
    return images

def extract_text_from_email(msg) -> str:
    """メールからテキスト本文を抽出"""
    text = ""
    if msg.is_multipart():
        # multipart/alternative の場合、text/plain を優先
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition"))
            if "attachment" in content_disposition:
                continue
            
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        text += payload.decode('utf-8', errors='ignore')
                    except Exception:
                        pass
            elif content_type == "text/html" and not text:
                # HTMLしかない場合はHTMLタグを除去して採用（簡易的）
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        html = payload.decode('utf-8', errors='ignore')
                        # 簡易的なタグ除去
                        text += re.sub(r'<[^>]+>', '', html)
                    except Exception:
                        pass
    else:
        content_type = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            if content_type == "text/plain":
                try:
                    text = payload.decode('utf-8', errors='ignore')
                except Exception:
                    pass
            elif content_type == "text/html":
                try:
                    html = payload.decode('utf-8', errors='ignore')
                    text = re.sub(r'<[^>]+>', '', html)
                except Exception:
                    pass
    return text.strip()

def check_email_for_orders(
    imap_server: str,
    email_address: str,
    password: str,
    sender_email: Optional[str] = None,
    days_back: int = 1
) -> List[Dict]:
    """
    メールをチェックして注文メールを取得
    
    Args:
        imap_server: IMAPサーバー（例: 'imap.gmail.com'）
        email_address: メールアドレス
        password: パスワードまたはアプリパスワード
        sender_email: 送信者メールアドレス（フィルタ用、Noneの場合は全て）
        days_back: 何日前まで遡るか
    
    Returns:
        メール情報のリスト (辞書: email_id, subject, from, date, images, body_text)
    """
    results = []
    
    try:
        # IMAP接続
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, password)
        mail.select("inbox")
        
        # 検索条件
        since_date = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        search_criteria = f'(SINCE {since_date})'
        
        if sender_email:
            search_criteria = f'(FROM "{sender_email}" SINCE {since_date})'
        
        # メール検索
        status, messages = mail.search(None, search_criteria)
        
        if status != "OK":
            return results
        
        email_ids = messages[0].split()
        
        for email_id in email_ids:
            try:
                # メール取得
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                
                # メール解析
                msg = email.message_from_bytes(msg_data[0][1])
                
                # メール情報
                subject = decode_mime_words(msg["Subject"] or "")
                from_addr = decode_mime_words(msg["From"] or "")
                date_str = msg["Date"]
                date = parsedate_to_datetime(date_str) if date_str else None
                
                # 画像抽出
                images = extract_images_from_email(msg)
                
                # 本文抽出
                body_text = extract_text_from_email(msg)
                
                # 返却データ構築 (後方互換性のためフラットな構造は維持せず、1メール1エントリにするのが理想だが、
                # 既存の app.py は画像単位でループしている可能性がある。
                # しかし、今回はテキスト解析も加わるため、1メール1エントリとし、app.py側で画像ループさせる形に変更するほうが綺麗。
                # ただし、既存の check_email_for_orders は `results.append({ ... 'image': img ... })` と画像単位で返している。
                # これを変更すると既存ロジックが壊れる。
                # Plan: 画像がある場合は画像ごとにエントリを作り、テキストのみの場合はテキストエントリを作る...
                # いや、app.py のロジックを見ると `for result in results:` で `result['image']` を参照している。
                # Phase 3 の要件は「画像またはテキスト」。
                # 既存のI/F (List[Dict]) を拡張し、
                # `image` キーがあるエントリ（画像モード用）と、
                # `body_text` キーがあり `image` がNoneのエントリ（テキストモード用）を混在させる、
                # あるいは 1メール1エントリに変えて app.py を大幅改修するか。
                
                # 今回は「画像またはテキスト」なので、
                # 1. 画像がある -> 従来通り画像ごとにエントリ追加 (body_text も付与しておくと役立つかも)
                # 2. 画像がない -> テキスト解析用に body_text を持つエントリを1つ追加 (image=None)
                
                processed = False
                if images:
                    for img_info in images:
                        results.append({
                            'email_id': email_id.decode(),
                            'subject': subject,
                            'from': from_addr,
                            'date': date,
                            'image': img_info['image'],
                            'filename': img_info['filename'],
                            'body_text': body_text # 画像解析でも補足情報として使えるかもしれない
                        })
                        processed = True
                
                # 画像がない場合でも、テキスト解析のニーズがあるため、エントリを追加する
                # ただし重複を防ぐため、app.py 側で判断できるようにする。
                # 今回は単純に「画像がない場合のみ」テキストエントリを追加するのではなく、
                # 「常に」テキストエントリを追加すると画像がある場合に重複する。
                # なので、「画像がない」かつ「テキストがある」場合にテキストエントリを追加する。
                # もしくは、Sender Rule で「テキストモード」の場合はテキストエントリが必要。
                # ここでは「画像が見つからなかった、かつ本文がある」場合にテキストエントリを追加する形にする。
                # (Sender Ruleによる制御は app.py 側で行うため、ここでは可能な限り情報を返す)
                
                if not processed and body_text:
                     results.append({
                        'email_id': email_id.decode(),
                        'subject': subject,
                        'from': from_addr,
                        'date': date,
                        'image': None,
                        'filename': 'body_text',
                        'body_text': body_text
                    })

            except Exception as e:
                print(f"メール処理エラー (ID: {email_id}): {e}")
                continue
        
        mail.close()
        mail.logout()
    
    except Exception as e:
        print(f"メールチェックエラー: {e}")
        raise
    
    return results

def mark_email_as_read(imap_server: str, email_address: str, password: str, email_id: str):
    """メールを既読にする"""
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(email_address, password)
        mail.select("inbox")
        mail.store(email_id, '+FLAGS', '\\Seen')
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"メール既読マークエラー: {e}")
