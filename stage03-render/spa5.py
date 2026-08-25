"""
案例：spa5 · https://spa5.scrape.center
Issue：#4
目标：大批量浏览器渲染抓取，演示两个提速技巧——复用浏览器实例、拦截无用资源
"""

import json
import time
from pathlib import Path

from playwright.sync_api import Browser, Route, sync_playwright

# ---------------------------------------------------------------------------
# 上一个脚本（spa1）证明了浏览器渲染比调接口慢。但有些站你别无选择，
# 只能用浏览器。那问题就变成：既然非用不可，怎么把它用得快一点？
#
# 本脚本演示两个最有效的提速技巧，并且真的跑个对比给你看：
#
#   技巧①【复用浏览器实例】
#       启动一个 chromium 进程要 0.5~2 秒，是整个流程里最贵的一步。
#       新手最容易写的错误代码：在循环里每抓一页就 launch 一次浏览器。
#       抓 100 页 = 白白启动 100 次浏览器。正确做法是开一次，一直用。
#
#   技巧②【拦截图片/字体等无用资源】
#       我们要的是书名和作者这些文字，可浏览器不知道，
#       它老老实实把每一张封面图都下载下来（一页 18 张图！）。
#       用 page.route() 可以拦住这些请求直接 abort 掉——反正没人看这个页面长啥样。
#
#       ⚠️ 踩过的坑：一开始我把 CSS（stylesheet）也一起拦了，结果整个页面白屏，
#       .item 元素根本不出现，wait_for_selector 直接超时。
#       原因是这个站是 webpack 打包的 Vue 应用，页面组件是"按需加载"的：
#       JS 要同时把该组件的 js 块和 css 块都下载成功，才认为这个组件加载完成。
#       CSS 被我们掐断 → 加载失败 → 组件压根不渲染 → 一条数据都抓不到。
#       教训：拦资源能提速，但别把页面赖以运转的东西也拦了。图片、字体拦了没事，
#       CSS 要看站——像本站这种就必须放行。改动后一定要跑一遍验证还能抓到数据。
# ---------------------------------------------------------------------------

BASE_URL = "https://spa5.scrape.center"

# 目标条数。这个站一共 9040 本书（接口 count 字段说的），全抓要 500 多页，
# 对练习站点是骚扰，对你也没有额外收获，所以【明确截断到前 200 本】。
TARGET_BOOKS = 200
BOOKS_PER_PAGE = 18
# 向上取整算出要翻几页：200 / 18 = 11.1 → 12 页（抓到 216 本，最后砍到 200）。
# 这里的 (a + b - 1) // b 是整数向上取整的常用写法。
TOTAL_PAGES = (TARGET_BOOKS + BOOKS_PER_PAGE - 1) // BOOKS_PER_PAGE

REQUEST_INTERVAL = 1
TIMEOUT_MS = 30000

# 做速度对比时只抓 2 页就够了，别为了测速把人家站点打太狠。
BENCHMARK_PAGES = 2

OUTPUT_PATH = Path(__file__).parent / "data" / "spa5.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 这几类资源对"抓文字"毫无用处，全部拦掉。
# image=图片，font=字体文件，media=音视频。
# 注意这里【没有】stylesheet——原因见文件开头那段踩坑说明。
BLOCKED_TYPES = {"image", "font", "media"}


def block_useless(route: Route) -> None:
    """
    page.route() 的回调：每个即将发出的请求都会先经过这里，由我们裁决。
    route.abort()    = 掐掉这个请求，浏览器当它失败了（页面照样能渲染，只是没图）
    route.continue_() = 放行，正常发出去
    """
    if route.request.resource_type in BLOCKED_TYPES:
        route.abort()
    else:
        route.continue_()


def parse_books(page) -> list[dict]:
    """从当前已渲染好的页面里，把这一页 18 本书的信息抠出来。"""
    books = []
    for item in page.query_selector_all(".item"):
        name_el = item.query_selector("h3.name")
        authors_el = item.query_selector("p.authors")

        # 作者字段在页面上是"张三 / 李四"这种一整串，接口里则是个数组。
        # 这里按 / 拆开，并且把每一段前后的空白和换行去掉。
        authors_raw = authors_el.inner_text() if authors_el else ""
        authors = [a.strip() for a in authors_raw.split("/") if a.strip()]

        # 详情页链接长这样 /detail/7952978，末尾那串数字就是这本书的 id。
        link_el = item.query_selector("a")
        href = link_el.get_attribute("href") if link_el else ""
        book_id = href.rsplit("/", 1)[-1] if href else ""

        books.append(
            {
                "id": book_id,
                "name": name_el.inner_text().strip() if name_el else "",
                "authors": authors,
            }
        )
    return books


def crawl(
    browser: Browser, pages_to_crawl: int, block: bool, quiet: bool = False
) -> tuple[list[dict], float, dict]:
    """
    用【同一个】浏览器实例抓 pages_to_crawl 页。
    block=True 时开启资源拦截。
    返回：(书列表, 耗时秒数, 请求统计)

    注意这个函数只 new_page() 一次，然后在循环里反复 goto——
    这就是技巧①：一个标签页从头用到尾，不用抓一页开一个。
    """
    books: list[dict] = []
    # 统计两个数：浏览器"发起"了多少个图片请求，其中真正"下载完成"了几个。
    # 这两个数差得越多，说明越多请求是白发的（发出去又被取消）。
    stats = {"img_started": 0, "img_finished": 0}

    # 用独立的 context，等于给这一轮一个全新的浏览器缓存。
    # 不这么做的话，第二轮会直接命中第一轮留下的缓存，测出来的速度是假的。
    context = browser.new_context(user_agent=USER_AGENT)
    page = context.new_page()

    page.on(
        "request",
        lambda r: stats.__setitem__("img_started", stats["img_started"] + 1)
        if r.resource_type == "image"
        else None,
    )
    page.on(
        "requestfinished",
        lambda r: stats.__setitem__("img_finished", stats["img_finished"] + 1)
        if r.resource_type == "image"
        else None,
    )

    if block:
        # "**/*" 是通配符，意思是"所有请求都交给 block_useless 处理"。
        page.route("**/*", block_useless)

    start = time.time()
    for page_num in range(1, pages_to_crawl + 1):
        url = f"{BASE_URL}/page/{page_num}"
        if not quiet:
            print(f"  正在渲染：{url}")
        page.goto(url, timeout=TIMEOUT_MS)
        # 照例等元素出现，不用 sleep 死等。
        page.wait_for_selector(".item", timeout=TIMEOUT_MS)
        books.extend(parse_books(page))
        time.sleep(REQUEST_INTERVAL)

    elapsed = time.time() - start
    context.close()  # 用完把 context 关掉，免得开太多吃内存
    return books, elapsed, stats


def run_benchmark(browser: Browser) -> tuple[tuple[float, dict], tuple[float, dict]]:
    """
    对比实验：同样抓 2 页，关掉拦截 vs 打开拦截，各要多久、各发了多少图片请求。
    两边共用同一个 browser，所以"启动浏览器"的成本不掺进来，
    量出来的就是纯粹的"资源拦截"带来的影响。
    """
    print(f"\n【对比实验】同样抓 {BENCHMARK_PAGES} 页，看拦截资源到底有没有用")

    print("\n(1) 不拦截：让浏览器自由发挥")
    _, slow_seconds, slow_stats = crawl(browser, BENCHMARK_PAGES, block=False, quiet=True)
    print(f"    耗时 {slow_seconds:.2f} 秒")

    print("\n(2) 开启拦截：图片/字体/音视频全掐掉")
    _, fast_seconds, fast_stats = crawl(browser, BENCHMARK_PAGES, block=True, quiet=True)
    print(f"    耗时 {fast_seconds:.2f} 秒")

    return (slow_seconds, slow_stats), (fast_seconds, fast_stats)


def save(books: list[dict]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n已保存 {len(books)} 条数据到 {OUTPUT_PATH}")


def main() -> None:
    with sync_playwright() as p:
        # 技巧①的体现：整个脚本从头到尾，只在这里 launch 一次浏览器。
        # 下面的对比实验 + 正式抓取，全都复用这一个实例。
        launch_start = time.time()
        browser = p.chromium.launch(headless=True)
        launch_seconds = time.time() - launch_start
        print(f"启动浏览器耗时 {launch_seconds:.2f} 秒（这是最贵的一步，所以只做一次）")

        (slow_seconds, slow_stats), (fast_seconds, fast_stats) = run_benchmark(browser)

        # 正式抓取：开着拦截，抓满 200 本。
        print(f"\n【正式抓取】目标前 {TARGET_BOOKS} 本书，共 {TOTAL_PAGES} 页")
        books, crawl_seconds, _ = crawl(browser, TOTAL_PAGES, block=True)

        browser.close()

    # 12 页抓到 216 本，砍到正好 200 本。
    # 列表切片 [:200] 的意思是"只要前 200 个"。
    books = books[:TARGET_BOOKS]
    save(books)

    # -----------------------------------------------------------------------
    # 技巧① 的收益：实打实，而且是线性的
    # -----------------------------------------------------------------------
    print("\n" + "=" * 62)
    print("技巧① 复用浏览器实例")
    print("=" * 62)
    print(f"启动一次浏览器 = {launch_seconds:.2f} 秒")
    print(f"如果每抓一页都重开浏览器，抓 {TOTAL_PAGES} 页要白白多花")
    print(f"    {launch_seconds:.2f} × {TOTAL_PAGES - 1} ≈ {launch_seconds * (TOTAL_PAGES - 1):.1f} 秒")
    print(f"页数越多，省得越多——这个技巧任何时候都值得用。")

    # -----------------------------------------------------------------------
    # 技巧② 的收益：在本站【没测出提速】，如实记录并解释原因
    # -----------------------------------------------------------------------
    print("\n" + "=" * 62)
    print(f"技巧② 拦截图片/字体（同样抓 {BENCHMARK_PAGES} 页）")
    print("=" * 62)
    print(f"{'方式':<16}{'耗时(秒)':>12}{'发起图片请求':>16}{'真正下载完成':>16}")
    print("-" * 62)
    print(
        f"{'不拦截':<14}{slow_seconds:>12.2f}"
        f"{slow_stats['img_started']:>16}{slow_stats['img_finished']:>16}"
    )
    print(
        f"{'拦截':<15}{fast_seconds:>12.2f}"
        f"{fast_stats['img_started']:>16}{fast_stats['img_finished']:>16}"
    )
    print("-" * 62)

    diff = slow_seconds - fast_seconds
    if diff > 0:
        print(f"结论：拦截快了 {diff:.2f} 秒（{diff / slow_seconds * 100:.1f}%）")
    else:
        print(f"结论：拦截反而慢了 {-diff:.2f} 秒——【没有提速】，如实记录。")

    # -----------------------------------------------------------------------
    # 为什么在这个站上拦截没提速？这是本脚本最值得记住的一课：
    #
    # 看上面那张表的最后两列：不拦截时浏览器"发起"了几十个图片请求，
    # 但"真正下载完成"的只有个位数。为什么？因为我们用的是 wait_for_selector：
    # 书名一出现就立刻抓数据、然后马上 goto 下一页——
    # 这时候那些封面图还在半路上，直接被浏览器取消了。
    #
    # 也就是说：**图片本来就不在我们的关键路径上，它没耽误我们时间**，
    # 所以拦掉它自然也省不出时间。反过来，page.route() 本身是有成本的：
    # 每一个请求都要从浏览器绕回 Python 问一句"这个要不要拦"，
    # 几十个请求绕下来，开销甚至盖过了省下的那点东西。
    #
    # 那这个技巧是不是没用？不是，它在这些场景下才真正回本：
    #   1. 你用的是 wait_until="networkidle" 或者要等页面完全加载——
    #      这时图片就在关键路径上，拦掉立竿见影
    #   2. 图片又大又多（比如电商大图站），或者你的带宽很小
    #   3. 你想对目标站点客气一点：拦截后这 38 个图片请求根本不会发出去，
    #      省的是【人家的】流量和带宽——这条理由本身就够充分了
    #
    # 真正的教训是：**优化要先测，别凭感觉**。
    # 网上都说"拦图片能提速"，但在你自己的站点和等待策略下到底成不成立，
    # 跑一次对比实验才知道。测出来没用就如实写没用，别为了好看编个数字。
    # -----------------------------------------------------------------------
    print(
        "\n（为什么没提速？看表格最后两列：不拦截时发起的图片请求大多没下载完就被取消了，"
        "\n  说明图片本来就没挡我们的路。详细解释见本文件末尾注释。）"
    )
    print(f"\n正式抓取 {TOTAL_PAGES} 页共耗时 {crawl_seconds:.2f} 秒，得到 {len(books)} 本书。")


if __name__ == "__main__":
    main()
