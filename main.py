"""
沖縄県内の地域活動・移住定住促進ニュース、および全国の移住定住促進事業ニュースを
RSSフィードとGoogleニュース検索から自動収集し、HTMLファイルとして出力するアプリ。

実行方法:
    python main.py

設定変更:
    config.yaml を編集することでキーワードやRSSフィードを追加・削除できます。
"""

import html
import json
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


DEFAULT_REGION = "全国"
DEFAULT_CATEGORY = "その他"
DEFAULT_SUB_CATEGORY = "その他"


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
    一致した場合は最初に一致したキーワード設定（dict）を返し、一致しなければNoneを返す。
    """
    for keyword_cfg in keywords:
        terms = keyword_cfg["keyword"].split()
        if terms and all(term in text for term in terms):
            return keyword_cfg
    return None


def is_excluded_source(display_source, link, exclude_domains):
    """display_source（出典表記）またはlinkに、除外対象ドメインが含まれるか判定する。
    Googleニュース検索結果は出典表記にドメイン名がそのまま入ることが多い
    （例: "mbp-japan.com"）ため、リンクのドメインだけでなく出典表記もチェックする。
    """
    if not exclude_domains:
        return False
    haystack = f"{display_source or ''} {link or ''}".lower()
    return any(domain.lower() in haystack for domain in exclude_domains if domain)


def fetch_feed(url, source_name, keyword_cfg=None, keyword_filter=None,
                global_exclude_domains=None):
    """RSS/Atomフィードを取得して記事リストを返す。
    keyword_filter にキーワード設定リストを渡すと、タイトル・概要が
    いずれかのキーワードに一致する記事だけを残し、一致したキーワードの
    region/categoryを記事に紐づける。
    keyword_cfg を渡した場合（Googleニュース検索時）は、そのキーワードの
    region/categoryをそのまま全記事に紐づける。
    matched_cfg（キーワード設定）またはグローバル設定に exclude_domains が
    指定されている場合、該当する出典の記事は除外する。
    """
    articles = []
    parsed = feedparser.parse(url)
    for entry in parsed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        matched_cfg = keyword_cfg
        if keyword_filter is not None:
            summary = entry.get("summary", "") or ""
            matched_cfg = match_keyword(f"{title} {summary}", keyword_filter)
            if matched_cfg is None:
                continue

        pub_date = parse_entry_date(entry)

        # Googleニュース検索結果は「タイトル - 出典」の形式になっていることが多いので分離する
        entry_source = entry.get("source", {}).get("title") if entry.get("source") else None
        display_source = entry_source or source_name

        exclude_domains = list(global_exclude_domains or [])
        exclude_domains += (matched_cfg or {}).get("exclude_domains", []) or []
        if is_excluded_source(display_source, link, exclude_domains):
            continue

        articles.append({
            "title": title,
            "link": link,
            "source": display_source,
            "date": pub_date,
            "tag": matched_cfg["keyword"] if matched_cfg else source_name,
            "region": (matched_cfg or {}).get("region") or DEFAULT_REGION,
            "category": (matched_cfg or {}).get("category") or DEFAULT_CATEGORY,
            "sub_category": (matched_cfg or {}).get("sub_category") or DEFAULT_SUB_CATEGORY,
        })
    return articles


def collect_articles(config):
    all_articles = []

    global_exclude_domains = config.get("exclude_domains", [])

    keywords = config.get("keywords", [])
    google_news_cfg = config.get("google_news", {})
    for keyword_cfg in keywords:
        keyword = keyword_cfg["keyword"]
        url = build_google_news_url(keyword, google_news_cfg)
        print(f"[Googleニュース検索] {keyword} を取得中...")
        articles = fetch_feed(
            url, "Googleニュース", keyword_cfg=keyword_cfg,
            global_exclude_domains=global_exclude_domains,
        )
        print(f"  -> {len(articles)} 件取得")
        all_articles.extend(articles)

    rss_feeds = config.get("rss_feeds", [])
    for feed in rss_feeds:
        name = feed.get("name", feed.get("url"))
        url = feed.get("url")
        if not url:
            continue
        print(f"[RSS] {name} を取得中...")
        articles = fetch_feed(
            url, name, keyword_filter=keywords,
            global_exclude_domains=global_exclude_domains,
        )
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


REGION_TABS = ["すべて", "沖縄", "全国"]
CATEGORY_TABS = ["すべて", "移住定住", "地域おこし", "人材確保", "その他"]


def build_sub_category_map(articles):
    """実際に収集された記事から、category -> sub_categoryタブ一覧のマップを組み立てる。
    "all" キーには全カテゴリ共通（ジャンル未選択時）のsub_category一覧を格納する。
    件数の多い順（同数の場合は名前順）に並べる。
    """
    counts_by_category = {}
    counts_all = {}
    for article in articles:
        category = article["category"]
        sub_category = article["sub_category"]
        counts_by_category.setdefault(category, {})
        counts_by_category[category][sub_category] = counts_by_category[category].get(sub_category, 0) + 1
        counts_all[sub_category] = counts_all.get(sub_category, 0) + 1

    def ordered_tabs(counts):
        return ["すべて"] + sorted(counts, key=lambda name: (-counts[name], name))

    sub_category_map = {"all": ordered_tabs(counts_all)}
    for category, counts in counts_by_category.items():
        sub_category_map[category] = ordered_tabs(counts)
    return sub_category_map


def render_filter_tabs(sub_category_map):
    def render_row(row_id, filter_type, values, label):
        buttons = []
        for i, value in enumerate(values):
            filter_value = "all" if value == "すべて" else value
            active_class = " active" if i == 0 else ""
            buttons.append(
                f'<button type="button" class="filter-btn{active_class}" '
                f'data-filter-type="{filter_type}" data-filter-value="{html.escape(filter_value)}">'
                f'{html.escape(value)}</button>'
            )
        return (
            f'<div class="filter-group">'
            f'<span class="filter-label">{html.escape(label)}</span>'
            f'<div class="filter-row" id="{row_id}">{"".join(buttons)}</div>'
            f'</div>'
        )

    region_row = render_row("region-filters", "region", REGION_TABS, "地域")
    category_row = render_row("category-filters", "category", CATEGORY_TABS, "ジャンル")
    sub_category_row = render_row(
        "subcategory-filters", "subCategory", sub_category_map.get("all", ["すべて"]), "サブジャンル（検索元）"
    )
    return f'<div class="filters">{region_row}{category_row}{sub_category_row}</div>'


def render_html(articles, generated_at):
    rows = []
    for article in articles:
        date_str = article["date"].strftime("%Y-%m-%d %H:%M") if article["date"] else "日付不明"
        title = html.escape(article["title"])
        link = html.escape(article["link"])
        source = html.escape(article["source"])
        tag = html.escape(article["tag"])
        region = html.escape(article["region"])
        category = html.escape(article["category"])
        sub_category = html.escape(article["sub_category"])
        rows.append(f"""
        <tr data-region="{region}" data-category="{category}" data-sub-category="{sub_category}">
          <td class="date">{date_str}</td>
          <td class="title"><a href="{link}" target="_blank" rel="noopener noreferrer">{title}</a></td>
          <td class="source">{source}</td>
          <td class="region"><span class="badge badge-region">{region}</span></td>
          <td class="category"><span class="badge badge-category">{category}</span></td>
          <td class="tag"><span class="badge">{tag}</span></td>
        </tr>""")

    if rows:
        rows_html = "\n".join(rows)
        no_match_row = (
            '<tr id="no-match-row" class="no-match-row" style="display:none;">'
            '<td colspan="6" class="empty">条件に一致する記事がありません</td></tr>'
        )
    else:
        rows_html = '<tr><td colspan="6" class="empty">記事が見つかりませんでした</td></tr>'
        no_match_row = ""

    sub_category_map = build_sub_category_map(articles)
    sub_category_map_json = json.dumps(sub_category_map, ensure_ascii=False)

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
  .badge-region {{
    background: #e6e0f8;
    color: #4b3593;
  }}
  .badge-category {{
    background: #fde8d2;
    color: #a45b12;
  }}
  .empty {{
    text-align: center;
    color: #999;
    padding: 40px;
  }}
  .filters {{
    margin-bottom: 16px;
  }}
  .filter-group {{
    margin-bottom: 8px;
  }}
  .filter-label {{
    display: block;
    font-size: 0.75rem;
    color: #777;
    margin-bottom: 4px;
  }}
  .filter-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 8px;
  }}
  .filter-btn {{
    border: 1px solid #ccc;
    background: #fff;
    color: #333;
    border-radius: 16px;
    padding: 6px 16px;
    font-size: 0.85rem;
    cursor: pointer;
  }}
  .filter-btn:hover {{
    border-color: #2f4858;
  }}
  .filter-btn.active {{
    background: #2f4858;
    border-color: #2f4858;
    color: #fff;
  }}
</style>
</head>
<body>
  <h1>沖縄・全国 移住定住ニュース</h1>
  <div class="meta">生成日時: {generated_at} ／ 記事数: {len(articles)}件</div>
  {render_filter_tabs(sub_category_map)}
  <table>
    <thead>
      <tr>
        <th>日付</th>
        <th>タイトル</th>
        <th>出典</th>
        <th>地域</th>
        <th>ジャンル</th>
        <th>検索元</th>
      </tr>
    </thead>
    <tbody>
      {rows_html}
      {no_match_row}
    </tbody>
  </table>
  <script>
    (function () {{
      var SUB_CATEGORY_MAP = {sub_category_map_json};
      var state = {{ region: "all", category: "all", subCategory: "all" }};
      var rows = Array.prototype.slice.call(
        document.querySelectorAll("table tbody tr[data-region]")
      );
      var noMatchRow = document.getElementById("no-match-row");
      var subCategoryContainer = document.getElementById("subcategory-filters");

      function applyFilters() {{
        var visibleCount = 0;
        rows.forEach(function (row) {{
          var matchesRegion = state.region === "all" || row.dataset.region === state.region;
          var matchesCategory = state.category === "all" || row.dataset.category === state.category;
          var matchesSubCategory = state.subCategory === "all" || row.dataset.subCategory === state.subCategory;
          var visible = matchesRegion && matchesCategory && matchesSubCategory;
          row.style.display = visible ? "" : "none";
          if (visible) visibleCount++;
        }});
        if (noMatchRow) {{
          noMatchRow.style.display = visibleCount === 0 ? "" : "none";
        }}
      }}

      function renderSubCategoryTabs(category) {{
        var values = SUB_CATEGORY_MAP[category] || ["すべて"];
        subCategoryContainer.innerHTML = "";
        values.forEach(function (value, i) {{
          var filterValue = value === "すべて" ? "all" : value;
          var btn = document.createElement("button");
          btn.type = "button";
          btn.className = "filter-btn" + (i === 0 ? " active" : "");
          btn.dataset.filterType = "subCategory";
          btn.dataset.filterValue = filterValue;
          btn.textContent = value;
          subCategoryContainer.appendChild(btn);
        }});
        state.subCategory = "all";
      }}

      document.querySelector(".filters").addEventListener("click", function (event) {{
        var btn = event.target.closest(".filter-btn");
        if (!btn) return;

        var filterType = btn.dataset.filterType;
        var filterValue = btn.dataset.filterValue;
        state[filterType] = filterValue;

        var row = btn.closest(".filter-row");
        Array.prototype.forEach.call(row.querySelectorAll(".filter-btn"), function (b) {{
          b.classList.toggle("active", b === btn);
        }});

        if (filterType === "category") {{
          renderSubCategoryTabs(filterValue);
        }}

        applyFilters();
      }});
    }})();
  </script>
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
