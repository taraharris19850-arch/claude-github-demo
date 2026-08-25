"""
案例：antispider5 · https://antispider5.scrape.center
Issue：#6
反爬手段：IP 限频 —— 同一个 IP 每 5 分钟最多访问 10 次，超了就封 10 分钟
目标：亲眼看一次被封是什么样，然后写出正确的退避/换代理应对逻辑，把数据抓完
"""

import json
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# 让脚本能 import 同目录下的 proxy_pool 模块（不管从哪个目录运行都行）
sys.path.insert(0, str(Path(__file__).parent))
import proxy_pool  # noqa: E402

# ────────────────────────────────────────────────────────────────
# ① 这个站用的什么反爬手段？
#    最朴素也最有效的一种：**按 IP 数请求次数**。
#    规则是"同一个 IP，5 分钟内最多 10 次"，超了就把这个 IP 关小黑屋 10 分钟。
#
# ② 它是怎么认出爬虫的？
#    它根本不去判断"你是不是爬虫"。它只看**频率**。
#    正常人看网页，5 分钟点十几下已经算手快了；爬虫一秒能发几十个请求。
#    所以频率本身就是最难伪造的特征 —— 你可以伪造 UA、伪造 webdriver 标志，
#    但只要你想抓得快，就一定会暴露。这是本阶段"最讲道理"的一道反爬。
#
# ③ 我们用什么办法绕过？
#    只有两条路，而且都不是"破解"，是"配合"：
#    路线 A（换身份）：用代理换 IP。每个 IP 都有自己的 10 次额度，
#                     10 个可用代理 = 10 倍速度。这是真实项目的标准做法。
#    路线 B（放慢）：算清楚它的额度，把自己的速度压到额度以内。
#                   5 分钟 10 次 = 平均每 30 秒 1 次，那就每 31 秒发一次。
#                   慢，但绝对安全，而且不需要任何额外成本。
#    再加一条兜底：**万一还是被封了，要能认出来并退避等待**，
#    而不是傻乎乎地继续硬撞。
#    （注：常有人说"硬撞会让封禁计时不断重置"。本阶段实测**没有**观察到这个现象：
#      antispider6 被封后每 60 秒重试一次，第 11 轮就恢复了，跟站点声明的 10 分钟吻合。
#      所以别把这句话当定论。不硬撞的真正理由更简单：撞了也没用，还给人家添堵。）
#
# ⚠️ 本脚本会**故意触发一次封禁**来观察现象（这是作业要求的实验）。
#    观察完就退避，绝不反复撞。真实项目里不要这么干。
# ────────────────────────────────────────────────────────────────

BASE_URL = "https://antispider5.scrape.center"
TOTAL_PAGES = 10
OUTPUT_PATH = Path(__file__).parent / "data" / "antispider5.json"

# 温柔模式的间隔：5 分钟 10 次 ⇒ 平均 30 秒 1 次，取 31 秒留点余量
GENTLE_INTERVAL = 31
# 被封后退避多久再试。站点说封 10 分钟，这里分次等，每次 60 秒，最多 12 次
BACKOFF_STEP = 60
MAX_BACKOFF_ROUNDS = 12
# 被封时服务器可能给的状态码
BLOCK_STATUS = {403, 429, 503}

DEMO_TRIGGER_BLOCK = True   # 是否做"故意触发封禁"的实验
DEMO_MAX_BURST = 20         # 实验最多连打多少次（打到被封就停）

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def is_blocked(response: requests.Response) -> bool:
    """判断这个响应是不是"被限流了"。"""
    if response.status_code in BLOCK_STATUS:
        return True
    # 有些站会用 200 状态码返回一个"访问太频繁"的提示页，也要认出来
    lowered = response.text.lower()
    return "too many requests" in lowered or "访问频率" in response.text


def demo_trigger_block(session: requests.Session) -> None:
    """实验：故意快速连打，看第几次开始被拒，被拒时长什么样。"""
    print("=" * 60)
    print("【实验】故意高频请求，观察限频到底怎么发生（只做这一次）")
    print("=" * 60)
    for i in range(1, DEMO_MAX_BURST + 1):
        start = time.time()
        response = session.get(f"{BASE_URL}/page/1", timeout=20)
        cost = time.time() - start
        blocked = is_blocked(response)
        flag = "❌ 被拒" if blocked else "✅ 正常"
        print(f"  第 {i:2} 次请求：状态码 {response.status_code}  "
              f"正文 {len(response.text):6} 字节  耗时 {cost:.2f}s  {flag}")
        if blocked:
            print(f"\n  → 从第 {i} 次开始被拒绝。")
            print(f"  → 状态码：{response.status_code}")
            print(f"  → 响应头 Retry-After：{response.headers.get('Retry-After', '（没有）')}")
            print(f"  → 响应正文：{response.text.strip()[:300]!r}")
            print("\n  实验到此为止，下面转入正确的应对逻辑，不再硬撞。\n")
            return
        time.sleep(0.3)
    print(f"\n  连打 {DEMO_MAX_BURST} 次都没被拒 —— 可能限制放宽了，或者计数窗口刚好翻篇。\n")


def try_switch_proxy() -> dict:
    """路线 A：被封时试着换一个代理 IP。

    拿不到可用代理就返回空字典，调用方会自动退回到"路线 B：退避等待"。
    ⚠️ 免费公开代理可用率很低，而且就算能上网也常被目标站点拉黑，
       所以这里**不能假设它一定成功**，必须有兜底。
    """
    print("  尝试路线 A：换一个代理 IP……")
    proxy = proxy_pool.get_valid_proxy(max_try=5)
    if proxy is None:
        print("  没拿到可用代理，退回路线 B（退避等待）")
        return {}
    print(f"  拿到可用代理 {proxy}，接下来用它发请求")
    return proxy_pool.to_requests_proxies(proxy)


def fetch_page(session: requests.Session, page: int, proxies: dict) -> tuple:
    """抓第 page 页。被限流就退避重试，返回 (html, 当前使用的proxies)。

    返回的 html 可能是 None —— 表示试到最后还是没抓下来，如实往上报，
    绝不返回假数据。
    """
    url = f"{BASE_URL}/page/{page}"
    for attempt in range(1, MAX_BACKOFF_ROUNDS + 1):
        try:
            response = session.get(url, timeout=20, proxies=proxies or None)
        except requests.RequestException as exc:
            print(f"  第 {page} 页 第 {attempt} 次：网络错误 {type(exc).__name__}")
            if proxies:
                print("  代理可能挂了，弃用它，改回本机 IP")
                proxies = {}
            time.sleep(5)
            continue

        if not is_blocked(response):
            return response.text, proxies

        print(f"  第 {page} 页 第 {attempt} 次：被限流（状态码 {response.status_code}）")
        # 先试换 IP；换不到就老实等
        if not proxies:
            proxies = try_switch_proxy()
            if proxies:
                continue
        print(f"  退避 {BACKOFF_STEP} 秒后重试（已退避 {attempt}/{MAX_BACKOFF_ROUNDS} 轮）")
        time.sleep(BACKOFF_STEP)

    return None, proxies


def parse_movies(html: str) -> list:
    """解析一页 HTML。这个站是服务端渲染的，结构跟 stage01 的 ssr1 一样。"""
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
    session = requests.Session()
    session.headers.update(HEADERS)

    if DEMO_TRIGGER_BLOCK:
        demo_trigger_block(session)

    print("=" * 60)
    print(f"【正式抓取】温柔模式：每 {GENTLE_INTERVAL} 秒 1 次，共 {TOTAL_PAGES} 页")
    print(f"（预计耗时约 {TOTAL_PAGES * GENTLE_INTERVAL // 60} 分钟，被封还要更久，请耐心）")
    print("=" * 60)

    all_movies = []
    failed_pages = []
    proxies: dict = {}

    for page in range(1, TOTAL_PAGES + 1):
        html, proxies = fetch_page(session, page, proxies)
        if html is None:
            print(f"  第 {page} 页：退避到上限仍未成功，跳过（如实记录，不编数据）")
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
