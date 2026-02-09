"""
出荷ラベルPDF生成モジュール
A4用紙1枚に8分割（2列x4段）のラベルを生成（複数ページ対応）
最初のページに出荷一覧表を追加
"""
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.units import mm
from reportlab.lib.colors import black, gray, white, HexColor
from reportlab.platypus import Table, TableStyle
from typing import List, Dict
import os


class LabelPDFGenerator:
    """出荷ラベルPDF生成クラス"""
    
    # A4サイズ（縦）
    A4_WIDTH = 210 * mm
    A4_HEIGHT = 297 * mm
    
    # ラベルサイズ（2列x4段）
    LABEL_WIDTH = 105 * mm  # 210 / 2
    LABEL_HEIGHT = 74.25 * mm  # 297 / 4
    
    # 1ページあたりのラベル数
    LABELS_PER_PAGE = 8
    
    def __init__(self, font_path: str = None):
        """
        初期化
        
        Args:
            font_path: IPAexGothicフォントのパス（Noneの場合はデフォルトパスを試行）
        """
        self.font_path = font_path or self._find_font_path()
        self._register_font()
    
    def _find_font_path(self) -> str:
        """IPAexGothicフォントのパスを検索"""
        # 一般的なフォントパスを試行
        possible_paths = [
            'ipaexg.ttf',
            'fonts/ipaexg.ttf',
            'C:/Windows/Fonts/ipaexg.ttf',
            '/usr/share/fonts/ipaexg.ttf',
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
        
        # フォントが見つからない場合は警告を出すが、後でエラーハンドリング
        return 'ipaexg.ttf'
    
    def _register_font(self):
        """IPAexGothicフォントを登録"""
        self.bold_font_available = False
        try:
            if os.path.exists(self.font_path):
                pdfmetrics.registerFont(TTFont('IPAGothic', self.font_path))
                self.font_available = True
                # 太字フォント（ipaexgb.ttf）があれば登録
                bold_paths = [
                    'ipaexgb.ttf', 'fonts/ipaexgb.ttf',
                    'C:/Windows/Fonts/ipaexgb.ttf', '/usr/share/fonts/ipaexgb.ttf',
                ]
                for bp in bold_paths:
                    if os.path.exists(bp):
                        pdfmetrics.registerFont(TTFont('IPAGothic-Bold', bp))
                        self.bold_font_available = True
                        break
            else:
                print(f"警告: フォントファイルが見つかりません: {self.font_path}")
                self.font_available = False
        except Exception as e:
            print(f"フォント登録エラー: {e}")
            self.font_available = False
    
    def _get_font_name(self) -> str:
        """使用するフォント名を返す"""
        return 'IPAGothic' if self.font_available else 'Helvetica'
    
    def _get_font_name_bold(self) -> str:
        """日付等に使う太字フォント名を返す"""
        if self.bold_font_available:
            return 'IPAGothic-Bold'
        # Helvetica-Bold doesn't support Japanese characters (月/日)
        # Fallback to Regular IPAGothic to ensure characters are visible
        return 'IPAGothic' if self.font_available else 'Helvetica-Bold'
    
    def _rearrange_labels_for_cut_and_stack(self, labels: List[Dict]) -> List[Dict]:
        """
        Cut and Stack形式用にラベルを再配置
        
        仕様: 各ページnにおいて、各スロットに以下のインデックスのデータを配置
        - 左上（スロット0）: n番目
        - 右上（スロット1）: n + P番目
        - 左2段目（スロット2）: n + 2P番目
        - 右2段目（スロット3）: n + 3P番目
        - ... (同様に右下まで計8スロット)
        
        変換式:
        - 元のインデックスiに対して:
          - slot = i // P (スロット番号: 0-7)
          - page = i % P (ページ番号: 0から開始)
        - 再配置後のインデックスj = page * 8 + slot
        
        Args:
            labels: 元のラベルリスト
            
        Returns:
            再配置されたラベルリスト（空のスロットは空の辞書で埋める）
        """
        total_labels = len(labels)
        total_pages = (total_labels + self.LABELS_PER_PAGE - 1) // self.LABELS_PER_PAGE
        
        if total_pages == 0:
            return []
        
        total_slots = total_pages * self.LABELS_PER_PAGE
        
        # 再配置後のリストを初期化（空の辞書で埋める）
        rearranged = [{}] * total_slots
        
        # 元のインデックスiを、再配置後のインデックスjに変換
        for i in range(total_labels):
            slot = i // total_pages  # スロット番号 (0-7)
            page = i % total_pages   # ページ番号 (0から開始)
            # 再配置後のインデックス: ページpageのスロットslotの位置
            j = page * self.LABELS_PER_PAGE + slot
            if j < total_slots:
                rearranged[j] = labels[i]
        
        return rearranged
    
    def generate_pdf(self, labels: List[Dict], summary_data: List[Dict], 
                    shipment_date: str, output_path: str):
        """
        PDFを生成（複数ページ対応 + 出荷一覧表）
        Cut and Stack形式: 裁断後に重ねるだけで順番が揃う
        
        Args:
            labels: ラベル情報のリスト（全ラベル）
            summary_data: 出荷一覧表用のデータ
            shipment_date: 出荷日（YYYY-MM-DD形式）
            output_path: 出力PDFファイルパス
        """
        c = canvas.Canvas(output_path, pagesize=(self.A4_WIDTH, self.A4_HEIGHT))
        font_name = self._get_font_name()
        
        # 出荷日を表示用に変換（月/日、ゼロ埋めなし 例: 2/7）
        from datetime import datetime
        shipment_date_obj = datetime.strptime(shipment_date, '%Y-%m-%d')
        shipment_date_display = f"{shipment_date_obj.month}月{shipment_date_obj.day}日"  # 口数と区別するため漢字表記
        
        # 1ページ目：出荷一覧表
        self._draw_summary_page(c, summary_data, shipment_date_display, font_name)
        
        # 出荷一覧表の後に改ページ（ラベルページと分離）
        c.showPage()
        
        # Cut and Stack形式に再配置
        rearranged_labels = self._rearrange_labels_for_cut_and_stack(labels)
        total_labels = len(labels)
        total_pages = (total_labels + self.LABELS_PER_PAGE - 1) // self.LABELS_PER_PAGE
        
        # スロット順序: 左上(0) → 右上(1) → 左2段目(2) → 右2段目(3) → ... → 右4段目(7)
        slot_to_pos = [
            (0, 0),  # スロット0: 左上
            (1, 0),  # スロット1: 右上
            (0, 1),  # スロット2: 左2段目
            (1, 1),  # スロット3: 右2段目
            (0, 2),  # スロット4: 左3段目
            (1, 2),  # スロット5: 右3段目
            (0, 3),  # スロット6: 左4段目
            (1, 3),  # スロット7: 右4段目
        ]
        
        # 各ページを描画
        for page_idx in range(total_pages):
            if page_idx > 0:  # 2ページ目以降は改ページ
                c.showPage()
            
            # このページの各スロットを描画
            for slot in range(self.LABELS_PER_PAGE):
                # 再配置後のインデックス: ページpage_idxのスロットslotの位置
                rearranged_idx = page_idx * self.LABELS_PER_PAGE + slot
                
                # 空のスロットはスキップ（エラーを防ぐ）
                if rearranged_idx >= len(rearranged_labels):
                    continue
                
                label = rearranged_labels[rearranged_idx]
                
                # 空の辞書の場合はスキップ
                if not label or not label.get('store'):
                    continue
                
                # スロット位置から列・行を取得
                col, row = slot_to_pos[slot]
                
                # 座標計算
                x = col * self.LABEL_WIDTH
                y = self.A4_HEIGHT - (row + 1) * self.LABEL_HEIGHT
                
                # 端数ラベルの判定を改善（is_fractionフラグまたはquantityが満杯でない場合）
                is_fraction = label.get('is_fraction', False)
                if not is_fraction:
                    # sequenceが「X/X」形式（最後の箱）の場合も端数と判定
                    sequence = label.get('sequence', '')
                    if '/' in sequence:
                        parts = sequence.split('/')
                        if len(parts) == 2:
                            try:
                                current = int(parts[0])
                                total = int(parts[1])
                                if current == total and total > 1:
                                    is_fraction = True
                            except ValueError:
                                pass
                
                # ラベルを描画
                if is_fraction:
                    self._draw_fraction_label(c, x, y, label, font_name)
                else:
                    self._draw_standard_label(c, x, y, label, font_name)
                
                # 切断用ガイド線（再配置後のインデックスを使用）
                # 最後のラベルかどうかは、再配置後のインデックスとtotal_labelsで判定
                is_last_label = (rearranged_idx >= total_labels - 1)
                self._draw_guide_lines(c, x, y, col, row, rearranged_idx, total_labels, is_last_label)
        
        c.save()
    
    def _draw_summary_page(self, c: canvas.Canvas, summary_data: List[Dict], 
                          shipment_date: str, font_name: str):
        """出荷一覧表ページを描画（TableオブジェクトとTableStyleを使用）"""
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import Paragraph
        
        # フォントサイズを調整（A4一枚に確実に収まるように最適化）
        title_font_size = 26
        header_font_size = 16
        data_font_size = 14
        summary_title_font_size = 17
        summary_data_font_size = 14
        
        # タイトル（上マージン最小限に）
        c.setFont(font_name, title_font_size)
        c.drawString(10 * mm, self.A4_HEIGHT - 22 * mm, f"【出荷一覧表】 {shipment_date}")
        
        # テーブルデータの準備
        table_data = []
        # ヘッダー行
        header_row = ["店舗名", "品目", "フル箱", "端数箱", "総数"]
        table_data.append(header_row)
        
        # データ行（品目列は品目+荷姿の表示名を使用＝マスターで管理した判別しやすい名称）
        for entry in summary_data:
            store = str(entry.get('store', ''))
            item_display = str(entry.get('item_display', entry.get('item', '')))
            boxes = str(entry.get('boxes', 0))
            rem_box = str(entry.get('rem_box', 0))
            total_quantity = entry.get('total_quantity', 0)
            unit_label = entry.get('unit_label', '')
            total_display = f"{total_quantity}{unit_label}" if total_quantity > 0 and unit_label else str(total_quantity)
            table_data.append([store, item_display, boxes, rem_box, total_display])
        
        # テーブルの列幅を設定（mm単位）- A4幅（210mm）に収まるように調整
        # 左右マージン10mmずつ = 20mm、テーブル幅は190mm以内に収める
        col_widths = [42 * mm, 52 * mm, 30 * mm, 30 * mm, 36 * mm]  # 合計190mm
        # 行の高さを調整（A4一枚に確実に収まるように）
        row_height = 15 * mm
        
        # Tableオブジェクトを作成
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        
        # TableStyleを設定（視認性を最大化）
        table_style = TableStyle([
            # グリッド線（全体）- 太めの線で見やすく
            ('GRID', (0, 0), (-1, -1), 1.0, HexColor('#666666')),  # 濃いグレーで太めの線
            
            # ヘッダー行のスタイル（1行目、インデックス0）
            ('BACKGROUND', (0, 0), (-1, 0), HexColor('#C0C0C0')),  # より濃い灰色の背景で視認性向上
            ('TEXTCOLOR', (0, 0), (-1, 0), black),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),  # 中央揃え
            ('FONTNAME', (0, 0), (-1, 0), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), header_font_size),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),
            
            # データ行のスタイル
            ('FONTNAME', (0, 1), (-1, -1), font_name),
            ('FONTSIZE', (0, 1), (-1, -1), data_font_size),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [white, HexColor('#F0F0F0')]),  # 1行おきに色を変える（白と薄い灰色、コントラスト向上）
            
            # 行の高さとパディング（A4一枚に確実に収まるように最適化）
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ])
        
        table.setStyle(table_style)
        
        # テーブルのサイズを計算
        table_width, table_height = table.wrap(0, 0)
        
        # テーブルを描画する位置を計算（左右マージン10mm）
        table_x = 10 * mm
        table_y = self.A4_HEIGHT - 48 * mm
        
        # テーブルを描画
        table.drawOn(c, table_x, table_y - table_height)
        
        # 品目ごとの総数セクション用のY座標を更新
        current_y = table_y - table_height - 10 * mm
        
        # 品目ごとの総数セクションを追加
        # テーブルの下に余白を確保（A4一枚に収まるように調整）
        summary_start_y = current_y - 8 * mm
        
        # 品目ごとに集計
        from collections import defaultdict
        item_totals = defaultdict(int)
        item_units = {}
        
        for entry in summary_data:
            item = entry.get('item', '')
            spec = entry.get('spec', '').strip()
            total_quantity = entry.get('total_quantity', 0)
            unit_label = entry.get('unit_label', '')
            
            # キーをitemとspecの組み合わせにする（胡瓜の3本Pとバラを別物として扱う）
            key = (item, spec)
            item_totals[key] += total_quantity
            item_units[key] = unit_label
        
        # 品目ごとの総数セクションのタイトル
        c.setFont(font_name, summary_title_font_size)
        summary_title = f"【{shipment_date} 出荷・作成総数】"
        c.drawString(10 * mm, summary_start_y, summary_title)
        
        # 品目ごとの総数を2列で表示（左半分・右半分に分割）
        summary_y_base = summary_start_y - 14 * mm
        row_height = 13 * mm  # 1行あたりの高さ
        left_x = 10 * mm
        right_x = self.A4_WIDTH / 2 + 12 * mm  # 右列は用紙中央 + 余白
        
        c.setFont(font_name, summary_data_font_size)
        
        # キーをソート（品目名→規格の順）
        sorted_items = sorted(item_totals.items(), key=lambda x: (x[0][0], x[0][1]))
        n = len(sorted_items)
        mid = (n + 1) // 2  # 左列に1つ多くする場合: 0〜mid-1 が左、mid〜n-1 が右
        left_items = sorted_items[:mid]
        right_items = sorted_items[mid:]
        
        # 左列を描画（品目表示名＝品目+荷姿で統一）
        left_y = summary_y_base
        for (item, spec), total in left_items:
            unit_label = item_units.get((item, spec), '')
            display_name = f"{item} {spec}".strip() if spec else item
            summary_text = f"・{display_name}：{total}{unit_label}"
            c.drawString(left_x, left_y, summary_text)
            left_y -= row_height
        
        # 右列を描画
        right_y = summary_y_base
        for (item, spec), total in right_items:
            unit_label = item_units.get((item, spec), '')
            display_name = f"{item} {spec}".strip() if spec else item
            summary_text = f"・{display_name}：{total}{unit_label}"
            c.drawString(right_x, right_y, summary_text)
            right_y -= row_height
    
    def _draw_text_in_quadrant(self, c: canvas.Canvas, text: str, font_name: str, 
                               max_font_size: int, quadrant_width: float, 
                               quadrant_height: float) -> tuple:
        """
        指定された領域内に収まるようにフォントサイズを自動調整してテキストを描画
        
        Returns:
            (font_size, text_width, text_height) のタプル
        """
        font_size = max_font_size
        text_width = c.stringWidth(text, font_name, font_size)
        text_height = font_size * 0.7  # フォント高さの概算
        
        # 領域内に収まるまでフォントサイズを縮小
        while (text_width > quadrant_width * 0.9 or 
               text_height > quadrant_height * 0.9) and font_size > 8:
            font_size -= 1
            text_width = c.stringWidth(text, font_name, font_size)
            text_height = font_size * 0.7
        
        return font_size, text_width, text_height
    
    def _draw_standard_label(self, c: canvas.Canvas, x: float, y: float, 
                            label: Dict, font_name: str):
        """通常ラベルを描画（4つの領域に厳格に分割）"""
        # ラベル枠（薄い線）
        c.setStrokeColor(gray, alpha=0.3)
        c.setLineWidth(0.5)
        c.rect(x, y, self.LABEL_WIDTH, self.LABEL_HEIGHT, stroke=1, fill=0)
        
        # テキスト色を黒に
        c.setFillColor(black)
        
        # 4つの領域のサイズ
        q_width = self.LABEL_WIDTH / 2  # 52.5mm
        q_height = self.LABEL_HEIGHT / 2  # 37.125mm
        
        # Q1: 左上 - 目的地（店舗名）を最大サイズ（中央寄せ）
        store = label.get('store', '')
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, store, font_name, 50, q_width, q_height
        )
        c.setFont(font_name, font_size)
        q1_center_x = x + q_width / 2  # Q1の中央X座標
        q1_center_y = y + self.LABEL_HEIGHT - q_height / 2  # Q1の中央Y座標
        c.drawString(q1_center_x - text_width / 2, q1_center_y - text_height / 2, store)
        
        # Q2: 右上 - コンテナ数（通し番号）（中央寄せ）
        sequence = label.get('sequence', '')
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, sequence, font_name, 40, q_width, q_height
        )
        c.setFont(font_name, font_size)
        q2_center_x = x + self.LABEL_WIDTH - q_width / 2  # Q2の中央X座標
        q2_center_y = y + self.LABEL_HEIGHT - q_height / 2  # Q2の中央Y座標
        c.drawString(q2_center_x - text_width / 2, q2_center_y - text_height / 2, sequence)
        
        # Q3: 左下 - 品目（中央寄せ）
        item = label.get('item', '')
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, item, font_name, 50, q_width, q_height
        )
        c.setFont(font_name, font_size)
        q3_center_x = x + q_width / 2  # Q3の中央X座標
        q3_center_y = y + q_height / 2  # Q3の中央Y座標
        c.drawString(q3_center_x - text_width / 2, q3_center_y - text_height / 2, item)
        
        # Q4: 右下 - 入り数（中央寄せ）
        quantity = label.get('quantity', '')
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, quantity, font_name, 30, q_width, q_height
        )
        c.setFont(font_name, font_size)
        q4_center_x = x + self.LABEL_WIDTH - q_width / 2  # Q4の中央X座標
        q4_center_y = y + q_height / 2  # Q4の中央Y座標
        c.drawString(q4_center_x - text_width / 2, q4_center_y - text_height / 2, quantity)
        
        # 出荷日（ラベル水平中央、大きめの文字）
        shipment_date = label.get('shipment_date', '')
        if shipment_date:
            center_x = x + self.LABEL_WIDTH / 2
            date_y = y + 12  # 下端から12pt上
            c.setFont(font_name, 16)
            c.drawCentredString(center_x, date_y, shipment_date)
    
    def _draw_fraction_label(self, c: canvas.Canvas, x: float, y: float, 
                            label: Dict, font_name: str):
        """端数ラベル（最後の1箱）を描画（4つの領域、Q4に超巨大フォント、下部に二重線、！ウォーターマーク）"""
        # 「！」ウォーターマークを背景に描画（とても薄い灰色）
        c.saveState()
        c.setFillColor(gray, alpha=0.08)  # 非常に薄い灰色
        c.setFont(font_name, 120)  # 大きなフォントサイズ
        exclamation_width = c.stringWidth('！', font_name, 120)
        exclamation_x = x + (self.LABEL_WIDTH - exclamation_width) / 2
        exclamation_y = y + (self.LABEL_HEIGHT - 120 * 0.7) / 2
        c.drawString(exclamation_x, exclamation_y, '！')
        c.restoreState()
        
        # 太い黒の破線枠（端数ラベル）
        c.setStrokeColor(black)
        c.setLineWidth(4)  # 太めの破線
        c.setDash([12, 6])  # 破線パターン（長めの破線）
        c.rect(x + 3, y + 3, self.LABEL_WIDTH - 6, self.LABEL_HEIGHT - 6, 
              stroke=1, fill=0)
        c.setDash()  # 破線をリセット
        
        # 下部に太い二重線を描画
        c.setStrokeColor(black)
        c.setLineWidth(2)
        line_y = y + self.LABEL_HEIGHT / 2  # 中央の横線
        c.line(x + 5, line_y, x + self.LABEL_WIDTH - 5, line_y)
        c.setLineWidth(1.5)
        c.line(x + 5, line_y - 1, x + self.LABEL_WIDTH - 5, line_y - 1)
        
        # テキスト色を黒に
        c.setFillColor(black)
        
        # 4つの領域のサイズ
        q_width = self.LABEL_WIDTH / 2  # 52.5mm
        q_height = self.LABEL_HEIGHT / 2  # 37.125mm
        
        # Q1: 左上 - 目的地（店舗名）を最大サイズ（中央寄せ）
        store = label.get('store', '')
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, store, font_name, 50, q_width, q_height
        )
        c.setFont(font_name, font_size)
        q1_center_x = x + q_width / 2  # Q1の中央X座標
        q1_center_y = y + self.LABEL_HEIGHT - q_height / 2  # Q1の中央Y座標
        c.drawString(q1_center_x - text_width / 2, q1_center_y - text_height / 2, store)
        
        # Q2: 右上 - コンテナ数（通し番号）（中央寄せ）
        sequence = label.get('sequence', '')
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, sequence, font_name, 40, q_width, q_height
        )
        c.setFont(font_name, font_size)
        q2_center_x = x + self.LABEL_WIDTH - q_width / 2  # Q2の中央X座標
        q2_center_y = y + self.LABEL_HEIGHT - q_height / 2  # Q2の中央Y座標
        c.drawString(q2_center_x - text_width / 2, q2_center_y - text_height / 2, sequence)
        
        # Q3: 左下 - 品目（Q4と重ならないように幅を制限、中央寄せ）
        item = label.get('item', '')
        # Q4が超巨大フォントになるため、Q3の幅を制限（Q4のスペースを確保）
        q3_max_width = q_width * 0.8  # Q3の最大幅を80%に制限
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, item, font_name, 50, q3_max_width, q_height
        )
        c.setFont(font_name, font_size)
        q3_center_x = x + q3_max_width / 2  # Q3の中央X座標（制限された幅内）
        q3_center_y = y + q_height / 2  # Q3の中央Y座標
        c.drawString(q3_center_x - text_width / 2, q3_center_y - text_height / 2, item)
        
        # Q4: 右下 - 数量を超巨大フォント（Q3と重ならないように、中央寄せ）
        quantity = label.get('quantity', '')
        # Q4を大幅に拡張（Q3の右側のスペースも使用）
        q4_extended_width = self.LABEL_WIDTH - q3_max_width - 10  # Q3の右側まで使用
        q4_extended_height = q_height
        font_size, text_width, text_height = self._draw_text_in_quadrant(
            c, quantity, font_name, 60, q4_extended_width, q4_extended_height
        )
        c.setFont(font_name, font_size)
        q4_center_x = x + q3_max_width + 10 + q4_extended_width / 2  # Q4の中央X座標（拡張領域内）
        q4_center_y = y + q_height / 2  # Q4の中央Y座標
        c.drawString(q4_center_x - text_width / 2, q4_center_y - text_height / 2, quantity)
        
        # 出荷日（ラベル最下段・水平中央、太字で視認性最大化）
        shipment_date = label.get('shipment_date', '')
        if shipment_date:
            center_x = x + self.LABEL_WIDTH / 2
            date_y = y + 5 * mm  # ラベル下端から5mm上にどっしり配置
            date_font = self._get_font_name_bold()
            c.setFont(date_font, 22)  # ラベルに合わせて拡大
            c.drawCentredString(center_x, date_y, shipment_date)
    
    def _draw_guide_lines(self, c: canvas.Canvas, x: float, y: float, 
                         col: int, row: int, label_idx: int, total_labels: int, is_last_label: bool = False):
        """切断用ガイド線を描画（極めて薄いグレー、間隔の広い破線）"""
        c.setStrokeColor(gray, alpha=0.15)  # 極めて薄いグレー
        c.setLineWidth(0.3)
        c.setDash([20, 10])  # 間隔の広い破線
        
        # 右側の縦線（左列で、最後のラベルでない場合）
        if col == 0 and not is_last_label:
            c.line(x + self.LABEL_WIDTH, y, 
                  x + self.LABEL_WIDTH, y + self.LABEL_HEIGHT)
        
        # 下側の横線（最下段でない場合）
        if row < 3:
            c.line(x, y, x + self.LABEL_WIDTH, y)
        
        c.setDash()  # 破線をリセット
