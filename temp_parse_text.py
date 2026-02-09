
def parse_order_text(text: str, sender: str, subject: str, api_key: str) -> list:
    """メール本文（テキスト）を解析して注文データを抽出"""
    genai.configure(api_key=api_key)
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
    except Exception:
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
        except Exception:
            model = genai.GenerativeModel('gemini-pro')
            
    known_stores = get_known_stores()
    item_normalization = get_item_normalization()
    store_list = "、".join(known_stores)
    item_settings_for_prompt = load_item_settings()
    unit_lines = "\n".join([f"- {name}: {s.get('default_unit', 0)}{s.get('unit_type', '袋')}/コンテナ" for name, s in sorted(item_settings_for_prompt.items()) if s.get("default_unit", 0) > 0])
    
    prompt = f"""
    メール本文から注文情報を抽出し、JSON形式で返してください。
    
    【送信者】{sender}
    【件名】{subject}
    
    【店舗名リスト（参考）】
    {store_list}
    ※リストになくても、文脈から店舗名と判断できる場合は抽出してください。
    
    【品目名の正規化ルール】
    {json.dumps(item_normalization, ensure_ascii=False, indent=2)}
    
    【計算ルール（1コンテナあたりの入数）】
    {unit_lines}
    
    【重要ルール】
    - 出力は純粋なJSONのみ (Markdown記法なし)。
    - unit, boxes, remainderには「数字のみ」を入れてください。
    - 「×数字」が総数の場合は boxes/remainder に分解し、箱数の場合は boxes に入れてください（文脈から判断）。
    - 日付情報が含まれている場合でも、今回の出力には含めず、注文明細のみ抽出してください。
    
    【出力JSON形式】
    [{{"store":"店舗名","item":"品目名","spec":"規格","unit":数字,"boxes":数字,"remainder":数字}}]
    
    【メール本文】
    {text}
    """
    
    try:
        response = model.generate_content(prompt)
        text_resp = response.text.strip()
        if '```json' in text_resp:
            text_resp = text_resp.split('```json')[1].split('```')[0].strip()
        elif '```' in text_resp:
            parts = text_resp.split('```')
            for part in parts:
                if '{' in part and '[' in part:
                    text_resp = part.strip()
                    break
        result = json.loads(text_resp)
        if isinstance(result, dict):
            result = [result]
        return result
    except Exception as e:
        st.error(f"テキスト解析エラー: {e}")
        return None
