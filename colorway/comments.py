"""把文字评语拆成可追溯的片段：实物指代、观看条件、感受用词、明示采用。

同一句里可以同时出现位置、观感和采用，因此一条子句可能带多个标签；
“留到打样”“待定”这类推迟语义会单独标出，不算已经采用。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from pack_check import read_tables

# 位置词只说明拍摄图里的实物位置，不代表颜色本身。
SIDE_WORDS = (
    "左前", "右前", "左边", "右边", "左侧", "右侧", "图左", "图右",
    "前排靠左", "前排靠右", "后排靠左", "后排靠右", "前排", "后排",
)
# 观看条件：不能拿来覆盖交付时采用的官方色名。
VIEWING_WORDS = (
    "暖光", "暖", "日光", "灯下", "对着灯", "背光", "冷光", "光下",
    "青灰", "更深", "更深些", "像", "看起来", "看着", "观感", "偏", "近似", "显",
)
# 明示采用：能被理解为“就用这个叫法”。
ADOPTION_WORDS = (
    "另起色名", "改称", "叫作", "就叫", "叫", "官方", "正式名", "本系列",
    "原色名", "标牌", "仍叫", "还叫", "就是", "定名",
)
# 推迟/待定：有采用动作但没有定案。
DEFERRAL_WORDS = ("留到", "待定", "待打样", "打样再", "暂定", "之后再")
NEGATION_WORDS = ("不是", "不选", "不换", "不作", "没有", "别", "续认", "作废", "不用", "并非", "不要")
CONFIRM_WORDS = ("确认", "按", "还是", "续认", "原来", "仍", "照")

SAMPLE_PATTERN = re.compile(r"S\d+")
QUOTED_PATTERN = re.compile(r"“([^”]+)”")
LAYOUT_PATTERN = re.compile(r"(左前|右前|左边|右边|左侧|右侧|图左|图右|前排靠左|前排靠右|后排靠左|后排靠右)\s*(?:为|是|:)?\s*(S\d+)")


@dataclass(frozen=True)
class Fragment:
    """评语中一个可被单独引用的片段。"""

    text: str
    kind: str
    samples: tuple[str, ...] = ()
    side: str = ""


@dataclass(frozen=True)
class CommentReading:
    """一条评语读出来的片段、指代和观看条件。"""

    comment_id: str
    brand: str
    layout: str
    light: str
    reply_to: str
    fragments: tuple[Fragment, ...] = ()
    layout_samples: tuple[tuple[str, str], ...] = ()
    samples: tuple[str, ...] = ()
    negations: tuple[str, ...] = ()
    confirmations: tuple[str, ...] = ()
    quoted_names: tuple[str, ...] = ()

    def fragments_of(self, kind: str) -> tuple[Fragment, ...]:
        return tuple(fragment for fragment in self.fragments if fragment.kind == kind)

    def sample_for(self, side_word: str) -> str:
        wanted = side_of_word(side_word)
        if not wanted:
            return ""
        for name, sample in self.layout_samples:
            if side_of_word(name) == wanted:
                return sample
        return ""

    def samples_for_clause(self, clause: str) -> tuple[str, ...]:
        explicit = tuple(dict.fromkeys(SAMPLE_PATTERN.findall(clause)))
        if explicit:
            return explicit
        found = []
        for word in SIDE_WORDS:
            if word in clause:
                sample = self.sample_for(word)
                if sample:
                    found.append(sample)
        return tuple(dict.fromkeys(found))


def split_sentences(text: str) -> list[str]:
    """保留原文用字，只按句号和逗号切出互不覆盖的片段。"""
    parts = re.split(r"[。，；！？]", text)
    return [part for part in parts if part]


def side_of_word(word: str) -> str:
    if "左" in word:
        return "left"
    if "右" in word:
        return "right"
    return ""


def layout_samples(layout: str) -> tuple[tuple[str, str], ...]:
    return tuple(LAYOUT_PATTERN.findall(layout))


def classify(clause: str) -> str:
    """按“推迟 > 采用 > 否定 > 感受 > 陈述”给出子句的主标签。"""
    if any(word in clause for word in DEFERRAL_WORDS):
        return "deferral"
    if any(word in clause for word in ADOPTION_WORDS):
        return "adoption"
    if any(word in clause for word in NEGATION_WORDS):
        return "negation"
    if any(word in clause for word in VIEWING_WORDS):
        return "perception"
    return "statement"


def read_comment(row: dict) -> CommentReading:
    layout_map = layout_samples(row["layout"])
    fragments: list[Fragment] = []
    for clause in split_sentences(row["text"]):
        samples = tuple(
            dict.fromkeys(SAMPLE_PATTERN.findall(clause))
            or tuple(sample for word, sample in layout_map if word in clause)
        )
        side = ""
        for word in SIDE_WORDS:
            if word in clause:
                side = word
                break
        if side:
            fragments.append(Fragment(text=clause, kind="position", samples=samples, side=side))
        kind = classify(clause)
        if kind != "statement" or not side:
            fragments.append(Fragment(text=clause, kind=kind, samples=samples, side=side))
    samples = tuple(
        dict.fromkeys(
            SAMPLE_PATTERN.findall(row["text"]) or [sample for _, sample in layout_map]
        )
    )
    return CommentReading(
        comment_id=row["id"],
        brand=row["brand"],
        layout=row["layout"],
        light=row["light"],
        reply_to=row["reply_to"],
        fragments=tuple(fragments),
        layout_samples=layout_map,
        samples=samples,
        negations=tuple(word for word in NEGATION_WORDS if word in row["text"]),
        confirmations=tuple(word for word in CONFIRM_WORDS if word in row["text"]),
        quoted_names=tuple(QUOTED_PATTERN.findall(row["text"])),
    )


def read_comments(
    tables: dict | None = None, directory: Path | str | None = None
) -> list[CommentReading]:
    """读取评语；指定 directory 时从该资料包读，便于处理下一次评样。"""
    if tables is None:
        tables = read_tables(Path(directory)) if directory else read_tables()
    return [read_comment(row) for row in tables["comments.tsv"]]


def thread(readings: list[CommentReading]) -> dict[str, list[CommentReading]]:
    """按 reply_to 把评语串成讨论链，最早的在前。"""
    by_id = {reading.comment_id: reading for reading in readings}
    children: dict[str, list[CommentReading]] = {}
    roots = []
    for reading in readings:
        if reading.reply_to and reading.reply_to in by_id:
            children.setdefault(reading.reply_to, []).append(reading)
        else:
            roots.append(reading)
    ordered: dict[str, list[CommentReading]] = {}
    for root in roots:
        chain = [root]
        pointer = root.comment_id
        while pointer in children:
            following = children[pointer]
            chain.extend(following)
            pointer = following[-1].comment_id
        ordered[root.comment_id] = chain
    return ordered
