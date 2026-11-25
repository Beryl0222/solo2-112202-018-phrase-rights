"""把工作底稿渲染成面向前台角色的纯文本简报。"""
from __future__ import annotations

import json


def _line(value: str, indent: int = 0) -> str:
    return "  " * indent + value


def render_briefs(workspace: dict | None = None, outlets: tuple[str, ...] = ()) -> str:
    from .compile import build_workspace

    workspace = workspace or build_workspace()
    lines: list[str] = ["# 色名与发布工作底稿", ""]
    for outlet_id, data in workspace["outlets"].items():
        if outlets and outlet_id not in outlets:
            continue
        requirement = data["requirements"]
        lines.append(f"## 渠道 {outlet_id}（{requirement['brand']} / {requirement['market']}）")
        lines.append(_line(f"呈现方式：{requirement['style']}；状态：{requirement['phase']}"))
        for term in data["terms"]:
            lines.append(
                _line(
                    f"- 图卡 {term['view']}：{term['label']} → {term['sample']}"
                    f"（{term['status']}）{term['layout']}",
                    1,
                )
            )
        for card in requirement["cards"]:
            if card["suggested_text"]:
                lines.append(_line(f"自足说明：{card['view']} → {card['suggested_text']}", 1))
            elif card["needs_text"]:
                lines.append(_line(f"待处理：{card['view']} → {'；'.join(card['reasons'])}", 1))
        for warning in requirement["retention_warnings"]:
            lines.append(_line(f"保留项：{warning['asset']} {warning['issue']}", 1))
        lines.append("")

    lines.append("## 可发布版本")
    for outlet_id, report in workspace["release"]["outlets"].items():
        if outlets and outlet_id not in outlets:
            continue
        for variant in report["variants"]:
            lines.append(_line(f"- {outlet_id} {variant['kind']}：覆盖 {'、'.join(variant['covers']) or '无'}"))
            for key, text in variant["card_texts"].items():
                lines.append(_line(f"{key}：{text}", 2))
            for tradeoff in variant["tradeoffs"]:
                lines.append(_line(tradeoff, 2))
            for blocked in variant["blocked"]:
                lines.append(_line(f"不可发布：{blocked}", 2))
        for conflict in report["crop_conflicts"]:
            lines.append(_line(f"- 裁卡冲突：{conflict['instruction']}"))
        for item in report["non_publishable"]:
            lines.append(_line(f"- 不可发布：{item['item']}｜{item['reason']}"))

    lines.append("")
    lines.append("## 色名冲突")
    for conflict in workspace["names"]["conflicts"]:
        lines.append(_line(json.dumps(conflict, ensure_ascii=False)))
    lines.append("")
    lines.append("## 需设计师确认")
    for item in workspace["comments"]["ambiguities"]:
        lines.append(_line(f"- {item['term']}：{item['question']}"))
    lines.append("")
    lines.append("## 改单")
    for order in workspace["orders"]:
        lines.append(
            _line(
                f"- {order['order']}：{order['status']} → "
                f"{order['final_label']} / {order['final_sample']}"
            )
        )
        for step in order["steps"]:
            lines.append(_line(f"{step['request']} {step['action']}：{step['detail']}", 2))
    return "\n".join(lines)
