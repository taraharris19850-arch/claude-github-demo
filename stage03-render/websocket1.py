"""
案例：websocket1 · https://websocket1.scrape.center
Issue：#4
目标：用 websockets 库连上聊天室的 WebSocket，收发消息并把完整往来记录存下来
"""

import json
import ssl
import time
import uuid
from datetime import datetime
from pathlib import Path

import certifi
from websockets.sync.client import connect

# ---------------------------------------------------------------------------
# 【WebSocket 和普通 HTTP 请求有什么区别？】
#
# HTTP = 写信。
#     你寄一封信（请求），对方回一封信（响应），然后这次来往就结束了。
#     你想再问一句？重新写一封、重新贴邮票、重新寄。每次都是一次性的。
#     关键限制：**只能你先开口**。服务器有新消息想主动告诉你？没门，它没你地址。
#     所以传统网页要做"实时"效果只能靠"轮询"：每隔 1 秒问一次"有新消息吗？"
#     ——99% 的回答都是"没有"，纯属浪费。
#
# WebSocket = 打电话。
#     拨通之后线就一直接着不挂，双方谁想说话随时开口，不用重新拨号。
#     服务器有新消息，直接推给你，不用你一遍遍地问。
#     这就是【全双工长连接】：全双工=双方能同时说，长连接=接通了就不断开。
#
# 怎么"拨通"的？一开始其实还是发一个普通的 HTTP 请求，
# 但头里带一句 "Upgrade: websocket"，意思是"能不能把这条线升级成电话？"
# 服务器同意后回 101 状态码（Switching Protocols），这条 TCP 连接就从此改说 WebSocket 了。
# 这个过程叫【握手】，握完手之后就跟 HTTP 没关系了。
# 地址也从 http:// 变成 ws://，https:// 变成 wss://（wss 就是加密版，相当于 WebSocket 的 HTTPS）。
#
# 【怎么找到这个 WebSocket 地址的？】
# 直接 curl 首页只能拿到一个空壳 HTML，地址藏在 JS 里。我是这么挖出来的：
#   1. curl 首页，看到它加载了 /js/app.xxx.js 和 /js/chunk-e3bb7ce4.xxx.js
#   2. 把这两个 JS 下载下来，搜 "WebSocket" 这个关键词
#   3. 在 chunk 里搜到了这么一段（压缩过的代码）：
#        j = "https:" === location.protocol ? "wss" : "ws",
#        T = new WebSocket("".concat(j, "://").concat(location.host, "/websocket"))
#      翻译过来就是：协议是 https 就用 wss，地址 = wss://当前域名/websocket
#   4. 同一段代码里还能看到收发消息的格式：
#        发送：ws.send(JSON.stringify({ sender: 这个uuid, content: 文本 }))
#        接收：JSON.parse(收到的) 里取 sender 和 answer 两个字段
#
# 这套"扒 JS 找线索"的功夫，后面第 6 阶段的 JS 逆向会天天用到。
# ---------------------------------------------------------------------------

WS_URL = "wss://websocket1.scrape.center/websocket"

# 每条消息之间至少歇 1 秒，别把人家聊天室刷屏了。
MESSAGE_INTERVAL = 1

# 等一条回复最多等多久（秒）。
RECV_TIMEOUT = 20
OPEN_TIMEOUT = 20

OUTPUT_PATH = Path(__file__).parent / "data" / "websocket1.json"

# 要发过去的几句话。这个站是个"复读机"机器人，会把你说的话原样加个感叹号还给你，
# 所以内容本身不重要，重点是把"发出去—收回来"这个来回跑通并记录下来。
MESSAGES_TO_SEND = [
    "你好",
    "我在学 WebSocket 抓包",
    "这是第三条测试消息",
    "再见",
]


def build_ssl_context() -> ssl.SSLContext:
    """
    造一个 SSL 上下文，并明确告诉它到哪儿找根证书。

    为什么要多写这一步？这是我在这个脚本里踩的第一个坑：
    直接 connect() 会报 CERTIFICATE_VERIFY_FAILED（证书验证失败）。
    原因是 macOS 上用官网装的 Python，标准库 ssl 模块找不到系统的根证书库，
    而 requests / httpx 之所以没事，是因为它们自带了一份证书（certifi 这个包）。
    websockets 用的是标准库，就得我们手动把 certifi 那份指给它。

    注意：网上很多帖子会教你写 ssl._create_unverified_context() 来"解决"这个报错——
    那是【关掉证书验证】，等于把防伪标签撕了，中间人可以随便冒充服务器。
    正确做法是像下面这样，给它一份靠谱的证书，而不是干脆不检查。
    """
    return ssl.create_default_context(cafile=certifi.where())


def chat() -> dict:
    """
    连上聊天室，把 MESSAGES_TO_SEND 里的话一句句发过去，每发一句就等一句回复。
    返回一个字典，里面是完整的消息往来记录。
    """
    # 这个 sender 是我们这个"客户端"的身份证。
    # 页面里的 JS 也是这么干的：进页面时随机生成一个 uuid，之后每条消息都带上它。
    # 服务器靠它区分是谁在说话，回复里也会原样带回来。
    sender = str(uuid.uuid4())
    print(f"我的 sender 身份：{sender}")
    print(f"正在连接：{WS_URL}")

    transcript: list[dict] = []

    # with 语句保证不管中间出什么错，最后都会正经地把连接关掉（发一个关闭帧）。
    # 直接把进程杀掉是"啪"地挂断电话，不礼貌也容易让服务端留下悬空连接。
    with connect(WS_URL, ssl=build_ssl_context(), open_timeout=OPEN_TIMEOUT) as ws:
        print("连接成功！（HTTP 握手已升级为 WebSocket）\n")

        for text in MESSAGES_TO_SEND:
            # ---- 发 ----
            payload = json.dumps({"sender": sender, "content": text})
            ws.send(payload)
            sent_at = datetime.now().isoformat(timespec="seconds")
            print(f"→ 我说：  {text}")
            transcript.append(
                {
                    "direction": "sent",  # sent = 我发出去的
                    "time": sent_at,
                    "raw": payload,  # 原始报文，留证据
                    "text": text,
                }
            )

            # ---- 收 ----
            # 注意这里能直接 recv()，是因为这个站是"一问一答"的复读机。
            # 真实场景下服务器可能随时主动推消息（比如别人发言、行情跳动），
            # 那就不能这么写，得开一个循环一直收，或者用异步版本边收边处理。
            reply_raw = ws.recv(timeout=RECV_TIMEOUT)
            received_at = datetime.now().isoformat(timespec="seconds")
            reply = json.loads(reply_raw)
            answer = reply.get("answer", "")
            print(f"← 机器人：{answer}")
            transcript.append(
                {
                    "direction": "received",  # received = 服务器回给我的
                    "time": received_at,
                    "raw": reply_raw,
                    "text": answer,
                    # 把服务器回的 sender 也记下来，方便核对是不是自己那条消息的回复。
                    "sender_echo": reply.get("sender", ""),
                }
            )

            time.sleep(MESSAGE_INTERVAL)

    print("\n连接已正常关闭。")

    return {
        "ws_url": WS_URL,
        "sender": sender,
        "message_count": len(transcript),
        "transcript": transcript,
    }


def save(record: dict) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已保存 {record['message_count']} 条消息记录到 {OUTPUT_PATH}")


def main() -> None:
    record = chat()
    save(record)

    # 简单核对一下：发出去几条、收回来几条，对不对得上。
    sent = sum(1 for m in record["transcript"] if m["direction"] == "sent")
    received = sum(1 for m in record["transcript"] if m["direction"] == "received")
    print(f"\n统计：发出 {sent} 条，收到 {received} 条回复。")


if __name__ == "__main__":
    main()
