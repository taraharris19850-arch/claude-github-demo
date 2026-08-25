"""
案例：antispider3 · https://antispider3.scrape.center
Issue：#6
反爬手段：文字偏移。书名被拆成一个个字，在源码里顺序是打乱的，
         靠 CSS 的 left 定位把每个字"摆"回正确位置，所以只有眼睛看着是对的
目标：找出错乱规律，把书名还原成正确顺序
"""

import json
import re
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    "所见顺序 ≠ 源码顺序"。书名《清白家风》在网页上看着好好的，
#    但源码里四个字的排列是「清 家 风 白」—— 顺序是乱的。
#
# ② 它是怎么认出爬虫的？
#    这个站其实**不认爬虫**，它谁都不拦。它玩的是另一招：
#    让你抓到的数据是**错的**，而且错得很隐蔽 —— 你以为抓成功了，
#    存进数据库才发现一堆乱码般的书名。这比直接封你更阴。
#
# ③ 我们用什么办法绕过？
#    ── 发现规律的过程（这段比结论值钱）──
#    第 1 步：用 Playwright 渲染页面，把第一本书的书名标签打印出来看。
#             看到的是：<h3 class="name whole">Wonder</h3> —— 短书名是完整的。
#    第 2 步：往下翻，看到第二本书长这样：
#             <h3 class="m-b-sm name">
#               <span class="char" style="left: 0px;">清</span>
#               <span class="char" style="left: 32px;">家</span>
#               <span class="char" style="left: 48px;">风</span>
#               <span class="char" style="left: 16px;">白</span>
#             </h3>
#             ↑ 每个字一个 <span>，每个 span 上带一个 style="left: N px"。
#    第 3 步：关键一眼 —— 这些 left 值是 0 / 16 / 32 / 48，正好是 16 的倍数，
#             也就是"第 0 个字位、第 1 个字位、第 2 个字位、第 3 个字位"。
#             16px 就是一个汉字的宽度。
#             按 left 从小到大排：0=清, 16=白, 32=家, 48=风 → "清白家风"。对上了！
#    第 4 步：结论 —— **left 值就是这个字的真实位置**。源码里 span 的先后顺序
#             是随机打乱的，但 CSS 的绝对定位会把它们摆回正确位置，
#             所以人眼看到的是对的，直接 get_text() 拿到的是错的。
#    ── 破解方法 ──
#    把所有 span 按 left 数值从小到大排序，再把字拼起来。
#
#    另外注意 class="name whole" 的那种：whole 表示"完整的"，
#    书名短的时候站点懒得打乱，直接给完整文字，要单独处理。
#
#    ★ 自我验证：这个站还有一个返回干净数据的 API（/api/book/），
#      本脚本会拿 API 的书名跟我们还原出来的书名逐条对比，
#      对得上才算真的还原对了 —— 不靠"看起来像对的"来蒙混过关。
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider3.scrape.center"
PAGE_SIZE = 18            # 站点每页 18 本书
TOTAL_PAGES = 5           # 只抓 5 页（90 本）够学习用了，不折腾人家服务器
REQUEST_INTERVAL = 2
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider3.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def restore_name(h3_html: str, h3_class: str) -> str:
    """把一个书名 <h3> 的内部 HTML 还原成正确顺序的书名。

    h3_class 里带 whole 的，说明站点没打乱，直接把文字取出来即可。
    """
    if "whole" in (h3_class or ""):
        # 没有 span，整段就是书名本身，去掉可能的标签和空白
        return re.sub(r"<[^>]+>", "", h3_html).strip()

    # findall 会按源码顺序返回 (left值, 这个字) 的列表
    pairs = re.findall(
        r'style="left:\s*(-?\d+)px;"[^>]*>\s*([^<]*?)\s*</span>', h3_html
    )
    # 核心一步：按 left 数值（转成 int 再比，不能按字符串比，
    # 否则 "160" 会排在 "32" 前面）从小到大排序
    pairs.sort(key=lambda pair: int(pair[0]))
    # 坑：书名里的**空格**也占一个 span，但 span 里本来就有换行和缩进，
    # 去掉首尾空白后它就变成空字符串了，一拼接空格就丢了
    #（实测《王小波全集 第一卷》会被还原成《王小波全集第一卷》）。
    # 所以约定：抠出来是空的，就说明这一格原本是个空格。
    return "".join(char if char else " " for _left, char in pairs)


def fetch_clean_names(page_index: int) -> dict:
    """从站点自带的 API 拿这一页的"标准答案"，用来验证我们的还原对不对。"""
    url = f"{BASE_URL}/api/book/?limit={PAGE_SIZE}&offset={(page_index - 1) * PAGE_SIZE}"
    data = requests.get(url, headers=HEADERS, timeout=20).json()
    return {item["id"]: item["name"] for item in data["results"]}


def main() -> None:
    books = []
    matched = 0
    checked = 0

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        for page_index in range(1, TOTAL_PAGES + 1):
            url = f"{BASE_URL}/page/{page_index}"
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector(".item", timeout=60000)

            clean_names = fetch_clean_names(page_index)

            for card in page.query_selector_all(".item"):
                link = card.query_selector("a[href^='/detail/']")
                book_id = link.get_attribute("href").split("/")[-1] if link else None

                h3 = card.query_selector("h3.name")
                if h3 is None:
                    continue
                raw_order = h3.inner_text().replace("\n", "")   # 直接取文字（错的）
                name = restore_name(h3.inner_html(), h3.get_attribute("class"))

                authors_el = card.query_selector("p.authors")
                authors = authors_el.inner_text().strip() if authors_el else None

                # 跟 API 的标准答案对一下
                expected = clean_names.get(book_id)
                if expected is not None:
                    checked += 1
                    if expected.strip() == name.strip():
                        matched += 1

                books.append(
                    {
                        "id": book_id,
                        "name_raw": raw_order,   # 源码里的错乱顺序，留着对比看
                        "name": name,            # 还原后的正确书名
                        "authors": authors,
                    }
                )

            print(f"第 {page_index} 页：累计 {len(books)} 本")
            if page_index == 1:
                print("  举例（源码顺序 → 还原后）：")
                for b in books[1:4]:
                    print(f"    {b['name_raw']}  →  {b['name']}")
            if page_index < TOTAL_PAGES:
                time.sleep(REQUEST_INTERVAL)

        browser.close()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    rate = matched / checked * 100 if checked else 0
    print(f"\n还原准确率（跟站点 API 的标准答案逐条比对）：{matched}/{checked} = {rate:.1f}%")
    print(f"共 {len(books)} 本，已写入 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
