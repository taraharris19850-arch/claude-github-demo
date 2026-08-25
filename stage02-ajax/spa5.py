"""
案例：spa5 · https://spa5.scrape.center
Issue：#3
接口：GET /api/book/?limit=50&offset=0
目标：不解析 HTML，直接调接口拿全部图书数据
"""

# ============================================================
# 这个接口是怎么找到的？
# ============================================================
# spa5 是图书网站，页面依然是空壳 SPA。
# 沿用 spa4 学到的思路——**接口路径通常跟站点内容同名**：
#   电影站 → /api/movie/    新闻站 → /api/news/    图书站 → /api/book/
# 于是直接试（注意 URL 要加引号，否则 zsh 会把 ? 当通配符）：
#     curl -s "https://spa5.scrape.center/api/book/?limit=2&offset=0"
# 一次命中。
#
# 保底办法（猜不中时用，对任何 SPA 都有效）：
#     curl -s https://spa5.scrape.center/ | grep -o '/js/app[^"]*\.js'
#     curl -s "https://spa5.scrape.center/js/app.xxxx.js" | grep -o '/api/[a-z]*'
#
# 参数含义：
#   limit  = 这一批要几条（实测最大能给到 100，本脚本用 50 是为了多翻几页、
#            让进度条动起来更直观；调大能更快，调小更温和）
#   offset = 跳过前面多少条
#
# 返回结构：
#   {"count": 9040, "results": [ {"id","name","authors","cover","score"} ]}
#   - count   总共 9040 本书  ← 本脚本靠它算「要翻多少页」
#   - authors 是个**列表**（一本书可能多个作者），不是字符串
#   ★ 数据脏：有些书的作者名里带换行和一堆空格，比如 "\n            董桥"。
#     真实世界的接口数据就是这样，所以本脚本做了清洗（见 clean_authors）。
#
# ============================================================
# ★ 关于数据量：本脚本做了截断，只抓前 500 本
# ============================================================
# 接口 count = 9040 本，远超作业设定的 1000 条门槛。
# 按每批 50 条、间隔 1 秒算，抓全要 181 次请求 ≈ 3 分钟，
# 而且对一个免费练习站点没必要。
# 所以**主动截断，只抓前 500 本**（MAX_ITEMS = 500）——
# 这是明确的取舍，不是「抓全了」，README 里也写明了。
# 想抓全就把 MAX_ITEMS 改成 None，代码本身支持。
# ============================================================

import json
import time
from pathlib import Path

import requests

BASE_URL = "https://spa5.scrape.center"
LIST_API = BASE_URL + "/api/book/"
LIMIT = 50          # 每批 50 条
INTERVAL = 1.0      # 请求间隔 ≥ 1 秒
MAX_ITEMS = 500     # ★ 截断：最多抓 500 本。改成 None 就是抓全部 9040 本
MAX_PAGES = 300     # 安全阀

OUT_FILE = Path(__file__).parent / "data" / "spa5.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def get_json(url, params=None):
    """发 GET 请求 → 检查状态码 → 转成 Python 字典 → 歇 1 秒。"""
    resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    time.sleep(INTERVAL)
    return data


def clean_authors(authors):
    """把作者列表洗干净。

    接口返回的作者名里混着换行符和大段空格，例如：
        ["\n            董桥", "海豚简装"]
    这里做三件事：
      1. .strip() 去掉每个名字首尾的空白（包括换行）；
      2. 用 if a 过滤掉洗完变成空字符串的项；
      3. authors 有可能根本不是列表（缺字段时是 None），先兜个底。
    """
    if not authors:
        return []
    return [a.strip() for a in authors if a and a.strip()]


def main():
    print("开始抓取 spa5 图书数据……")

    # ---------- 第一步：先请求一次，从 count 读出总数，据此算要翻多少页 ----------
    first = get_json(LIST_API, {"limit": LIMIT, "offset": 0})
    total = first["count"]

    # 实际要抓多少条：总数和截断上限里取小的那个。min() 就是「取较小值」。
    target = total if MAX_ITEMS is None else min(total, MAX_ITEMS)

    # 要翻多少页？用「向上取整除法」：(a + b - 1) // b
    # 比如 500 条、每页 50 → (500+49)//50 = 10 页；
    # 如果是 501 条 → (501+49)//50 = 11 页（多出的 1 条也得单开一页）。
    # 直接写 500//50 在有余数时会少算一页，这个小技巧值得记住。
    pages = (target + LIMIT - 1) // LIMIT

    print(f"接口告诉我们一共有 {total} 本书")
    print(f"本次计划抓取 {target} 本（每页 {LIMIT} 条，共需翻 {pages} 页）")
    if MAX_ITEMS is not None and total > MAX_ITEMS:
        print(f"注意：总量 {total} 本超过上限，已截断为前 {MAX_ITEMS} 本，并非抓全。")

    books = list(first["results"])   # 第一页已经拿到了，先放进篮子
    print(f"进度：已抓取 {min(len(books), target)}/{target}")

    # ---------- 第二步：从第 2 页开始接着翻 ----------
    for page in range(2, pages + 1):
        offset = (page - 1) * LIMIT   # 第 N 页的 offset = (N-1) × limit
        data = get_json(LIST_API, {"limit": LIMIT, "offset": offset})
        batch = data.get("results", [])
        if not batch:
            print("这一页返回为空，提前结束。")
            break
        books.extend(batch)
        # 进度打印：让人看得到脚本在动，而不是干等着以为卡死了
        print(f"进度：已抓取 {min(len(books), target)}/{target}")
        if len(books) >= target:
            break
        if page >= MAX_PAGES:
            print(f"警告：已达安全上限 {MAX_PAGES} 页，主动停止。")
            break

    books = books[:target]   # 最后一页可能多拿几条，切一刀让数量刚好

    # ---------- 第三步：挑字段 + 清洗 + 存文件 ----------
    result = []
    for b in books:
        result.append({
            "name": b.get("name"),                        # 书名
            "authors": clean_authors(b.get("authors")),   # 作者（列表，已洗掉换行空格）
            "score": b.get("score"),                      # 评分（接口给的是字符串，如 "8.8"）
            "id": b.get("id"),                            # 图书 id，日后想抓详情要用
        })

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"完成！共 {len(result)} 条数据（站点总量 {total} 条，做了截断），已存到 {OUT_FILE}")


if __name__ == "__main__":
    main()
