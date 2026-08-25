"""
案例：antispider4 · https://antispider4.scrape.center
Issue：#6
反爬手段：字体/CSS 伪装。评分数字根本不在 HTML 里，
         HTML 里只有一堆空标签 <i class="icon icon-789">，
         真正的数字藏在 CSS 的 ::before 里，再由一个特制字体画出来
目标：解出 class 名到真实数字的对应表，把评分还原出来
"""

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin

import requests
from fontTools.ttLib import TTFont
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    电影评分"9.5"在网页上看得清清楚楚，但你去看 HTML 源码，只有：
#        <p class="score">
#          <span><i class="icon icon-789"></i></span>
#          <span><i class="icon icon-981"></i></span>
#          <span><i class="icon icon-504"></i></span>
#        </p>
#    三个**完全空**的 <i> 标签。文字一个都没有。
#
# ② 它是怎么认出爬虫的？
#    同样不认爬虫，走的是"让你抓不到"的路子，两层：
#    第一层：数字写在 CSS 里，用的是 ::before 伪元素
#            （.icon-789:before{content:"9"}）。
#            伪元素是 CSS "凭空造"出来的内容，它不属于 HTML 文档，
#            ★ 这就是为什么用鼠标选中网页上的评分去复制，什么都复制不到 ★
#            —— 你的鼠标能看见它，却选不中它，因为它压根不是文档里的字。
#            爬虫拿到的 HTML 里当然也没有。
#    第二层：class 名字是**乱编的三位数**。icon-789 是 "9"、icon-981 是 "."、
#            icon-504 是 "5"、icon-272 是 "0"…… 数字和 class 名毫无关系，
#            纯粹是打乱的查找表。你不去读那个 264KB 的 CSS，就永远猜不出来。
#    再加上一个自定义字体（font-family: scrape），把数字画成特殊字形。
#
# ③ 我们用什么办法绕过？
#    照着浏览器的流程自己走一遍：
#    第 1 步 用 Playwright 渲染页面，拿到 <i> 的 class 名（icon-789 …）
#    第 2 步 下载站点的 CSS，正则抠出所有 .icon-XXX:before{content:"Y"} 的对应关系
#    第 3 步 用 fontTools 打开 @font-face 引用的 .woff 字体，读它的 cmap 表
#            （cmap = character map，"哪个字符编码对应哪个字形"的对照表），
#            检查字体有没有在字形层面再做一次错位
#    第 4 步 按对照表把 class 名翻译回数字
#
#    ★ 本次实测的诚实结论（重要）：
#      读出来的 cmap 是 '0'→zero、'1'→one …… '9'→nine、'.'→period，
#      **全是标准字形名，字体并没有把 9 画成 5 这种错位**。
#      也就是说这个站的秘密 100% 在 CSS 那张乱序查找表里，字体只是障眼法。
#      （已用截图肉眼核对：页面显示 9.5，CSS 解出 9.5，API 也是 9.5，三者一致。）
#      如果哪天字体真做了错位，cmap 里就会看到 '9'→'uniE5A1' 这种对不上号的名字，
#      那时才需要去比对字形轮廓。这一步的价值是**排除**了一种可能，不是白做。
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider4.scrape.center"
TOTAL_PAGES = 11          # 站点共 104 部电影，每页 10 部
REQUEST_INTERVAL = 1
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider4.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def build_icon_table(css_urls: list) -> dict:
    """下载 CSS，抠出 {class后缀: 真实字符} 的对照表。"""
    table = {}
    for url in css_urls:
        css = requests.get(url, headers=HEADERS, timeout=30).text
        # 只要数字和小数点这几种，评分用得上的就这些
        for key, char in re.findall(r'\.icon-(\d+):before\{content:"([\d.])"\}', css):
            table[key] = char
    return table


def inspect_font(css_urls: list) -> None:
    """把自定义字体下载下来，用 fontTools 读 cmap，看字体有没有做字形错位。"""
    for url in css_urls:
        css = requests.get(url, headers=HEADERS, timeout=30).text
        # 在 @font-face 里找 font-family:scrape 那一段，取它的 .woff 地址
        block = re.search(r"@font-face\{font-family:scrape;[^}]*\}", css)
        if not block:
            continue
        woff = re.search(r"url\(([^)]+\.woff)\)", block.group())
        if not woff:
            continue
        font_url = urljoin(url, woff.group(1))
        print(f"  字体文件：{font_url}")
        data = requests.get(font_url, headers=HEADERS, timeout=30).content
        tmp = Path(__file__).parent / "data" / "antispider4_font.woff"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)

        font = TTFont(tmp)
        cmap = font.getBestCmap()   # {unicode码点: 字形名}
        print(f"  字体共 {len(cmap)} 个字形。数字部分的 cmap：")
        rows = [f"{ch}->{cmap.get(ord(ch))}" for ch in "0123456789."]
        print("    " + "  ".join(rows))
        standard = {
            "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
            "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
            ".": "period",
        }
        scrambled = [c for c, g in standard.items() if cmap.get(ord(c)) != g]
        if scrambled:
            print(f"    ⚠️ 字体在字形层面做了错位，涉及：{scrambled}")
        else:
            print("    ✅ 字形名全部标准 → 字体没做错位，秘密全在 CSS 的对照表里")
        return


def main() -> None:
    movies = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector(".item", timeout=60000)

        # 页面用到哪些 CSS，直接问浏览器要，不要把文件名写死
        #（那些文件名带哈希值，站点一改版就变）
        css_urls = page.evaluate(
            "() => Array.from(document.querySelectorAll('link[rel=stylesheet]')).map(e => e.href)"
        )
        print("页面加载的 CSS：")
        for u in css_urls:
            print("  " + u)

        print("\n【第 3 步】用 fontTools 检查字体：")
        inspect_font(css_urls)

        icon_table = build_icon_table(css_urls)
        print(f"\n【第 2 步】从 CSS 解出的对照表（共 {len(icon_table)} 项）：")
        print("  " + json.dumps(icon_table, ensure_ascii=False))

        print("\n【第 4 步】逐页翻译评分：")
        for page_index in range(1, TOTAL_PAGES + 1):
            page.goto(f"{BASE_URL}/page/{page_index}", wait_until="domcontentloaded",
                      timeout=60000)
            try:
                page.wait_for_selector(".item", timeout=15000)
            except PlaywrightTimeoutError:
                # 实测：API 说共 104 部（第 11 页还有 4 条测试数据），
                # 但前端翻到第 11 页时页面是空的 —— 这是站点自己的分页上限，
                # 不是被反爬拦了。抓到哪算哪，如实记录，不硬等。
                print(f"  第 {page_index} 页：页面没有渲染出任何条目，到此为止")
                break
            for card in page.query_selector_all(".item"):
                name_el = card.query_selector("h2")
                icons = card.query_selector_all("p.score i.icon")
                keys = [
                    (i.get_attribute("class") or "").split("icon-")[-1] for i in icons
                ]
                score = "".join(icon_table.get(k, "?") for k in keys)
                infos = [i.inner_text().strip() for i in card.query_selector_all(".info")]
                movies.append(
                    {
                        "name": name_el.inner_text().strip() if name_el else None,
                        "categories": [
                            c.inner_text().strip()
                            for c in card.query_selector_all(".categories button span")
                        ],
                        "info": infos[0] if len(infos) > 0 else None,
                        "published_at": infos[1] if len(infos) > 1 else None,
                        "score_raw": keys,   # 源码里的 class 后缀，留着对比看
                        "score": score,      # 翻译出来的真实评分
                    }
                )
            print(f"  第 {page_index} 页：累计 {len(movies)} 部")
            if page_index == 1:
                for m in movies[:3]:
                    print(f"    {m['name'][:16]:20} {m['score_raw']} → {m['score']}")
            time.sleep(REQUEST_INTERVAL)
        browser.close()

    # 自我验证：跟站点自带 API 的干净评分逐条对一下
    # 这一步是"跟标准答案对答案"。它排在 Playwright 抓完 10 页之后，
    # 如果这里因为一次网络抖动挂掉，前面五分钟的活就白干了 —— 实测发生过一次。
    # 所以加上退避重试：1s → 2s → 4s，三次都失败才真的放弃（并把异常抛出去，
    # 不能悄悄跳过校验假装成功，那样准确率就成了没人验过的空话）。
    api = None
    for attempt in range(3):
        try:
            api = requests.get(
                f"{BASE_URL}/api/movie/?limit=200&offset=0", headers=HEADERS, timeout=30
            ).json()["results"]
            break
        except Exception as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  校验接口第 {attempt + 1} 次失败（{type(exc).__name__}），{wait} 秒后重试")
            time.sleep(wait)
    expected = {m["name"]: str(m["score"]) for m in api}
    checked = matched = 0
    for m in movies:
        want = expected.get((m["name"] or "").split(" - ")[0])
        if want is not None:
            checked += 1
            matched += int(want == m["score"])

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(movies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rate = matched / checked * 100 if checked else 0
    print(f"\n翻译准确率（跟站点 API 的标准答案比对）：{matched}/{checked} = {rate:.1f}%")
    print(f"共 {len(movies)} 部，已写入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
