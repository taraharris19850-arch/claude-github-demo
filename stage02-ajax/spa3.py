"""
案例：spa3 · https://spa3.scrape.center
Issue：#3
接口：GET /api/movie/?limit=10&offset=0
目标：不解析 HTML，直接调接口拿全部电影数据
"""

# ============================================================
# 这个接口是怎么找到的？
# ============================================================
# spa3 和 spa1 是同一批练习站点，页面外观几乎一样，区别只在**交互方式**：
#   - spa1：页面底部有「1 2 3 …」页码按钮，点一下换一页；
#   - spa3：没有页码，你得用鼠标滚轮往下拉，拉到底才自动加载下一批。
# 这在前端叫「滚动加载 / 无限滚动（infinite scroll）」。
#
# 找接口的办法和 spa1 完全一样（浏览器 F12 → Network → XHR，
# 或者 curl 猜路径验证）：
#     curl -s "https://spa3.scrape.center/api/movie/?limit=10&offset=0"
# 结果发现——接口跟 spa1 一模一样，也是 /api/movie/，也是 limit + offset。
#
# ============================================================
# ★ 本案例最重要的一个认知：滚动加载在接口层面 = offset 递增
# ============================================================
# 「翻页」和「滚动加载」看起来是两种完全不同的东西，
# 但那只是**前端给人看的外观差异**，跟数据怎么来的没关系：
#
#   点击「第 3 页」  →  前端发请求 offset=20
#   滚动到底第 3 次  →  前端发请求 offset=20
#
# 一模一样。区别只是「谁来触发这次请求」：一个是点击事件，一个是滚动事件。
# 对爬虫来说，我们根本不模拟点击也不模拟滚动，直接自己算 offset 发请求就行。
# 所以：**对爬虫而言，滚动式分页和页码式分页没有任何本质区别。**
#
# 这也是为什么很多人一看到无限滚动就想上 Selenium 去「模拟滚动」——
# 完全没必要，那是绕远路。看清接口就是一个循环的事。
#
# 参数含义（同 spa1，这套 limit/offset 是行业通用约定）：
#   limit  = 这一批要几条
#   offset = 跳过前面多少条
# 返回结构：{"count": 总条数, "results": [ {...}, {...} ]}
#
# 另外一个小发现：spa3 的**列表**接口就直接返回了 drama（剧情简介）和
# actors（演员表），而 spa1 的列表接口没有、必须再去请求详情接口。
# 这说明：不同站点接口设计不同，**动手前一定先打印一条原始数据看清结构**，
# 别想当然。
# ============================================================

import json
import time
from pathlib import Path

import requests

BASE_URL = "https://spa3.scrape.center"
LIST_API = BASE_URL + "/api/movie/"
LIMIT = 10        # 每批取 10 条
INTERVAL = 1.0    # 请求间隔 ≥ 1 秒
MAX_PAGES = 200   # 安全阀：万一循环条件写错，最多也只转 200 圈就停，不会无限跑下去

OUT_FILE = Path(__file__).parent / "data" / "spa3.json"

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


def fetch_all(list_api, limit=LIMIT):
    """通用的分页循环：不停地递增 offset，直到抓完为止。

    这个函数不关心网站是「点页码」还是「往下滚」，它只做一件事：
    从 offset=0 开始，每次 +limit，一直请求到没有数据为止。
    换个网站只要接口也是 limit/offset 风格，这段代码原样就能用。

    停止条件有三个，满足任意一个就停：
      1. 这一批返回的 results 是空列表 → 说明后面没数据了；
      2. 已经拿到的条数 >= 接口告诉我们的 count 总数 → 抓够了；
      3. 循环次数超过 MAX_PAGES → 安全阀，防止写错条件导致死循环。
    """
    items = []      # 攒所有数据的篮子
    offset = 0      # 从第 0 条开始
    total = None    # 总条数，第一次请求回来才知道

    for page in range(MAX_PAGES):
        data = get_json(list_api, {"limit": limit, "offset": offset})

        if total is None:                 # 只在第一次请求后记录总数
            total = data.get("count")
            print(f"接口告诉我们一共有 {total} 条数据")

        batch = data.get("results", [])   # 这一批拿到的数据

        # 停止条件 1：返回空了，说明翻到底了
        if not batch:
            print("这一批返回为空，说明已经抓完，停止。")
            break

        items.extend(batch)
        print(f"  第 {page + 1} 批：offset={offset}，本批 {len(batch)} 条，累计 {len(items)}/{total}")

        offset += limit   # ★ 这一行就是「滚动到底」的等价物

        # 停止条件 2：已经抓够 count 条了
        if total is not None and len(items) >= total:
            print("已抓够接口声明的总数，停止。")
            break
    else:
        # for...else：只有循环是「跑满 MAX_PAGES 次自然结束」才会走到这里
        print(f"警告：已达安全上限 {MAX_PAGES} 批，主动停止。")

    return items


def main():
    print("开始抓取 spa3 电影数据（滚动加载式分页）……")
    movies = fetch_all(LIST_API)

    # 只挑关心的字段。spa3 的列表接口里就带了 drama，省掉了请求详情这一轮。
    result = []
    for m in movies:
        result.append({
            "name": m.get("name"),                  # 片名
            "categories": m.get("categories", []),  # 类别
            "score": m.get("score"),                # 评分
            "regions": m.get("regions", []),        # 地区
            "minute": m.get("minute"),              # 片长（分钟）
            "drama": m.get("drama"),                # 剧情简介
        })

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"完成！共 {len(result)} 条数据，已存到 {OUT_FILE}")


if __name__ == "__main__":
    main()
