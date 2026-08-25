"""
案例：ssr1 · https://ssr1.scrape.center
Issue：#2
目标：抓取全部电影的片名、类别、评分、上映时间
"""

import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# 站点根地址。第 1 页是 /page/1，第 2 页是 /page/2……规律很简单，
# 所以下面用一个循环把 1~10 页拼出来就行。
BASE_URL = "https://ssr1.scrape.center"
TOTAL_PAGES = 10

# 两次请求之间至少歇 1 秒。练习站点是别人免费提供的，
# 请求太密等于在攻击人家，这是爬虫最基本的礼貌。
REQUEST_INTERVAL = 1

# 输出文件放在本脚本同级的 data/ 目录里。
# __file__ 是"当前这个 .py 文件的路径"，用它算出的路径不管从哪个目录运行都对。
OUTPUT_PATH = Path(__file__).parent / "data" / "ssr1.json"

# 带上浏览器的 User-Agent。很多网站看到 requests 默认的标识就会拒绝，
# 这个站点虽然不拦，但养成习惯没坏处。
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def fetch_page(page: int) -> str:
    """下载第 page 页的 HTML 源码，返回一个字符串。"""
    url = f"{BASE_URL}/page/{page}"
    print(f"正在抓取：{url}")
    response = requests.get(url, headers=HEADERS, timeout=10)
    # raise_for_status()：如果服务器返回 404/500 这类错误码就主动抛异常，
    # 免得后面拿着一个错误页面去解析，白忙一场还找不到原因。
    response.raise_for_status()
    return response.text


def parse_movies(html: str) -> list:
    """把一页的 HTML 解析成电影列表。"""
    # lxml 是第三方解析器，比 Python 自带的 html.parser 快，容错也更好。
    soup = BeautifulSoup(html, "lxml")

    movies = []
    # 观察网页源码可以发现：每部电影都被包在 class 含 "el-card" 和 "item" 的 div 里。
    # select() 用的是 CSS 选择器，".el-card.item" 表示"同时有这两个 class"。
    for card in soup.select(".el-card.item"):
        # 片名在 <h2> 里。用 strip=True 去掉首尾多余的空白和换行。
        name_tag = card.select_one("h2")
        name = name_tag.get_text(strip=True) if name_tag else None

        # 类别是一组按钮，每个按钮里一个 <span>，所以结果天然是个列表。
        categories = [
            span.get_text(strip=True)
            for span in card.select(".categories span")
        ]

        # 评分在 class="score" 的 <p> 里，页面上带着换行空格，要 strip。
        score_tag = card.select_one(".score")
        score = score_tag.get_text(strip=True) if score_tag else None

        # 上映时间比较麻烦：页面里有好几个 class="info" 的 div
        # （一个放地区/片长，一个放上映时间），标签本身长得一模一样。
        # 所以不能按位置取，只能把所有 info 里的文字捞出来，
        # 找那条以"上映"结尾的——这叫"按内容特征定位"，比按位置定位稳得多。
        release_date = None
        for info in card.select(".info"):
            text = info.get_text(strip=True)
            if text.endswith("上映"):
                # 原文形如 "1993-07-26上映"，砍掉末尾两个字只留日期。
                release_date = text.replace("上映", "").strip()
                break

        movies.append({
            "name": name,
            "categories": categories,
            "score": score,
            "release_date": release_date,
        })

    return movies


def main():
    all_movies = []

    for page in range(1, TOTAL_PAGES + 1):
        html = fetch_page(page)
        movies = parse_movies(html)
        all_movies.extend(movies)
        print(f"  第 {page} 页解析到 {len(movies)} 部电影")

        # 最后一页抓完就没必要再等了。
        if page < TOTAL_PAGES:
            time.sleep(REQUEST_INTERVAL)

    # parents=True：父目录不存在就一起建；exist_ok=True：已存在也不报错。
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        # ensure_ascii=False 是关键：不加的话中文会被写成 霸 这种转义码，
        # 文件还是对的，但人眼完全没法读。
        json.dump(all_movies, f, ensure_ascii=False, indent=2)

    print(f"\n共抓取 {len(all_movies)} 部电影，已保存到 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
