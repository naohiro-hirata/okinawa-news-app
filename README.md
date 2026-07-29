# 沖縄・全国 移住定住ニュース収集アプリ

沖縄県内の地域活動・移住定住促進に関するニュースと、全国の移住定住促進事業に関するニュースを
RSSフィード・Googleニュース検索から自動収集し、見やすいHTMLファイルとして出力します。

## セットアップ（初回のみ）

```bash
pip install -r requirements.txt
```

## 実行方法

```bash
python main.py
```

実行すると `output/news.html` が生成されます。ブラウザでこのファイルを開いてください。

Windowsのコンソールで実行時のログが文字化けする場合は、以下のように実行すると解消します。

```bash
# PowerShell
$env:PYTHONUTF8="1"; python main.py

# Git Bash
PYTHONUTF8=1 python main.py
```

（ログ表示のみの問題で、出力されるHTMLファイル自体は常に正しいUTF-8です）

## 設定の変更方法

`config.yaml` を編集してください。

- `keywords`: Googleニュース検索するキーワードのリスト
- `google_news`: Googleニュース検索の言語・地域設定
- `rss_feeds`: 直接購読するRSSフィード（name / url）
- `max_age_days`: 何日以内の記事を対象にするか（0にすると日付フィルタなし）
- `output_file`: 出力するHTMLファイルのパス

編集後は再度 `python main.py` を実行するだけで反映されます。

## 既知の制限・今後の改善候補

- 琉球新報は現時点で有効なRSS配信URLが見つからなかったため、デフォルトのRSS購読リストには含めていません。有効なURLが見つかれば `config.yaml` の `rss_feeds` に追加できます。
- 現状は毎回手動実行です。定期実行したい場合はタスクスケジューラ（Windows）やcronで `python main.py` を定期的に呼び出してください。
- タイトルの完全一致でも重複除去していますが、表記ゆれ（全角/半角、末尾の媒体名など）までは吸収していません。
