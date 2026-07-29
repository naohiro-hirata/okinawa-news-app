"""
沖縄県内の地域活動・移住定住促進ニュース、および全国の移住定住促進事業ニュースを
RSSフィードとGoogleニュース検索から自動収集し、HTMLファイルとして出力するアプリ。

実行方法:
    python main.py

設定変更:
    config.yaml を編集することでキーワードやRSSフィードを追加・削除できます。
"""

import html
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

import feedparser
import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_google_news_url(keyword, google_news_cfg):
    query = urllib.parse.quote(keyword)
    hl = google_news_cfg.get("hl", "ja")
    gl = google_news_cfg.get("gl", "JP")
    ceid = google_news_cfg.get("ceid", "JP:ja")
    return f"https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={ceid}"


def parse_entry_date(entry):
    """フィードエントリから日付を取得する。取得できない場合はNoneを返す。"""
    for field in ("published", "updated"):
        value = entry.get(field)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except (TypeError, ValueError):
                continue

    for field in ("published_parsed", "updated_parsed"):
        value = entry.get(field)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue

    return None


def match_keyword(text, keywords):
    """textが keywords のいずれかに一致するか判定する。
    各キーワードはスペース区切りのAND条件として扱う（Googleニュース検索と同じ考え方）。
    一致した場合は最初に一致したキーワードを返し、一致しなければNoneを返す。
    """
    for keyword in keywords:
        terms = keyword.split()
        if terms and all(term in text for term in terms):
            return keyword
    return None


def fetch_feed(url, source_name, tag, keyword_filter=None):
    """RSS/Atomフィードを取得して記事リストを返す。
    keyword_filter にキーワードリストを渡すと、タイトル・概要が
    いずれかのキーワードに一致する記事だけを残す。
    """
    articles = []
    parsed = feedparser.parse(url)
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        matched_tag = tag
        if keyword_filter is not None:
            summary = entry.get("summary", "") or ""
            matched = match_keyword(f"{title} {summary}", keyword_filter)
            if matched is None:
                continue
            matched_tag = matched

        pub_date = parse_entry_date(entry)

        # Googleニュース検索結果は「タイトル - 出典」の形式になっていることが多いので分離する
        entry_source = entry.get("source", {}).get("title") if entry.get("source") else None
        display_source = entry_source or source_name

        articles.append({
            "title": title,
            "link": link,
            "source": display_source,
            "date": pub_date,
            "tag": matched_tag,
        })
    return articles


def collect_articles(config):
    all_articles = []

    keywords = config.get("keywords", [])
    google_news_cfg = config.get("google_news", {})
    for keyword in keywords:
        url = build_google_news_url(keyword, google_news_cfg)
        print(f"[Googleニュース検索] {keyword} を取得中...")
        articles = fetch_feed(url, "Googleニュース", keyword)
        print(f"  -> {len(articles)} 件取得")
        all_articles.extend(articles)

    rss_feeds = config.get("rss_feeds", [])
    for feed in rss_feeds:
        name = feed.get("name", feed.get("url"))
        url = feed.get("url")
        if not url:
            continue
        print(f"[RSS] {name} を取得中...")
        articles = fetch_feed(url, name, "RSS購読", keyword_filter=keywords)
        print(f"  -> {len(articles)} 件取得（キーワード一致分のみ）")
        all_articles.extend(articles)

    return all_articles


def dedupe_articles(articles):
    seen_links = set()
    seen_titles = set()
    deduped = []
    for article in articles:
        link_key = article["link"].strip()
        title_key = article["title"].strip()
        if link_key in seen_links or title_key in seen_titles:
            continue
        seen_links.add(link_key)
        seen_titles.add(title_key)
        deduped.append(article)
    return deduped


def filter_by_age(articles, max_age_days):
    if not max_age_days:
        return articles
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    filtered = []
    for article in articles:
        if article["date"] is None or article["date"] >= cutoff:
            filtered.append(article)
    return filtered


def sort_articles(articles):
    # 日付不明の記事は末尾に回す
    return sorted(
        articles,
        key=lambda a: a["date"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )


def render_html(articles, generated_at):
    rows = []
    for article in articles:
        date_str = article["date"].strftime("%Y-%m-%d %H:%M") if article["date"] else "日付不明"
        title = html.escape(article["title"])
        link = html.escape(article["link"])
        source = html.escape(article["source"])
        tag = html.escape(article["tag"])
        rows.append(f"""
        <tr>
          <td class="date">{date_str}</td>
          <td class="title"><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></td>
          <td class="source">{source}</td>
          <td class="tag"><span class="badge">{tag}</span></td>
        </tr>""")

    rows_html = "\n".join(rows) if rows else '<tr><td colspan="4" class="empty">記事が見つかりませんでした</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>沖縄・全国 移住定住ニュース</title>
<style>
  body {{
    font-family: "Hiragino Kaku Gothic ProN", "Meiryo", sans-serif;
    background: #f5f6f8;
    color: #222;
    margin: 0;
    padding: 24px;
  }}
  h1 {{
    font-size: 1.5rem;
    margin-bottom: 4px;
  }}
  .meta {{
    color: #666;
    font-size: 0.85rem;
    margin-bottom: 20px;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  }}
  th, td {{
    padding: 10px 12px;
    border-bottom: 1px solid #e5e5e5;
    text-align: left;
    vertical-align: top;
    font-size: 0.9rem;
  }}
  th {{
    background: #2f4858;
    color: #fff;
    position: sticky;
    top: 0;
  }}
  tr:hover {{
    background: #f0f7f4;
  }}
  .date {{
    white-space: nowrap;
    color: #555;
  }}
  .source {{
    white-space: nowrap;
    color: #555;
  }}
  a {{
    color: #1a5276;
    text-decoration: none;
  }}
  a:hover {{
    text-decoration: underline;
  }}
  .badge {{
    display: inline-block;
    background: #dceef0;
    color: #1a6b78;
    border-radius: 12px;
    padding: 2px 10px;
    font-size: 0.75rem;
    white-space: nowrap;
  }}
  .empty {{
    text-align: center;
    color: #999;
    padding: 40px;
  }}
</style>
</head>
<body>
  <h1>沖縄・全国 移住定住ニュース</h1>
  <div class="meta">生成日時: {generated_at} ／ 記事数: {len(articles)}件</div>
  <table>
    <thead>
      <tr>
        <th>日付</th>
        <th>タイトル</th>
        <th>出典</th>
        <th>検索元</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""


def main():
    config = load_config()

    articles = collect_articles(config)
    print(f"\n合計 {len(articles)} 件取得（重複除去前）")

    articles = dedupe_articles(articles)
    print(f"重複除去後: {len(articles)} 件")

    articles = filter_by_age(articles, config.get("max_age_days", 0))
    print(f"日付フィルタ後: {len(articles)} 件")

    articles = sort_articles(articles)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html_content = render_html(articles, generated_at)

    output_path = Path(__file__).parent / config.get("output_file", "output/news.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_content, encoding="utf-8")

    print(f"\n完了: {output_path} を出力しました")


if __name__ == "__main__":
    main()
