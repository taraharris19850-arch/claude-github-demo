# 阶段4 · 模拟登录：拿到需要身份才能看的数据

**对应 issue：#5** → https://github.com/taraharris19850-arch/claude-github-demo/issues/5

案例来源：https://scrape.center

## 本目录的代码

| 案例 | 脚本 | 状态 | 踩坑记录 |
|---|---|---|---|
| [login2](https://login2.scrape.center) | `login2.py` | 已完成 | 登录接口 `POST /login`，表单字段 `username` / `password`（无 CSRF token）。坑1：`requests` 默认自动跟随重定向，未登录请求 `/page/1` 会一路跟到登录页显示 200，看不出被拦，要加 `allow_redirects=False` 才能看见真实的 302 → `/login?next=/page/1`。坑2：必须用 `requests.Session()`，单发 `requests.get()` 不会保存服务器种下的 `sessionid` Cookie |
| [login3](https://login3.scrape.center) | `login3.py` | 已完成 | 登录接口 `POST /api/login`（**结尾不带斜杠**，写成 `/api/login/` 直接 404，卡了最久），提交 JSON `{"username": ..., "password": ...}`，返回 `{"token": "..."}`；数据接口 `GET /api/book/?limit=18&offset=0`（是书籍站不是电影站，共 9200 本）。坑：`Authorization` 前缀必须是 `jwt`，用常见的 `Bearer` 会 401——而没带令牌也是 401，两种错误长得一样，很容易误判成密码错了 |

> 每完成一个案例，把「状态」改成 `已完成`，并在「踩坑记录」里写一句你卡在哪、怎么解决的。
> 同时回 issue #5 把对应的 checkbox 勾上 —— 两边都要更新，这是本仓库的硬规则（见根目录 CLAUDE.md）。

## 数据输出

抓到的数据统一存进 `stage04-login/data/`，文件名与脚本同名，例如 `login2.json`。

| 文件 | 内容 | 条数 |
|---|---|---|
| `data/login2.json` | 电影片名、类别、评分、上映时间 | 100（10 页 × 10 部，**抓全**） |
| `data/login3.json` | 图书书名、作者、评分等 | 90（**已截断**，全站共 9200 本） |

> `login3` 只抓 5 页：本阶段要演示的是「带令牌 vs 不带令牌」的差别，多抓 9000 本对练习没有额外收获，只是骚扰站点。把 `login3.py` 里的 `TOTAL_PAGES` 改大即可抓更多。
