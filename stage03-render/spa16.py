"""
案例：spa16 · https://spa16.scrape.center
Issue：#4
目标：用 httpx 对比 HTTP/2 与 HTTP/1.1，打印实际协商到的协议版本，并抓取图书数据
"""

import json
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# 这个站点专门用来演示 HTTP/2。它有个很硬气的脾气：**只认 HTTP/2，不认 HTTP/1.1**。
# 你用 HTTP/1.1 去敲门，它理都不理，直接把连接掐了。
# （下面的 probe_protocol() 会把这个现象真的跑一遍给你看。）
#
# 【HTTP/2 比 HTTP/1.1 强在哪？——大白话版】
#
# 想象你去银行办事：
#
#   HTTP/1.1 = 一个窗口，一次只能办一件事。
#       你要办 5 件事，就得排 5 次队；办完一件才能办下一件。
#       浏览器嫌太慢，就耍了个花招：同时开 6 个窗口（6 条 TCP 连接）。
#       但也就 6 个，再多就得等——这就是所谓的「队头阻塞」：
#       排在前面那件事卡住了，后面的只能干等着。
#
#   HTTP/2 = 还是一个窗口，但可以「同时」办很多件事。
#       你把 5 件事一起递进去，柜员并行处理，谁先办完谁先给你。
#       这就叫【多路复用】(multiplexing)：一条连接上同时跑多个请求，不用排队。
#
# 除了多路复用，HTTP/2 还有两个实惠：
#   · 头部压缩（HPACK）：每个请求都要带 User-Agent、Cookie 这些重复的头，
#     HTTP/1.1 每次都原样重发一遍，HTTP/2 把重复的部分压掉，省流量。
#   · 二进制分帧：HTTP/1.1 传的是纯文本，HTTP/2 传的是二进制帧，机器解析更快更不容易出错。
#
# 【对爬虫的实际意义】
#   1. 有些站（比如本站）压根不给 HTTP/1.1 开门，你不上 HTTP/2 就抓不到数据
#   2. 你的 requests 库【不支持】HTTP/2，遇到这种站只能干瞪眼，
#      所以这里换成 httpx——它是"支持 HTTP/2 的 requests"，用法几乎一模一样
#   3. 反爬角度：只支持 HTTP/1.1 的客户端本身就是一种特征，
#      真实浏览器现在基本都走 HTTP/2，你走 HTTP/1.1 反而显眼
#
# 【小坑提醒】用 curl 手动验证接口时，URL 一定要用引号包起来：
#     curl "https://spa16.scrape.center/api/book/?limit=18&offset=0"
#   不加引号的话，zsh 会把 ? 和 & 当成它自己的特殊符号，
#   报一个莫名其妙的 "no matches found" 错误。
# ---------------------------------------------------------------------------

BASE_URL = "https://spa16.scrape.center"

# 这个站的图书接口和 spa5 是同一套（一共 9040 本）。
# 同样【只抓前 200 本】——练手够用，也不去骚扰人家站点。
TARGET_BOOKS = 200
BOOKS_PER_PAGE = 18
TOTAL_PAGES = (TARGET_BOOKS + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE

REQUEST_INTERVAL = 1
TIMEOUT = 30

OUTPUT_PATH = Path(__file__).parent / "data" / "spa16.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def probe_protocol() -> None:
    """
    分别以 http2=True 和 http2=False 请求同一个地址，把实际协商到的协议打印出来。
    这是"眼见为实"环节——不看这个，你只会背概念，不会真的相信。

    小知识：客户端和服务器是怎么"商量"用哪个协议的？
    在 HTTPS 握手的时候有个叫 ALPN 的环节，客户端说"我会 h2 和 http/1.1"，
    服务器挑一个回："那就 h2 吧"。httpx 的 http2=True 就是让它在这一步把 h2 报上去。
    """
    print("=" * 62)
    print("实验一：同一个地址，分别用 HTTP/2 和 HTTP/1.1 去请求")
    print("=" * 62)

    url = f"{BASE_URL}/api/book/?limit=1&offset=0"

    for use_http2 in (True, False):
        label = "HTTP/2" if use_http2 else "HTTP/1.1"
        print(f"\n[{label}] httpx.Client(http2={use_http2})")
        try:
            # trust_env=False：不去读系统的代理环境变量。
            # 加这个是为了让实验结果干净——排除"是不是代理捣的鬼"这种干扰。
            with httpx.Client(
                http2=use_http2, timeout=TIMEOUT, headers=HEADERS, trust_env=False
            ) as client:
                response = client.get(url)
                # response.http_version 就是【实际】用上的协议，不是你请求的那个。
                # 这个区别很重要：你写 http2=True，如果服务器不支持，
                # 它会悄悄退回 HTTP/1.1，这里才看得出真相。
                print(f"    实际协商到的协议：{response.http_version}")
                print(f"    状态码：{response.status_code}")
        except httpx.HTTPError as exc:
            # 注意：这里【预期】会失败——本站不支持 HTTP/1.1。
            # 失败本身就是实验结果，所以我们把它抓住打印出来，而不是让脚本崩掉。
            print(f"    请求失败：{type(exc).__name__}: {exc}")
            print("    ↑ 这不是 bug，是本站的设计：它只跟 HTTP/2 说话。")

    print("\n结论：http2=True 才拿得到数据；http2=False 直接被服务器掐断连接。")
    print("这就是为什么这一关必须用 httpx 而不能用 requests——requests 不支持 HTTP/2。")


def fetch_books() -> list[dict]:
    """
    用 HTTP/2 把前 200 本书抓下来。

    这里有个容易忽略的细节：整个循环共用【同一个】 Client。
    这不只是少写几行代码——HTTP/2 的多路复用是"一条连接上跑多个请求"，
    每次都新建 Client 等于每次都重新握手建连接，多路复用的好处就全浪费了。
    （和 spa5 里"复用浏览器实例"是同一个道理：贵的东西要重复利用。）
    """
    print("\n" + "=" * 62)
    print(f"实验二：用 HTTP/2 抓取前 {TARGET_BOOKS} 本书")
    print("=" * 62)

    books: list[dict] = []

    with httpx.Client(
        http2=True, timeout=TIMEOUT, headers=HEADERS, trust_env=False
    ) as client:
        for page_num in range(1, TOTAL_PAGES + 1):
            offset = (page_num - 1) * BOOKS_PER_PAGE
            url = f"{BASE_URL}/api/book/?limit={BOOKS_PER_PAGE}&offset={offset}"
            print(f"[{page_num}/{TOTAL_PAGES}] {url}")

            response = client.get(url)
            response.raise_for_status()

            for book in response.json()["results"]:
                # 作者字段里混着换行和多余空格（接口原始数据就这样），清理一下。
                authors = [a.strip() for a in (book.get("authors") or []) if a.strip()]
                books.append(
                    {
                        "id": book["id"],
                        "name": book["name"],
                        "authors": authors,
                        "score": book.get("score") or "",
                        "http_version": response.http_version,  # 留个证据：确实是 HTTP/2 抓的
                    }
                )

            # 老规矩，每页之间歇 1 秒。
            time.sleep(REQUEST_INTERVAL)

    return books[:TARGET_BOOKS]


def save(books: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已保存 {len(books)} 条数据到 {OUTPUT_PATH}")


def main() -> None:
    probe_protocol()
    books = fetch_books()
    save(books)

    # 顺手统计一下：这 200 条是不是真的全都走的 HTTP/2。
    versions = {b["http_version"] for b in books}
    print(f"这批数据用到的协议版本：{versions}")


if __name__ == "__main__":
    main()
