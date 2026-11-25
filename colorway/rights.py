"""解析品牌词表里的图片发布许可。

photo_right 按拍摄版式逐条限定，逗号分段；每段开头若出现版式字母，后面
的规则就归到那个版式。同一张图可以有“可叠字但中心不可”“可裁单卡但另一
版式不可发布”这类组合，不能只看整串里有没有某个词。
"""
from __future__ import annotations

from dataclasses import dataclass, field

LAYOUTS = ("N", "M")
OVERLAY_POSITIONS = ("左下", "右下", "左上", "右上", "左侧", "右侧", "顶部", "底部")
MAXIMIZE_WORDS = ("可裁", "可裁单卡", "可裁切")
WHOLE_WORDS = ("整图可用", "整图", "整页可用")
FORBID_WORDS = ("不可发布", "不可用", "禁用")
HISTORICAL_WORDS = ("旧换季页", "旧区域", "旧称")


@dataclass
class LayoutRights:
    layout: str
    may_overlay: bool = False
    overlay_positions: tuple[str, ...] = ()
    center_forbidden: bool = False
    may_crop: bool = False
    whole_only: bool = False
    forbidden: bool = False
    historical: bool = False
    raw: list[str] = field(default_factory=list)

    @property
    def may_edit(self) -> bool:
        return (self.may_overlay or self.may_crop) and not self.forbidden

    @property
    def may_publish(self) -> bool:
        return not self.forbidden and (self.may_overlay or self.may_crop or self.whole_only)

    @property
    def may_crop_for_channel(self) -> bool:
        """渠道会裁图时，该版式还能不能给出独立卡。

        “只允许整图”属于不可裁，即使整图本身可以发布。
        """
        return self.may_publish and self.may_crop and not self.forbidden

    def summary(self) -> str:
        bits = []
        if self.may_overlay:
            where = "、".join(self.overlay_positions) or "可叠字处"
            bits.append(f"可叠字（{where}）")
        if self.center_forbidden:
            bits.append("中心不可叠字")
        if self.may_crop:
            bits.append("可裁单卡")
        if self.whole_only:
            bits.append("只允许整图")
        if self.forbidden:
            bits.append("不可发布")
        if self.historical:
            bits.append("旧换季页系列名")
        return "，".join(bits) or "未明确可编辑范围"


def parse_photo_right(text: str) -> dict[str, LayoutRights]:
    """把许可串拆成 版式 → 规则。没有版式字母的段落不归属任何版式。"""
    rights: dict[str, LayoutRights] = {}
    current: LayoutRights | None = None
    for segment in (part.strip() for part in text.replace("；", "，").split("，")):
        if not segment:
            continue
        head = segment[0] if segment else ""
        if head in LAYOUTS:
            # 段首字母是版式；若后面紧跟逗号分层（如“N 不可发布”）。
            current = rights.setdefault(head, LayoutRights(layout=head))
            body = segment[1:].strip()
        else:
            body = segment
        if current is None:
            # 版式之前的说明，如“旧换季页区域系列名”，留给 first layout 吗？不，保留在 text。
            continue
        current.raw.append(segment)
        _apply(current, body)
    if not rights and text:
        # 没有版式字母但明确整段禁用时，按“所有版式都不可用”处理。
        if any(word in text for word in FORBID_WORDS):
            for layout in LAYOUTS:
                rights[layout] = LayoutRights(layout=layout, forbidden=True, raw=[text])
    for right in rights.values():
        if any(word in "，".join(right.raw) for word in HISTORICAL_WORDS):
            right.historical = True
    return rights


def _apply(right: LayoutRights, body: str) -> None:
    for word in FORBID_WORDS:
        if word in body:
            right.forbidden = True
    for word in MAXIMIZE_WORDS:
        if word in body:
            right.may_crop = True
    for word in WHOLE_WORDS:
        if word in body:
            right.whole_only = True
    if "叠字" in body or "覆盖" in body or "文字" in body:
        positions = tuple(word for word in OVERLAY_POSITIONS if word in body)
        if "可" in body and not body.startswith("中心不可"):
            right.may_overlay = True
            right.overlay_positions = tuple(dict.fromkeys((*right.overlay_positions, *positions)))
        if "中心" in body and "不可" in body:
            right.center_forbidden = True


def rights_for(text: str, layout: str) -> LayoutRights | None:
    return parse_photo_right(text).get(layout)


def layout_mentions(text: str) -> tuple[str, ...]:
    return tuple(layout for layout in LAYOUTS if layout in parse_photo_right(text))
