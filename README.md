# Claude Code × GitHub 协作演示

这是一个用来演示 **Claude Code 如何与 GitHub 配合工作** 的最小项目。

## 这个项目干什么

`greet.py` 是一个命令行小程序：你给它一个名字，它跟你打招呼。

```bash
python3 greet.py 小明
# 输出：你好，小明！
```

## 演示流程（Claude Code 全程代劳）

| 步骤 | 你说的话 | Claude 做的事 |
|------|---------|--------------|
| 1 | "给这个程序加个功能" | 修改 `greet.py` |
| 2 | "跑一下看对不对" | 执行程序、检查输出 |
| 3 | "提交并推到 GitHub" | `git commit` + `git push` |
| 4 | "开个 PR" | 用 `gh pr create` 创建拉取请求 |

整个过程你不需要记任何 git 命令 —— 用大白话说需求就行。

## 几个名词（说人话版）

- **仓库 (repository)**：一个带"完整修改历史"的项目文件夹。
- **提交 (commit)**：给项目当前状态拍一张快照，附一句说明。可以随时回到任何一张快照。
- **推送 (push)**：把本地的快照上传到 GitHub，这样换台电脑、或者别人也能拿到。
- **拉取请求 (Pull Request)**：一份"我想这样改，你看行不行"的提案，改动先摆出来讨论，同意了再合并。

---

## 📚 爬虫学习计划

本仓库现在同时用作 **Python 爬虫学习仓库**，素材来自 [scrape.center](https://scrape.center) 的 54 个练习案例站点，拆成 10 个阶段：

| 阶段 | 主题 | Issue | 难度 | 学时 | 代码目录 |
|---|---|---|---|---|---|
| 0 | 建规则与骨架 | [#1](../../issues/1) | — | — | `CLAUDE.md` |
| 1 | 静态网页基础 | [#2](../../issues/2) | 入门 | 8h | `stage01-static/` |
| 2 | Ajax 接口 | [#3](../../issues/3) | 入门 | 8h | `stage02-ajax/` |
| 3 | 浏览器自动化 | [#4](../../issues/4) | 入门 | 10h | `stage03-render/` |
| 4 | 模拟登录 | [#5](../../issues/5) | 入门 | 6h | `stage04-login/` |
| 5 | 反爬对抗 | [#6](../../issues/6) | 进阶 | 12h | `stage05-antispider/` |
| 6 | JS 逆向入门 | [#7](../../issues/7) | 进阶 | 16h | `stage06-jsreverse/` |
| 7 | JS 混淆还原 | [#8](../../issues/8) | 高阶 | 16h | `stage07-obfuscation/` |
| 8 | AST 与 WASM | [#9](../../issues/9) | 高阶 | 20h | `stage08-ast-wasm/` |
| 9 | 验证码 | [#10](../../issues/10) | 进阶 | 16h | `stage09-captcha/` |
| 10 | App 抓包逆向 | [#11](../../issues/11) | 高阶 | 30h | `stage10-app/` |

### 仓库铁律：代码与 Issue 双向可追溯

> 看到任何一行代码，能查到它**为什么存在**；看到任何一个 issue，能点到它**产出了哪些代码**。

- 每次提交的 commit message 结尾必须带 `#<issue编号>`
- 每个 issue 正文都有「产出代码」表，写清文件路径
- 每个阶段目录的 README 开头写明「对应 issue：#N」

完整条款见 [CLAUDE.md](CLAUDE.md)。

---

演示者：Tara · 由 Claude Code 协助创建
