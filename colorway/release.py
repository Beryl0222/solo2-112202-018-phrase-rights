"""发布层：本地化商品用语、图文关联、合规版本和不可发布范围。

用语只认品牌词表里的正式名；渠道稿和旧换季名单独标注。图卡说明来自
assets.retain，不能为了删词而丢掉辨样依据。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import CatalogView, Pack
from .names import all_name_uses, formal_names, historical_names, is_draft
from .publication import (
    brand_rights,
    card_needs_self_contained_text,
    is_crop_style,
    is_whole_reference,
    region_slot,
)

@dataclass
class MarketTerm:
    market: str
    brand: str
    sample: str
    official: tuple[str, ...] = ()
    live: tuple[str, ...] = ()
    legacy: tuple[str, ...] = ()
    draft: tuple[str, ...] = ()
    other_brand: tuple[str, ...] = ()
    publishable: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "market": self.market,
            "brand": self.brand,
            "sample": self.sample,
            "official": list(self.official),
            "live_labels": list(self.live),
            "legacy_labels": list(self.legacy),
            "draft_labels": list(self.draft),
            "other_brand_terms": list(self.other_brand),
            "publishable": list(self.publishable),
            "blocked": list(self.blocked),
            "notes": list(self.notes),
        }


def market_terms(pack: Pack) -> list[MarketTerm]:
    """按市场×品牌×样给出可发布用语，标明旧称、草稿和他牌词。"""
    rows: list[MarketTerm] = []
    brands_markets = sorted({(entry.brand, entry.market) for entry in pack.glossary})
    brands_markets += sorted(
        {
            (outlet.brand, outlet.market)
            for outlet in pack.outlets
            if (outlet.brand, outlet.market) not in set(brands_markets)
        }
    )
    for brand, market in brands_markets:
        samples = sorted(
            {entry.sample for entry in pack.glossary if entry.brand == brand and entry.market == market}
            | {
                view.sample
                for view in pack.catalog
                if pack.outlet(view.outlet).brand == brand
                and pack.outlet(view.outlet).market == market
            }
        )
        for sample in samples:
            row = MarketTerm(market=market, brand=brand, sample=sample)
            official = [
                entry.name
                for entry in formal_names(pack)
                if entry.brand == brand and entry.market == market and entry.sample == sample
            ]
            legacy = [
                entry.name
                for entry in historical_names(pack)
                if entry.brand == brand and entry.market == market and entry.sample == sample
            ]
            live = [
                view.label
                for view in pack.catalog
                if pack.outlet(view.outlet).brand == brand
                and pack.outlet(view.outlet).market == market
                and view.sample == sample
                and not is_draft(view)
            ]
            draft = [
                view.label
                for view in pack.catalog
                if pack.outlet(view.outlet).brand == brand
                and pack.outlet(view.outlet).market == market
                and view.sample == sample
                and is_draft(view)
            ]
            other_brand = [
                use.term
                for use in all_name_uses(pack)
                if use.market == market
                and use.sample == sample
                and use.brand != brand
                and use.status != "draft"
            ]
            row.official = tuple(dict.fromkeys(official))
            row.live = tuple(dict.fromkeys(live))
            row.legacy = tuple(dict.fromkeys(legacy))
            row.draft = tuple(dict.fromkeys(draft))
            row.other_brand = tuple(dict.fromkeys(other_brand))
            row.publishable = row.official or row.live
            if not row.official and row.live:
                row.notes += ("渠道已有上线名，但品牌词表没有正式名，发布前须设计师确认",)
            if row.legacy:
                row.blocked += tuple(
                    f"{name}（旧换季名，不作新发布用语）" for name in row.legacy
                )
            if row.draft:
                row.blocked += tuple(
                    f"{name}（草稿，未上线）"
                    for name in row.draft
                    if name not in row.official and name not in row.live
                )
            if row.other_brand:
                row.blocked += tuple(
                    f"{name}（属于他牌，不能跨品牌使用）" for name in row.other_brand
                )
            if len(set(row.publishable)) > 1:
                row.notes += (
                    "同一块样在同一市场有多个正式/上线名：" + "、".join(row.publishable),
                )
            if len(set(row.live)) > 1:
                row.notes += (
                    "渠道已同时上线多个叫法：" + "、".join(dict.fromkeys(row.live)),
                )
            rows.append(row)
    return rows


def localized_terms(pack: Pack) -> dict:
    rows = market_terms(pack)
    return {
        "by_market": {
            market: [row.as_dict() for row in rows if row.market == market]
            for market in sorted({row.market for row in rows})
        },
        "consistency": term_consistency(pack),
        "rule": "新发布只用品牌正式名；旧换季名只服务既有订单，不写成新词指向的另一块样",
    }


def term_consistency(pack: Pack) -> list[dict]:
    """同一品牌同一市场同一块样的用语是否一致。"""
    findings = []
    for row in market_terms(pack):
        if len(set(row.live)) > 1:
            findings.append(
                {
                    "kind": "one_sample_many_live_labels",
                    "market": row.market,
                    "brand": row.brand,
                    "sample": row.sample,
                    "labels": sorted(set(row.live)),
                    "official": list(row.official),
                    "action": "先定一个在售名，其余按旧称处理并只服务既有订单",
                }
            )
        if row.official and any(label not in row.official for label in row.live):
            stray = sorted(set(row.live) - set(row.official))
            findings.append(
                {
                    "kind": "live_label_without_official",
                    "market": row.market,
                    "brand": row.brand,
                    "sample": row.sample,
                    "labels": stray,
                    "official": list(row.official),
                    "action": "已上线的非正式名须设计师确认后补登记或撤下",
                }
            )
    return findings


@dataclass
class ArtLink:
    view: str
    outlet: str
    sample: str
    label: str
    layout_letter: str
    position: str
    assets: tuple[str, ...]
    retain: tuple[str, ...]
    overlay_allowed: bool
    overlay_note: str
    self_contained_text: str
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "view": self.view,
            "outlet": self.outlet,
            "sample": self.sample,
            "label": self.label,
            "layout": self.layout_letter,
            "position": self.position,
            "assets": list(self.assets),
            "retain": list(self.retain),
            "overlay_allowed": self.overlay_allowed,
            "overlay_note": self.overlay_note,
            "self_contained_text": self.self_contained_text,
            "notes": list(self.notes),
        }


def _position_slot(positions: tuple[str, ...]) -> str:
    for position in positions:
        return position
    return ""


def art_links(pack: Pack) -> list[ArtLink]:
    """每张图卡对应到原片区域、必须保留的辨样依据和可叠字范围。"""
    links: list[ArtLink] = []
    for view in pack.catalog:
        outlet = pack.outlet(view.outlet)
        letter = view.layout_letter
        position = _position_slot(view.positions)
        assets = [
            asset
            for asset in pack.assets
            if asset.layout == letter
            and (not position or position in asset.region or region_slot(asset.region) == position)
        ]
        retain = tuple(asset.retain for asset in assets)
        rights = brand_rights(pack, outlet.brand, outlet.market)
        right = rights.get(letter)
        permission = right.summary() if right else ""
        overlay = bool(right and right.may_overlay and not right.forbidden)
        if right is None:
            note = "品牌词表未登记该图的文字覆盖范围"
        elif right.center_forbidden:
            note = f"{permission}；中心不可叠字"
        else:
            note = permission
        needed = card_needs_self_contained_text(pack, view.id)
        extra = []
        if is_whole_reference(view) and is_crop_style(outlet):
            extra.append("图卡依赖整图辨样，裁成单卡时必须带自足说明")
        if is_draft(view):
            extra.append("草稿图卡不对用户开放，核对后才可发布")
        links.append(
            ArtLink(
                view=view.id,
                outlet=outlet.id,
                sample=view.sample,
                label=view.label,
                layout_letter=letter,
                position=position,
                assets=tuple(asset.id for asset in assets),
                retain=retain,
                overlay_allowed=overlay,
                overlay_note=note,
                self_contained_text=needed["suggested_text"] if needed["needs_text"] else "",
                notes=tuple(extra),
            )
        )
    return links


@dataclass
class Variant:
    key: str
    kind: str
    outlet: str
    covers: tuple[str, ...]
    views: tuple[str, ...]
    card_texts: dict[str, str] = field(default_factory=dict)
    tradeoffs: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "key": self.key,
            "kind": self.kind,
            "outlet": self.outlet,
            "covers": list(self.covers),
            "views": list(self.views),
            "card_texts": dict(self.card_texts),
            "tradeoffs": list(self.tradeoffs),
            "blocked": list(self.blocked),
        }


def compliant_variants(pack: Pack, outlet_id: str) -> list[Variant]:
    """同一渠道的多套合规输出：独立图卡与多变体图册。"""
    outlet = pack.outlet(outlet_id)
    views = [view for view in pack.catalog if view.outlet == outlet_id and not is_draft(view)]
    variants: list[Variant] = []
    crops = is_crop_style(outlet)

    cards = []
    texts = {}
    tradeoffs = []
    blocked = []
    for view in views:
        link = next(item for item in art_links(pack) if item.view == view.id)
        cards.append(view.id)
        if crops and (is_whole_reference(view) or not view.positions):
            texts[view.id] = link.self_contained_text or (
                f"样 {view.sample}" + (f"，{link.position}" if link.position else "")
            )
            tradeoffs.append(f"{view.id} 裁成单卡后需自足说明：{texts[view.id]}")
        if any("系列色名" in retain for retain in link.retain):
            tradeoffs.append(
                f"{view.id} 的说明含系列色名限制，删词时须保留对照说明"
            )
    if not views:
        variants.append(
            Variant(
                key=f"{outlet_id}-none",
                kind="no_publishable_version",
                outlet=outlet_id,
                covers=tuple(
                    view.id for view in pack.catalog if view.outlet == outlet_id and is_draft(view)
                ),
                views=(),
                blocked=(
                    "该渠道目前只有草稿或没有可发布图卡，编辑确认后才生成发布版本",
                ),
            )
        )
    if views:
        variants.append(
            Variant(
                key=f"{outlet_id}-cards",
                kind="individual_cards",
                outlet=outlet_id,
                covers=tuple(view.id for view in views),
                views=tuple(cards),
                card_texts=texts,
                tradeoffs=tuple(tradeoffs),
                blocked=tuple(blocked),
            )
        )

    album_views = [
        view
        for view in views
        if view.layout_letter and any(
            asset.layout == view.layout_letter for asset in pack.assets
        )
    ]
    if album_views:
        album_tradeoffs = [
            "整页保留全部样和位置，不必裁掉齿印或样牌",
            "图册不能按单卡改词，旧词错误会整页带出",
        ]
        if crops:
            album_tradeoffs.append("渠道只展示独立卡时，图册不能被直接采用")
        variants.append(
            Variant(
                key=f"{outlet_id}-album",
                kind="multi_variant_album",
                outlet=outlet_id,
                covers=tuple(view.id for view in album_views),
                views=tuple(view.id for view in album_views),
                tradeoffs=tuple(album_tradeoffs),
            )
        )
    return variants


def crop_channel_conflicts(pack: Pack, outlet_id: str) -> list[dict]:
    """同一裁卡渠道里各自正确的两种叫法，比较要保留的图记和文字。"""
    outlet = pack.outlet(outlet_id)
    if not is_crop_style(outlet):
        return []
    views = [view for view in pack.catalog if view.outlet == outlet_id]
    links = {link.view: link for link in art_links(pack)}
    by_sample: dict[str, list[CatalogView]] = {}
    for view in views:
        by_sample.setdefault(view.sample, []).append(view)
    by_label: dict[str, list[CatalogView]] = {}
    for view in views:
        by_label.setdefault(view.label, []).append(view)
    # 在途改单涉及的色名，用来判断单卡文字是否还能接住顾客的改单请求。
    in_flight = _in_flight(pack, outlet_id)
    findings = []
    for sample, sample_views in sorted(by_sample.items()):
        labels = sorted({view.label for view in sample_views})
        if len(labels) < 2:
            continue
        findings.append(
            {
                "kind": "same_sample_two_labels",
                "outlet": outlet_id,
                "sample": sample,
                "labels": labels,
                "views": [view.id for view in sample_views],
                "instruction": (
                    f"{sample} 在同一渠道有 {'、'.join(labels)} 多个叫法；"
                    "裁卡前先统一图卡标题和订单用语，避免同一块样多种叫法。"
                ),
                "keep": [
                    {
                        "view": view.id,
                        "marks": [
                            retain
                            for retain in links[view.id].retain
                            if any(word in retain for word in ("齿印", "样牌", "材质纹", "字号"))
                        ],
                        "overlay_allowed": links[view.id].overlay_allowed,
                    }
                    for view in sample_views
                ],
            }
        )
    for label, label_views in sorted(by_label.items()):
        samples = sorted({view.sample for view in label_views})
        if len(samples) < 2:
            continue
        option_marks = []
        for view in label_views:
            link = links[view.id]
            marks = [
                retain
                for retain in link.retain
                if any(word in retain for word in ("齿印", "样牌", "材质纹", "字号"))
            ]
            option_marks.append(
                {
                    "view": view.id,
                    "sample": view.sample,
                    "position": link.position,
                    "marks": marks,
                    "text": link.self_contained_text
                    or (f"样 {view.sample}" + (f"，{link.position}" if link.position else "")),
                    "overlay_allowed": link.overlay_allowed,
                }
            )
        relevant_orders = [item for item in in_flight if item["seen_label"] == label]
        findings.append(
            {
                "kind": "same_label_two_samples",
                "outlet": outlet_id,
                "label": label,
                "samples": samples,
                "views": [view.id for view in label_views],
                "instruction": (
                    f"“{label}”在同一渠道指到 {'、'.join(samples)}；"
                    "发布员需比较保留哪些图记和文字，让单卡能分出实物并覆盖在途改单。"
                ),
                "compare": option_marks,
                "in_flight_orders": relevant_orders,
                "check": (
                    "逐张单卡核对：是否写出样号/位置，是否保留齿印、样牌等图记，"
                    "是否仍有可叠字空间说明差异；在途订单按已下单时看到的名字对样。"
                ),
            }
        )
    return findings


def _orders(pack: Pack):
    from .orders import order_snapshots

    return order_snapshots(pack)


def _in_flight(pack: Pack, outlet_id: str) -> list[dict]:
    """该渠道下单时的色名，以及还在改单流程里的目标色名。"""
    from .comments import read_comments
    from .orders import known_terms, resolve_all

    if outlet_id not in {outlet.id for outlet in pack.outlets}:
        return []
    items: list[dict] = []
    for order, snapshots in _orders(pack).items():
        for snapshot in snapshots:
            if snapshot.outlet != outlet_id:
                continue
            items.append(
                {
                    "order": order,
                    "seen_label": snapshot.label,
                    "sample": snapshot.sample,
                    "stage": "下单时看到",
                    "note": snapshot.note,
                }
            )
    vocabulary = known_terms(pack)
    for resolution in resolve_all(pack, read_comments()):
        for step in resolution.steps:
            if step.action not in {"intent", "ambiguous", "confirmed"}:
                continue
            for candidate in step.candidates:
                items.append(
                    {
                        "order": resolution.order,
                        "seen_label": candidate.label,
                        "sample": candidate.sample,
                        "stage": {"intent": "在途改单", "ambiguous": "待顾客选样", "confirmed": "已确认改单"}[
                            step.action
                        ],
                        "request": step.request,
                    }
                )
    return items


def non_publishable(pack: Pack, outlet_id: str) -> list[dict]:
    """原材料或许可不支持的部分，明确列出而不是默默省略。"""
    outlet = pack.outlet(outlet_id)
    rights = brand_rights(pack, outlet.brand, outlet.market)
    blocked: list[dict] = []
    for asset in pack.assets:
        right = rights.get(asset.layout)
        if right is None:
            blocked.append(
                {
                    "item": f"原片 {asset.id}（{asset.layout}）",
                    "reason": f"{outlet.brand}/{outlet.market} 的品牌词表未登记 {asset.layout} 图的发布许可",
                }
            )
        elif right.forbidden:
            blocked.append(
                {
                    "item": f"原片 {asset.id}（{asset.layout}）",
                    "reason": f"{outlet.brand}/{outlet.market} 的品牌词表明确写有 {asset.layout} 图不可发布",
                }
            )
    for view in pack.catalog:
        if view.outlet != outlet_id:
            continue
        if is_draft(view):
            blocked.append(
                {
                    "item": f"图卡 {view.id}",
                    "reason": "草稿，不对用户开放；需编辑确认后另立发布版本",
                }
            )
        right = rights.get(view.layout_letter)
        if right is not None and right.forbidden:
            blocked.append(
                {
                    "item": f"图卡 {view.id}",
                    "reason": f"所用 {view.layout_letter} 图在该市场不可发布，即使图卡已上线也要下架核对",
                }
            )
    for row in market_terms(pack):
        if row.market != outlet.market or row.brand != outlet.brand:
            continue
        if not row.official and not row.live:
            blocked.append(
                {
                    "item": f"{row.sample} 的商品用语",
                    "reason": "该市场没有正式名或上线名",
                }
            )
    # 同一词落到两块样、又只有一块有独立原始图记时，另一块不能沿用该词发布。
    labels: dict[str, dict[str, list[str]]] = {}
    for view in pack.catalog:
        owner = pack.outlet(view.outlet)
        if owner.market != outlet.market:
            continue
        labels.setdefault(view.label, {}).setdefault(view.sample, []).append(view.id)
    for label, samples in labels.items():
        if len(samples) < 2:
            continue
        distinct_marks = {}
        for sample in samples:
            letters = {
                view.layout_letter for view in pack.catalog if view.sample == sample and view.layout_letter
            }
            distinct_marks[sample] = any(
                any(word in asset.retain for word in ("齿印", "样牌", "材质纹", "字号"))
                for letter in letters
                for asset in pack.assets_for(letter)
            )
        if not all(distinct_marks.values()):
            missing = sorted(sample for sample, marked in distinct_marks.items() if not marked)
            blocked.append(
                {
                    "item": f"“{label}”的多卡发布",
                    "reason": (
                        f"同名不同样，且 {'、'.join(missing)} 缺少独立图记，"
                        "原材料不足以让顾客区分，保留为不可发布范围"
                    ),
                }
            )
    return blocked


def release_report(pack: Pack) -> dict:
    return {
        "localized_terms": localized_terms(pack),
        "art_links": [link.as_dict() for link in art_links(pack)],
        "outlets": {
            outlet.id: {
                "variants": [variant.as_dict() for variant in compliant_variants(pack, outlet.id)],
                "crop_conflicts": crop_channel_conflicts(pack, outlet.id),
                "non_publishable": non_publishable(pack, outlet.id),
            }
            for outlet in pack.outlets
        },
    }
