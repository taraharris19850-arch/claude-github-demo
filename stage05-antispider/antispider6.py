"""
案例：antispider6 · https://antispider6.scrape.center
Issue：#6
反爬手段：账号限频 —— 必须登录才能看，同一个**账号**每 5 分钟最多 10 次
目标：搞清登录方式，演示账号维度的限频，实现退避应对并抓到数据
"""

import json
import random
import string
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    两层叠在一起：
#    第一层 必须登录。不登录连首页都看不到，直接被踢到 /login。
#    第二层 登录之后，**按账号**计数：同一个账号 5 分钟内最多 10 次。
#
# ② 它是怎么认出爬虫的？
#    还是看频率，但计数的"篮子"从 IP 换成了**账号**。
#    服务器给你发一个 sessionid 的 Cookie，你之后每个请求都带着它，
#    服务器就知道"这是那个叫 admin 的人第几次访问"。
#    比起数 IP，数账号更精准：一个办公室几十号人共用一个出口 IP，
#    按 IP 封会误伤好人；按账号封只砸到那一个人头上。
#
#    ★ 怎么证明它数的是账号不是 IP？——本脚本会做一个实验：
#      先把 admin 这个账号打到被封，然后**在同一台机器、同一个 IP 上**
#      注册一个全新账号立刻访问。如果新账号能通，就说明封的是账号，不是 IP。
#
# ③ 我们用什么办法绕过？
#    换 IP 在这里**完全没用** —— 你换到天涯海角，账号还是那一个。
#    正确的办法是：
#    路线 A（换账号）：准备一批账号轮着用，每个账号用满 10 次就换下一个。
#    路线 B（放慢）：还是老实按 30 秒 1 次的节奏走。
#    再加兜底：被封了要认出来并退避，别硬撞。
#
#    登录方式怎么探明的（实际过程）：
#    1. GET / → 返回一个 <form method="POST">，字段名 username / password
#    2. 直接 POST 到 / → 被 302 到 /login?next=/，说明真正的登录接口是 /login
#    3. POST /login（表单形式，不是 JSON）+ admin/admin → 成功，
#       Session 里多出一个 sessionid Cookie，之后带着它就能看内容
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider6.scrape.center"
LOGIN_URL = f"{BASE_URL}/login"
REGISTER_URL = f"{BASE_URL}/register"
TOTAL_PAGES = 10
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider6.json"

GENTLE_INTERVAL = 31       # 5 分钟 10 次 ⇒ 每 31 秒 1 次
BACKOFF_STEP = 60
MAX_BACKOFF_ROUNDS = 12
DEMO_MAX_BURST = 20

DEMO_TRIGGER_BLOCK = True   # 是否做"故意打爆一个账号"的实验
DEMO_SECOND_ACCOUNT = True  # 是否注册第二个账号来证明"封的是账号不是 IP"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def is_blocked(response: requests.Response) -> bool:
    """判断响应是不是"被限流"。"""
    if response.status_code in {403, 429, 503}:
        return True
    lowered = response.text.lower()
    return "too many requests" in lowered or "访问频率" in response.text


def is_logged_in(response: requests.Response) -> bool:
    """看响应里有没有电影卡片；没有说明还停在登录页。"""
    return "el-card item" in response.text


def login(username: str, password: str) -> requests.Session:
    """用表单方式登录，返回带着 sessionid Cookie 的 Session。"""
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.post(
        LOGIN_URL, data={"username": username, "password": password}, timeout=20
    )
    ok = is_logged_in(response)
    print(f"  登录 {username}/{password} → 状态码 {response.status_code}，"
          f"{'成功' if ok else '失败'}；Cookie: {session.cookies.get_dict()}")
    if not ok:
        raise RuntimeError(f"登录失败：{username}")
    return session


def register_random_account() -> tuple:
    """注册一个随机新账号，返回 (用户名, 密码)。"""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"stage05_{suffix}"
    password = "Stage05Demo!2024"
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.post(
        REGISTER_URL,
        data={
            "username": username,
            "email": f"{username}@example.com",
            "password1": password,
            "password2": password,
        },
        timeout=20,
    )
    print(f"  注册新账号 {username} → 状态码 {response.status_code}")
    return username, password


def demo_burst(session: requests.Session, who: str) -> int:
    """故意快速连打，返回"第几次被拒"；一直没被拒就返回 0。"""
    print(f"\n【实验一】用账号 {who} 高频请求，看第几次被拦：")
    for i in range(1, DEMO_MAX_BURST + 1):
        response = session.get(f"{BASE_URL}/page/1", timeout=20)
        blocked = is_blocked(response)
        print(f"  第 {i:2} 次：状态码 {response.status_code}  "
              f"正文 {len(response.text):6} 字节  {'❌ 被拒' if blocked else '✅ 正常'}")
        if blocked:
            print(f"\n  → 从第 {i} 次开始被拒绝")
            print(f"  → 响应正文：{response.text.strip()[:250]!r}")
            return i
        time.sleep(0.3)
    print(f"  连打 {DEMO_MAX_BURST} 次都没被拦（可能计数窗口刚好翻篇）")
    return 0


def demo_second_account() -> requests.Session:
    """实验二：同一个 IP，换一个全新账号，看还能不能访问。"""
    print("\n【实验二】同一台机器、同一个 IP，换一个全新账号试试：")
    username, password = register_random_account()
    try:
        session = login(username, password)
    except RuntimeError:
        print("  新账号登录失败，实验二作罢")
        return None
    response = session.get(f"{BASE_URL}/page/1", timeout=20)
    if is_blocked(response):
        print("  ❌ 新账号也被拦 → 说明它数的是 IP，不是账号")
        return None
    print(f"  ✅ 新账号立刻就能访问（状态码 {response.status_code}，"
          f"{len(response.text)} 字节）")
    print("  → 结论：IP 没变，账号变了就通了 ⇒ 它计数的篮子是**账号**，不是 IP。")
    print("  → 所以对付这种反爬，买再多代理 IP 也没用，得准备一批账号。")
    return session


def fetch_page(session: requests.Session, page: int) -> str:
    """抓第 page 页，被限流就退避重试。抓不到就返回 None，绝不编数据。"""
    url = f"{BASE_URL}/page/{page}"
    for attempt in range(1, MAX_BACKOFF_ROUNDS + 1):
        try:
            response = session.get(url, timeout=20)
        except requests.RequestException as exc:
            print(f"  第 {page} 页 第 {attempt} 次：网络错误 {type(exc).__name__}")
            time.sleep(5)
            continue
        if not is_blocked(response):
            return response.text
        print(f"  第 {page} 页 第 {attempt} 次：被限流（状态码 {response.status_code}），"
              f"退避 {BACKOFF_STEP} 秒")
        time.sleep(BACKOFF_STEP)
    return None


def parse_movies(html: str) -> list:
    """解析一页 HTML，结构与 ssr1 相同。"""
    soup = BeautifulSoup(html, "lxml")
    movies = []
    for card in soup.select(".el-card.item"):
        name_tag = card.select_one("h2")
        score_tag = card.select_one(".score")
        infos = [i.get_text(strip=True) for i in card.select(".info")]
        movies.append(
            {
                "name": name_tag.get_text(strip=True) if name_tag else None,
                "categories": [
                    b.get_text(strip=True) for b in card.select(".categories button span")
                ],
                "info": infos[0] if len(infos) > 0 else None,
                "published_at": infos[1] if len(infos) > 1 else None,
                "score": score_tag.get_text(strip=True) if score_tag else None,
            }
        )
    return movies


def main() -> None:
    print("=" * 60)
    print("【第 1 步】登录（凭证 admin/admin，实测有效）")
    print("=" * 60)
    admin_session = login("admin", "admin")

    worker = admin_session
    if DEMO_TRIGGER_BLOCK:
        demo_burst(admin_session, "admin")
        if DEMO_SECOND_ACCOUNT:
            fresh = demo_second_account()
            if fresh is not None:
                # 用新账号继续干活，admin 让它自己在小黑屋里冷静
                worker = fresh

    print("\n" + "=" * 60)
    print(f"【第 2 步】温柔模式抓取：每 {GENTLE_INTERVAL} 秒 1 次，共 {TOTAL_PAGES} 页")
    print("=" * 60)
    all_movies = []
    failed_pages = []
    for page in range(1, TOTAL_PAGES + 1):
        html = fetch_page(worker, page)
        if html is None:
            print(f"  第 {page} 页：退避到上限仍未成功，跳过（如实记录）")
            failed_pages.append(page)
        else:
            movies = parse_movies(html)
            all_movies.extend(movies)
            print(f"  第 {page} 页：拿到 {len(movies)} 条，累计 {len(all_movies)} 条")
        if page < TOTAL_PAGES:
            time.sleep(GENTLE_INTERVAL)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(all_movies, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n共 {len(all_movies)} 条，已写入 {OUTPUT_PATH}")
    if failed_pages:
        print(f"⚠️ 没抓下来的页：{failed_pages}")
    else:
        print("全部 10 页都抓到了")


if __name__ == "__main__":
    main()
