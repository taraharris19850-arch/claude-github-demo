# 阶段1 · 静态网页基础：把网页变成数据

**对应 issue：#2** → https://github.com/taraharris19850-arch/claude-github-demo/issues/2

案例来源：https://scrape.center

## 本目录的代码

| 案例 | 脚本 | 状态 | 踩坑记录 |
|---|---|---|---|
| [ssr1](https://ssr1.scrape.center) | `ssr1.py` | 已完成 | 多个 `class="info"` 的 div 长得一样，按位置取会错位；改成「找文字以『上映』结尾的那条」才稳。另有 4 部电影站点本身就没写上映时间，`release_date` 为 `null` 属正常 |
| [ssr2](https://ssr2.scrape.center) | `ssr2.py` | 已完成 | 站点后来换上了正规 Let's Encrypt 证书，教程预期的 SSLError 已复现不了；改成用一份残缺的 CA 名单人为制造同样的报错来演示 |
| [ssr3](https://ssr3.scrape.center) | `ssr3.py` | 已完成 | 顺利 |
| [ssr4](https://ssr4.scrape.center) | `ssr4.py` | 已完成 | 顺利。注意重试到最后一次要把异常抛出去，不能悄悄返回空数据 |

> 每完成一个案例，把「状态」改成 `已完成`，并在「踩坑记录」里写一句你卡在哪、怎么解决的。
> 同时回 issue #2 把对应的 checkbox 勾上 —— 两边都要更新，这是本仓库的硬规则（见根目录 CLAUDE.md）。

## 数据输出

抓到的数据统一存进 `stage01-static/data/`，文件名与脚本同名，例如 `ssr1.json`。
