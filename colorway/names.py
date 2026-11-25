"""色名、渠道用语与历史叫法的对照。

同一段文字在不同来源里可能是：正式色名、已上线的渠道用语、旧换季页的
区域系列名，或仅存在于草稿。这里用记录号保留每种出处，不合并来源。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .model import CatalogView, Glossary, Pack

STATUS_ORDER = {"formal": 0, "published": 1, "historical": 2, "draft": 3}


@dataclass(frozen=True)
class NameUse:
    """一次“某词指某块样”的记录。"""

    term: str
    sample: str
    brand: str
    market: str
    status: str
    source: str
    at: datetime | None = None
    note: str = ""

    @property
    def order_key(self) -> tuple:
        return (STATUS_ORDER[self.status], self.source)


@dataclass(frozen=True)
class TermCandidate:
    """顾客说出的词在某个市场、某个时点能指到的实物。"""

    sample: str
    term: str
    uses: tuple[NameUse, ...]

    @property
    def sources(self) -> tuple[str, ...]:
        return tuple(use.source for use in self.uses)

    @property
    def is_live(self) -> bool:
        return any(use.status in ("published", "formal") for use in self.uses)

    @property
    def is_historical_only(self) -> bool:
        return not self.is_live and any(use.status == "historical" for use in self.uses)

    @property
    def status(self) -> str:
        if self.is_live:
            return "live"
        if self.is_historical_only:
            return "historical"
        return "draft"


def is_draft(view: CatalogView) -> bool:
    return "草稿" in view.layout or "草稿" in view.label


def glossary_uses(entry: Glossary) -> NameUse:
    status = "historical" if entry.is_historical else "formal"
    return NameUse(
        term=entry.name,
        sample=entry.sample,
        brand=entry.brand,
        market=entry.market,
        status=status,
        source=entry.id,
        note=entry.photo_right,
    )


def catalog_uses(view: CatalogView, outlet_brand: str, market: str) -> NameUse:
    status = "draft" if is_draft(view) else "published"
    return NameUse(
        term=view.label,
        sample=view.sample,
        brand=outlet_brand,
        market=market,
        status=status,
        source=view.id,
        at=view.published,
        note=view.layout,
    )


def all_name_uses(pack: Pack) -> list[NameUse]:
    uses = [glossary_uses(entry) for entry in pack.glossary]
    for view in pack.catalog:
        outlet = pack.outlet(view.outlet)
        uses.append(catalog_uses(view, outlet.brand, outlet.market))
    return uses


def formal_names(pack: Pack) -> list[Glossary]:
    return [entry for entry in pack.glossary if not entry.is_historical]


def historical_names(pack: Pack) -> list[Glossary]:
    return [entry for entry in pack.glossary if entry.is_historical]


def resolve_term(
    pack: Pack,
    term: str,
    market: str,
    as_of: datetime | None = None,
    brand: str | None = None,
    include_drafts: bool = False,
) -> list[TermCandidate]:
    """按市场、品牌和时点找出该词可能指向的样。

    时点只约束渠道上线记录；正式色名和历史名不因个人评语而失效。
    同一来源在同一时点只贡献一次。草稿默认不进入面向顾客的候选。
    """
    grouped: dict[str, list[NameUse]] = {}
    for use in all_name_uses(pack):
        if use.term != term or use.market != market:
            continue
        if brand is not None and use.brand != brand:
            continue
        if use.status == "draft" and not include_drafts:
            continue
        if use.status == "published" and as_of is not None and use.at and use.at > as_of:
            continue
        grouped.setdefault(use.sample, []).append(use)
    candidates = [
        TermCandidate(sample=sample, term=term, uses=tuple(sorted(uses, key=lambda use: use.order_key)))
        for sample, uses in grouped.items()
    ]
    return sorted(candidates, key=lambda candidate: candidate.sample)


def name_conflicts(pack: Pack, market: str | None = None) -> list[dict]:
    """同词多样、同样多名，以及同一名称跨市场指不同样。"""
    uses = all_name_uses(pack)
    if market is not None:
        uses = [use for use in uses if use.market == market]
    conflicts = []
    by_term: dict[tuple[str, str], list[NameUse]] = {}
    by_sample: dict[tuple[str, str], list[NameUse]] = {}
    for use in uses:
        by_term.setdefault((use.market, use.term), []).append(use)
        by_sample.setdefault((use.market, use.sample), []).append(use)
    for (market_name, term), term_uses in sorted(by_term.items()):
        samples = sorted({use.sample for use in term_uses})
        if len(samples) > 1:
            conflicts.append(
                {
                    "kind": "term_multiple_samples",
                    "market": market_name,
                    "term": term,
                    "samples": samples,
                    "sources": sorted(use.source for use in term_uses),
                }
            )
    for (market_name, sample), sample_uses in sorted(by_sample.items()):
        terms = sorted({use.term for use in sample_uses})
        if len(terms) > 1:
            conflicts.append(
                {
                    "kind": "sample_multiple_terms",
                    "market": market_name,
                    "sample": sample,
                    "terms": terms,
                    "sources": sorted(use.source for use in sample_uses),
                }
            )
    cross: dict[str, dict[str, set[str]]] = {}
    for use in all_name_uses(pack):
        cross.setdefault(use.term, {}).setdefault(use.market, set()).add(use.sample)
    for term, markets in sorted(cross.items()):
        if len(markets) < 2:
            continue
        samples = {sample for values in markets.values() for sample in values}
        if len(samples) > 1:
            conflicts.append(
                {
                    "kind": "term_market_split",
                    "term": term,
                    "markets": {name: sorted(values) for name, values in sorted(markets.items())},
                }
            )
    return conflicts


def term_scope(pack: Pack) -> dict[str, dict]:
    """一个词实际出现在哪些市场、品牌和样上。

    “不同地区属于当地系列名称”就是这里显出来的作用域差异，不能把一地的
    系列名当作所有市场的通用名。
    """
    scope: dict[str, dict] = {}
    for use in all_name_uses(pack):
        entry = scope.setdefault(
            use.term,
            {"markets": {}, "brands": set(), "samples": set(), "statuses": set(), "sources": set()},
        )
        entry["markets"].setdefault(use.market, set()).add(use.sample)
        entry["brands"].add(use.brand)
        entry["samples"].add(use.sample)
        entry["statuses"].add(use.status)
        entry["sources"].add(use.source)
    result = {}
    for term, entry in sorted(scope.items()):
        result[term] = {
            "markets": {market: sorted(samples) for market, samples in sorted(entry["markets"].items())},
            "brands": sorted(entry["brands"]),
            "samples": sorted(entry["samples"]),
            "statuses": sorted(entry["statuses"]),
            "sources": sorted(entry["sources"]),
            "single_market": len(entry["markets"]) == 1,
            "single_brand": len(entry["brands"]) == 1,
        }
    return result


def term_timeline(pack: Pack, term: str, market: str) -> list[dict]:
    """一个词在同一市场的指代变化，按上线时间排序。"""
    uses = [
        use
        for use in all_name_uses(pack)
        if use.term == term and use.market == market and use.status != "draft"
    ]
    uses.sort(key=lambda use: (use.at is None, use.at, use.source))
    timeline = []
    for use in uses:
        timeline.append(
            {
                "source": use.source,
                "status": use.status,
                "sample": use.sample,
                "brand": use.brand,
                "at": use.at.isoformat() if use.at else None,
                "note": use.note,
            }
        )
    samples = {use.sample for use in uses}
    if len(samples) > 1:
        first = next(use for use in uses if use.sample != uses[0].sample)
        timeline.append(
            {
                "warning": "term_referent_changed",
                "term": term,
                "from": uses[0].sample,
                "to": first.sample,
                "detail": "同词前后指到不同实物，旧订单不能按新指向改派",
            }
        )
    return timeline


def terms_for_outlet(pack: Pack, outlet_id: str) -> list[dict]:
    """渠道实际出现的用语，标出正式名/历史名/草稿。"""
    outlet = pack.outlet(outlet_id)
    rows = []
    for view in pack.catalog:
        if view.outlet != outlet_id:
            continue
        formal = [
            entry.id
            for entry in formal_names(pack)
            if entry.brand == outlet.brand
            and entry.market == outlet.market
            and entry.sample == view.sample
            and entry.name == view.label
        ]
        historical = [
            entry.id
            for entry in historical_names(pack)
            if entry.brand == outlet.brand
            and entry.market == outlet.market
            and entry.sample == view.sample
            and entry.name == view.label
        ]
        if formal:
            status = "formal"
        elif historical:
            status = "historical"
        elif is_draft(view):
            status = "draft"
        else:
            status = "channel_only"
        rows.append(
            {
                "view": view.id,
                "sample": view.sample,
                "label": view.label,
                "status": status,
                "formal_sources": formal,
                "historical_sources": historical,
                "layout": view.layout,
                "published": view.published.isoformat() if view.published else None,
            }
        )
    return rows
