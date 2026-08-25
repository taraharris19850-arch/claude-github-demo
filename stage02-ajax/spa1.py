"""
案例：spa1 · https://spa1.scrape.center
Issue：#3
接口：GET /api/movie/?limit=10&offset=0
目标：不解析 HTML，直接调接口拿全部电影数据
"""

# ============================================================
# 这个接口是怎么找到的？（本阶段的核心学习点，务必看懂）
# ============================================================
# 1) 先 `curl -s https://spa1.scrape.center/` 看首页 HTML，会发现里面
#    只有一个空的 <div id="app"></div>，一部电影名字都没有。
#    这就是「单页应用（SPA）」：HTML 只是个空壳子，
#    真正的数据是页面加载完之后，用 JavaScript 再发一次请求去拿的。
#    这种「页面加载完再偷偷发的请求」就叫 Ajax 请求。
#
# 2) 怎么找到那个偷偷发的请求？两个办法：
#    a. 平时用浏览器：按 F12 打开开发者工具 → Network 面板 → 筛选 XHR/Fetch，
#       刷新页面，列表里出现的那条请求就是接口。
#    b. 没有浏览器（比如我们现在这样）：把页面加载的 JS 文件下载下来搜关键字：
#          curl -s https://spa1.scrape.center/js/app.xxxx.js | grep -o '/api/[a-z]*'
#       也可以直接猜常见路径（电影站十有八九是 /api/movie/）再用 curl 验证：
#          curl -s "https://spa1.scrape.center/api/movie/?limit=10&offset=0"
#       ★ 注意：用 curl 时 URL 一定要加引号，否则 zsh 会把 ? 当成通配符报错。
#
# 3) 参数什么含义？（这是分页接口最通用的一对参数，几乎所有网站都这么设计）
#    - limit  = 「这一次要几条」。limit=10 就是一次返回 10 条。
#    - offset = 「从第几条开始，跳过前面多少条」。offset=0 从头开始，
#               offset=10 表示跳过前 10 条、从第 11 条开始返回。
#    所以第 N 页的 offset = (N - 1) * limit。这就是「翻页」的真相：
#    页面上的「第 2 页」按钮，底下干的事就是把 offset 从 0 改成 10 再请求一次。
#
# 4) 返回的 JSON 结构长这样：
#    {"count": 104, "results": [ {电影1}, {电影2}, ... ]}
#    - count   = 数据库里一共多少条（用来算总页数）
#    - results = 这一页的数据列表
#
# 5) 列表接口不返回「剧情简介」，简介只在详情接口里有：
#       GET /api/movie/<id>/     例如 /api/movie/1/
#    所以本脚本分两步走：先翻页拿到全部电影的 id，再逐个请求详情补上简介。
#
# ============================================================
# 比起阶段1「下载 HTML 再用 BeautifulSoup 解析」，直接调接口好在哪？
# ============================================================
# ① 数据本来就是结构化的：接口返回的是 JSON，用 json.loads() 一转就是
#    Python 的字典，想要评分就 movie['score']，不用再写一堆
#    soup.find('div', class_='xxx') 去页面里「大海捞针」。
# ② 请求次数少、传输量小：一次请求能拿 10 条甚至 100 条的纯数据，
#    而 HTML 里夹杂着大量样式、脚本、广告，下载量大得多。
# ③ 不怕页面改版：网站改个 CSS 类名，阶段1 的解析代码立刻全挂；
#    但接口是给程序用的、要保持兼容，字段名一般很稳定。
# ④ 字段更全更干净：接口连 alias（外文名）、regions（地区）这些
#    页面上根本没显示的字段都给了。
# ============================================================

import json      # 把接口返回的 JSON 文本转成 Python 字典
import time      # 用来做请求间隔（sleep），别把练习站点打挂
from pathlib import Path   # 处理文件路径，比手写字符串拼接更安全

import requests  # 发 HTTP 请求的库，爬虫最常用的工具

# ---- 基础配置：把会变的东西抽出来放最上面，以后要改只改这一处 ----
BASE_URL = "https://spa1.scrape.center"
LIST_API = BASE_URL + "/api/movie/"        # 列表接口
DETAIL_API = BASE_URL + "/api/movie/{id}/" # 详情接口，{id} 待会儿用 format 填进去
LIMIT = 10          # 每页取 10 条（跟网站自己翻页时用的一样）
INTERVAL = 1.0      # 每次请求之间至少等 1 秒，这是爬虫最基本的礼貌

# 输出文件路径。__file__ 是「当前这个 .py 文件自己的路径」，
# .parent 取它所在的文件夹，这样不管你在哪个目录下运行脚本，都能存到正确位置。
OUT_FILE = Path(__file__).parent / "data" / "spa1.json"

# 伪装成浏览器。有些站点看到没有 User-Agent 就当是爬虫直接拒绝，
# 加上这一行是几乎所有爬虫脚本的标配。
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}


def get_json(url, params=None):
    """发一个 GET 请求，把返回的 JSON 转成 Python 字典返回。

    单独抽成一个函数，是因为「发请求 → 检查状态码 → 转 JSON → 歇一秒」
    这四步每次都要做，写成函数就不用复制粘贴四遍了。
    """
    resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
    # raise_for_status()：如果服务器返回 404、500 这类错误码，就主动抛异常，
    # 免得后面拿着一堆错误页面的内容当数据用，出了问题还找不到原因。
    resp.raise_for_status()
    data = resp.json()   # requests 自带的方法，等价于 json.loads(resp.text)
    time.sleep(INTERVAL)  # 请求间隔 ≥ 1 秒
    return data


def main():
    print("开始抓取 spa1 电影数据……")

    # ---------- 第一步：翻页，把所有电影的「列表信息」拿全 ----------
    # 先请求一次 offset=0，目的有两个：拿到第一页数据 + 从 count 得知总共多少条。
    first = get_json(LIST_API, {"limit": LIMIT, "offset": 0})
    total = first["count"]           # 总条数（实测是 104 条，不是常说的 100）
    movies = list(first["results"])  # 先把第一页的结果放进来
    print(f"接口告诉我们一共有 {total} 部电影，每页 {LIMIT} 条")

    # 接着从 offset=LIMIT 开始，一页一页往后翻，直到 offset 超过总数。
    # range(起点, 终点, 步长)：从 10 开始，每次 +10，一直到 total 为止。
    offset = LIMIT
    while offset < total:
        data = get_json(LIST_API, {"limit": LIMIT, "offset": offset})
        movies.extend(data["results"])  # extend 是「把一个列表里的元素全塞进来」
        print(f"  列表已抓取 {len(movies)}/{total}")
        offset += LIMIT

    # ---------- 第二步：逐个请求详情接口，补上「剧情简介」 ----------
    # 列表接口不返回 drama（剧情简介）字段，只有详情接口才有，所以必须再跑一轮。
    print("列表抓完，开始逐部抓详情（为了拿剧情简介）……")
    result = []
    for i, movie in enumerate(movies, start=1):   # start=1 让计数从 1 开始，好读
        detail = get_json(DETAIL_API.format(id=movie["id"]))
        # 只挑我们关心的字段存下来，而不是把接口返回的所有字段一股脑存进去。
        # .get(键, 默认值) 比 [键] 安全：万一某部电影缺这个字段，也不会报错崩溃。
        result.append({
            "name": detail.get("name"),                    # 片名
            "categories": detail.get("categories", []),    # 类别，是个列表如 ["剧情","爱情"]
            "score": detail.get("score"),                  # 评分
            "published_at": detail.get("published_at"),    # 上映时间
            "drama": detail.get("drama"),                  # 剧情简介（来自详情接口）
        })
        print(f"  详情已抓取 {i}/{total}：{detail.get('name')}")

    # ---------- 第三步：存成 JSON 文件 ----------
    # mkdir(parents=True, exist_ok=True)：如果 data 文件夹不存在就建一个，
    # 已经存在也不报错。
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    # ensure_ascii=False：不加这个的话中文会被存成 霸王 这种鬼样子。
    # indent=2：每层缩进 2 个空格，存出来的文件人眼能读。
    OUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"完成！共 {len(result)} 条数据，已存到 {OUT_FILE}")


# 这行是 Python 的固定写法：只有「直接运行这个文件」时才执行 main()，
# 如果这个文件被别的文件 import 进去，就不会自动跑。
if __name__ == "__main__":
    main()
