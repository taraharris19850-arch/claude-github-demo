"""
案例：antispider1 · https://antispider1.scrape.center
Issue：#6
反爬手段：检测 WebDriver，发现是自动化浏览器就不显示页面
目标：隐藏自动化特征，正常抓取电影数据
"""

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    JS 在页面里读一个叫 navigator.webdriver 的开关。
#    浏览器被程序（Selenium / Playwright）操控时，浏览器自己会把这个开关拨到 true，
#    等于举手说"我不是人在点，我是被程序遥控的"。网站读到 true 就把正文换成
#    "Webdriver Forbidden."，什么数据都不给。
#
# ② 它是怎么认出爬虫的？
#    不是靠 IP，不是靠 User-Agent，而是靠这个浏览器**自曝身份**的标志位。
#    这是 W3C WebDriver 规范里明确要求的：被自动化控制的浏览器必须暴露这个标记。
#    也就是说，不是网站多聪明，是浏览器自己"打了小报告"。
#
# ③ 我们用什么办法绕过？
#    两层保险：
#    a) 启动时加 --disable-blink-features=AutomationControlled，
#       让 Chromium 从源头上不要设置这个标记；
#    b) 用 page.add_init_script() 注入一段 JS。这个 JS 的特别之处是：
#       它在**网站自己的脚本运行之前**就执行。所以等网站的检测代码开始跑时，
#       navigator.webdriver 早就被我们改成 undefined 了。
#       顺序是关键 —— 页面加载完再改就晚了，检测早就跑完了。
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider1.scrape.center"
TOTAL_PAGES = 10
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider1.json"

# 这段 JS 会在每个页面的最开头执行，赶在网站的检测代码前面。
# Object.defineProperty 的作用是"重新定义某个属性长什么样"，
# 这里把 navigator.webdriver 的取值器改成永远返回 undefined，
# 也就是伪装成"这个浏览器根本没有这个属性"——普通人用的浏览器就是这样。
STEALTH_SCRIPT = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
"""


def demo_without_stealth(playwright) -> None:
    """演示：不做任何伪装时，页面上只有一句 'Webdriver Forbidden.'。

    注意这里**单独开了一个全新的浏览器**，而且不加任何启动参数。
    因为 --disable-blink-features=AutomationControlled 是**整个浏览器级别**的开关，
    只要启动时加了，这个浏览器开出来的所有页面都已经被伪装过了，
    再拿它做"对照组"就是自欺欺人 —— 对照组必须是真正干净的环境。
    """
    browser = playwright.chromium.launch()  # 干干净净，什么手脚都不做
    page = browser.new_page()
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)  # 给 Vue 一点时间把页面渲染出来
    print("【对照组】不伪装时：")
    print("  navigator.webdriver =", page.evaluate("() => navigator.webdriver"))
    print("  页面正文 =", repr(page.inner_text("body").strip()[:120]))
    browser.close()


def make_stealth_page(browser):
    """开一个"伪装过"的页面：注入脚本，把自动化特征抹掉。"""
    page = browser.new_page()
    # add_init_script：注册一段"每次导航前都先跑一遍"的脚本。
    page.add_init_script(STEALTH_SCRIPT)
    return page


def parse_page(page) -> list:
    """从已经渲染好的页面里，把这一页 10 部电影的信息抠出来。"""
    movies = []
    for card in page.query_selector_all(".el-card.item"):
        name_el = card.query_selector("h2")
        cats = [c.inner_text().strip() for c in card.query_selector_all(".categories button span")]
        infos = [i.inner_text().strip() for i in card.query_selector_all(".info")]
        score_el = card.query_selector("p.score")
        movies.append(
            {
                "name": name_el.inner_text().strip() if name_el else None,
                "categories": cats,
                # 第 1 行 info 是"地区 / 片长"，第 2 行是"上映时间"
                "info": infos[0] if len(infos) > 0 else None,
                "published_at": infos[1] if len(infos) > 1 else None,
                "score": score_el.inner_text().strip() if score_el else None,
            }
        )
    return movies


def main() -> None:
    all_movies = []
    with sync_playwright() as p:
        # 先跑对照组（干净浏览器），看看不伪装是什么下场
        demo_without_stealth(p)

        browser = p.chromium.launch(
            # 这个启动参数让 Chromium 不要主动暴露"我被自动化控制"这件事。
            args=["--disable-blink-features=AutomationControlled"]
        )
        print("\n【实验组】注入伪装脚本后：")
        page = make_stealth_page(browser)
        for i in range(1, TOTAL_PAGES + 1):
            url = f"{BASE_URL}/page/{i}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # 等到电影卡片真的出现为止；出现了就说明没被拦。
            page.wait_for_selector(".el-card.item", timeout=30000)
            movies = parse_page(page)
            all_movies.extend(movies)
            print(f"  第 {i} 页：拿到 {len(movies)} 条，累计 {len(all_movies)} 条")

        print("  navigator.webdriver =", page.evaluate("() => navigator.webdriver"))
        browser.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(all_movies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n共 {len(all_movies)} 条，已写入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
