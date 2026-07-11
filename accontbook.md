
```dataviewjs
const pages = dv.pages().where(p => p.type === 'receipt' && (p.file.folder === 'data' || p.file.folder.endsWith('/data')));
const incomes = dv.pages().where(p => p.type === 'income' && (p.file.folder === 'data' || p.file.folder.endsWith('/data')));
const currentMonth = new Date().toISOString().slice(0, 7); // YYYY-MM形式

// 今月のデータのみ抽出 (Luxon DateTime や文字列に安全に対応)
const getMonthStr = (dateVal) => {
    if (!dateVal) return "";
    if (typeof dateVal === 'string') return dateVal.slice(0, 7);
    if (dateVal.toFormat) return dateVal.toFormat("yyyy-MM");
    if (dateVal.toISOString) return dateVal.toISOString().slice(0, 7);
    return String(dateVal).slice(0, 7);
};

const thisMonthPages = pages.filter(p => p.date && getMonthStr(p.date) === currentMonth);
const thisMonthIncomes = incomes.filter(p => p.date && getMonthStr(p.date) === currentMonth);

// --- 1. データ集計 ---
// 当月サブカテゴリ別（支出）
const subcategoryMap = {};
const subToCatMap = {}; // サブカテゴリからカテゴリへのマッピング (明度カラー用)
const multiSubcatCategories = new Set(["食費", "嗜好品", "美容", "趣味"]);

const getSubcatDisplayName = (sub, cat) => {
    const s = String(sub || 'その他').trim();
    const c = String(cat || 'その他').trim();
    if (s === "その他" && !multiSubcatCategories.has(c)) {
        return c; // サブカテゴリがその他しかない場合はカテゴリ名を表示
    }
    return s;
};

for (const p of thisMonthPages) {
    if (p.items) {
        for (const item of p.items) {
            const cat = item.category || 'その他';
            const rawSub = item.subcategory || 'その他';
            const sub = getSubcatDisplayName(rawSub, cat);
            const price = parseInt(item.price) || 0;
            subcategoryMap[sub] = (subcategoryMap[sub] || 0) + price;
            subToCatMap[sub] = cat;
        }
    } else {
        const cat = p.category || 'その他';
        const rawSub = p.subcategory || 'その他';
        const sub = getSubcatDisplayName(rawSub, cat);
        const total = parseInt(p.total) || 0;
        subcategoryMap[sub] = (subcategoryMap[sub] || 0) + total;
        subToCatMap[sub] = cat;
    }
}

// 当月支払い方法別（支出）
const payMap = {};
for (const p of thisMonthPages) {
    let method = p.pay_method || '不明';
    if (method.toLowerCase() === 'visa debit' || method === 'Visa Debit') {
        method = 'クレジットカード';
    }
    const total = parseInt(p.total) || 0;
    payMap[method] = (payMap[method] || 0) + total;
}

// 過去すべての月別集計（収支推移用）
const monthlySpendMap = {};
const monthlyCatSpendMap = {}; // { YYYY-MM: { categoryName: total_price } }
for (const p of pages) {
    const m = getMonthStr(p.date);
    if (m) {
        monthlySpendMap[m] = (monthlySpendMap[m] || 0) + (parseInt(p.total) || 0);
        if (!monthlyCatSpendMap[m]) {
            monthlyCatSpendMap[m] = {};
        }
        if (p.items) {
            for (const item of p.items) {
                const cat = item.category || 'その他';
                const price = parseInt(item.price) || 0;
                monthlyCatSpendMap[m][cat] = (monthlyCatSpendMap[m][cat] || 0) + price;
            }
        } else {
            const cat = p.category || 'その他';
            const total = parseInt(p.total) || 0;
            monthlyCatSpendMap[m][cat] = (monthlyCatSpendMap[m][cat] || 0) + total;
        }
    }
}

const monthlyIncomeMap = {};
for (const p of incomes) {
    const m = getMonthStr(p.date);
    if (m) {
        monthlyIncomeMap[m] = (monthlyIncomeMap[m] || 0) + (parseInt(p.amount) || 0);
    }
}

const allMonthsSet = new Set([...Object.keys(monthlySpendMap), ...Object.keys(monthlyIncomeMap)]);
const sortedMonths = Array.from(allMonthsSet).sort();

// --- 2. HTMLレイアウト生成 ---
const containerEl = this.container;
containerEl.empty();

// 全体コンテナのスタイル設定 (Are.na風極限ミニマリズム)
containerEl.createEl("style", { text: `
    .notion-container { display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-start; }
    .notion-left-col { flex: 2.2; min-width: 320px; display: flex; flex-direction: column; gap: 20px; }
    .notion-right-col { flex: 1; min-width: 280px; display: flex; flex-direction: column; gap: 20px; }
    
    .dashboard-grid { display: flex; gap: 15px; flex-wrap: wrap; }
    
    .dashboard-card { 
        width: 100%;
        padding: 20px; 
        background: #ffffff; 
        border-radius: 0px; 
        border: 1px solid #cdcdcd; 
        color: #000000;
        box-shadow: none; 
        font-size: 0.85em; 
        box-sizing: border-box;
        transition: border-color 0.2s;
    }
    .dashboard-card:hover {
        border-color: #000000; 
    }
    
    .dashboard-card h3 {
        font-family: Menlo, Monaco, Consolas, "Courier New", monospace; 
        font-size: 0.95em;
        font-weight: 600;
        margin-top: 0;
        margin-bottom: 15px;
        color: #000000;
        border-bottom: 1px solid #cdcdcd;
        padding-bottom: 8px;
        letter-spacing: 0.8px;
    }
    
    .form-input {
        padding: 8px 12px; 
        border-radius: 0px; 
        border: 1px solid #cdcdcd; 
        background: #ffffff; 
        color: #000000;
        font-size: 0.85em;
        font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
        width: 100%;
        box-sizing: border-box;
        transition: border-color 0.2s;
    }
    .form-input:focus { 
        border-color: #F443C8; 
        outline: none; 
    }
    
    .btn-submit {
        padding: 8px 16px; 
        border-radius: 0px; 
        background: #000000; 
        border: 1px solid #000000;
        color: #ffffff; 
        cursor: pointer; 
        font-size: 0.85em;
        font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
        font-weight: 600;
        transition: background 0.2s, border-color 0.2s;
        width: 100%;
    }
    .btn-submit:hover { 
        background: #F443C8; 
        border-color: #F443C8;
        color: #ffffff;
    }
    
    .summary-item {
        text-align: left;
        padding: 10px 0;
        border-bottom: 1px dashed #cdcdcd; 
        font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
        color: #000000;
    }
    .summary-item:last-child {
        border-bottom: none;
    }
    .summary-label {
        font-size: 0.8em;
        color: #666666;
        margin-bottom: 4px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .summary-num { 
        font-size: 1.3em; 
        font-weight: 700; 
    }
    .summary-spend { color: #000000; } 
    .summary-income { color: #F443C8; } 
    .summary-balance { color: #000000; }
    
    .chart-container {
        position: relative;
        width: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    .chart-center-text {
        position: absolute;
        top: 42%;
        left: 50%;
        transform: translate(-50%, -50%);
        text-align: center;
        font-family: Menlo, Monaco, Consolas, "Courier New", monospace;
        pointer-events: none;
        z-index: 10;
    }
    .chart-center-label {
        font-size: 0.65em;
        color: #666666;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        margin-bottom: 2px;
    }
    .chart-center-val {
        font-size: 1.1em;
        font-weight: 700;
        color: #000000;
    }
` });

// 2カラムコンテナの作成
const mainContainer = containerEl.createEl("div", { attr: { class: "notion-container" } });
const leftCol = mainContainer.createEl("div", { attr: { class: "notion-left-col" } });
const rightCol = mainContainer.createEl("div", { attr: { class: "notion-right-col" } });

// --- 右カラム (サイドバー) ---
// 1. 今月の収支サマリーカード
const sumCard = rightCol.createEl("div", { attr: { class: "dashboard-card" } });
sumCard.createEl("h3", { text: "MONTH SUMMARY", attr: { style: "margin-top: 0;" } });
const sumContainer = sumCard.createEl("div", { attr: { style: "display: flex; flex-direction: column;" } });

const totalIncome = (() => {
    let sum = 0;
    for (const p of thisMonthIncomes) { sum += parseInt(p.amount) || 0; }
    return sum;
})();

const totalSpend = (() => {
    let sum = 0;
    for (const p of thisMonthPages) { sum += parseInt(p.total) || 0; }
    return sum;
})();

const balance = totalIncome - totalSpend;

const divInc = sumContainer.createEl("div", { attr: { class: "summary-item" } });
divInc.createEl("div", { text: "Total Incomes", attr: { class: "summary-label" } });
divInc.createEl("div", { text: `¥${totalIncome.toLocaleString()}`, attr: { class: "summary-num summary-income" } });

const divSpd = sumContainer.createEl("div", { attr: { class: "summary-item" } });
divSpd.createEl("div", { text: "Total Expenses", attr: { class: "summary-label" } });
divSpd.createEl("div", { text: `¥${totalSpend.toLocaleString()}`, attr: { class: "summary-num summary-spend" } });

const divBal = sumContainer.createEl("div", { attr: { class: "summary-item" } });
divBal.createEl("div", { text: "Balance", attr: { class: "summary-label" } });
divBal.createEl("div", { text: `¥${balance.toLocaleString()}`, attr: { class: `summary-num ${balance >= 0 ? 'summary-income' : 'summary-spend'}` } });


// 2. 入金フォームカード
const formCard = rightCol.createEl("div", { attr: { class: "dashboard-card" } });
formCard.createEl("h3", { text: "ADD INCOME", attr: { style: "margin-top: 0;" } });
const inputDiv = formCard.createEl("div", { attr: { style: "display: flex; flex-direction: column; gap: 10px;" } });

const row1 = inputDiv.createEl("div", { attr: { style: "display: flex; gap: 10px;" } });
const dateInput = row1.createEl("input", { attr: { type: "date", class: "form-input", style: "flex: 1;" } });
dateInput.value = new Date().toISOString().slice(0, 10);
const amountInput = row1.createEl("input", { attr: { type: "number", placeholder: "金額 (円)", class: "form-input", style: "flex: 1;" } });

const sourceInput = inputDiv.createEl("input", { attr: { type: "text", placeholder: "入金元 (給与、副収入など)", class: "form-input" } });
const submitBtn = inputDiv.createEl("button", { text: "SUBMIT", attr: { class: "btn-submit" } });

const msgEl = formCard.createEl("p", { attr: { style: "margin: 10px 0 0 0; font-family: Menlo, Monaco, Consolas, monospace; font-size: 0.85em; display: none;" } });

// 入金登録処理
submitBtn.onclick = async () => {
    const date = dateInput.value;
    const amount = parseInt(amountInput.value);
    const source = sourceInput.value.trim() || "その他";
    
    if (!date || isNaN(amount) || amount <= 0) {
        msgEl.setText("日付と正しい金額を入力してください。");
        msgEl.style.color = "var(--text-error)";
        msgEl.style.display = "block";
        return;
    }
    
    const currentFolder = dv.current().file.folder;
    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
    const fileName = currentFolder ? `${currentFolder}/data/income_${date}_${timestamp}.md` : `data/income_${date}_${timestamp}.md`;
    
    const fileContent = `---
type: income
date: ${date}
amount: ${amount}
source: "${source}"
---

# 入金: ${source} (¥${amount.toLocaleString()})
- **日付**: ${date}
- **金額**: ¥${amount.toLocaleString()}
- **入金元**: ${source}
`;

    try {
        await app.vault.create(fileName, fileContent);
        msgEl.setText(`登録完了: ${source} に ¥${amount.toLocaleString()} を登録しました。再ロードしてください。`);
        msgEl.style.color = "var(--text-success)";
        msgEl.style.display = "block";
        amountInput.value = "";
        sourceInput.value = "";
    } catch (e) {
        msgEl.setText(`登録エラー: ${e.message}`);
        msgEl.style.color = "var(--text-error)";
        msgEl.style.display = "block";
    }
};

// カテゴリと支払い方法の候補リストを収集
const allCategories = new Set(["食費", "嗜好品", "日用品", "美容", "趣味", "サブスク費", "交通費", "交際費", "医療費", "大学", "その他"]);
const allSubcategories = new Set(["自炊食材", "外食", "お酒", "タバコ", "お菓子", "被服", "美容", "趣味", "家具類", "その他"]);
const allPayMethods = new Set(["現金", "クレジットカード", "PayPay", "その他"]);

for (const p of pages) {
    if (p.items) {
        for (const item of p.items) {
            if (item.category) {
                const cat = String(item.category).trim();
                if (cat && !cat.includes("$") && !cat.includes("{") && !cat.includes('"')) {
                    allCategories.add(cat);
                }
            }
            if (item.subcategory) {
                const sub = String(item.subcategory).trim();
                if (sub && !sub.includes("$") && !sub.includes("{") && !sub.includes('"')) {
                    allSubcategories.add(sub);
                }
            }
        }
    }
}

// 3. 支出（出金）フォームカード
const expFormCard = rightCol.createEl("div", { attr: { class: "dashboard-card" } });
expFormCard.createEl("h3", { text: "ADD EXPENSE", attr: { style: "margin-top: 0;" } });
const expInputDiv = expFormCard.createEl("div", { attr: { style: "display: flex; flex-direction: column; gap: 10px;" } });

// 行1: 日付と金額
const expRow1 = expInputDiv.createEl("div", { attr: { style: "display: flex; gap: 10px;" } });
const expDateInput = expRow1.createEl("input", { attr: { type: "date", class: "form-input", style: "flex: 1;" } });
expDateInput.value = new Date().toISOString().slice(0, 10);
const expAmountInput = expRow1.createEl("input", { attr: { type: "number", placeholder: "金額 (円)", class: "form-input", style: "flex: 1;" } });

// 行2: 名称
const expNameInput = expInputDiv.createEl("input", { attr: { type: "text", placeholder: "名称 (例: スーパー、家賃、昼食など)", class: "form-input" } });

// Datalistの作成
const catDatalistId = "expense-categories-list";
const subcatDatalistId = "expense-subcategories-list";
const pmDatalistId = "expense-pay-methods-list";

const expCatDatalist = expFormCard.createEl("datalist", { attr: { id: catDatalistId } });
for (const cat of allCategories) {
    expCatDatalist.createEl("option", { attr: { value: cat } });
}

const expSubcatDatalist = expFormCard.createEl("datalist", { attr: { id: subcatDatalistId } });
for (const sub of allSubcategories) {
    expSubcatDatalist.createEl("option", { attr: { value: sub } });
}

const expPmDatalist = expFormCard.createEl("datalist", { attr: { id: pmDatalistId } });
for (const pm of allPayMethods) {
    expPmDatalist.createEl("option", { attr: { value: pm } });
}

// 行3: カテゴリとサブカテゴリ
const expRow2 = expInputDiv.createEl("div", { attr: { style: "display: flex; gap: 10px;" } });
const expCategoryInput = expRow2.createEl("input", { attr: { type: "text", placeholder: "カテゴリ", list: catDatalistId, class: "form-input", style: "flex: 1;" } });
const expSubcategoryInput = expRow2.createEl("input", { attr: { type: "text", placeholder: "サブカテゴリ", list: subcatDatalistId, class: "form-input", style: "flex: 1;" } });

// 行4: 支払い方法
const expPayMethodInput = expInputDiv.createEl("input", { attr: { type: "text", placeholder: "支払い方法", list: pmDatalistId, class: "form-input" } });

const expSubmitBtn = expInputDiv.createEl("button", { text: "SUBMIT", attr: { class: "btn-submit" } });
const expMsgEl = expFormCard.createEl("p", { attr: { style: "margin: 10px 0 0 0; font-family: Menlo, Monaco, Consolas, monospace; font-size: 0.85em; display: none;" } });

// カテゴリに連動するサブカテゴリの動的分岐ロジック
const categoryToSubcatMap = {
    "食費": ["自炊食材", "外食"],
    "嗜好品": ["お酒", "タバコ", "お菓子"],
    "美容": ["被服", "美容"],
    "趣味": ["趣味", "家具類"]
};

const updateSubcatOptions = () => {
    const cat = expCategoryInput.value.trim();
    expSubcatDatalist.empty();
    
    if (categoryToSubcatMap[cat]) {
        const subs = categoryToSubcatMap[cat];
        for (const sub of subs) {
            expSubcatDatalist.createEl("option", { attr: { value: sub } });
        }
        if (!subs.includes(expSubcategoryInput.value)) {
            expSubcategoryInput.value = "";
        }
        expSubcategoryInput.placeholder = "サブカテゴリを選択";
        expSubcategoryInput.disabled = false;
    } else {
        expSubcatDatalist.createEl("option", { attr: { value: "その他" } });
        if (cat === "") {
            expSubcategoryInput.value = "";
            expSubcategoryInput.placeholder = "サブカテゴリ";
            expSubcategoryInput.disabled = false;
        } else {
            expSubcategoryInput.value = "その他";
            expSubcategoryInput.placeholder = "自動決定: その他";
            expSubcategoryInput.disabled = true;
        }
    }
};

expCategoryInput.oninput = updateSubcatOptions;
expCategoryInput.onchange = updateSubcatOptions;

// 支出登録処理
expSubmitBtn.onclick = async () => {
    const date = expDateInput.value;
    const amount = parseInt(expAmountInput.value);
    const shop = expNameInput.value.trim() || "その他";
    const category = expCategoryInput.value.trim() || "その他";
    const subcategory = expSubcategoryInput.value.trim() || "その他";
    const payMethod = expPayMethodInput.value.trim() || "現金";
    
    if (!date || isNaN(amount) || amount <= 0) {
        expMsgEl.setText("日付と正しい金額を入力してください。");
        expMsgEl.style.color = "var(--text-error)";
        expMsgEl.style.display = "block";
        return;
    }
    
    const getExpenseClass = (cat) => {
        if (["サブスク費"].includes(cat)) return "固定費";
        if (["食費", "嗜好品", "日用品", "美容", "交通費", "医療費", "大学", "その他"].includes(cat)) return "変動費";
        if (["交際費", "趣味"].includes(cat)) return "特別費";
        return "変動費";
    };
    const expenseClass = getExpenseClass(category);
    
    const currentFolder = dv.current().file.folder;
    const timestamp = new Date().toISOString().replace(/[-:T]/g, '').slice(0, 14);
    const cleanShop = shop.replace(/[\\/:*?"<>|]/g, "_");
    const fileName = currentFolder ? `${currentFolder}/data/${date}_${cleanShop}_${timestamp}.md` : `data/${date}_${cleanShop}_${timestamp}.md`;
    
    const fileContent = `---
type: receipt
expense_class: "${expenseClass}"
date: ${date}
shop: "その他"
total: ${amount}
tax_8_total: 0
tax_10_total: 0
pay_method: "${payMethod}"
original_file: "manual_input"
items:
  - name: "${shop}"
    unit_price: ${amount}
    quantity: 1
    discount: 0
    price: ${amount}
    tax_rate: 10
    category: "${category}"
    subcategory: "${subcategory}"
---

# 支出手入力: ${shop} (¥${amount.toLocaleString()})
- **日付**: ${date}
- **名称**: ${shop}
- **合計金額**: ¥${amount.toLocaleString()}
- **支払い方法**: ${payMethod}
- **カテゴリ**: ${category}
- **サブカテゴリ**: ${subcategory}
`;

    try {
        await app.vault.create(fileName, fileContent);
        expMsgEl.setText(`登録完了: ${shop} に ¥${amount.toLocaleString()} を登録しました。再ロードしてください。`);
        expMsgEl.style.color = "var(--text-success)";
        expMsgEl.style.display = "block";
        expAmountInput.value = "";
        expNameInput.value = "";
        expCategoryInput.value = "";
        expSubcategoryInput.value = "";
        expSubcategoryInput.disabled = false;
        expSubcategoryInput.placeholder = "サブカテゴリ";
        expPayMethodInput.value = "";
    } catch (e) {
        expMsgEl.setText(`登録エラー: ${e.message}`);
        expMsgEl.style.color = "var(--text-error)";
        expMsgEl.style.display = "block";
    }
};


// --- 左カラム (メイン) ---
// 1. 中段：過去の収支推移 (棒グラフ - 履歴全体)
const historyCard = leftCol.createEl("div", { attr: { class: "dashboard-card" } });
historyCard.createEl("h3", { text: "REVENUE & EXPENSE HISTORY", attr: { style: "margin-top: 0;" } });

// 2. 下段グリッド (当月カテゴリ別割合 & 当月支払い方法別割合)
const bottomGrid = leftCol.createEl("div", { attr: { class: "dashboard-grid", style: "width: 100%; gap: 20px;" } });

const col1 = bottomGrid.createEl("div", { attr: { class: "dashboard-card", style: "flex: 1; min-width: 240px;" } });
col1.createEl("h3", { text: "EXPENSES BY SUBCATEGORY", attr: { style: "margin-top: 0;" } });

const col2 = bottomGrid.createEl("div", { attr: { class: "dashboard-card", style: "flex: 1; min-width: 240px;" } });
col2.createEl("h3", { text: "EXPENSES BY PAYMENT METHOD", attr: { style: "margin-top: 0;" } });

// --- 3. グラフ描画 (F443C8 / ブラック / ホワイト / cdcdcd テーマ) ---
const colors = [
    'rgba(244, 67, 200, 0.8)',   // アクセントカラー F443C8 (ピンク)
    'rgba(0, 0, 0, 0.85)',       // ブラック
    'rgba(100, 100, 100, 0.8)',  // ミディアムグレー
    'rgba(205, 205, 205, 0.8)',  // メインカラー cdcdcd (ライトグレー)
    'rgba(244, 67, 200, 0.4)',   // 薄ピンク
    'rgba(50, 50, 50, 0.8)',     // ダークグレー
    'rgba(150, 150, 150, 0.8)'   // グレー
];

// グラフ1: 過去の収支推移 (Stacked Bar Chart, 支出カテゴリ色分け)
const definedCategories = ["食費", "嗜好品", "日用品", "美容", "趣味", "サブスク費", "交通費", "交際費", "医療費", "大学", "その他"];
const categoryColorsMap = {
    "食費": "#F443C8",      // ピンク
    "嗜好品": "#7D1C4F",     // ディープマゼンタ
    "日用品": "#cdcdcd",     // ライトグレー
    "美容": "#61CBDE",      // スカイブルー
    "趣味": "#EFED59",      // イエロー
    "サブスク費": "#543F98",  // バイオレット
    "交通費": "#596C4E",    // オリーブグリーン
    "交際費": "#1D3057",    // ネイビー
    "医療費": "#818181",    // ミディアムグレー
    "大学": "#4FD57C",     // グリーン
    "その他": "#E4E5E4"     // ライトグレー
};

const historyDatasets = [];

// 1. 収入スタック (Income)
historyDatasets.push({
    label: '収入',
    data: sortedMonths.map(m => monthlyIncomeMap[m] || 0),
    backgroundColor: 'rgba(244, 67, 200, 0.35)', // 薄めのピンクで区別
    borderColor: '#F443C8',
    borderWidth: 1,
    stack: 'Income'
});

// 2. 支出スタック (Expense, カテゴリ積み上げ)
for (const cat of definedCategories) {
    const hasData = sortedMonths.some(m => (monthlyCatSpendMap[m] && monthlyCatSpendMap[m][cat]) > 0);
    if (hasData) {
        historyDatasets.push({
            label: cat,
            data: sortedMonths.map(m => (monthlyCatSpendMap[m] && monthlyCatSpendMap[m][cat]) || 0),
            backgroundColor: categoryColorsMap[cat] || '#b0b0b0',
            borderColor: categoryColorsMap[cat] || '#b0b0b0',
            borderWidth: 1,
            stack: 'Expense'
        });
    }
}

const historyChartData = {
    type: 'bar',
    data: {
        labels: sortedMonths,
        datasets: historyDatasets
    },
    options: {
        legend: { position: 'bottom' },
        responsive: true,
        maintainAspectRatio: false,
        scales: {
            xAxes: [{ stacked: true }],
            yAxes: [{ stacked: true }],
            x: { stacked: true },
            y: { stacked: true }
        }
    }
};

// グラフ2: サブカテゴリ別 (Doughnut) - 親カテゴリの色相をベースにした明度変更
const categoryHslBase = {
    "食費": { h: 315, s: 90 },       // ピンク
    "嗜好品": { h: 329, s: 63 },     // ディープマゼンタ
    "日用品": { h: 0, s: 0 },         // ライトグレー
    "美容": { h: 189, s: 69 },       // スカイブルー
    "趣味": { h: 61, s: 83 },        // イエロー
    "サブスク費": { h: 254, s: 42 },  // バイオレット
    "交通費": { h: 98, s: 16 },      // オリーブグリーン
    "交際費": { h: 220, s: 50 },     // ネイビー
    "医療費": { h: 0, s: 0 },         // ミディアムグレー
    "大学": { h: 140, s: 61 },       // グリーン
    "その他": { h: 0, s: 0 }          // ライトグレー
};

const getSubcatColor = (sub, parentCat) => {
    const base = categoryHslBase[parentCat] || { h: 0, s: 0 };
    let l = 60; // デフォルト明度
    
    if (parentCat === "食費") {
        if (sub === "自炊食材") l = 72; // 明るい
        else if (sub === "外食") l = 50; // 暗い
    } else if (parentCat === "嗜好品") {
        if (sub === "お酒") l = 45; // 明るめ
        else if (sub === "タバコ") l = 20; // 非常に暗い
        else if (sub === "お菓子") l = 33; // 中間
    } else if (parentCat === "美容") {
        if (sub === "被服") l = 70; // 明るい
        else if (sub === "美容") l = 50; // 暗い
    } else if (parentCat === "趣味") {
        if (sub === "趣味") l = 72; // 明るい
        else if (sub === "家具類") l = 48; // 暗い
    } else {
        if (sub === "その他" || sub === parentCat) {
            l = parentCat === "交際費" ? 23 
              : parentCat === "医療費" ? 51 
              : parentCat === "大学" ? 57 
              : parentCat === "日用品" ? 80
              : parentCat === "その他" ? 88
              : 65;
        } else {
            let hash = 0;
            for (let i = 0; i < sub.length; i++) {
                hash = sub.charCodeAt(i) + ((hash << 5) - hash);
            }
            l = 35 + (Math.abs(hash) % 40);
        }
    }
    
    // 彩度の微調整 (アクロマティックカラー以外)
    const s = base.s === 0 ? 0 : base.s;
    return `hsl(${base.h}, ${s}%, ${l}%)`;
};

const getSortIndex = (sub, parentCat) => {
    if (parentCat === "食費") {
        if (sub === "自炊食材") return 0;
        if (sub === "外食") return 1;
    }
    if (parentCat === "嗜好品") {
        if (sub === "お酒") return 2;
        if (sub === "タバコ") return 3;
        if (sub === "お菓子") return 4;
    }
    if (parentCat === "日用品") return 5;
    if (parentCat === "美容") {
        if (sub === "被服") return 6;
        if (sub === "美容") return 7;
    }
    if (parentCat === "趣味") {
        if (sub === "趣味") return 8;
        if (sub === "家具類") return 9;
    }
    if (parentCat === "サブスク費") return 10;
    if (parentCat === "交通費") return 11;
    if (parentCat === "交際費") return 12;
    if (parentCat === "医療費") return 13;
    if (parentCat === "大学") return 14;
    if (parentCat === "その他") return 15;
    return 100;
};

const subcatLabels = Object.keys(subcategoryMap).sort((a, b) => {
    const parentA = subToCatMap[a] || "その他";
    const parentB = subToCatMap[b] || "その他";
    return getSortIndex(a, parentA) - getSortIndex(b, parentB);
});

const generatedSubcatColors = subcatLabels.map(sub => {
    const parentCat = subToCatMap[sub] || "その他";
    return getSubcatColor(sub, parentCat);
});

const chartData1 = {
    type: 'doughnut',
    data: {
        labels: subcatLabels,
        datasets: [{
            data: subcatLabels.map(sub => subcategoryMap[sub]),
            backgroundColor: generatedSubcatColors
        }]
    },
    options: {
        legend: { position: 'bottom' }
    }
};

// グラフ3: 支払い方法別 (Doughnut)
const chartData2 = {
    type: 'doughnut',
    data: {
        labels: Object.keys(payMap),
        datasets: [{
            data: Object.values(payMap),
            backgroundColor: colors.slice(0, Object.keys(payMap).length)
        }]
    },
    options: {
        legend: { position: 'bottom' }
    }
};

if (window.renderChart) {
    try {
        // スクロール用ラッパーの追加 (3ヶ月表示・左右スライダスクロール対応)
        const historyScrollWrapper = historyCard.createEl("div", { 
            attr: { style: "width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; margin-top: 10px;" } 
        });
        const minMonthsVisible = 3;
        const chartWidthPct = sortedMonths.length > minMonthsVisible 
            ? (sortedMonths.length * (100 / minMonthsVisible)) 
            : 100;
        const historyChartInner = historyScrollWrapper.createEl("div", { 
            attr: { style: `width: ${chartWidthPct}%; min-width: 100%; position: relative; height: 280px;` } 
        });
        
        window.renderChart(historyChartData, historyChartInner);
        
        // 初期状態で最新月（一番右）にスクロール
        setTimeout(() => {
            historyScrollWrapper.scrollLeft = historyScrollWrapper.scrollWidth - historyScrollWrapper.clientWidth;
        }, 150);

        if (thisMonthPages.length > 0) {
            // カテゴリ別
            const wrapper1 = col1.createEl("div", { attr: { class: "chart-container" } });
            window.renderChart(chartData1, wrapper1);
            const centerText1 = wrapper1.createEl("div", { attr: { class: "chart-center-text" } });
            centerText1.createEl("div", { text: "TOTAL SPEND", attr: { class: "chart-center-label" } });
            centerText1.createEl("div", { text: `¥${totalSpend.toLocaleString()}`, attr: { class: "chart-center-val" } });

            // 支払い方法別
            const wrapper2 = col2.createEl("div", { attr: { class: "chart-container" } });
            window.renderChart(chartData2, wrapper2);
            const centerText2 = wrapper2.createEl("div", { attr: { class: "chart-center-text" } });
            centerText2.createEl("div", { text: "TOTAL SPEND", attr: { class: "chart-center-label" } });
            centerText2.createEl("div", { text: `¥${totalSpend.toLocaleString()}`, attr: { class: "chart-center-val" } });
        } else {
            col1.createEl("p", { text: "今月は支出データがないため、割合グラフを表示できません。" });
            col2.createEl("p", { text: "今月は支出データがないため、割合グラフを表示できません。" });
        }
    } catch (e) {
        containerEl.createEl("p", { text: `※ グラフのレンダリング中にエラーが発生しました: ${e.message}`, attr: { style: "color: var(--text-error);" } });
    }
} else {
    containerEl.createEl("p", { text: "※ Obsidian Charts プラグインが有効化されていないか、window.renderChart API が利用できません。", attr: { style: "color: var(--text-warning);" } });
}
```

---

## 最近購入した商品明細

```dataview
TABLE item.name as 商品名, item.price as 金額, item.category as カテゴリ, item.subcategory as サブカテゴリ
WHERE type = "receipt"
FLATTEN items as item
SORT date DESC, item.price DESC
LIMIT 30
```



## 今月のレシート一覧

```dataview
TABLE date as 日付, shop as 店舗名, total as 合計金額, pay_method as 支払い方法
WHERE type = "receipt" AND file.day.month = date(today).month AND file.day.year = date(today).year
SORT date DESC
```

---
