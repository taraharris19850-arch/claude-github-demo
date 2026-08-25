"""
案例：login2 · https://login2.scrape.center
Issue：#5
目标：用 Session + Cookies 完成模拟登录并抓取登录后才可见的数据
"""

import json
import os
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://login2.scrape.center"

# 这个站点的登录接口就是 /login，用 POST 提交。
# 表单字段名是怎么知道的？把登录页的 HTML 抓下来，找 <input> 标签的 name 属性：
#   curl -s https://login2.scrape.center/login | grep '<input'
# 看到 name="username" 和 name="password"，就是这两个字段名。
LOGIN_URL = f"{BASE_URL}/login"

TOTAL_PAGES = 10
REQUEST_INTERVAL = 1

OUTPUT_PATH = Path(__file__).parent / "data" / "login2.json"

# ---------------------------------------------------------------------------
# 账号密码：优先从"环境变量"里读。
#
# 环境变量就像贴在电脑上的一张便利贴，程序运行时能看见，但它不在代码文件里，
# 所以不会被 git 提交上去。用法（在终端里先设好再运行脚本）：
#   LOGIN_USER=admin LOGIN_PASS=admin ./venv/bin/python stage04-login/login2.py
#
# os.environ.get("LOGIN_USER", "admin") 的意思是：
# "去便利贴上找 LOGIN_USER，找不到就用 admin 这个默认值"。
#
# 【重要】这里之所以敢写死默认值 admin/admin，是因为 login2.scrape.center
# 是一个专门给人练手的公开站点，账号密码本来就印在教程里，泄露了也没有任何损失。
# 真实项目里，密码、API Key、数据库口令绝对不能出现在代码里——代码一旦推到
# 仓库，历史记录会永远留着它，就算你后来删掉也还能翻出来。
# ---------------------------------------------------------------------------
USERNAME = os.environ.get("LOGIN_USER", "admin")
PASSWORD = os.environ.get("LOGIN_PASS", "admin")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def mask(value: str, keep: int = 20) -> str:
    """把敏感字符串截断后再打印，只留前 keep 个字符。

    为什么要这么做？因为日志、终端输出经常会被复制到聊天记录、截图、
    工单系统里。完整的 Cookie 值等同于你的登录凭证——别人拿到它，
    不需要密码就能冒充你。养成"打印凭证必截断"的习惯，成本为零，收益很大。
    """
    if value is None:
        return "(无)"
    if len(value) <= keep:
        return value
    return value[:keep] + "..."


def parse_movies(html: str) -> list:
    """把一页的 HTML 解析成电影列表。结构和 stage01 的 ssr1 完全一样。"""
    soup = BeautifulSoup(html, "lxml")

    movies = []
    for card in soup.select(".el-card.item"):
        name_tag = card.select_one("h2")
        name = name_tag.get_text(strip=True) if name_tag else None

        categories = [
            span.get_text(strip=True)
            for span in card.select(".categories span")
        ]

        score_tag = card.select_one(".score")
        score = score_tag.get_text(strip=True) if score_tag else None

        # 页面里有好几个 class="info" 的 div，标签长得一模一样，
        # 只能按内容特征找那条以"上映"结尾的（和 ssr1 里踩过的坑相同）。
        release_date = None
        for info in card.select(".info"):
            text = info.get_text(strip=True)
            if text.endswith("上映"):
                release_date = text.replace("上映", "").strip()
                break

        movies.append({
            "name": name,
            "categories": categories,
            "score": score,
            "release_date": release_date,
        })

    return movies


def step1_without_login():
    """第一步：不登录，直接敲受保护的页面，看看会发生什么。"""
    print("=" * 70)
    print("第 1 步：不登录，直接请求 /page/1")
    print("=" * 70)

    url = f"{BASE_URL}/page/1"

    # allow_redirects=False 很关键。
    # requests 默认会"自动跟着跳转走"：服务器说"你去 /login"，它就默默去了，
    # 于是你看到的是最终那个登录页的 200，根本察觉不到中间发生过重定向。
    # 关掉自动跳转，才能亲眼看见服务器返回的原始那一手：302。
    response = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=False)

    print(f"请求地址：{url}")
    print(f"状态码：{response.status_code}")

    if response.status_code in (301, 302, 303, 307, 308):
        # Location 响应头告诉浏览器"该去哪儿"。
        # next=/page/1 是站点贴心的设计：记住你原本想去哪，登录完好送你回去。
        print(f"响应头 Location：{response.headers.get('Location')}")
        print("→ 结论：服务器把我们踢回了登录页。没有身份，就看不到数据。")
    else:
        print("→ 结论：没有被重定向（站点行为可能变了，需要重新探查）。")

    print()


def step2_login() -> requests.Session:
    """第二步：登录，并把服务器发的 Cookie 收进 Session 里。"""
    print("=" * 70)
    print("第 2 步：提交表单登录")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 先说清楚两个概念，这是整个阶段最核心的知识点：
    #
    # 【Cookie 是什么】
    # HTTP 这个协议天生"健忘"——每一次请求在服务器眼里都是全新的陌生人，
    # 上一秒你刚输过密码，下一秒再请求，服务器根本不记得你是谁。
    # 于是有了 Cookie：你登录成功后，服务器发给你一张"会员卡"
    # （这个站点发的卡叫 sessionid），并在自己的账本上记下"这张卡号 = admin"。
    # 之后你每次请求都要把这张卡出示一遍，服务器一查账本就知道你是谁了。
    #
    # 【requests.Session() 帮你做了什么】
    # 如果用 requests.get() 一次次单独发请求，那就是每次都换一个陌生人去敲门，
    # 服务器发的会员卡收都没收，下次自然还是被拦在门外。
    # Session 就是一个"随身卡包"：它会自动把服务器发的 Cookie 收好，
    # 之后用这个 Session 发的每一个请求，都自动把卡夹带上出示，
    # 你一行额外的代码都不用写。这就是为什么模拟登录一定要用 Session。
    # -----------------------------------------------------------------------
    session = requests.Session()
    session.headers.update(HEADERS)

    print(f"登录接口：POST {LOGIN_URL}")
    print(f"表单字段：username={USERNAME}, password={'*' * len(PASSWORD)}")

    # data= 表示用"表单格式"提交（对应网页上点那个登录按钮的效果），
    # requests 会自动加上 Content-Type: application/x-www-form-urlencoded。
    # 注意：这里同样关掉自动跳转，因为我们想看登录接口本身返回了什么。
    response = session.post(
        LOGIN_URL,
        data={"username": USERNAME, "password": PASSWORD},
        timeout=10,
        allow_redirects=False,
    )

    print(f"状态码：{response.status_code}")
    print(f"响应头 Location：{response.headers.get('Location')}")

    # 登录成功的标志：服务器回了 302，并且给我们种下了 sessionid。
    if not session.cookies:
        raise RuntimeError("登录失败：服务器一个 Cookie 都没发，检查账号密码或表单字段名。")

    print("\n拿到的 Cookie（值已截断，只显示前 20 个字符）：")
    for cookie in session.cookies:
        print(f"  {cookie.name} = {mask(cookie.value)}")
        print(f"    ↑ 所属域名：{cookie.domain}，有效路径：{cookie.path}")

    print("\n→ 结论：会员卡（sessionid）已经收进 Session 的卡包里了。")
    print()

    return session


def step3_fetch_with_session(session: requests.Session) -> list:
    """第三步：带着 Session 再去请求，这次应该畅通无阻。"""
    print("=" * 70)
    print("第 3 步：带着 Session（已含 Cookie）重新请求受保护页面")
    print("=" * 70)

    all_movies = []

    for page in range(1, TOTAL_PAGES + 1):
        url = f"{BASE_URL}/page/{page}"

        # 注意这里：我们没有手动传任何 Cookie 参数。
        # session.get() 自己就把卡包里的 sessionid 带上了——这就是 Session 的价值。
        response = session.get(url, timeout=10)
        response.raise_for_status()

        movies = parse_movies(response.text)

        if page == 1:
            print(f"请求地址：{url}")
            print(f"状态码：{response.status_code}（没有被重定向，说明服务器认出我们了）")
            if movies:
                print(f"第一部电影：{movies[0]['name']}")
            print()

        all_movies.extend(movies)
        print(f"  第 {page} 页解析到 {len(movies)} 部电影")

        if page < TOTAL_PAGES:
            time.sleep(REQUEST_INTERVAL)

    print("\n→ 结论：同一个地址，登录前 302 被踢走，登录后 200 拿到数据。")
    print()

    return all_movies


def main():
    step1_without_login()
    time.sleep(REQUEST_INTERVAL)

    session = step2_login()
    time.sleep(REQUEST_INTERVAL)

    movies = step3_fetch_with_session(session)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        # ensure_ascii=False：不加的话中文会被写成 \uXXXX 转义码，人眼没法读。
        json.dump(movies, f, ensure_ascii=False, indent=2)

    print(f"共抓取 {len(movies)} 部电影，已保存到 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
