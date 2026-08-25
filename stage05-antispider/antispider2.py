"""
案例：antispider2 · https://antispider2.scrape.center
Issue：#6
反爬手段：检测 User-Agent，看到不像浏览器的标识就直接 403 拒绝
目标：换上正常浏览器的 User-Agent，正常抓取电影数据
"""

import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    检查每个请求头里的 User-Agent（简称 UA）。
#
#    什么是 User-Agent？你每次访问网页，浏览器都会随请求附上一张"自我介绍卡片"，
#    上面写着"我是 Mac 上的 Chrome 120 版"。这就是 User-Agent。
#    它本来是给网站用来做适配的（比如给手机浏览器发手机版页面）。
#
# ② 它是怎么认出爬虫的？
#    Python 的 requests 库**默认**会把自我介绍写成 "python-requests/2.32.3"。
#    这等于你去人家门口，举着一块牌子写"我是爬虫程序"。
#    网站看一眼 UA 就知道了，连页面都不用给你，直接回 403 Forbidden。
#
# ③ 我们用什么办法绕过？
#    自己写一张正常的自我介绍卡片。UA 只是一个普通的字符串请求头，
#    谁都能随便填，服务器**没有任何办法验证它是真是假**。
#    所以把它换成真实 Chrome 的 UA 字符串就通过了。
#
#    这也说明：单纯查 UA 是最弱的一道反爬门槛，一行代码就能过。
#    但它能挡掉绝大多数"完全不懂事"的脚本，成本几乎为零，所以到处都在用。
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider2.scrape.center"
TOTAL_PAGES = 10
REQUEST_INTERVAL = 1  # 两次请求之间歇 1 秒，做人要厚道
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider2.json"

# 一张正常的"自我介绍卡片"：Mac + Chrome 120。
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def demo_default_ua() -> None:
    """对照组：用 requests 的默认 UA 去请求，看看被怎么打发。"""
    print("【对照组】用 requests 默认 UA：")
    # requests.utils.default_headers() 能查到默认到底写了什么
    default_ua = requests.utils.default_headers()["User-Agent"]
    print(f"  发出去的 User-Agent = {default_ua}")
    response = requests.get(BASE_URL, timeout=15)
    print(f"  状态码 = {response.status_code}")
    print(f"  响应正文 = {response.text.strip()[:160]!r}")


def fetch_page(page: int) -> str:
    """带着浏览器 UA 抓第 page 页。"""
    url = f"{BASE_URL}/page/{page}"
    response = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def parse_movies(html: str) -> list:
    """解析一页 HTML，返回电影列表。页面结构和 stage01 的 ssr1 一模一样。"""
    soup = BeautifulSoup(html, "lxml")
    movies = []
    for card in soup.select(".el-card.item"):
        name_tag = card.select_one("h2")
        score_tag = card.select_one(".score")
        infos = [i.get_text(strip=True) for i in card.select(".info")]
        movies.append(
            {
                "name": name_tag.get_text(strip=True) if name_tag else None,
                "categories": [
                    b.get_text(strip=True) for b in card.select(".categories button span")
                ],
                "info": infos[0] if len(infos) > 0 else None,
                "published_at": infos[1] if len(infos) > 1 else None,
                "score": score_tag.get_text(strip=True) if score_tag else None,
            }
        )
    return movies


def main() -> None:
    demo_default_ua()

    print(f"\n【实验组】换成 Chrome 的 UA：\n  {BROWSER_HEADERS['User-Agent']}")
    all_movies = []
    for page in range(1, TOTAL_PAGES + 1):
        html = fetch_page(page)
        movies = parse_movies(html)
        all_movies.extend(movies)
        print(f"  第 {page} 页：拿到 {len(movies)} 条，累计 {len(all_movies)} 条")
        if page < TOTAL_PAGES:
            time.sleep(REQUEST_INTERVAL)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(all_movies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n共 {len(all_movies)} 条，已写入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
