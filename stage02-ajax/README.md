# 阶段2 · Ajax 接口：绕过页面直接拿数据

**对应 issue：#3** → https://github.com/taraharris19850-arch/claude-github-demo/issues/3

案例来源：https://scrape.center

## 本目录的代码

| 案例 | 脚本 | 状态 | 踩坑记录 |
|---|---|---|---|
| [spa1](https://spa1.scrape.center) | `spa1.py` | 已完成 | 接口 `GET https://spa1.scrape.center/api/movie/?limit=10&offset=0`（详情 `/api/movie/<id>/`）。坑：列表接口不返回 `drama`（剧情简介），只有详情接口才有，所以得先翻页拿全部 id，再逐部请求详情补简介，共 104 部（不是常说的 100 部）|
| [spa3](https://spa3.scrape.center) | `spa3.py` | 已完成 | 接口 `GET https://spa3.scrape.center/api/movie/?limit=10&offset=0`。坑：一看到「无限滚动」以为要上 Selenium 模拟滚动，其实滚动加载在接口层面就是 offset 递增，跟点页码没有任何区别，一个 while 循环搞定；而且它的列表接口直接带 `drama`，比 spa1 还省一轮请求 |
| [spa4](https://spa4.scrape.center) | `spa4.py` | 已完成 | 接口 `GET https://spa4.scrape.center/api/news/?limit=100&offset=0`。坑一：照抄 spa1 猜 `/api/movie/` 直接 404，接口路径跟站点内容走（新闻站就是 `/api/news/`）。坑二：作业要「来源」就顺手取 `source` 字段，结果整列全是 null——真正有值的是 `website`（如「新浪新闻」），必须先打印一条原始 JSON 看清结构 |
| [spa5](https://spa5.scrape.center) | `spa5.py` | 已完成 | 接口 `GET https://spa5.scrape.center/api/book/?limit=50&offset=0`。坑：`authors` 是**列表**不是字符串，而且脏，名字里混着换行和大段空格（如 `"\n            董桥"`），得逐个 `.strip()` 清洗。另外算总页数要用向上取整 `(总数+limit-1)//limit`，直接整除会漏掉最后不满一页的那几条 |

> 每完成一个案例，把「状态」改成 `已完成`，并在「踩坑记录」里写一句你卡在哪、怎么解决的。
> 同时回 issue #3 把对应的 checkbox 勾上 —— 两边都要更新，这是本仓库的硬规则（见根目录 CLAUDE.md）。

## 本阶段学到的核心

1. **SPA（单页应用）的 HTML 是空壳**。`curl` 首页只能看到一个空的 `<div id="app"></div>`，数据是页面加载完之后由 JS 再发一次请求（Ajax）取回来的。
2. **怎么找那个接口**：浏览器按 F12 → Network → 筛 XHR/Fetch 刷新页面；没有浏览器就直接猜常见路径（电影站 `/api/movie/`、新闻站 `/api/news/`、图书站 `/api/book/`）用 `curl` 验证，猜不中就抓 JS bundle `grep '/api/'`。
3. **`limit` / `offset` 是分页接口的通用约定**：`limit` = 这一批要几条，`offset` = 跳过前面多少条。第 N 页的 `offset = (N-1) × limit`。
4. **翻页 vs 滚动加载，对爬虫没有区别**，两者在接口层面都只是 offset 递增，差别只在前端由「点击」还是「滚动」触发。
5. **动手前先打印一条完整的原始 JSON**。字段名靠猜必踩坑（spa4 的 `source` 全是 null 就是活例子）。

## 比起阶段1 解析 HTML，直接调接口好在哪

- **数据本来就是结构化的**：返回 JSON，`movie['score']` 直接取，不用再写一堆 `soup.find('div', class_='xxx')` 大海捞针。
- **请求次数少、传输量小**：一次能拿 10～100 条纯数据，HTML 里还夹着样式、脚本、广告。
- **不怕页面改版**：网站改个 CSS 类名，阶段1 的解析代码立刻全挂；接口是给程序用的，字段名要保持兼容，稳定得多。
- **字段更全**：接口连页面上压根没显示的 `alias`（外文名）、`regions`（地区）都给了。

## 数据输出

抓到的数据统一存进 `stage02-ajax/data/`，文件名与脚本同名，例如 `spa1.json`。

| 文件 | 条数 | 说明 |
|---|---|---|
| `data/spa1.json` | 104 | 全部，含剧情简介 |
| `data/spa3.json` | 104 | 全部，含剧情简介 |
| `data/spa4.json` | 500 | **做了截断**：站点总量 451370 条，全抓需约 4514 次请求 / 75 分钟，只取前 500 条 |
| `data/spa5.json` | 500 | **做了截断**：站点总量 9040 条，超过 1000 条门槛，只取前 500 条 |

> spa4 / spa5 的截断是明确的取舍，**不是抓全了**。两个脚本里都有 `MAX_ITEMS = 500`，改成 `None` 就是抓全部，代码逻辑本身支持。

## 怎么运行

```bash
./venv/bin/python stage02-ajax/spa1.py
./venv/bin/python stage02-ajax/spa3.py
./venv/bin/python stage02-ajax/spa4.py
./venv/bin/python stage02-ajax/spa5.py
```

四个脚本都彼此独立，请求间隔均设为 ≥ 1 秒（练习站点是公共资源，别打挂了）。
