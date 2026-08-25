#!/usr/bin/env python3
"""一个用来演示 Claude Code 与 GitHub 协作的命令行小程序。"""

import sys


def greet(name: str) -> str:
    """生成一句问候语。"""
    return f"你好，{name}！"


def main() -> None:
    name = sys.argv[1] if len(sys.argv) > 1 else "世界"
    print(greet(name))


if __name__ == "__main__":
    main()
