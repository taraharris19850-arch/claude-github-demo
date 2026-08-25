"""
案例：antispider7 · https://antispider7.scrape.center
Issue：#6
反爬手段：IP + 账号**双重**限频，两个计数器同时生效，任何一个超了都被拦
目标：证明"只换 IP"和"只换账号"都不够，实现正确的退避应对并抓到数据
"""

import json
import random
import string
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent))
import proxy_pool  # noqa: E402

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    把 antispider5（数 IP）和 antispider6（数账号）**叠在一起**：
#    服务器同时维护两个计数器 —— 一个记"这个 IP 来过几次"，
#    一个记"这个账号来过几次"。**任意一个超标，请求就被拦**。
#
#    另外它的前端是 Vue 单页应用，登录用的是 JWT（不是 Cookie）：
#    POST /api/login {username, password} → 拿到一串 token，
#    之后每个请求加请求头 Authorization: jwt <token>。
#    数据接口是 GET /api/book/?limit=18&offset=N。
#   （这些接口是从站点的 app.js 里读出来的：里面写着
#    url:{index:"/api/book", login:"/api/login", register:"/api/register"}）
#
# ② 它是怎么认出爬虫的？
#    两个维度交叉验证频率。这样做的好处是堵死了单点绕过：
#    - 你想靠代理池狂换 IP？账号那个计数器照样在涨。
#    - 你想靠批量小号轮换？IP 那个计数器照样在涨。
#    要真正提速，必须**IP 和账号成对地换**（一个 IP 配一个账号），
#    成本一下子从"买代理"变成"买代理 + 养号"，翻了好几倍。
#    这就是这道反爬的真正意图：不是拦死你，是**把成本抬到不划算**。
#
# ③ 我们用什么办法绕过？
#    本脚本用三个实验把上面这段话验证一遍：
#      实验一：用 admin 打到被封，确认限频存在
#      实验二：同一个 IP，换一个**全新账号** → 如果还是被拦，
#              说明 IP 计数器独立存在，"只换账号"不够
#      实验三：同一个账号，换一个**代理 IP** → 如果还是被拦，
#              说明账号计数器独立存在，"只换 IP"也不够
#    然后老老实实退避 + 温柔速率把数据抓完。
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider7.scrape.center"
LOGIN_URL = f"{BASE_URL}/api/login"
REGISTER_URL = f"{BASE_URL}/api/register"
BOOK_URL = f"{BASE_URL}/api/book/"

PAGE_SIZE = 18
TOTAL_PAGES = 5            # 抓 5 页 = 90 本，够用了，别折腾人家
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider7.json"

GENTLE_INTERVAL = 31
BACKOFF_STEP = 60
MAX_BACKOFF_ROUNDS = 12
DEMO_MAX_BURST = 20

DEMO_TRIGGER_BLOCK = True

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def is_blocked(response: requests.Response) -> bool:
    if response.status_code in {403, 429, 503}:
        return True
    lowered = response.text.lower()
    return "too many requests" in lowered or "访问频率" in response.text


def login(username: str, password: str) -> str:
    """登录拿 JWT token。失败返回 None。"""
    response = requests.post(
        LOGIN_URL, json={"username": username, "password": password},
        headers=HEADERS, timeout=20,
    )
    if response.status_code != 200:
        print(f"  登录 {username} 失败：状态码 {response.status_code} "
              f"{response.text.strip()[:150]!r}")
        return None
    token = response.json().get("token")
    print(f"  登录 {username} 成功，拿到 token：{token[:40]}...（长度 {len(token)}）")
    return token


def register_random_account() -> tuple:
    """注册一个随机新账号，返回 (用户名, 密码)；失败返回 (None, None)。"""
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    username = f"stage05_{suffix}"
    password = "Stage05Demo!2024"
    response = requests.post(
        REGISTER_URL, json={"username": username, "password": password},
        headers=HEADERS, timeout=20,
    )
    print(f"  注册新账号 {username} → 状态码 {response.status_code}")
    if response.status_code not in (200, 201):
        print(f"    响应：{response.text.strip()[:200]!r}")
        return None, None
    return username, password


def auth_headers(token: str) -> dict:
    """JWT 的用法：放进 Authorization 请求头，前缀是 'jwt '（这个站的写法）。"""
    return {**HEADERS, "Authorization": f"jwt {token}"}


def get_books(token: str, offset: int, proxies: dict = None) -> requests.Response:
    return requests.get(
        BOOK_URL,
        params={"limit": PAGE_SIZE, "offset": offset},
        headers=auth_headers(token),
        proxies=proxies or None,
        timeout=25,
    )


def demo_burst(token: str) -> int:
    print("\n【实验一】用 admin 的 token 高频请求，看第几次被拦：")
    for i in range(1, DEMO_MAX_BURST + 1):
        response = get_books(token, 0)
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


def demo_new_account_same_ip() -> str:
    """实验二：IP 不变，换全新账号。还被拦 ⇒ IP 计数器独立存在。"""
    print("\n【实验二】IP 不变，换一个全新账号 —— 只换账号够不够？")
    username, password = register_random_account()
    if username is None:
        print("  注册失败，实验二作罢")
        return None
    token = login(username, password)
    if token is None:
        return None
    response = get_books(token, 0)
    if is_blocked(response):
        print(f"  ❌ 新账号照样被拦（状态码 {response.status_code}）")
        print("  → 结论：账号换了、IP 没换，还是过不去 ⇒ **IP 计数器独立存在**。")
        print("  → 所以光靠养一堆小号是没用的。")
    else:
        print(f"  ✅ 新账号能访问（状态码 {response.status_code}）")
        print("  → 说明这一刻 IP 的额度还没用完，账号计数器先爆的。")
    return token


def demo_new_ip_same_account(token: str) -> None:
    """实验三：账号不变，换代理 IP。还被拦 ⇒ 账号计数器独立存在。"""
    print("\n【实验三】账号不变，换一个代理 IP —— 只换 IP 够不够？")
    proxy = proxy_pool.get_valid_proxy(max_try=5)
    if proxy is None:
        print("  没拿到可用的免费代理，这个实验做不了 —— 如实记录，不假装做过。")
        print("  （道理仍然成立：账号计数器认的是 token，跟你从哪个 IP 来无关。）")
        return
    proxies = proxy_pool.to_requests_proxies(proxy)
    try:
        response = get_books(token, 0, proxies=proxies)
    except requests.RequestException as exc:
        print(f"  代理 {proxy} 连不上目标站点（{type(exc).__name__}），实验三作罢")
        return
    if is_blocked(response):
        print(f"  ❌ 换了 IP 照样被拦（状态码 {response.status_code}）")
        print("  → 结论：IP 换了、账号没换，还是过不去 ⇒ **账号计数器独立存在**。")
        print("  → 所以光买代理也是没用的。")
    else:
        print(f"  ✅ 换 IP 后能访问（状态码 {response.status_code}）")
        print("  → 说明这一刻是 IP 计数器先爆的，账号额度还没用完。")


def fetch_with_backoff(token: str, offset: int) -> dict:
    """抓一页，被限流就退避重试。抓不到返回 None，绝不编数据。"""
    for attempt in range(1, MAX_BACKOFF_ROUNDS + 1):
        try:
            response = get_books(token, offset)
        except requests.RequestException as exc:
            print(f"  offset={offset} 第 {attempt} 次：网络错误 {type(exc).__name__}")
            time.sleep(5)
            continue
        if not is_blocked(response):
            return response.json()
        print(f"  offset={offset} 第 {attempt} 次：被限流"
              f"（状态码 {response.status_code}），退避 {BACKOFF_STEP} 秒")
        time.sleep(BACKOFF_STEP)
    return None


def main() -> None:
    print("=" * 60)
    print("【第 1 步】JWT 登录（凭证 admin/admin，实测有效）")
    print("=" * 60)
    token = login("admin", "admin")
    if token is None:
        raise SystemExit("登录失败，脚本终止")

    worker_token = token
    if DEMO_TRIGGER_BLOCK:
        demo_burst(token)
        new_token = demo_new_account_same_ip()
        demo_new_ip_same_account(token)
        if new_token:
            worker_token = new_token

    print("\n" + "=" * 60)
    print(f"【第 2 步】温柔模式抓取：每 {GENTLE_INTERVAL} 秒 1 次，共 {TOTAL_PAGES} 页"
          f"（每页 {PAGE_SIZE} 本）")
    print("=" * 60)
    books = []
    failed = []
    for page in range(1, TOTAL_PAGES + 1):
        data = fetch_with_backoff(worker_token, (page - 1) * PAGE_SIZE)
        if data is None:
            print(f"  第 {page} 页：退避到上限仍未成功，跳过（如实记录）")
            failed.append(page)
        else:
            for item in data.get("results", []):
                books.append(
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        # 站点返回的作者字段里带换行和缩进，顺手清理一下
                        "authors": [a.strip() for a in item.get("authors") or []],
                        "score": item.get("score"),
                    }
                )
            print(f"  第 {page} 页：累计 {len(books)} 本（站点共 {data.get('count')} 本）")
        if page < TOTAL_PAGES:
            time.sleep(GENTLE_INTERVAL)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(books, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n共 {len(books)} 本，已写入 {OUTPUT_PATH}")
    if failed:
        print(f"⚠️ 没抓下来的页：{failed}")
    else:
        print(f"计划的 {TOTAL_PAGES} 页全部抓到")


if __name__ == "__main__":
    main()
