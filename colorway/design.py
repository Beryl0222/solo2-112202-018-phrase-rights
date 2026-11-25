"""从自然语言评语追到样色和拍摄位置。

评语里的“青灰”“暖光下像石蓝”只是观感；只有明示采用的品牌词才进入命名。
本模块输出这个区分，并把需要设计师确认的叫法单独列出。
"""
from __future__ import annotations

from dataclasses import dataclass

from .comments import CommentReading, read_comments, thread
from .model import Pack


@dataclass(frozen=True)
class Ambiguity:
    """需要设计师确认的一项叫法。"""

    term: str
    samples: tuple[str, ...]
    channels: tuple[str, ...]
    question: str
    sources: tuple[str, ...] = ()


def side_of(word: str) -> str:
    if "左" in word:
        return "left"
    if "右" in word:
        return "right"
    return ""


def _fragment_rows(readings: list[CommentReading], kind: str) -> list[dict]:
    rows = []
    for reading in readings:
        for fragment in reading.fragments_of(kind):
            rows.append(
                {
                    "comment": reading.comment_id,
                    "brand": reading.brand,
                    "light": reading.light,
                    "text": fragment.text,
                    "samples": list(
                        fragment.samples or reading.samples_for_clause(fragment.text)
                    ),
                    "side": side_of(fragment.side),
                }
            )
    return rows


def _claim_term(row: dict, reading: CommentReading) -> str:
    """从采用句里取出品牌词；引号优先，其次看句中的“叫/称”。"""
    for name in reading.quoted_names:
        if name in row["text"]:
            return name
    return _quoted_from(row)


def reading_summary(reading: CommentReading) -> dict:
    """把一条评语拆成可复核的片段。"""
    perceptions = [
        fragment.text for fragment in reading.fragments_of("perception")
    ]
    adoptions = [
        {**row, "term": _claim_term(row, reading)}
        for row in _fragment_rows([reading], "adoption")
    ]
    deferrals = _fragment_rows([reading], "deferral")
    return {
        "id": reading.comment_id,
        "brand": reading.brand,
        "layout": reading.layout,
        "light": reading.light,
        "reply_to": reading.reply_to,
        "physical_reference": _fragment_rows([reading], "position"),
        "viewing_conditions": {
            "light": reading.light,
            "perception_phrases": perceptions,
            "note": "观看条件只用于解释色差，不覆盖官方色名",
        },
        "adopted_terms": adoptions,
        "deferred": deferrals,
        "samples": list(reading.samples),
        "quoted_names": list(reading.quoted_names),
        "negations": list(reading.negations),
        "confirmations": list(reading.confirmations),
        "decision": "deferred" if deferrals and not adoptions else (
            "adopted" if adoptions else "observed"
        ),
    }


def adoption_claims(readings: list[CommentReading]) -> list[dict]:
    """明示采用的品牌词和它落到的样、市场、来源。"""
    claims = []
    for row in _fragment_rows(readings, "adoption"):
        claims.append(
            {
                **row,
                "term": _quoted_from({**row, "quoted_names": []}),
                "market_scope": "西区" if "西区" in row["text"] else "见回复链",
                "source_kind": "designer_comment",
            }
        )
    return claims


def perception_claims(readings: list[CommentReading]) -> list[dict]:
    claims = []
    for row in _fragment_rows(readings, "perception"):
        claims.append({**row, "source_kind": "designer_observation"})
    return claims


def _channels_for(pack: Pack, term: str, samples: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                view.outlet
                for view in pack.catalog
                if view.label == term and view.sample in samples
            }
        )
    )


def ambiguities(pack: Pack, readings: list[CommentReading]) -> list[Ambiguity]:
    """颜色多义时，指出哪些样品与渠道的叫法要设计师确认。"""
    found: list[Ambiguity] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()

    # 1. 同一市场同词落到多样的样。
    by_term: dict[tuple[str, str], set[str]] = {}
    for view in pack.catalog:
        outlet = pack.outlet(view.outlet)
        by_term.setdefault((outlet.market, view.label), set()).add(view.sample)
    for entry in pack.glossary:
        by_term.setdefault((entry.market, entry.name), set()).add(entry.sample)
    for (market, term), samples in sorted(by_term.items()):
        if len(samples) < 2:
            continue
        key = (term, tuple(sorted(samples)))
        if key in seen:
            continue
        seen.add(key)
        found.append(
            Ambiguity(
                term=term,
                samples=tuple(sorted(samples)),
                channels=_channels_for(pack, term, tuple(sorted(samples))),
                question=(
                    f"{market}的“{term}”已指到 {'、'.join(sorted(samples))}，"
                    "请确认各渠道采用哪一块样、旧订单按哪一块样履约。"
                ),
                sources=tuple(
                    sorted(
                        [view.id for view in pack.catalog if view.label == term]
                        + [entry.id for entry in pack.glossary if entry.name == term]
                    )
                ),
            )
        )

    # 2. 评语里的采用与旧换季名指向不同样。
    for claim in adoption_claims(readings):
        name = _quoted_from(claim)
        samples = tuple(claim["samples"])
        if not name or len(samples) != 1:
            continue
        elsewhere = [
            entry
            for entry in pack.glossary
            if entry.name == name and entry.sample != samples[0]
        ]
        if elsewhere:
            key = (name, tuple(sorted({samples[0], *(entry.sample for entry in elsewhere)})))
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Ambiguity(
                    term=name,
                    samples=key[1],
                    channels=_channels_for(pack, name, key[1]),
                    question=(
                        f"评语把“{name}”用于 {samples[0]}，旧换季页却把它用于 "
                        f"{'、'.join(sorted(entry.sample for entry in elsewhere))}；"
                        "请确认新旧页面各自的可发布名，以及老订单按哪一块样履约。"
                    ),
                    sources=tuple([claim["comment"]] + [entry.id for entry in elsewhere]),
                )
            )

    # 3. 渠道草稿用了正式名表里没有的叫法。
    for view in pack.catalog:
        if "草稿" not in view.layout:
            continue
        outlet = pack.outlet(view.outlet)
        formal = [
            entry
            for entry in pack.glossary
            if entry.brand == outlet.brand
            and entry.market == outlet.market
            and entry.sample == view.sample
        ]
        if not any(entry.name == view.label for entry in formal):
            found.append(
                Ambiguity(
                    term=view.label,
                    samples=(view.sample,),
                    channels=(view.outlet,),
                    question=f"草稿 {view.id} 的“{view.label}”不在正式名表内，请确认能否发布。",
                    sources=(view.id,),
                )
            )
    return found


def _quoted_from(claim: dict) -> str:
    for fragment in claim.get("quoted_names", []):
        if fragment:
            return fragment
    text = claim["text"]
    if "“" in text and "”" in text:
        return text.split("“", 1)[1].split("”", 1)[0]
    return _unquoted_term(text)


def scoped_effects(pack: Pack, readings: list[CommentReading]) -> list[dict]:
    """明确限定在某地的采用，不改变其它品牌对其自有样板的命名。

    返回每条采用的可作用范围和必须保持原样的范围，便于编辑核对。
    """
    effects = []
    markets = pack.markets()
    for claim in adoption_claims(readings):
        term = claim.get("term") or ""
        scope = claim.get("market_scope") or ""
        scoped_markets = (
            [scope] if scope and scope != "见回复链" and scope in markets else list(markets)
        )
        untouched_markets = [market for market in markets if market not in scoped_markets]
        other_brands = sorted(
            {
                entry.brand
                for entry in pack.glossary
                if entry.market in scoped_markets and entry.brand != claim["brand"]
            }
        )
        effects.append(
            {
                "comment": claim["comment"],
                "brand": claim["brand"],
                "term": term,
                "samples": claim["samples"],
                "scoped_markets": scoped_markets,
                "unchanged_markets": untouched_markets,
                "unchanged_brands": other_brands,
                "note": (
                    "该回复只在所指市场生效；其它品牌对其自有样板的命名不受影响"
                    if untouched_markets or other_brands
                    else "未限地域，仍须先与正式名表核对"
                ),
            }
        )
    return effects


BRAND_TERM_SUFFIXES = ("改称", "叫作", "就叫", "另起色名", "定名", "称为", "叫作", "称")


def _unquoted_term(text: str) -> str:
    """从未加引号的采用句里取出品牌词，如“右边仍叫石蓝”。"""
    for marker in ("叫", "称", "就是本系列", "本系列", "就是"):
        if marker in text:
            tail = text.split(marker, 1)[1].strip()
            tail = tail.lstrip("“”\"' ")
            for stop in ("，", "。", "；"):
                tail = tail.split(stop, 1)[0]
            if tail and not any(word in tail for word in ("的", "了", "不")):
                return tail
    return ""


def comment_report(pack: Pack, readings: list[CommentReading] | None = None) -> dict:
    readings = readings or read_comments()
    chains = thread(readings)
    return {
        "comments": [reading_summary(reading) for reading in readings],
        "threads": {
            root: [reading.comment_id for reading in chain] for root, chain in chains.items()
        },
        "adoptions": adoption_claims(readings),
        "scoped_effects": scoped_effects(pack, readings),
        "perceptions": perception_claims(readings),
        "ambiguities": [
            {
                "term": item.term,
                "samples": list(item.samples),
                "channels": list(item.channels),
                "question": item.question,
                "sources": list(item.sources),
            }
            for item in ambiguities(pack, readings)
        ],
        "official_name_rule": "评语中的观感、光源猜测和明示采用均不覆盖交付时的官方色名",
    }
