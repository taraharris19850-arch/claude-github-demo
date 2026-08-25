"""
案例：ssr4 · https://ssr4.scrape.center
Issue：#2
目标：抓取全部电影的片名、类别、评分、上映时间
"""

import json
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

# ssr4 每个响应都固定慢 5 秒，专门用来练"超时"和"重试"。
# 真实世界里网络抖动、对方服务器变慢是常态，
# 一个不会重试的爬虫跑到一半就会因为一次偶发超时全盘失败。
URL = "https://ssr4.scrape.center/page/1"
OUTPUT_PATH = Path(__file__).parent / "data" / "ssr4.json"

# 重试策略：最多试 3 次；失败后等待时间 1 秒 → 2 秒 → 4 秒，每次翻倍。
# 这叫「指数退避」（exponential backoff）：对方可能正忙，
# 越急着重试越是雪上加霜，所以每失败一次就多让一会儿。
MAX_RETRIES = 3
TIMEOUT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def demo_timeout():
    """第一步：故意把超时设成 3 秒，看着它超时失败。"""
    print("=" * 60)
    print("【演示 1】timeout=3 请求一个固定慢 5 秒的站点：")

    # time.perf_counter() 是专门用来计时的高精度秒表，
    # 前后各读一次、相减就是耗时。（别用 time.time()，它会受系统对时影响。）
    start = time.perf_counter()
    try:
        requests.get(URL, headers=HEADERS, timeout=3)
        print("居然没超时，可能站点这次变快了。")
    except requests.exceptions.Timeout:
        elapsed = time.perf_counter() - start
        print(f"抓到 Timeout 异常，等了 {elapsed:.2f} 秒就放弃了。")
        print("人话解释：timeout 是你给对方的耐心上限。站点要 5 秒才回话，")
        print("         你只肯等 3 秒，于是没等到答复就主动挂断了。")


def fetch_with_retry(url: str) -> str:
    """
    第二步：带重试的请求函数。

    超时了不立刻认输，而是退一步、多等一会儿再试，最多试 MAX_RETRIES 次。
    这是生产环境里爬虫的标准写法。
    """
    print("=" * 60)
    print(f"【演示 2】timeout={TIMEOUT} + 最多重试 {MAX_RETRIES} 次：")

    # range(1, MAX_RETRIES + 1) 生成 1、2、3，attempt 就是"这是第几次尝试"。
    for attempt in range(1, MAX_RETRIES + 1):
        start = time.perf_counter()
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            response.raise_for_status()
            elapsed = time.perf_counter() - start
            print(f"  第 {attempt} 次尝试：成功，耗时 {elapsed:.2f} 秒 "
                  f"（能明显感到那 5 秒延迟）")
            return response.text
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError) as e:
            elapsed = time.perf_counter() - start
            print(f"  第 {attempt} 次尝试：失败（{type(e).__name__}），"
                  f"耗时 {elapsed:.2f} 秒")

            # 已经是最后一次了就别再等了，直接把异常抛给调用方。
            # 一个失败的任务应该"响亮地失败"，而不是悄悄返回空数据。
            if attempt == MAX_RETRIES:
                print(f"  已重试 {MAX_RETRIES} 次仍然失败，放弃。")
                raise

            # 2 ** 0 = 1，2 ** 1 = 2，2 ** 2 = 4，正好是 1s → 2s → 4s。
            wait = 2 ** (attempt - 1)
            print(f"  等待 {wait} 秒后重试……")
            time.sleep(wait)

    # 理论上走不到这里（要么 return 要么 raise），写出来只是让函数出口更清楚。
    raise RuntimeError("重试逻辑异常退出")


def parse_movies(html: str) -> list:
    """解析逻辑和 ssr1 完全一样：页面结构没变，变的只是响应变慢了。"""
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

        # 页面里有多个 class="info" 的 div，靠"文字以'上映'结尾"来认哪个是上映时间。
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


def main():
    demo_timeout()

    # 演示 1 和演示 2 之间也歇一秒，别连着捶人家服务器。
    time.sleep(1)

    html = fetch_with_retry(URL)

    movies = parse_movies(html)
    print(f"解析到 {len(movies)} 部电影")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

    print(f"已保存到 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
