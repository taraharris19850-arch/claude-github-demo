"""
案例：spa1 · https://spa1.scrape.center
Issue：#4
目标：用 Playwright 驱动真浏览器渲染页面后再取数据，与直接调接口对比耗时
"""

import json
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# 这个站点和阶段1的 ssr1 长得几乎一样，但骨子里完全不同：
#
#   ssr1（阶段1）：服务器直接把带电影名字的 HTML 发给你     → requests 一抓就有
#   spa1（本阶段）：服务器只发一个空壳 HTML + 一堆 JS      → requests 抓下来是空的
#
# 空壳里只有 <div id="app"></div>，电影列表是 JS 在浏览器里跑起来之后，
# 自己再去调接口拿数据、再把 DOM 一个个插进去的。这种站叫 SPA（单页应用）。
#
# 对付 SPA 有两条路，本脚本把两条路都走一遍做对比：
#   路线 A：开一个真浏览器（Playwright），让 JS 跑完，再从渲染好的 DOM 里抠文字
#   路线 B：绕过页面，直接调 JS 在背后调的那个接口（/api/movie/），拿现成的 JSON
# ---------------------------------------------------------------------------

BASE_URL = "https://spa1.scrape.center"
TOTAL_PAGES = 10  # 每页 10 条，10 页共 100 部

# 两次请求之间至少歇 1 秒，别把练习站点打挂——这是爬虫最基本的礼貌。
REQUEST_INTERVAL = 1

# 浏览器渲染本身就慢（要下载 JS、执行 JS、等接口返回），超时给足 30 秒。
# 单位是毫秒，这是 Playwright 的约定。
TIMEOUT_MS = 30000

OUTPUT_PATH = Path(__file__).parent / "data" / "spa1.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def split_title(raw: str) -> tuple[str, str]:
    """
    页面上标题是"霸王别姬 - Farewell My Concubine"这样拼在一起的，
    而接口里 name 和 alias 是分开两个字段。为了两边能对比，这里拆一下。
    split(" - ", 1) 里的 1 表示"最多只拆一刀"，防止英文名里本来就带 - 被拆碎。
    """
    parts = raw.split(" - ", 1)
    name = parts[0].strip()
    alias = parts[1].strip() if len(parts) > 1 else ""
    return name, alias


# ---------------------------------------------------------------------------
# 路线 A：真浏览器渲染
# ---------------------------------------------------------------------------
def scrape_with_browser() -> tuple[list[dict], float, int]:
    """
    用 Playwright 开一个无头浏览器，逐页打开、等数据出现、再抠 DOM。
    返回：(电影列表, 耗时秒数, 实际发出的 HTTP 请求数)
    """
    movies: list[dict] = []
    request_count = 0
    start = time.time()

    # sync_playwright() 要用 with 包起来，退出时它会自动把浏览器进程收干净，
    # 不然容易留下一堆僵尸 chromium 进程占内存。
    with sync_playwright() as p:
        # headless=True 表示"无头"：浏览器在后台跑，不弹窗口出来晃眼。
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS["User-Agent"])

        # 挂一个监听器，浏览器每发一个 HTTP 请求就 +1。
        # 这行是本脚本的重点之一：你会看到浏览器为了显示这一页，
        # 悄悄发了几十个请求（HTML、JS、CSS、每张海报图……），而接口方案只要 1 个。
        counter = {"n": 0}
        page.on("request", lambda _req: counter.__setitem__("n", counter["n"] + 1))

        for page_num in range(1, TOTAL_PAGES + 1):
            url = f"{BASE_URL}/page/{page_num}"
            print(f"[浏览器] 正在渲染：{url}")
            page.goto(url, timeout=TIMEOUT_MS)

            # 关键：等元素出现，而不是 sleep(3) 死等。
            # sleep 是"闭着眼睛赌 3 秒够了"——网慢了就抓空，网快了就白等。
            # wait_for_selector 是"盯着页面，.item 一出现就立刻往下走"，又快又稳。
            page.wait_for_selector(".item", timeout=TIMEOUT_MS)

            for item in page.query_selector_all(".item"):
                title_el = item.query_selector("h2.m-b-sm")
                name, alias = split_title(title_el.inner_text() if title_el else "")

                # 类别是一排按钮，每个按钮里一个 span，文字里带换行和空格，要 strip 掉。
                categories = [
                    el.inner_text().strip()
                    for el in item.query_selector_all(".categories span")
                ]

                score_el = item.query_selector(".score")
                score = score_el.inner_text().strip() if score_el else ""

                # 上映时间在第二个 .info 里，长这样："1993-07-26 上映"，
                # 把结尾的"上映"两个字去掉，只留日期。
                published_at = ""
                infos = item.query_selector_all(".info")
                if len(infos) > 1:
                    published_at = infos[1].inner_text().replace("上映", "").strip()

                movies.append(
                    {
                        "name": name,
                        "alias": alias,
                        "categories": categories,
                        "score": score,
                        "published_at": published_at,
                    }
                )

            time.sleep(REQUEST_INTERVAL)

        request_count = counter["n"]
        browser.close()

    return movies, time.time() - start, request_count


# ---------------------------------------------------------------------------
# 路线 B：直接调接口
# ---------------------------------------------------------------------------
def scrape_with_api() -> tuple[list[dict], float, int]:
    """
    绕过页面，直接调 JS 在背后调的接口。
    接口地址是在浏览器开发者工具的 Network 面板里翻出来的：
        /api/movie/?limit=10&offset=0
    limit 是"这一页要几条"，offset 是"从第几条开始"，
    所以第 N 页的 offset = (N-1) * limit——分页接口基本都是这个套路。
    返回：(电影列表, 耗时秒数, 请求数)
    """
    movies: list[dict] = []
    request_count = 0
    start = time.time()

    limit = 10
    for page_num in range(1, TOTAL_PAGES + 1):
        offset = (page_num - 1) * limit
        url = f"{BASE_URL}/api/movie/?limit={limit}&offset={offset}"
        print(f"[接口] 正在请求：{url}")

        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()  # 状态码不是 200 就直接报错，别拿着错误页往下跑
        request_count += 1

        # 接口直接返回 JSON，字段清清楚楚，连解析 HTML 这一步都省了。
        for movie in response.json()["results"]:
            movies.append(
                {
                    "name": movie["name"],
                    "alias": movie.get("alias") or "",
                    "categories": movie["categories"],
                    "score": str(movie["score"]),
                    "published_at": movie.get("published_at") or "",
                }
            )

        time.sleep(REQUEST_INTERVAL)

    return movies, time.time() - start, request_count


def save(movies: list[dict]) -> None:
    """把结果写成 JSON 文件。"""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False 让中文按原样存，不然会变成 中文 这种鬼东西。
    OUTPUT_PATH.write_text(
        json.dumps(movies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已保存 {len(movies)} 条数据到 {OUTPUT_PATH}")


def main() -> None:
    browser_movies, browser_seconds, browser_requests = scrape_with_browser()
    print()
    api_movies, api_seconds, api_requests = scrape_with_api()

    # 存浏览器渲染的结果——本阶段练的就是渲染这条路。
    save(browser_movies)

    print("\n" + "=" * 58)
    print("耗时对比（同样抓 10 页 100 部电影）")
    print("=" * 58)
    print(f"{'方式':<14}{'耗时(秒)':>12}{'HTTP 请求数':>14}{'抓到条数':>12}")
    print("-" * 58)
    print(
        f"{'浏览器渲染':<12}{browser_seconds:>12.2f}"
        f"{browser_requests:>14}{len(browser_movies):>12}"
    )
    print(
        f"{'直接调接口':<12}{api_seconds:>12.2f}"
        f"{api_requests:>14}{len(api_movies):>12}"
    )
    print("-" * 58)
    # 注意：两种方式都各自 sleep 了 10 秒（每页 1 秒的礼貌间隔），
    # 所以这 10 秒是共同的固定成本，真正的差距要看减掉它之后的部分。
    print(f"倍数差：浏览器渲染耗时是直接调接口的 {browser_seconds / api_seconds:.1f} 倍")
    print(f"（其中各含 {TOTAL_PAGES} 秒的礼貌等待，扣掉后差距更悬殊：", end="")
    print(
        f"{(browser_seconds - TOTAL_PAGES) / max(api_seconds - TOTAL_PAGES, 0.01):.1f} 倍）"
    )

    # -----------------------------------------------------------------------
    # 结论：什么时候用哪条路？
    #
    # 【能找到接口就调接口】——首选，快一个数量级，还省内存。
    #   浏览器渲染慢在哪？它要老老实实做一遍人类用户做的事：
    #   下载 JS、启动 JS 引擎、执行 JS、发接口请求、拼 DOM、下载每一张海报图……
    #   而你要的其实只是那个接口返回的 JSON。绕开中间商，直接找源头。
    #
    # 【什么时候不得不上浏览器】：
    #   1. 翻遍 Network 面板也找不到接口 —— 数据可能直接写死在 JS 里
    #   2. 接口参数被加密 —— 比如带一个 token/sign 字段，是 JS 算出来的
    #      （这正是后面阶段 6「JS 逆向」要啃的硬骨头；在啃下来之前，
    #        用浏览器让 JS 自己把参数算出来，是最省事的过渡方案）
    #   3. 必须先登录、先点按钮、先滚动到底才出数据的交互式页面
    #   4. 站点有 JS 指纹检测，非浏览器的请求直接被拒
    #
    # 一句话：浏览器渲染是"打不过就加入"的兜底方案，不是默认方案。
    # -----------------------------------------------------------------------


if __name__ == "__main__":
    main()
