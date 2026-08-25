#!/bin/bash
# ---------------------------------------------------------------
# 学习进度查询工具
#
# Issue：#16
# 用法：./status.sh        （或双击「查看学习进度.command」）
# 作用：一眼看清 scrape.center 学习计划的进度，并自检仓库的
#       「代码与 Issue 双向可追溯」规则有没有被违反。
#
# 说明：只调用 2 次 gh（issue 列表 + milestone 列表），
#       其余全部本地计算，所以跑起来很快。
# ---------------------------------------------------------------

cd "$(dirname "$0")" || exit 1

REPO="taraharris19850-arch/claude-github-demo"
PY="./venv/bin/python"
[ -x "$PY" ] || PY="python3"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# 一次性把 GitHub 上的数据拉下来（拉不到就留空，脚本照样能跑）
gh issue list --repo "$REPO" --state all --limit 100 \
   --json number,title,state,labels > "$TMP/issues.json" 2>/dev/null || echo "[]" > "$TMP/issues.json"
gh api "repos/$REPO/milestones?state=all" > "$TMP/milestones.json" 2>/dev/null || echo "[]" > "$TMP/milestones.json"

$PY - "$TMP" <<'PYEOF'
import sys, os, json, glob, subprocess

tmp = sys.argv[1]
tty = sys.stdout.isatty()
def c(code): return code if tty else ""
B, DIM, G, Y, R, CY, N = c("\033[1m"), c("\033[2m"), c("\033[32m"), c("\033[33m"), c("\033[31m"), c("\033[36m"), c("\033[0m")

def w(s):
    """按终端显示宽度算长度：中日韩字符占 2 格，其余占 1 格。"""
    return sum(2 if ord(ch) > 0x2E7F else 1 for ch in s)

def pad(s, width):
    """按显示宽度左对齐补空格；超长就截断加省略号。"""
    while w(s) > width:
        s = s[:-1]
    return s + " " * (width - w(s))

def load(name):
    try:
        return json.load(open(os.path.join(tmp, name), encoding="utf-8"))
    except Exception:
        return []

issues = {i["number"]: i for i in load("issues.json")}
milestones = load("milestones.json")
LINE = DIM + "─" * 62 + N

print()
print(f"{B}{CY}  scrape.center 爬虫学习进度{N}")
print(f"{DIM}  taraharris19850-arch/claude-github-demo{N}")
print(LINE)

# ── 1. 目标（Milestone）────────────────────────────────────────
print(f"\n{B}🎯 目标{N}")
if not milestones:
    print(f"   {DIM}（还没设定目标，或连不上 GitHub）{N}")
for m in milestones:
    done, opened = m["closed_issues"], m["open_issues"]
    total = done + opened
    pct = done / total if total else 0
    filled = round(pct * 20)
    bar = "█" * filled + "░" * (20 - filled)
    color = G if done == total else Y
    flag = "✅" if done == total else "🔸"
    print(f"   {flag} {B}{m['title']}{N}")
    print(f"      {color}[{bar}]{N} {B}{done}/{total}{N}  ({pct*100:.0f}%)")

# ── 2. 各阶段 ─────────────────────────────────────────────────
print(f"\n{B}📚 各阶段{N}")
print(f"   {DIM}{pad('状态',6)}{pad('Issue',6)}{pad('阶段',26)}{pad('脚本',7)}{pad('数据',9)}{N}")

for d in sorted(glob.glob("stage*/")):
    d = d.rstrip("/")
    readme = os.path.join(d, "README.md")
    if not os.path.exists(readme):
        continue
    text = open(readme, encoding="utf-8").read()

    # 从目录 README 里读它对应哪个 issue —— 用的正是仓库规则约定的那行标注
    num = None
    for tok in text.split("对应 issue：#")[1:2]:
        num = int("".join(ch for ch in tok[:4] if ch.isdigit()))

    title = text.split("\n")[0].lstrip("# ")
    title = title.split("：")[0]                      # 只留「阶段N · 主题」

    scripts = len(glob.glob(os.path.join(d, "*.py")))
    rows = 0
    for f in glob.glob(os.path.join(d, "data", "*.json")):
        try:
            j = json.load(open(f, encoding="utf-8"))
            rows += len(j) if isinstance(j, list) else len(j.get("transcript", j))
        except Exception:
            pass

    iss = issues.get(num)
    if iss and iss["state"] == "CLOSED":
        mark = f"{G}✅{N}"
    elif scripts > 0:
        mark = f"{Y}🔸{N}"                            # 有代码但 issue 还没关
    else:
        mark = f"{DIM}⬜{N}"

    n_s = f"{scripts} 个" if scripts else "—"
    n_r = f"{rows} 条" if rows else "—"
    print(f"   {mark}  {DIM}{pad('#'+str(num), 6)}{N}{pad(title,26)}{pad(n_s,7)}{pad(n_r,9)}")

# ── 3. 双向追溯自检 ───────────────────────────────────────────
print(f"\n{B}🔍 双向追溯自检{N}  {DIM}（检查有没有违反 CLAUDE.md 的规则）{N}")
fail = False

# A. 每个 .py 是否都挂了 Issue 编号
pys = sorted(glob.glob("stage*/*.py"))
bad = [f for f in pys if "Issue：#" not in open(f, encoding="utf-8").read()]
if not bad:
    print(f"   {G}✓{N} 全部 {len(pys)} 个 .py 文件都标注了 Issue 编号")
else:
    print(f"   {R}✗{N} 以下文件缺 {B}Issue：#N{N} 文件头：")
    for f in bad: print(f"       {R}{f}{N}")
    fail = True

# B. 每条提交是否都带 #编号
log = subprocess.run(["git", "log", "--format=%h %s", "main"],
                     capture_output=True, text=True).stdout.strip().split("\n")
log = [l for l in log if l and "初始提交" not in l]
bad = [l for l in log if "#" not in l]
if not bad:
    print(f"   {G}✓{N} 全部 {len(log)} 条提交都关联了 Issue（初始提交除外）")
else:
    print(f"   {R}✗{N} 以下提交没带 {B}#编号{N}：")
    for l in bad: print(f"       {R}{l}{N}")
    fail = True

# C. 每个阶段目录 README 是否都标注了对应 issue
bad = [d + "README.md" for d in sorted(glob.glob("stage*/"))
       if os.path.exists(d + "README.md")
       and "对应 issue：#" not in open(d + "README.md", encoding="utf-8").read()]
if not bad:
    print(f"   {G}✓{N} 全部阶段目录 README 都标注了对应 Issue")
else:
    print(f"   {R}✗{N} 以下 README 缺「对应 issue：#N」标注：")
    for f in bad: print(f"       {R}{f}{N}")
    fail = True

# D. issue 承诺的路径是否真实存在（方向 B 的核心校验）
missing = []
for num, iss in issues.items():
    if iss["state"] != "CLOSED":
        continue
    body = subprocess.run(["gh", "issue", "view", str(num), "--json", "body", "--jq", ".body"],
                          capture_output=True, text=True).stdout
    # 只认表格行里的路径。issue 的「产出代码」表才是承诺，
    # 行文中提到的路径（比如解释一次改名）只是引用，不构成承诺。
    # 见 issue #20：早先不加这层过滤，说明文字里的旧路径会被当成承诺而误报。
    for line in body.split("\n"):
        if not line.strip().startswith("|"):
            continue
        for tok in line.split("`"):
            if (tok.startswith("stage") and tok.endswith(".py")
                    and not os.path.exists(tok) and (num, tok) not in missing):
                missing.append((num, tok))   # 同一路径可能出现在多张表里，去重
if not missing:
    print(f"   {G}✓{N} 已关闭 Issue 里承诺的代码文件全部真实存在")
else:
    print(f"   {R}✗{N} 以下 Issue 承诺的文件在仓库里找不到：")
    for num, f in missing: print(f"       {R}#{num} → {f}{N}")
    fail = True

print()
print(LINE)
if not fail:
    print(f"{G}{B}  双向追溯完好：任意代码可查到 Issue，任意 Issue 可找到代码。{N}")
else:
    print(f"{R}{B}  发现违规项，请按上面提示修复。{N}")
print(LINE)
print(f"\n{DIM}  待办清单：{N}gh issue list --state open")
print(f"{DIM}  阶段详情：{N}gh issue view 6")
print(f"{DIM}  某行代码为什么存在：{N}git log -1 --format=%s -- stage05-antispider/antispider4.py")
print()
sys.exit(1 if fail else 0)
PYEOF
