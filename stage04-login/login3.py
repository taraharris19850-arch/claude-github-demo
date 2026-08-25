"""
案例：login3 · https://login3.scrape.center
Issue：#5
目标：用 Session + Cookies 完成模拟登录并抓取登录后才可见的数据
      （本例是同一目标的另一种实现：服务端不发 Cookie，改发 JWT 令牌）
"""

import base64
import json
import os
import time
from pathlib import Path

import requests

BASE_URL = "https://login3.scrape.center"

# 登录接口。怎么探出来的？先猜最常见的 /api/login/，结果 404；
# 去掉末尾那个斜杠试 /api/login，返回 200 —— 就是它。
#   curl -s -o /dev/null -w '%{http_code}' -X POST \
#     https://login3.scrape.center/api/login \
#     -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}'
# 【坑】Django 站点通常带尾斜杠，这个站点偏偏不带，多一个 / 就 404。
LOGIN_URL = f"{BASE_URL}/api/login"

# 数据接口。这个站点是"书籍"站，不是电影站。
DATA_URL = f"{BASE_URL}/api/book/"

PAGE_SIZE = 18       # 每页 18 条，和网页上翻一页的数量一致
TOTAL_PAGES = 5      # ★ 截断：全站共 9200 本，本脚本只抓 5 页（90 本）。
                     #   本阶段要演示的是「带令牌 vs 不带令牌」的差别，
                     #   多抓 9000 本对练习没有额外收获，只是骚扰站点。
                     #   想抓全部就把这里改大，或改成从接口返回的 count 算出总页数。
REQUEST_INTERVAL = 1

OUTPUT_PATH = Path(__file__).parent / "data" / "login3.json"

# 账号密码走环境变量，读不到再回退默认值。用法：
#   LOGIN_USER=admin LOGIN_PASS=admin ./venv/bin/python stage04-login/login3.py
# 这里能写死默认值，只因为 login3.scrape.center 是公开练习站点，
# 账密本来就印在教程里。真实项目中凭证绝不能进代码库——推上去就会永远留在
# git 历史里，事后删掉也翻得出来。
USERNAME = os.environ.get("LOGIN_USER", "admin")
PASSWORD = os.environ.get("LOGIN_PASS", "admin")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def mask(value: str, keep: int = 20) -> str:
    """打印凭证前先截断，只留前 keep 个字符。

    JWT 尤其要注意：这串东西本身就等于你的身份。谁复制走了完整的 token，
    在它过期之前就能完全冒充你，连密码都不用知道。
    """
    if value is None:
        return "(无)"
    return value if len(value) <= keep else value[:keep] + "..."


def decode_jwt_part(part: str) -> dict:
    """把 JWT 的一段（header 或 payload）做 base64 解码，还原成字典。"""
    # JWT 用的是 "base64url" 变体，并且按规矩把末尾的填充符 '=' 去掉了。
    # Python 的解码函数却要求长度必须是 4 的倍数，所以要手动把 '=' 补回来。
    # (-len(part) % 4) 算出还差几个字符才凑够 4 的倍数。
    padded = part + "=" * (-len(part) % 4)
    raw = base64.urlsafe_b64decode(padded)
    return json.loads(raw)


def step1_without_token():
    """第一步：不带令牌请求数据接口，看服务器怎么回。"""
    print("=" * 70)
    print("第 1 步：不带 token，直接请求数据接口")
    print("=" * 70)

    url = f"{DATA_URL}?limit={PAGE_SIZE}&offset=0"
    response = requests.get(url, headers=HEADERS, timeout=10)

    print(f"请求地址：{url}")
    print(f"状态码：{response.status_code}")
    # WWW-Authenticate 这个响应头是服务器在明说"我要的是哪种认证方式"，
    # 这里它回的是 JWT realm="api"，等于直接告诉我们该带 JWT。
    print(f"响应头 WWW-Authenticate：{response.headers.get('WWW-Authenticate')}")
    print(f"响应体：{response.text.strip()}")
    print("→ 结论：401 Unauthorized。没有令牌，接口一个字节数据都不给。")
    print()


def step2_get_token() -> str:
    """第二步：登录换取 JWT 令牌，并把它拆开看看里面装了什么。"""
    print("=" * 70)
    print("第 2 步：登录，换一张 JWT 通行证")
    print("=" * 70)

    print(f"登录接口：POST {LOGIN_URL}")

    # 注意用的是 json=（不是 login2 里的 data=）。
    # json= 会把字典序列化成 JSON 字符串，并自动带上
    # Content-Type: application/json —— 这是现代 API 接口的通用格式。
    # （这个站点其实两种格式都收，但既然是 API，用 JSON 更规范。）
    response = requests.post(
        LOGIN_URL,
        headers=HEADERS,
        json={"username": USERNAME, "password": PASSWORD},
        timeout=10,
    )
    response.raise_for_status()

    token = response.json().get("token")
    if not token:
        raise RuntimeError(f"登录失败，响应里没有 token：{response.text[:200]}")

    print(f"状态码：{response.status_code}")
    print(f"拿到 token（已截断）：{mask(token)}")
    print(f"完整长度：{len(token)} 个字符")
    print()

    # -----------------------------------------------------------------------
    # 把 JWT 拆开看
    #
    # JWT = JSON Web Token，长这样：xxxxx.yyyyy.zzzzz
    # 用两个点分成三段：
    #   header    —— 说明这张票用什么算法签名的
    #   payload   —— 票面信息：你是谁、什么时候过期
    #   signature —— 防伪签名，服务器用只有自己知道的密钥算出来的
    # -----------------------------------------------------------------------
    parts = token.split(".")
    print("-" * 70)
    print(f"JWT 用 '.' 分成了 {len(parts)} 段：")
    print(f"  [1] header    ：{mask(parts[0])}")
    print(f"  [2] payload   ：{mask(parts[1])}")
    print(f"  [3] signature ：{mask(parts[2])}")
    print("-" * 70)

    header = decode_jwt_part(parts[0])
    payload = decode_jwt_part(parts[1])

    print("\nheader 解码后（这张票的「制票工艺」）：")
    print(json.dumps(header, ensure_ascii=False, indent=2))

    print("\npayload 解码后（这张票的「票面信息」）：")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    # payload 里的 exp 是过期时间戳（从 1970 年算起的秒数），换成人看得懂的时间。
    if "exp" in payload:
        expire_at = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(payload["exp"]))
        remain_minutes = (payload["exp"] - time.time()) / 60
        print(f"\n  exp = {payload['exp']}，即 {expire_at}（约 {remain_minutes:.0f} 分钟后过期）")

    print("\n  signature 那一段我们解不开，也不需要解——")
    print("  它是服务器用自己的私密密钥算出来的防伪码，我们没有密钥。")

    # -----------------------------------------------------------------------
    # 【为什么 payload 谁都能解码？】
    # 因为那三段用的是 base64 编码，不是加密。
    # 编码 ≠ 加密：base64 只是把字节换一种写法（为了能安全地塞进 HTTP 头里），
    # 它没有密钥，任何人拿到都能一秒还原——你刚才亲眼看到了。
    # 所以：JWT 里绝对不能放密码、身份证号、银行卡这类秘密，
    # 里面只该放"公开了也无所谓"的信息，比如用户 ID、用户名、过期时间。
    #
    # 那 JWT 靠什么保证安全？靠第三段 signature。
    # 你可以随便改 payload 里的 user_id 想冒充别人，但你算不出对应的新签名
    # （没有服务器的密钥），服务器一验签就发现对不上，直接拒绝。
    # 一句话：JWT 的安全性来自"防篡改"，不来自"保密"。
    #
    # 【JWT 和 Cookie 的区别】（对比 login2）
    #   Cookie/Session：服务器发给你一张会员卡（sessionid），
    #     同时在自己的账本上记一笔"这张卡号 = admin"。
    #     每次你出示卡，服务器都要翻账本查。
    #     → 服务器必须"记着"每一个登录的人，人多了账本就是负担，
    #       多台服务器之间还得共享这本账。
    #
    #   JWT：服务器发给你一张自带防伪签名的通行证，然后就把你忘了。
    #     信息全写在票面上（你是谁、什么时候过期），服务器不记账，
    #     每次只需验一下签名真伪，再看一眼有没有过期。
    #     → 服务器无状态，加机器很轻松。
    #     代价是：票发出去就收不回来了，没到期之前想强制某人下线很麻烦。
    # -----------------------------------------------------------------------
    print()
    return token


def step3_fetch_with_token(token: str) -> list:
    """第三步：带上 Authorization 请求头，正常取数据。"""
    print("=" * 70)
    print("第 3 步：带上 Authorization 请求头再请求")
    print("=" * 70)

    # -----------------------------------------------------------------------
    # 令牌要放进 Authorization 这个请求头里，格式是「前缀 + 空格 + token」。
    #
    # 【坑】前缀不能乱写。很多教程里写 "Bearer"，但这个站点用的是
    # Django REST Framework JWT 那一套，它认的前缀是 "jwt"。
    # 实测：Authorization: Bearer <token> → 401
    #       Authorization: jwt    <token> → 200
    # 前缀写错和没带令牌，服务器给的都是 401，很容易误以为是密码错了。
    # -----------------------------------------------------------------------
    session = requests.Session()
    session.headers.update(HEADERS)
    # 放进 session.headers 之后，这个 session 发的每个请求都会自动带上它，
    # 不用每次手写 headers=——作用和 login2 里 Session 自动带 Cookie 一样。
    session.headers["Authorization"] = f"jwt {token}"

    print(f"设置请求头：Authorization: jwt {mask(token)}")
    print()

    all_books = []

    for page in range(1, TOTAL_PAGES + 1):
        # 这个接口用 limit/offset 翻页：
        # limit 是"一次要几条"，offset 是"从第几条开始跳过"。
        # 第 1 页 offset=0，第 2 页 offset=18，第 3 页 offset=36……
        offset = (page - 1) * PAGE_SIZE
        url = f"{DATA_URL}?limit={PAGE_SIZE}&offset={offset}"

        response = session.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        books = data.get("results", [])

        if page == 1:
            print(f"请求地址：{url}")
            print(f"状态码：{response.status_code}（成功！同一个接口，只是多了一个请求头）")
            print(f"全站共有 {data.get('count')} 本书")
            if books:
                print(f"第一本：{books[0].get('name')}")
            print()

        for book in books:
            all_books.append({
                "id": book.get("id"),
                "name": book.get("name"),
                "authors": book.get("authors"),
                "score": book.get("score"),
                "cover": book.get("cover"),
            })

        print(f"  第 {page} 页（offset={offset}）拿到 {len(books)} 本书")

        if page < TOTAL_PAGES:
            time.sleep(REQUEST_INTERVAL)

    print("\n→ 结论：401 和 200 之间的差别，就只是一个 Authorization 请求头。")
    print()

    return all_books


def main():
    step1_without_token()
    time.sleep(REQUEST_INTERVAL)

    token = step2_get_token()
    time.sleep(REQUEST_INTERVAL)

    books = step3_fetch_with_token(token)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(books, f, ensure_ascii=False, indent=2)

    print(f"共抓取 {len(books)} 本书，已保存到 {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
