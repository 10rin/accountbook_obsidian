# Gemini-Obsidian 家計簿システム (Receipt Watcher)

このシステムは、指定フォルダに保存されたレシート画像を Gemini API (Gemini 2.5 Flash) を用いて自動解析し、Obsidian で読み込み可能な家計簿 Markdown データに変換して自動出力するシステムです。

---

## 目次
1. [セットアップ手順](#1-セットアップ手順)
2. [Obsidianでの連携方法](#2-obsidianでの連携方法)
3. [iPhoneショートカット連携（レシート自動アップロード）](#3-iphoneショートカット連携レシート自動アップロード)
4. [常時監視の起動方法](#4-常時監視の起動方法)

---

## 1. セットアップ手順

### 必要条件
- Python 3.10 以上
- Gemini API キー (Google AI Studio で取得可能)

### 導入手順

1. **依存パッケージのインストール**
   本フォルダに移動し、仮想環境を作成して依存パッケージをインストールします。
   ```bash
   # 仮想環境の作成（未作成の場合）
   python3 -m venv venv
   
   # 仮想環境のアクティベート
   source venv/bin/activate

   # 依存ライブラリのインストール
   pip install -r requirements.txt
   ```

2. **APIキーの設定**
   本フォルダのルート直下に `.env` ファイルを作成し、以下の通り Gemini API キーを設定します。
   ```env
   GEMINI_API_KEY="あなたのGemini_APIキー"
   ```
   *(※セキュリティのため、`.env` ファイルは Git 管理から除外されています)*

---

## 2. Obsidianでの連携方法

本システムは、生成された Markdown データを Obsidian の強力なコミュニティプラグインを用いて可視化します。

### 必要な Obsidian プラグインのインストール

Obsidian の「設定」➔「コミュニティプラグイン」から以下の2つのプラグインをインストールし、**有効化**してください。

1. **Dataview**
   - 生成されたレシートデータ (`type: receipt` / `type: income`) を集計・リスト表示するために必須です。
   - **設定時の注意**: プラグイン設定内の **「Enable JavaScript Queries」** および **「Enable Inline JavaScript Queries」** を必ず **ON** にしてください。これらが OFF だとダッシュボードが表示されません。
2. **Obsidian Charts**
   - 収支推移やカテゴリ別・支払い方法別の円グラフを表示するために使用します。

### ダッシュボードの配置

- 本プロジェクトの [accontbook.md](accontbook.md) は、家計簿ダッシュボードの本体です。
- このファイルを Obsidian の Vault（保管庫）内の任意の場所に配置します。
- レシートの自動生成データは [data/](data/) フォルダ内に保存されます。`accontbook.md` と `data` フォルダは同じ階層にあるか、Obsidian 側で `data` フォルダが正しく参照できる必要があります（Dataview クエリは `data` フォルダ内の `type: receipt` を検索するように組まれています）。

---

## 3. iPhoneショートカット連携（レシート自動アップロード）

iPhone で撮影したレシート画像を、Mac 側の監視対象フォルダである iCloud Drive 内の `receipts` フォルダへ自動で保存するための iOS ショートカットの作成手順です。

### 作成手順

1. iPhone で **「ショートカット」アプリ** を開きます。
2. 右上の「**＋**」ボタンをタップして、新規ショートカットを作成します。
3. ショートカット名（例: 「レシート保存」）を入力します。
4. 以下の順にアクションを追加します。

#### 【アクション 1: 写真を撮る】
- 「アクションを追加」をタップし、検索窓に「写真を撮る」と入力して追加します。
- 「**カメラで写真を撮る**」を選択します。
- 詳細設定（「＞」をタップ）で「カメラ: **背面**」、「表示を表示: **OFF**（撮影後すぐに進む場合。ONにするとプレビューを確認できます）」に設定します。

#### 【アクション 2: ファイルを保存】
- 検索窓に「ファイルを保存」と入力して追加します。
- アクションが「**カメラ写真** を **保存**」になっていることを確認します。
- 「**保存先を尋ねる**」を **OFF** にします。
- 保存先の設定をタップし、iCloud Drive 内の **`receipts`** フォルダを選択します。
  - ※もし `receipts` フォルダがない場合は、事前に iPhone の「ファイル」アプリを開き、「iCloud Drive」の直下に `receipts` という名前で新規フォルダを作成しておいてください。
- 「**ファイルが存在する場合は上書き**」は **OFF**（別名で保存されるようにする）にします。

#### 【アクション 3: 通知を表示（任意）】
- 検索窓に「通知を表示」と入力して追加します。
- テキストを「レシートをアップロードしました」などに設定します。これにより、処理が正常に完了したことが視覚的にわかります。

### 使い方
- iPhone のホーム画面にこのショートカットのアイコンを配置するか、背面タップや Siri から起動します。
- 起動するとカメラが立ち上がり、レシートを撮影して決定するだけで、自動で iCloud Drive 内の `receipts` フォルダに保存されます。
- Mac が起動していれば、後述の常時監視スクリプトがこれを検知して自動的に Gemini で OCR 解析し、Obsidian の `data/` フォルダに家計簿 Markdown として出力します（処理完了した元画像は自動で削除されます）。

---

## 4. 常時監視の起動方法

iCloud Drive の `receipts` フォルダを監視し続ける常時監視モードの起動方法です。

### 方法A: `ReceiptWatcher.app` で起動する (推奨)
本プロジェクトのルートにある [ReceiptWatcher.app](ReceiptWatcher.app) をダブルクリックして起動します。
これにより、バックグラウンドで自動的に常時監視スクリプトが走り始めます。

### 方法B: ターミナルから起動する
ターミナルで本プロジェクトフォルダに移動し、以下のコマンドを実行します（仮想環境 `venv` を使用している前提）。

```bash
# 仮想環境のアクティベート
source venv/bin/activate

# 監視モードでスクリプトを実行
python process_receipt.py --watch
```

起動すると、`👀 レシートフォルダの常時監視を開始しました...` と表示され、iCloud Drive への画像追加を自動的に待ち受けます。

---

### Mac起動時に自動でバックグラウンド実行したい場合 (高度な設定)

毎回起動させるのが面倒な場合、macOS の `launchd` を使用して、Mac のログイン時にバックグラウンドで自動起動させることができます。

1. `~/Library/LaunchAgents/com.user.receiptwatcher.plist` というファイルを以下の内容で作成します（パスや環境変数はご自身の環境に合わせて書き換えてください）。

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.EN">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.receiptwatcher</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/【あなたのMacユーザー名】/【このフォルダのパス】/venv/bin/python</string>
        <string>/Users/【あなたのMacユーザー名】/【このフォルダのパス】/process_receipt.py</string>
        <string>--watch</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/Users/【あなたのMacユーザー名】/【このフォルダのパス】</string>
    <key>StandardOutPath</key>
    <string>/Users/【あなたのMacユーザー名】/【このフォルダのパス】/watcher.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/【あなたのMacユーザー名】/【このフォルダのパス】/watcher.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>GEMINI_API_KEY</key>
        <string>あなたのGEMINI_API_KEY</string>
    </dict>
</dict>
</plist>
```

2. 以下のコマンドを実行して、サービスを登録・起動します。
   ```bash
   launchctl bootstrap gui/【あなたのユーザーID】 ~/Library/LaunchAgents/com.user.receiptwatcher.plist
   ```
   *(※ ユーザーIDは `id -u` コマンドで確認できます。デフォルトは通常 `501` です)*
