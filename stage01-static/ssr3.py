"""
案例：ssr3 · https://ssr3.scrape.center
Issue：#2
目标：抓取全部电影的片名、类别、评分、上映时间
"""

import json
import os
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth

# ssr3 的页面还是老样子，这一课学的是 HTTP Basic 认证：
# 服务器在门口设了个保安，不出示用户名密码就不让进。
URL = "https://ssr3.scrape.center/page/1"
OUTPUT_PATH = Path(__file__).parent / "data" / "ssr3.json"

# 账号密码从环境变量读，读不到就用练习站点的默认值 admin/admin。
# os.environ.get("键名", "默认值") 就是"有就用，没有就退回默认值"。
#
# ⚠️ 真实项目里绝对不能像下面这样把默认值写死在代码里：
# 代码一旦推到 GitHub，密码就等于公开了（GitHub 上有专门扫密码的机器人，
# 几分钟就能扫到）。正确做法是只从环境变量或密钥管理服务读，
# 读不到就直接报错退出，宁可跑不起来也不能留个默认口令。
# 这里之所以敢留默认值，是因为 admin/admin 本来就印在教程网页上，不是秘密。
USERNAME = os.environ.get("SSR3_USER", "admin")
PASSWORD = os.environ.get("SSR3_PASS", "admin")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def demo_without_auth():
    """第一步：不带凭证请求，看看会被怎么挡回来。"""
    print("=" * 60)
    print("【演示 1】不带用户名密码直接请求：")

    response = requests.get(URL, headers=HEADERS, timeout=10)
    print(f"状态码：{response.status_code}")

    # 401 Unauthorized 的意思是"你还没证明自己是谁"。
    # 注意它和 403 Forbidden 不一样：401 是"你没报身份"，
    # 403 是"你报了身份，但就是不许你看"。
    if response.status_code == 401:
        # 服务器还会回一个 WWW-Authenticate 头，告诉你它要哪种认证方式。
        print(f"服务器要求的认证方式：{response.headers.get('WWW-Authenticate')}")
        print("人话解释：401 = 门口保安拦下你，说'请先出示证件'。")
    else:
        print("没有返回 401，可能站点改了配置。")


def fetch_with_auth() -> str:
    """第二步：带上用户名密码再请求一次。"""
    print("=" * 60)
    print(f"【演示 2】带上凭证（用户名 {USERNAME}）请求：")

    # HTTPBasicAuth 帮你做的事其实很朴素：
    # 把 "用户名:密码" 用 Base64 编一下，塞进请求头 Authorization。
    # 注意 Base64 只是编码不是加密，谁都能解回来——
    # 所以 Basic 认证必须配合 HTTPS 使用，否则密码等于明文在网上裸奔。
    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=10,
        auth=HTTPBasicAuth(USERNAME, PASSWORD),
    )
    response.raise_for_status()
    print(f"状态码：{response.status_code}，页面大小 {len(response.text)} 字符")
    return response.text


def parse_movies(html: str) -> list:
    """解析逻辑和 ssr1 完全一样：页面结构没变，变的只是要先过认证这道门。"""
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
    demo_without_auth()
    html = fetch_with_auth()

    movies = parse_movies(html)
    print(f"解析到 {len(movies)} 部电影")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

    print(f"已保存到 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
