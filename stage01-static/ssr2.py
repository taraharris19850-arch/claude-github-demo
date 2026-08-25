"""
案例：ssr2 · https://ssr2.scrape.center
Issue：#2
目标：抓取全部电影的片名、类别、评分、上映时间
"""

import json
import os
import tempfile
from pathlib import Path

import certifi
import requests
import urllib3
from bs4 import BeautifulSoup

# ssr2 的页面和 ssr1 长得一模一样，这一课要学的不是解析，而是 HTTPS 证书。
# 按教程原本的设定，这个站点没有有效证书，requests 会直接拒绝连接。
URL = "https://ssr2.scrape.center/page/1"
OUTPUT_PATH = Path(__file__).parent / "data" / "ssr2.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def demo_plain_request():
    """第一步：先老老实实请求一次，看看不做任何处理会发生什么。"""
    print("=" * 60)
    print("【演示 1】不做任何处理，直接请求：")
    try:
        response = requests.get(URL, headers=HEADERS, timeout=10)
        print(f"没有报错，状态码 {response.status_code}。")
        print("说明：这个练习站点后来换上了正规证书，原本该出现的报错现在不会出现了。")
        print("     所以下面用【演示 1b】人为制造一次同样的失败，让你看清它长什么样。")
        return True
    except requests.exceptions.SSLError as e:
        print("抓到 SSLError（证书校验失败）。")
        print(f"原始报错（截断）：{str(e)[:150]}...")
        return False


def demo_forced_ssl_error():
    """
    第一步补充：人为制造一次证书校验失败。

    做法：requests 的 verify= 除了 True/False，还能传一个"信任名单"文件的路径。
    这个名单叫 CA 证书包，里面是全世界受信任的发证机构（CA）的证书，
    你的电脑靠它来判断"网站出示的证书是不是权威机构签发的"。
    这里我们只抽出名单里的第一张证书做成一个残缺名单——名单里没有真正的签发方，
    校验自然就过不了，报的错和"网站证书无效"时一模一样。
    """
    print("=" * 60)
    print("【演示 1b】故意用一份残缺的信任名单去校验：")

    # certifi 是 requests 自带的那份 CA 名单，用文本方式读出来。
    pem_text = Path(certifi.where()).read_text()
    begin, end = "-----BEGIN CERTIFICATE-----", "-----END CERTIFICATE-----"
    start = pem_text.index(begin)
    first_cert = pem_text[start:pem_text.index(end, start) + len(end)] + "\n"

    # 写进一个临时文件。delete=False 是因为 Windows 上不能一边开着一边给别人读，
    # 所以我们自己关掉、用完再手动删。
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(first_cert)
        broken_ca_path = f.name

    try:
        requests.get(URL, headers=HEADERS, timeout=10, verify=broken_ca_path)
        print("居然没报错，这不符合预期。")
    except requests.exceptions.SSLError as e:
        # 说人话：你的电脑要求对方出示"身份证"（HTTPS 证书），而且这张身份证
        # 必须由它认识的权威机构签发。现在名单里查不到签发方，
        # 电脑无法确认"对面到底是不是真的 ssr2"，于是干脆拒绝把数据发过去。
        # 这是保护你，不是故障。
        print("抓到 SSLError（证书校验失败）。")
        print("人话解释：Python 在自己的信任名单里找不到这张证书的签发机构，")
        print("         没法确认'对面到底是不是真的 ssr2'，于是拒绝连接。")
        print(f"原始报错（截断）：{str(e)[:150]}...")
    finally:
        os.unlink(broken_ca_path)


def fetch_with_verify_off() -> str:
    """第二步：明确告诉 requests"这个站点我信得过，别查证书了"。"""
    print("=" * 60)
    print("【演示 2】关闭证书校验后请求：")

    # verify=False 会让 urllib3 每次都打印一条 InsecureRequestWarning 警告，
    # 刷屏很烦。下面这行把警告静音——注意只是"不显示警告"，
    # 风险本身一点没变，别把静音当成解决了问题。
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # ⚠️ 为什么 verify=False 在真实项目里很危险：
    # 校验证书的本质是"验明对方身份"。关掉它以后，任何人只要能插在你和服务器
    # 中间（公共 WiFi、被黑的路由器、运营商劫持），就能冒充这个网站，
    # 把假数据发给你，还能原封不动看到你发出去的一切——包括账号密码。
    # 这就是「中间人攻击」（MITM）。数据仍然是加密的，
    # 但你是在跟冒充者加密通信，加密反而给了你虚假的安全感。
    # 正确做法：让站点装上正规证书；内网自签名证书就把自家 CA 证书交给 verify=
    # （verify="/path/to/ca.pem"，就像上面演示 1b 那样传路径），
    # 而不是简单粗暴地关掉校验。
    response = requests.get(URL, headers=HEADERS, timeout=10, verify=False)
    response.raise_for_status()
    print(f"请求成功，状态码 {response.status_code}，页面大小 {len(response.text)} 字符")
    return response.text


def parse_movies(html: str) -> list:
    """解析逻辑和 ssr1 完全一样：页面结构没变，变的只是传输层。"""
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
    succeeded = demo_plain_request()
    if succeeded:
        demo_forced_ssl_error()

    html = fetch_with_verify_off()

    movies = parse_movies(html)
    print(f"解析到 {len(movies)} 部电影")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)

    print(f"已保存到 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
