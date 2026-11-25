"""编辑视角：已上线图卡与草稿的处置差异，以及新词在哪些渠道真正可用。"""
from __future__ import annotations

from .comments import CommentReading, read_comments
from .design import adoption_claims
from .model import CatalogView, Pack
from .names import all_name_uses, is_draft


def view_disposition(pack: Pack, view: CatalogView) -> dict:
    """一张图卡该怎么处置：已上线、草稿、或将下架核对。"""
    outlet = pack.outlet(view.outlet)
    if is_draft(view):
        action = "hold_draft"
        detail = "草稿不对用户开放；先核对正式名与图文关联，另立发布版本后再上线"
    elif outlet.published:
        action = "live_keep"
        detail = "已上线；改词须另立版本，不能直接覆盖顾客已看到的色名"
    else:
        action = "pending"
        detail = "渠道待上架；按本次确认的正式名排版"
    return {
        "view": view.id,
        "outlet": outlet.id,
        "brand": outlet.brand,
        "market": outlet.market,
        "label": view.label,
        "sample": view.sample,
        "layout": view.layout,
        "draft": is_draft(view),
        "outlet_phase": outlet.phase,
        "action": action,
        "detail": detail,
    }


def split_after_editorial_approval(pack: Pack) -> list[dict]:
    """编辑把两个色名拆开在售时，导购仍要能凭下单时看到的色名找到实物。"""
    groups: dict[tuple[str, str, str], dict[str, list[str]]] = {}
    for use in all_name_uses(pack):
        if use.status == "draft":
            continue
        groups.setdefault((use.market, use.brand, use.sample), {}).setdefault(
            use.term, []
        ).append(use.source)
    findings = []
    for (market, brand, sample), terms in sorted(groups.items()):
        if len(terms) < 2:
            continue
        findings.append(
            {
                "market": market,
                "brand": brand,
                "sample": sample,
                "terms": {term: sorted(set(sources)) for term, sources in terms.items()},
                "guide_lookup": (
                    f"顾客提到 {'、'.join(sorted(terms))} 中任一名，都按 {sample} 找货；"
                    "已下单的按订单快照里的色名核对，不把已承诺颜色写成新词指向的另一块样。"
                ),
                "customer_facing_option": f"{sample}（可附位置和图记以分出实物）",
            }
        )
    return findings


def editorial_report(pack: Pack, readings: list[CommentReading] | None = None) -> dict:
    dispositions = [view_disposition(pack, view) for view in pack.catalog]
    availability: dict[str, dict] = {}
    for use in all_name_uses(pack):
        entry = availability.setdefault(
            use.term,
            {"term": use.term, "markets": {}, "sources": [], "statuses": set()},
        )
        entry["sources"].append(use.source)
        entry["statuses"].add(use.status)
        market = entry["markets"].setdefault(
            use.market,
            {"live_outlets": [], "draft_outlets": [], "formal": [], "historical": []},
        )
        if use.status == "published":
            market["live_outlets"].append(use.source)
        elif use.status == "draft":
            market["draft_outlets"].append(use.source)
        elif use.status == "formal":
            market["formal"].append(use.source)
        elif use.status == "historical":
            market["historical"].append(use.source)
    outlet_by_view = {view.id: view.outlet for view in pack.catalog}
    readings = readings if readings is not None else read_comments()
    for claim in adoption_claims(readings):
        term = claim.get("term") or ""
        if not term:
            continue
        scope = claim.get("market_scope") or ""
        markets = {
            entry.market
            for entry in pack.glossary
            if entry.brand == claim["brand"] and entry.name == term
        } or {
            outlet.market for outlet in pack.outlets if outlet.brand == claim["brand"]
        }
        if scope and scope != "见回复链":
            markets &= {scope}
        for market in sorted(markets):
            entry = availability.setdefault(
                term, {"term": term, "markets": {}, "sources": [], "statuses": set()}
            )
            entry["sources"].append(claim["comment"])
            entry["statuses"].add("designer_proposal")
            entry["markets"].setdefault(
                market,
                {"live_outlets": [], "draft_outlets": [], "formal": [], "historical": []},
            )
    for term, entry in availability.items():
        for market, buckets in entry["markets"].items():
            for key in ("live_outlets", "draft_outlets"):
                buckets[key] = sorted({outlet_by_view[source] for source in buckets[key] if source in outlet_by_view})
            buckets["formal"] = sorted(set(buckets["formal"]))
            buckets["historical"] = sorted(set(buckets["historical"]))
        entry["statuses"] = sorted(entry["statuses"])
        entry["sources"] = sorted(set(entry["sources"]))
        entry["usable_now"] = [
            market
            for market, buckets in entry["markets"].items()
            if buckets["live_outlets"] or buckets["formal"]
        ]
        entry["draft_only"] = [
            market
            for market, buckets in entry["markets"].items()
            if not buckets["live_outlets"] and not buckets["formal"] and buckets["draft_outlets"]
        ]
    return {
        "views": dispositions,
        "published_views": [item["view"] for item in dispositions if not item["draft"]],
        "draft_views": [item["view"] for item in dispositions if item["draft"]],
        "term_availability": availability,
        "split_terms_per_sample": split_after_editorial_approval(pack),
        "rule": "草稿只供内部核对；已上线图卡的用语不能回溯改动顾客已下单时的色名",
    }
