import hashlib
import os
import re
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET


SOURCE_URL = "https://www.ris.ac.jp/sports/rugby/index.html"
OUTPUT_FILE = "rissho_rugby.xml"

JST = timezone(timedelta(hours=9))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,"
        "image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


def clean_text(text):
    if not text:
        return ""

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def make_guid(link):
    return hashlib.sha256(
        link.encode("utf-8")
    ).hexdigest()


def fetch_page(url):
    for attempt in range(1, 4):
        try:
            print(
                f"取得 {attempt}/3: {url}"
            )

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=30,
            )

            print(
                f"HTTP: {response.status_code}"
            )

            response.raise_for_status()

            response.encoding = (
                response.apparent_encoding
                or "utf-8"
            )

            print(
                f"HTML文字数: {len(response.text)}"
            )

            return response.text

        except requests.RequestException as e:
            print(
                f"取得失敗: {e}"
            )

            if attempt < 3:
                print(
                    "10秒待って再試行します。"
                )
                time.sleep(10)

    return None


def parse_date(text):
    try:
        return datetime.strptime(
            text,
            "%Y.%m.%d",
        ).replace(
            hour=12,
            minute=0,
            second=0,
            tzinfo=JST,
        )

    except ValueError:
        return None


def extract_articles(page_html):
    soup = BeautifulSoup(
        page_html,
        "html.parser",
    )

    articles = {}

    for block in soup.select(
        "div.tpl-news"
    ):
        category_element = block.select_one(
            ".news-category"
        )

        if not category_element:
            continue

        category = clean_text(
            category_element.get_text(
                " ",
                strip=True,
            )
        )

        if category != "ラグビー":
            continue

        link_element = block.find(
            "a",
            href=True,
        )

        title_element = block.select_one(
            ".news-title"
        )

        date_element = block.select_one(
            "time.news-date"
        )

        if not (
            link_element
            and title_element
            and date_element
        ):
            continue

        title = clean_text(
            title_element.get_text(
                " ",
                strip=True,
            )
        )

        date_text = clean_text(
            date_element.get_text(
                " ",
                strip=True,
            )
        )

        article_date = parse_date(
            date_text
        )

        link = urljoin(
            SOURCE_URL,
            link_element.get(
                "href",
                "",
            ),
        )

        if not title:
            continue

        if article_date is None:
            continue

        if not link.startswith(
            "https://www.ris.ac.jp/"
        ):
            continue

        articles[link] = {
            "title": title,
            "link": link,
            "date": article_date,
            "category": category,
        }

    result = list(
        articles.values()
    )

    result.sort(
        key=lambda x: x["date"],
        reverse=True,
    )

    return result


def load_existing_items():
    items = {}

    if not os.path.exists(
        OUTPUT_FILE
    ):
        return items

    try:
        tree = ET.parse(
            OUTPUT_FILE
        )

        root = tree.getroot()

        for item in root.findall(
            "./channel/item"
        ):
            guid = (
                item.findtext(
                    "guid",
                    "",
                ).strip()
            )

            if not guid:
                continue

            items[guid] = {
                "title": item.findtext(
                    "title",
                    "",
                ),
                "link": item.findtext(
                    "link",
                    "",
                ),
                "description": (
                    item.findtext(
                        "description",
                        "",
                    )
                ),
                "pubDate": item.findtext(
                    "pubDate",
                    "",
                ),
                "category": item.findtext(
                    "category",
                    "",
                ),
                "guid": guid,
            }

    except Exception as e:
        print(
            f"既存RSS読込失敗: {e}"
        )

    return items


def build_rss(
    existing_items,
    current_articles,
):
    merged = dict(
        existing_items
    )

    new_count = 0

    for article in current_articles:
        guid = make_guid(
            article["link"]
        )

        if guid not in merged:
            new_count += 1

        merged[guid] = {
            "title": article[
                "title"
            ],
            "link": article[
                "link"
            ],
            "description": (
                "立正大学ラグビー部 トピックス"
            ),
            "pubDate": format_datetime(
                article["date"]
            ),
            "category": article[
                "category"
            ],
            "guid": guid,
        }

    def get_pubdate(item):
        try:
            dt = parsedate_to_datetime(
                item["pubDate"]
            )

            if dt.tzinfo is None:
                dt = dt.replace(
                    tzinfo=timezone.utc
                )

            return dt

        except Exception:
            return datetime(
                1970,
                1,
                1,
                tzinfo=timezone.utc,
            )

    sorted_items = sorted(
        merged.values(),
        key=get_pubdate,
        reverse=True,
    )

    rss = ET.Element(
        "rss",
        version="2.0",
    )

    channel = ET.SubElement(
        rss,
        "channel",
    )

    ET.SubElement(
        channel,
        "title",
    ).text = (
        "立正大学ラグビー部 トピックス"
    )

    ET.SubElement(
        channel,
        "link",
    ).text = SOURCE_URL

    ET.SubElement(
        channel,
        "description",
    ).text = (
        "立正大学ラグビー部の最新トピックス"
    )

    ET.SubElement(
        channel,
        "language",
    ).text = "ja"

    ET.SubElement(
        channel,
        "lastBuildDate",
    ).text = format_datetime(
        datetime.now(JST)
    )

    for data in sorted_items:
        item = ET.SubElement(
            channel,
            "item",
        )

        ET.SubElement(
            item,
            "title",
        ).text = data[
            "title"
        ]

        ET.SubElement(
            item,
            "link",
        ).text = data[
            "link"
        ]

        ET.SubElement(
            item,
            "description",
        ).text = data[
            "description"
        ]

        ET.SubElement(
            item,
            "pubDate",
        ).text = data[
            "pubDate"
        ]

        ET.SubElement(
            item,
            "category",
        ).text = data[
            "category"
        ]

        guid_element = ET.SubElement(
            item,
            "guid",
        )

        guid_element.set(
            "isPermaLink",
            "false",
        )

        guid_element.text = data[
            "guid"
        ]

    tree = ET.ElementTree(
        rss
    )

    ET.indent(
        tree,
        space="  ",
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )

    return (
        len(sorted_items),
        new_count,
    )


def main():
    existing_items = (
        load_existing_items()
    )

    print(
        f"既存RSS件数: "
        f"{len(existing_items)}"
    )

    page_html = fetch_page(
        SOURCE_URL
    )

    if page_html is None:
        if existing_items:
            print(
                "取得に失敗したため、"
                "既存XMLを維持します。"
            )
            return

        raise RuntimeError(
            "立正大学ラグビー部ページを"
            "取得できませんでした。"
        )

    try:
        articles = extract_articles(
            page_html
        )

    except Exception as e:
        if existing_items:
            print(
                f"解析失敗: {e}"
            )
            print(
                "既存XMLを維持します。"
            )
            return

        raise

    print()
    print(
        f"現在のトピックス取得件数: "
        f"{len(articles)}"
    )

    print()
    print(
        "=== 現在のラグビートピックス ==="
    )

    for i, article in enumerate(
        articles,
        1,
    ):
        print()
        print(
            f"{i:2d}. "
            f"{article['date'].strftime('%Y-%m-%d')} "
            f"{article['title']}"
        )

        print(
            f"    {article['link']}"
        )

    if len(articles) < 1:
        if existing_items:
            print()
            print(
                "ラグビー記事を取得できなかったため、"
                "既存XMLを維持します。"
            )
            return

        raise RuntimeError(
            "ラグビー記事を取得できませんでした。"
        )

    total_count, new_count = build_rss(
        existing_items,
        articles,
    )

    print()
    print(
        f"今回の新規記事: "
        f"{new_count}"
    )

    print(
        f"RSS保存件数: "
        f"{total_count}"
    )

    print(
        f"保存先: "
        f"{os.path.abspath(OUTPUT_FILE)}"
    )


if __name__ == "__main__":
    main()