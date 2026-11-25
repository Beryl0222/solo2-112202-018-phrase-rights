"""命令行：生成工作底稿、编辑简报和导购答复。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .compile import DEFAULT_DATA, build_workspace, write_workspace
from .render import render_briefs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=DEFAULT_DATA, help="业务资料包路径")
    parser.add_argument("--json", type=Path, help="写出完整工作底稿 JSON")
    parser.add_argument("--brief", action="store_true", help="打印渠道与名称简报")
    parser.add_argument("--outlet", action="append", default=[], help="只输出指定渠道")
    parser.add_argument("--orders", action="store_true", help="打印改单处理结果")
    parser.add_argument("--check", action="store_true", help="存在待确认项时返回非零")
    args = parser.parse_args(argv)

    workspace = build_workspace(args.directory)
    if args.json:
        target = write_workspace(args.directory, args.json)
        print(f"已写出 {target}")
    if args.brief or not (args.json or args.orders or args.check):
        print(render_briefs(workspace, tuple(args.outlet)))
    if args.orders:
        for order in workspace["orders"]:
            print(f"{order['order']}：{order['status']} → {order['final_label']} / {order['final_sample']}")
            for step in order["steps"]:
                print(f"  {step['request']} {step['action']}：{step['detail']}")
    if args.check:
        pending = [order for order in workspace["orders"] if order["status"] == "pending"]
        ambiguities = workspace["comments"]["ambiguities"]
        blockers = [
            item
            for report in workspace["release"]["outlets"].values()
            for item in report["non_publishable"]
        ]
        if pending or ambiguities:
            print(
                json.dumps(
                    {
                        "pending_orders": [order["order"] for order in pending],
                        "need_designer_confirmation": [
                            item["term"] for item in ambiguities
                        ],
                        "non_publishable": len(blockers),
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        print(json.dumps({"non_publishable": len(blockers)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
