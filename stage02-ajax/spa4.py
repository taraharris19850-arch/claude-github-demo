"""
案例：spa4 · https://spa4.scrape.center
Issue：#3
接口：GET /api/news/?limit=100&offset=0
目标：不解析 HTML，直接调接口拿全部新闻数据
"""

# ============================================================
# 这个接口是怎么找到的？（这次猜错了一次，过程更值得看）
# ============================================================
# spa4 是「新闻索引站」，页面同样是空壳 SPA，没有页码按钮。
#
# 第一次猜：照着 spa1/spa3 的经验试 /api/movie/
#     curl -s "https://spa4.scrape.center/api/movie/?limit=2&offset=0"
#   返回：<h1>Not Found</h1>  →  猜错了。
#   这是正常的，说明**接口路径跟站点内容有关**，不是所有练习站都叫 movie。
#
# 第二次猜：这是新闻站，那就试 /api/news/
#     curl -s "https://spa4.scrape.center/api/news/?limit=2&offset=0"
#   返回了一大坨 JSON  →  猜中了。
#
# 如果两次都猜不中怎么办？用「翻 JS 源码」这个更可靠的办法：
#     curl -s https://spa4.scrape.center/ | grep -o '/js/app[^"]*\.js'
#     curl -s "https://spa4.scrape.center/js/app.xxxx.js" | grep -o '/api/[a-z]*'
#   前端代码里必然写死了接口路径，grep 一下就出来了。这招对任何 SPA 都管用。
#
# 参数含义（跟前两个案例是同一套约定）：
#   limit  = 这一批要几条
#   offset = 跳过前面多少条
#
# 返回结构（先打印一条原始 JSON 看清楚，再决定取哪些字段）：
#   {"count": 451370, "results": [ {...} ]}
#   每条新闻的字段是：
#     id           内部编号
#     title        标题                ← 要
#     code         站内编码（没啥用）
#     url          新闻原文链接         ← 要
#     source       来源（实测大多是 null，空的）
#     domain       来源域名，如 news.sina.com.cn   ← 要（source 空时靠它认来源）
#     website      来源站点中文名，如「新浪新闻」   ← 要（这才是真正好用的「来源」）
#     thumb        缩略图地址
#     published_at 发布时间             ← 要
#     updated_at   入库更新时间
#   ★ 教训：作业要求取「来源」，如果想当然直接取 source 字段，
#     存出来会是一整列 null。所以**动手前一定先打印一条原始数据看清结构**。
#     本脚本运行时会先打印一条完整原始 JSON，就是为了养成这个习惯。
#
# ============================================================
# ★ 关于数据量：本脚本做了截断，只抓前 500 条
# ============================================================
# 接口返回的 count 是 451370 —— 四十五万条新闻。
# 按每批 100 条、每次请求间隔 1 秒算，抓全需要 4514 次请求 ≈ 75 分钟，
# 而且会给这个免费练习站点造成不必要的压力。
# 所以这里**主动截断，只抓前 500 条**（MAX_ITEMS = 500）。
# 这是明确的取舍，不是「抓全了」——README 里也写明了这一点。
# 如果你真想抓全，把 MAX_ITEMS 改成 None 即可，代码逻辑本身是支持抓全的。
# ============================================================

import json
import time
from pathlib import Path

import requests

BASE_URL = "https://spa4.scrape.center"
LIST_API = BASE_URL + "/api/news/"
LIMIT = 100         # 每批 100 条（接口允许，比默认的一次几条效率高得多）
INTERVAL = 1.0      # 请求间隔 ≥ 1 秒
MAX_ITEMS = 500     # ★ 截断：最多只抓 500 条。改成 None 就是抓全部
MAX_PAGES = 200     # 安全阀，防止死循环

OUT_FILE = Path(__file__).parent / "data" / "spa4.json"

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


def main():
    print("开始抓取 spa4 新闻数据……")

    items = []
    offset = 0
    total = None

    for page in range(MAX_PAGES):
        data = get_json(LIST_API, {"limit": LIMIT, "offset": offset})

        if total is None:
            total = data.get("count")
            print(f"接口告诉我们一共有 {total} 条新闻")
            # ★ 第一次请求时，先原样打印一条完整的新闻 JSON。
            #   目的是「看清结构再决定取哪些字段」，这是本阶段最该养成的习惯。
            if data.get("results"):
                print("--- 一条原始新闻数据长这样（看清结构再取字段）---")
                print(json.dumps(data["results"][0], ensure_ascii=False, indent=2))
                print("--- 原始数据结束 ---")

        batch = data.get("results", [])
        if not batch:                    # 返回空了，说明翻到底
            print("这一批返回为空，停止。")
            break

        items.extend(batch)
        offset += LIMIT                  # 递增 offset 换下一批

        # 达到截断上限就停。[:MAX_ITEMS] 是「切片」：只保留前 MAX_ITEMS 个元素，
        # 因为最后一批可能会多拿几条，切一刀让数量刚好。
        if MAX_ITEMS is not None and len(items) >= MAX_ITEMS:
            items = items[:MAX_ITEMS]
            print(f"已达到设定的截断上限 {MAX_ITEMS} 条，停止抓取。")
            break

        if total is not None and len(items) >= total:
            print("已抓够接口声明的总数，停止。")
            break

        print(f"  已抓取 {len(items)} 条")

    # 只挑关心的字段存下来
    result = []
    for n in items:
        result.append({
            "title": n.get("title"),                # 标题
            "published_at": n.get("published_at"),  # 发布时间
            # 来源：优先用 website（中文站名，如「新浪新闻」）；
            # 它要是空的，就退而用 source；再空就用域名 domain。
            # `或` 运算在 Python 里的效果是「前面的值是空的就取后面的」。
            "source": n.get("website") or n.get("source") or n.get("domain"),
            "url": n.get("url"),                    # 新闻原文链接
        })

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"完成！共 {len(result)} 条数据（总量 {total} 条，做了截断），已存到 {OUT_FILE}")


if __name__ == "__main__":
    main()
