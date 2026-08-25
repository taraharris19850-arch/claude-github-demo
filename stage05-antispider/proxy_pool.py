"""
案例：tool1 · https://proxypool.scrape.center/random
Issue：#6
反爬手段：（本文件不破解站点，而是造工具）应对"按 IP 封禁/限频"的通用武器 —— 代理池
目标：写一个可以被别的脚本 import 的代理池模块，能取代理、能验证代理、能剔除失效代理
"""

import time
from typing import Optional

import requests

# ────────────────────────────────────────────────────────────────
# ① 为什么需要代理？
#    网站限频、封禁，绝大多数是**按 IP** 来的（见 antispider5）。
#    代理服务器就是一个"中转站"：你把请求发给它，它替你去访问网站，
#    再把结果带回来。网站看到的来访 IP 是中转站的，不是你的。
#    换一个代理 = 换一个身份，被封的那个 IP 就不影响你了。
#
# ② 代理长什么样？
#    就是一个 "IP:端口"，比如 "120.92.111.242:15010"。
#    requests 用 proxies={"http": "http://IP:端口", "https": "http://IP:端口"} 来指定。
#
# ③ 为什么必须"先验证再用"？
#    公开免费代理是全网共享的，随时会挂：机器关了、被目标网站拉黑了、
#    带宽被人抢光了。拿到一个就直接用，多半是超时、连接被拒。
#    所以正确姿势是：取一个 → 先拿它去访问一个测试网址 → 通了才拿去干活。
#
# ⚠️ 本模块底部的自测会打印**真实可用率**。免费代理可用率极低是常态，
#    实测到 0/10 也不奇怪 —— 那正是"真实项目必须买付费代理"的证据。
# ────────────────────────────────────────────────────────────────

# 代理源：访问一次返回一个随机代理（纯文本，形如 "1.2.3.4:8080"）
PROXY_SOURCE = "https://proxypool.scrape.center/random"

# 验证代理用的测试网址。httpbin.org/ip 会把"它看到的来访 IP"回给你，
# 所以不但能验证通不通，还能顺便确认出口 IP 真的变了。
TEST_URL = "http://httpbin.org/ip"
TEST_TIMEOUT = 6  # 秒。免费代理慢是常态，但等太久不如换一个

# 简单的失效剔除：验证失败过的代理记在这里，之后不再使用。
# 用 set 是因为它判断"在不在里面"最快。
_dead_proxies: set = set()


def get_proxy() -> Optional[str]:
    """从代理源取一个代理，返回 "IP:端口" 字符串；取不到返回 None。

    这里只负责"取"，不保证能用 —— 能不能用要交给 validate_proxy() 判断。
    """
    try:
        response = requests.get(PROXY_SOURCE, timeout=10)
        response.raise_for_status()
        proxy = response.text.strip()
        # 简单校验一下格式，防止代理源出故障时返回一段 HTML 错误页
        if ":" not in proxy or len(proxy) > 64:
            return None
        return proxy
    except requests.RequestException as exc:
        print(f"  [代理源] 取代理失败：{type(exc).__name__}: {exc}")
        return None


def to_requests_proxies(proxy: str) -> dict:
    """把 "IP:端口" 变成 requests 认识的 proxies 字典。"""
    return {"http": f"http://{proxy}", "https": f"http://{proxy}"}


def validate_proxy(proxy: str, timeout: int = TEST_TIMEOUT) -> bool:
    """拿这个代理去访问测试网址，通了返回 True，否则 False 并把它拉黑。"""
    try:
        response = requests.get(
            TEST_URL, proxies=to_requests_proxies(proxy), timeout=timeout
        )
        if response.status_code == 200:
            return True
        print(f"  [验证] {proxy} 返回状态码 {response.status_code}")
    except requests.RequestException as exc:
        # 免费代理最常见的三种死法：连不上、握手失败、超时
        print(f"  [验证] {proxy} 不可用：{type(exc).__name__}")
    mark_dead(proxy)
    return False


def mark_dead(proxy: str) -> None:
    """把一个代理标记为失效，之后 get_valid_proxy 不会再返回它。"""
    _dead_proxies.add(proxy)


def get_valid_proxy(max_try: int = 10, interval: float = 0.5) -> Optional[str]:
    """反复取代理并验证，直到拿到一个**确实能用**的，或者试满 max_try 次。

    返回 "IP:端口"；max_try 次都没成功就返回 None，
    调用方看到 None 应该退回到"不用代理 + 慢速请求"这个方案，而不是死循环。
    """
    for attempt in range(1, max_try + 1):
        proxy = get_proxy()
        if proxy is None:
            time.sleep(interval)
            continue
        if proxy in _dead_proxies:
            print(f"  [第 {attempt} 次] {proxy} 之前验证失败过，跳过")
            continue
        print(f"  [第 {attempt} 次] 拿到 {proxy}，正在验证……")
        if validate_proxy(proxy):
            print(f"  [第 {attempt} 次] ✅ {proxy} 可用")
            return proxy
        time.sleep(interval)
    return None


def dead_count() -> int:
    """本次运行中被判定失效的代理数量。"""
    return len(_dead_proxies)


def _self_test(sample: int = 10) -> None:
    """自测：取 sample 个代理逐个验证，打印真实可用率。"""
    print(f"代理源：{PROXY_SOURCE}")
    print(f"测试网址：{TEST_URL}（超时 {TEST_TIMEOUT} 秒）")
    print(f"取 {sample} 个代理逐个验证……\n")

    ok = 0
    tested = 0
    for i in range(1, sample + 1):
        proxy = get_proxy()
        if proxy is None:
            print(f"{i:2}. 取代理失败，跳过")
            continue
        tested += 1
        print(f"{i:2}. {proxy}")
        if validate_proxy(proxy):
            ok += 1
            print("     ✅ 可用")
    print("\n" + "=" * 46)
    if tested:
        print(f"实测可用率：{ok}/{tested} = {ok / tested * 100:.0f}%")
    else:
        print("一个代理都没取到，代理源本身可能挂了")
    print(f"已拉黑失效代理：{dead_count()} 个")
    if ok == 0:
        print("\n可用率 0 —— 这不是代码有问题，这是免费公开代理的常态：")
        print("  它们全网共享、随时下线、还经常被目标网站直接拉黑。")
        print("  真实项目要么买付费代理（几十到几百元/月），要么自建代理服务器。")
    print("=" * 46)


if __name__ == "__main__":
    _self_test()
