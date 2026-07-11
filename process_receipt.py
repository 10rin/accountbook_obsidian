import os
import json
import time
import argparse
from datetime import datetime
from PIL import Image
from pydantic import BaseModel, Field
from typing import List
from google import genai
from google.genai import types
from pillow_heif import register_heif_opener
from watchdog.observers.polling import PollingObserver as Observer
from watchdog.events import FileSystemEventHandler

# .env ファイルから環境変数をロード
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# HEICファイルをPillowで直接開けるように登録
register_heif_opener()


# ==========================================
# 1. Pydanticスキーマ定義（APIレスポンス用 - RAWデータ）
# ==========================================
class RawItem(BaseModel):
    name: str = Field(description="品名・商品名。具体的な商標ではなく一般的な「ものの名前・一般名詞」に変換したもの。")
    unit_price: int = Field(description="レシートに印字されている、割引や税金が適用される前の単価（レシートの表示をそのまま読み取ること）。")
    quantity: int = Field(description="数量・個数。デフォルトは1。")
    discount: int = Field(description="この商品に直接適用された値引き・割引の総額（レシートの表示のまま）。値引き行は独立した商品とせず、対象商品に合算してください。", default=0)
    price: int = Field(description="割引適用後のこの商品の最終小計金額（レシートの表示のまま。基本的には (単価 * 数量) - 割引額）。")
    tax_rate: int = Field(description="この商品の消費税率（%）。食品・飲料は 8、お酒や日用品などは 10。", default=8)
    category: str = Field(description="商品のカテゴリ（中分類）。次のいずれかの分類のみを使用してください：'食費'、'嗜好品'、'日用品'、'美容'、'趣味'、'サブスク費'、'交通費'、'交際費'、'医療費'、'大学'、'その他'")
    subcategory: str = Field(description="商品のサブカテゴリ（小分類）。カテゴリが食費なら '自炊食材'、'外食'、'その他'。カテゴリが嗜好品なら 'お酒'、'タバコ'、'お菓子'。カテゴリが美容なら '被服'、'美容'。カテゴリが趣味なら '趣味'、'家具類'。それ以外なら 'その他'。")

class RawReceiptData(BaseModel):
    expense_class: str = Field(description="この支出全体の分類。サブスク費などは '固定費'。食費、嗜好品、日用品、美容、交通費、医療費、大学、その他などは '変動費'。交際費、趣味などは '特別費'。")
    date: str = Field(description="レシートの日付。YYYY-MM-DD形式。不明な場合は今日の年月日。")
    shop: str = Field(description="店舗名")
    total: int = Field(description="レシートの最終合計金額（支払合計金額、税込）")
    tax_8_total: int = Field(description="8%消費税対象の合計消費税額。記載がない場合は0。", default=0)
    tax_10_total: int = Field(description="10%消費税対象の合計消費税額。記載がない場合は0。", default=0)
    tax_type: str = Field(description="レシートの価格表示タイプ。商品価格が税抜き（外税）で印字されている場合は 'exclusive'、税込（内税）で印字されている場合は 'inclusive'。")
    pay_method: str = Field(description="支払い方法。必ず '現金'、'クレジットカード'、'PayPay'、'その他' のいずれか1つを選択してください。（デビットカードは 'クレジットカード'、交通系ICやiD、QUICPayなどは 'その他'）")
    items: List[RawItem] = Field(description="購入した商品のリスト。値引き情報は各商品の中に含め、独立した商品として扱わないでください。同じ商品は1つの項目にまとめ、数量(quantity)でカウントし、リスト内で重複させないでください。")

# ==========================================
# 2. 最終出力用スキーマ（税込計算後）
# ==========================================
class Item(BaseModel):
    name: str
    unit_price: int  # 税込
    quantity: int
    discount: int    # 税込値引き
    price: int       # 税込小計
    tax_rate: int
    category: str
    subcategory: str

class ReceiptData(BaseModel):
    expense_class: str
    date: str
    shop: str
    total: int
    tax_8_total: int
    tax_10_total: int
    pay_method: str
    items: List[Item]

# -----------------
# ディレクトリ設定
# -----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 監視対象を iCloud Drive 内の receipts フォルダに設定
RECEIPTS_DIR = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs/receipts")
DATA_DIR = os.path.join(BASE_DIR, "data")

def init_dirs():
    os.makedirs(RECEIPTS_DIR, exist_ok=True)
    os.makedirs(DATA_DIR, exist_ok=True)

# -----------------
# 3. Gemini API処理
# -----------------
def analyze_receipt(image_path: str) -> RawReceiptData:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY が設定されていません。プロジェクトルートの .env ファイル、または環境変数に設定してください。")

    client = genai.Client(api_key=api_key)
    image = Image.open(image_path)
    
    prompt = """
    このレシート画像を詳細に分析し、情報を正確に抽出してください。
    【重要】計算の辻褄を合わせるために、実際のレシートに印字されている数字を捏造したり変更したりしないでください。
    印字されている「文字通りの数字」をそのままOCR抽出することに集中してください。
    
    1. **支出区分（expense_class）の判定**:
       - レシート全体の支出の性質に基づいて、以下のいずれかに分類してください。
         - '固定費': 定期サブスクリプション（Netflix、Spotifyなど）など。
         - '変動費': 日々の生活費（食費、嗜好品、日用品、美容、交通費、医療費、大学費、その他の一時的な支払い）。
         - '特別費': 突発的な支出や趣味への大きな出費（プレゼント代、冠婚葬祭、旅行、映画やイベントの参加費、趣味の道具、家具の購入など）。

    2. **商品名の一般化（ものの名前への変換・最重要）と価格 of 対応関係**:
       - 商品名は、レシートに印字されている具体的な商標、メーカー名、ブランド名、型番などをそのまま使用するのではなく、一般的な「ものの名前・一般名詞」に変換して抽出してください。
       - (例: 「ブラックニッカ」 ➔ 「ウイスキー」、「助六寿司(彩)」 ➔ 「寿司」、「ただの炭酸水」 ➔ 「炭酸水」、「アサヒスーパードライ」 ➔ 「ビール」、「明治おいしい牛乳」 ➔ 「牛乳」、「コカ・コーラ 500ml」 ➔ 「コーラ」、「ネピア 鼻セレブ」 ➔ 「ティッシュ」 など)
       - 【重要】物品の購入に限らず、レシートや領収書に印字されている「調剤一部負担金」「調剤料」「技術料」「管理料」「診察代」「サービス料」などのサービス費や手数料、諸経費などの項目も、すべて漏れなく商品（item）として抽出してください。
       - レシートの縦・横の並びを正しく認識し、商品名（一般化されたもの）と金額のズレを防いでください。
       - 「ブラックニッカ（一般名: ウイスキー）」の横に「¥808」とある場合、一般化された商品名は「ウイスキー」、単価は「808」、数量「1」、小計「808」となります。他の行の数値（例えば他の商品の398など）と混同しないでください。
    3. **割引・値引きの処理**:
       - 商品名の下に「値引 -160」や「割引き」といった記述がある場合、その直前の商品に紐付けてください。
       - 値引き額（discount）には、印字された値引き額を正の整数（例: 160）で格納し、priceには値引き適用後の小計金額（税抜の場合は税抜の小計、例: 398 - 160 = 238）を格納してください。
       - 値引き自体を別商品としてリストに追加してはいけません。必ず対象の商品データにマージしてください。
    4. **消費税率の判定**:
       - 食料品や飲料（炭酸水、寿司など）は 「8%」。
       - お酒（ウイスキー、ブラックニッカ、ビール等）や、日用品、レジ袋などは 「10%」。
    5. **表示形式（tax_type）の判定ルール（最重要）**:
       - 商品行の金額（price）の合計（例: 116 + 808 + 238 = 1162）が、最終合計金額（total: 1270）より小さく、その差額が消費税額の合計（例: 28 + 80 = 108）と一致する場合、商品行の価格は**税抜**です。この場合、`tax_type` は必ず `'exclusive'` に設定してください。
       - 商品行の金額の合計が、そのまま最終合計金額（total）と一致する場合は、商品行の価格は**税込**です。この場合、`tax_type` は `'inclusive'` に設定してください。
    6. **支払い方法の判定**:
       - レシートの下部に印字されている決済手段を読み取り、必ず '現金'、'クレジットカード'、'PayPay'、'その他' の4つの中から最も適切なものを1つだけ選択してください。
       - 'visa debit' や 'デビットカード' などの記述はすべて 'クレジットカード' に統一してください。
       - 交通系IC、iD、QUICPay、各種タッチ決済、バーコード決済（PayPayを除く）などはすべて 'その他' と判定してください。
    7. **サブカテゴリ分類の制限（最重要）**:
       - サブカテゴリ（subcategory）は、カテゴリに応じて以下の選択肢から最も適切なものを選択してください：
         - `食費` ➔ '自炊食材' (食材全般、肉、魚、野菜、調味料、パン、麺類、お米、惣菜、お弁当、テイクアウトなど)、'外食' (レストラン等での外食代、カフェ代など)、'その他'。
         - `嗜好品` ➔ 'お酒' (ビール、ハイボール、ワイン、日本酒などのアルコール類全般)、'タバコ' (タバコ、加熱式タバコなど)、'お菓子' (お菓子、スイーツ、ジュースなど)、'その他'。
         - `美容` ➔ '被服' (洋服、靴、アクセサリー、クリーニング代など)、'美容' (化粧品、理美容院代など)。
         - `趣味` ➔ '趣味' (映画、趣味の道具、イベント参加費、旅行など)、'家具類' (ラック、棚、椅子、テーブルなど)。
         - `日用品` ➔ 'その他'。
         - `サブスク費` ➔ 'その他'。
         - `交通費` ➔ 'その他'。
         - `交際費` ➔ 'その他'。
         - `医療費` ➔ 'その他'。
         - `大学` ➔ 'その他'。
         - `その他` ➔ 'その他'。
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[image, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RawReceiptData,
        ),
    )
    
    data_dict = json.loads(response.text)
    return RawReceiptData(**data_dict)

# ==========================================
# 4. カテゴリ・サブカテゴリのクレンジング (Python側補正)
# ==========================================
CAT_CLEAN_MAP = {
    "食品類": "食費", "飲料": "食費", "酒類": "嗜好品", "惣菜": "食費", "パン": "食費", "麺類": "食費",
    "レトルト食品": "食費", "冷凍食品": "食費", "インスタント食品": "食費", "牛乳": "食費", "肉": "食費",
    "野菜": "食費", "果物": "食費", "乳製品": "食費", "調味料": "食費", "日用品": "日用品",
    "日用品費": "日用品", "消耗品": "日用品", "日用消耗品": "日用品", "美容健康": "美容",
    "被服・美容費": "美容", "衣類": "美容", "教養娯楽": "趣味", "交際・娯楽費": "趣味",
    "交際・娯楽": "趣味", "医療・健康費": "医療費", "医療費": "医療費", "交際費": "交際費",
    "趣味": "趣味", "食費": "食費", "嗜好品": "嗜好品", "その他": "その他",
    "住居費": "住居費", "水道光熱費": "水道光熱費", "通信費": "通信費", "保険料": "保険料",
    "サブスク費": "サブスク費", "交通費": "交通費", "大学": "大学"
}

def clean_category_and_subcategory(cat: str, sub: str, item_name: str) -> tuple[str, str]:
    c = str(cat).strip().replace('"', '').replace("'", "")
    s = str(sub).strip().replace('"', '').replace("'", "")
    name_lower = str(item_name).lower()
    
    new_c = CAT_CLEAN_MAP.get(c, "その他")
    
    if "たばこ" in name_lower or "タバコ" in name_lower or "iqos" in name_lower or "アイコス" in name_lower:
        new_c = "嗜好品"
    elif "酒" in name_lower or "ビール" in name_lower or "ハイボール" in name_lower:
        new_c = "嗜好品"
        
    new_s = "その他"
    if new_c == "食費":
        # 惣菜、お弁当、弁当、テイクアウトなどは「自炊食材」に分類する
        if s in ("外食", "外食(カフェ代など)", "カフェ", "カフェ利用") or "外食" in name_lower or "カフェ" in name_lower:
            new_s = "外食"
        else:
            new_s = "自炊食材"
    elif new_c == "嗜好品":
        if "酒" in name_lower or "ビール" in name_lower or "ハイボール" in name_lower or s in ("酒類", "お酒"):
            new_s = "お酒"
        elif "タバコ" in name_lower or "たばこ" in name_lower or "iqos" in name_lower or "アイコス" in name_lower or s == "タバコ":
            new_s = "タバコ"
        else:
            new_s = "お菓子"
    elif new_c == "美容":
        if s in ("衣類", "靴", "被服") or "服" in name_lower or "シャツ" in name_lower or "靴" in name_lower:
            new_s = "被服"
        else:
            new_s = "美容"
    elif new_c == "趣味":
        if "家具" in name_lower or "ラック" in name_lower or "スチールラック" in name_lower or "椅子" in name_lower or "テーブル" in name_lower or s == "家具類":
            new_s = "家具類"
        else:
            new_s = "趣味"
            
    return new_c, new_s

# ==========================================
# 5. 税込計算および端数調整処理（Python側）
# ==========================================
def calculate_tax_inclusive(raw: RawReceiptData) -> ReceiptData:
    processed_items = []
    
    for item in raw.items:
        rate = 1.08 if item.tax_rate == 8 else 1.10
        
        if raw.tax_type == "exclusive":
            # 外税表示の場合は、Pythonで税込を計算する (端数切り捨て)
            tax_unit_price = int(item.unit_price * rate)
            tax_discount = int(item.discount * rate)
            tax_price = int(item.price * rate)
        else:
            # 内税表示の場合は、すでに税込なのでそのまま使用
            tax_unit_price = item.unit_price
            tax_discount = item.discount
            tax_price = item.price
            
        clean_cat, clean_sub = clean_category_and_subcategory(item.category, item.subcategory, item.name)
        processed_items.append(Item(
            name=item.name,
            unit_price=tax_unit_price,
            quantity=item.quantity,
            discount=tax_discount,
            price=tax_price,
            tax_rate=item.tax_rate,
            category=clean_cat,
            subcategory=clean_sub
        ))
        
    # 全商品の税込金額の合計と、支払合計金額（total）を比較する
    calculated_total = sum(item.price for item in processed_items)
    diff = raw.total - calculated_total
    
    # 1円単位の端数ズレがある場合、最も金額の高い商品の価格を調整して合計を一致させる
    if diff != 0 and processed_items:
        highest_item = max(processed_items, key=lambda x: x.price)
        highest_item.price += diff
        
    return ReceiptData(
        expense_class=raw.expense_class,
        date=raw.date,
        shop=raw.shop,
        total=raw.total,
        tax_8_total=raw.tax_8_total,
        tax_10_total=raw.tax_10_total,
        pay_method=raw.pay_method,
        items=processed_items
    )

# -----------------
# 5. Markdownファイル保存
# -----------------
def save_as_markdown(data: ReceiptData, original_filename: str):
    timestamp = datetime.now().strftime("%H%M%S")
    clean_shop = "".join(c for c in data.shop if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    if not clean_shop:
        clean_shop = "unknown"
        
    filename = f"{data.date}_{clean_shop}_{timestamp}.md"
    file_path = os.path.join(DATA_DIR, filename)

    # yaml形式のitemsリストを作成
    items_yaml = ""
    for item in data.items:
        items_yaml += f"  - name: \"{item.name}\"\n"
        items_yaml += f"    unit_price: {item.unit_price}\n"
        items_yaml += f"    quantity: {item.quantity}\n"
        items_yaml += f"    discount: {item.discount}\n"
        items_yaml += f"    price: {item.price}\n"
        items_yaml += f"    tax_rate: {item.tax_rate}\n"
        items_yaml += f"    category: \"{item.category}\"\n"
        items_yaml += f"    subcategory: \"{item.subcategory}\"\n"

    content = f"""---
type: receipt
date: {data.date}
shop: "{data.shop}"
total: {data.total}
tax_8_total: {data.tax_8_total}
tax_10_total: {data.tax_10_total}
pay_method: "{data.pay_method}"
original_file: "{original_filename}"
items:
{items_yaml}---

# 🧾 レシート詳細: {data.shop} ({data.date})

- **店舗名**: {data.shop}
- **日付**: {data.date}
- **合計金額**: ¥{data.total:,} (内、消費税8%: ¥{data.tax_8_total:,} / 10%: ¥{data.tax_10_total:,})
- **支払い方法**: {data.pay_method}

## 購入商品一覧 (税込表記)
| 商品名 | 税込単価 | 数量 | 税込割引 | 税込金額 | 税率 | カテゴリ | サブカテゴリ |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- | :--- |
"""
    for item in data.items:
        content += f"| {item.name} | ¥{item.unit_price:,} | {item.quantity} | ¥{item.discount:,} | ¥{item.price:,} | {item.tax_rate}% | {item.category} | {item.subcategory} |\n"
        
    content += f"\n---\n*元画像: {original_filename}*"

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Markdown保存完了: {file_path}")

# -----------------
# 6. ヘルパー・個別処理・監視処理
# -----------------
def process_json_file(src_path: str):
    with open(src_path, "r", encoding="utf-8") as file:
        data_dict = json.load(file)
        
    entry_type = data_dict.get("type")
    
    if entry_type == "receipt":
        total = int(data_dict.get("total", 0))
        category = data_dict.get("category", "その他")
        subcategory = data_dict.get("subcategory", "その他")
        expense_class = data_dict.get("expense_class", "変動費")
        pay_method = data_dict.get("pay_method", "現金")
        if pay_method.lower() in ("visa debit", "visaデビット", "debit", "デビット", "デビットカード"):
            pay_method = "クレジットカード"
        
        clean_cat, clean_sub = clean_category_and_subcategory(category, subcategory, "手入力支出")
        item = Item(
            name="手入力支出",
            unit_price=total,
            quantity=1,
            discount=0,
            price=total,
            tax_rate=10,
            category=clean_cat,
            subcategory=clean_sub
        )
        
        data = ReceiptData(
            expense_class=expense_class,
            date=data_dict.get("date", datetime.now().strftime("%Y-%m-%d")),
            shop=data_dict.get("shop", "other"),
            total=total,
            tax_8_total=0,
            tax_10_total=0,
            pay_method=pay_method,
            items=[item]
        )
        
        # 保存時の original_filename として "manual_input" を渡す
        save_as_markdown(data, "manual_input")
        print(f"手入力支出をMarkdownとして保存しました: {data.shop} (¥{total})")
        
    elif entry_type == "income":
        date = data_dict.get("date", datetime.now().strftime("%Y-%m-%d"))
        amount = int(data_dict.get("amount", 0))
        source = data_dict.get("source", "その他")
        
        timestamp = datetime.now().strftime("%H%M%S")
        filename = f"income_{date}_{timestamp}.md"
        file_path = os.path.join(DATA_DIR, filename)
        
        content = f"""---
type: income
date: {date}
amount: {amount}
source: "{source}"
---

# 入金: {source} (¥{amount:,})
- **日付**: {date}
- **金額**: ¥{amount:,}
- **入金元**: {source}
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"手入力収入をMarkdownとして保存しました: {source} (¥{amount})")
        
    else:
        print(f"警告: 未知のエントリタイプです ({entry_type})")

def process_single_file(src_path: str):
    f = os.path.basename(src_path)
    try:
        # JSONファイル（手入力データ）の場合の処理
        if f.lower().endswith(".json"):
            process_json_file(src_path)
            os.remove(src_path)
            print(f"手入力JSONファイルを処理し、削除しました: {src_path}")
            return

        # 1. APIから税抜（Raw）のデータをそのままOCR抽出
        raw_data = analyze_receipt(src_path)
        
        # 2. Python側で税込価格の計算と端数調整を実施
        data = calculate_tax_inclusive(raw_data)
        
        # 3. 保存
        save_as_markdown(data, f)
        
        # 4. 解析成功した画像の消去（移動ではなく削除）
        os.remove(src_path)
        print(f"解析成功した元画像を削除しました: {src_path}")
        
    except Exception as e:
        print(f"エラーが発生しました ({f}): {e}")

def wait_for_file_stable(filepath: str, delay: float = 1.0, timeout: float = 10.0) -> bool:
    """ファイルが完全に書き込まれる（ファイルサイズが変化しなくなる）のを待つ"""
    last_size = -1
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            if not os.path.exists(filepath):
                return False
            current_size = os.path.getsize(filepath)
            if current_size == last_size and current_size > 0:
                return True
            last_size = current_size
        except OSError:
            pass
        time.sleep(delay)
    return False
# 処理中ファイルの重複防止用キャッシュ
processing_files = set()

class ReceiptWatchHandler(FileSystemEventHandler):
    def on_created(self, event):
        self._process_event(event)

    def on_moved(self, event):
        self._process_event(event)

    def on_modified(self, event):
        self._process_event(event)

    def _process_event(self, event):
        if event.is_directory:
            return
        
        # 移動イベント (dest_path がある) の場合は dest_path、それ以外は src_path
        src_path = getattr(event, 'dest_path', event.src_path)
        valid_extensions = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".json")
        if src_path.lower().endswith(valid_extensions):
            if src_path in processing_files:
                return
            processing_files.add(src_path)
            try:
                print(f"\n[新規ファイル/変更を検知] 処理待ち: {os.path.basename(src_path)}")
                # 同期中などによる不完全なファイル書き込みを待つ
                if wait_for_file_stable(src_path):
                    # 念のためファイル書き込み完了後に少し余裕を持たせる
                    time.sleep(0.5)
                    process_single_file(src_path)
                else:
                    print(f"警告: ファイル書き込みがタイムアウトしました。処理をスキップします: {src_path}")
            finally:
                if src_path in processing_files:
                    processing_files.remove(src_path)

def run_once():
    valid_extensions = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".json")
    files = [f for f in os.listdir(RECEIPTS_DIR) if os.path.isfile(os.path.join(RECEIPTS_DIR, f)) and f.lower().endswith(valid_extensions)]
    
    if not files:
        return
        
    print(f"{len(files)} 件の未処理レシート画像を検出しました。一括処理を開始します...")
    for f in files:
        src_path = os.path.join(RECEIPTS_DIR, f)
        print(f"\n--- 処理中: {f} ---")
        process_single_file(src_path)

def watch_receipts():
    # 起動時にすでにフォルダ内にある未処理ファイルを一括処理する
    run_once()
    
    print(f"\n👀 レシートフォルダの常時監視を開始しました (ネイティブ走査方式)...")
    print(f"監視対象: {RECEIPTS_DIR}")
    print("終了するには Ctrl+C を押してください。\n")
    
    valid_extensions = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".json")
    
    try:
        while True:
            try:
                files = [f for f in os.listdir(RECEIPTS_DIR) if os.path.isfile(os.path.join(RECEIPTS_DIR, f)) and f.lower().endswith(valid_extensions)]
            except Exception as e:
                print(f"フォルダ走査エラー: {e}")
                files = []
                
            for f in files:
                src_path = os.path.join(RECEIPTS_DIR, f)
                
                # 重複処理防止
                if src_path in processing_files:
                    continue
                    
                processing_files.add(src_path)
                try:
                    print(f"\n[新規ファイル/変更を検知] 処理待ち: {f}")
                    # 同期中などによる不完全なファイル書き込みを待つ
                    if wait_for_file_stable(src_path):
                        # 念のためファイル書き込み完了後に少し余裕を持たせる
                        time.sleep(0.5)
                        process_single_file(src_path)
                    else:
                        print(f"警告: ファイル書き込みがタイムアウトしました。処理をスキップします: {src_path}")
                finally:
                    if src_path in processing_files:
                        processing_files.remove(src_path)
            
            time.sleep(2.0)
            
    except KeyboardInterrupt:
        print("\n監視を停止しています...")

# -----------------
# 7. メイン処理
# -----------------
def main():
    parser = argparse.ArgumentParser(description="レシート画像解析スクリプト")
    parser.add_argument("--watch", action="store_true", help="フォルダを常時監視して自動で解析を実行する")
    args = parser.parse_args()
    
    init_dirs()
    
    if args.watch:
        watch_receipts()
    else:
        # 通常の一括処理モード
        valid_extensions = (".png", ".jpg", ".jpeg", ".webp", ".heic", ".json")
        files = [f for f in os.listdir(RECEIPTS_DIR) if os.path.isfile(os.path.join(RECEIPTS_DIR, f)) and f.lower().endswith(valid_extensions)]
        
        if not files:
            print("処理待ちのレシート画像が見つかりませんでした。")
            print(f"画像ファイルを {RECEIPTS_DIR} に配置して、スクリプトを再実行してください。")
            return

        print(f"{len(files)} 件のレシート画像を検出しました。処理を開始します...")
        for f in files:
            src_path = os.path.join(RECEIPTS_DIR, f)
            print(f"\n--- 処理中: {f} ---")
            process_single_file(src_path)

if __name__ == "__main__":
    main()
