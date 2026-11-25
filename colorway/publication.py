"""发布许可：图片可写区域、必须保留的辨样依据、裁图后的自足说明。

规范来自两处：glossary.photo_right 按品牌和拍摄版式限定可编辑区，
assets.retain 记录编辑要求保留的辨样依据。任何为删除禁用词而裁掉或遮住
retain 项的做法都要被拦下，因为连带的光源/色差限定也会一起丢失。
"""
from __future__ import annotations

from dataclasses import dataclass

from .model import Asset, CatalogView, Outlet, Pack
from .rights import LayoutRights, parse_photo_right

CROP_WORDS = ("裁", "独立卡", "分图卡")
WHOLE_WORDS = ("整图", "整页", "整张", "全图")
RETAIN_MARKS = ("齿印", "样牌", "材质纹", "字号")


def region_layout(region: str) -> str:
    return region.split()[0] if region else ""


def region_slot(region: str) -> str:
    parts = region.split()
    return parts[1] if len(parts) > 1 else ""


def is_crop_style(outlet: Outlet) -> bool:
    return any(word in outlet.style for word in CROP_WORDS)


def is_whole_reference(view: CatalogView) -> bool:
    return any(word in view.layout for word in WHOLE_WORDS)


def brand_rights(pack: Pack, brand: str, market: str) -> dict[str, LayoutRights]:
    """该品牌在该市场登记的各版式许可；多个登记项取并集（各自记录保留）。"""
    merged: dict[str, LayoutRights] = {}
    for entry in pack.glossary:
        if entry.brand != brand or entry.market != market:
            continue
        for layout, right in parse_photo_right(entry.photo_right).items():
            existing = merged.get(layout)
            if existing is None:
                merged[layout] = LayoutRights(
                    layout=layout,
                    may_overlay=right.may_overlay,
                    overlay_positions=right.overlay_positions,
                    center_forbidden=right.center_forbidden,
                    may_crop=right.may_crop,
                    whole_only=right.whole_only,
                    forbidden=right.forbidden,
                    historical=right.historical,
                    raw=list(right.raw),
                )
                continue
            existing.may_overlay = existing.may_overlay or right.may_overlay
            existing.may_crop = existing.may_crop or right.may_crop
            existing.whole_only = existing.whole_only or right.whole_only
            existing.center_forbidden = existing.center_forbidden or right.center_forbidden
            existing.overlay_positions = tuple(
                dict.fromkeys((*existing.overlay_positions, *right.overlay_positions))
            )
            existing.raw.extend(right.raw)
            # 任一登记项允许发布，就不因另一条的“不可发布”而整版禁用；
            # 但禁用要单独记下来，供不可发布范围使用。
            if right.forbidden and not existing.forbidden:
                existing.raw.append("另一登记项写有不可发布")
            existing.forbidden = existing.forbidden and right.forbidden
    return merged


@dataclass(frozen=True)
class AssetObligation:
    asset_id: str
    layout: str
    region: str
    retain: str
    may_edit: bool
    may_publish: bool
    may_crop: bool
    reason: str


def asset_obligations(pack: Pack, outlet_id: str) -> list[AssetObligation]:
    """一个渠道能改哪里、不能丢什么、能不能裁成独立卡。"""
    outlet = pack.outlet(outlet_id)
    rights = brand_rights(pack, outlet.brand, outlet.market)
    obligations = []
    for asset in pack.assets:
        right = rights.get(asset.layout)
        if right is None:
            obligations.append(
                AssetObligation(
                    asset_id=asset.id,
                    layout=asset.layout,
                    region=asset.region,
                    retain=asset.retain,
                    may_edit=False,
                    may_publish=False,
                    may_crop=False,
                    reason=f"{outlet.brand}/{outlet.market} 的品牌词表未登记 {asset.layout} 图的发布许可",
                )
            )
            continue
        obligations.append(
            AssetObligation(
                asset_id=asset.id,
                layout=asset.layout,
                region=asset.region,
                retain=asset.retain,
                may_edit=right.may_edit,
                may_publish=right.may_publish,
                may_crop=right.may_crop and not right.forbidden,
                reason=right.summary(),
            )
        )
    return obligations


def retained_without_editing(pack: Pack, outlet_id: str) -> list[AssetObligation]:
    """渠道裁图时，位于不可裁版式里的 retain 项。"""
    outlet = pack.outlet(outlet_id)
    if not is_crop_style(outlet):
        return []
    return [
        obligation
        for obligation in asset_obligations(pack, outlet_id)
        if not obligation.may_crop
    ]


def card_needs_self_contained_text(pack: Pack, view_id: str) -> dict:
    """整图才能辨样、而渠道又裁图时，单卡必须有自足说明。"""
    view = pack.view(view_id)
    outlet = pack.outlet(view.outlet)
    whole = is_whole_reference(view)
    crops = is_crop_style(outlet)
    reasons = []
    if whole and crops:
        reasons.append(
            f"图卡 {view.id} 依赖{'/'.join(word for word in WHOLE_WORDS if word in view.layout)}辨样，"
            f"渠道 {outlet.id} 会裁成独立卡"
        )
    if "草稿" in view.layout:
        reasons.append(f"图卡 {view.id} 是草稿，不对用户开放")
    positions = view.positions
    crop_related = crops and (whole or not positions)
    if crops and not positions and not whole:
        reasons.append(f"图卡 {view.id} 未写明具体位置，裁后无法核对是哪块样")
    assets = [
        asset
        for asset in pack.assets_for(view.layout_letter)
        if any(position in asset.region for position in positions)
    ]
    required = []
    for asset in assets:
        if any(word in asset.retain for word in RETAIN_MARKS):
            required.append({"asset": asset.id, "retain": asset.retain})
    return {
        "view": view.id,
        "outlet": outlet.id,
        "sample": view.sample,
        "label": view.label,
        "needs_text": bool(reasons),
        "reasons": reasons,
        "required_retain": required,
        "suggested_text": suggested_card_text(view, assets) if crop_related else "",
    }


def suggested_card_text(view: CatalogView, assets: list[Asset]) -> str:
    parts = [f"样 {view.sample}"]
    if view.positions:
        parts.append("、".join(view.positions))
    marks = []
    for asset in assets:
        for mark in RETAIN_MARKS:
            if mark in asset.retain:
                marks.append(mark)
    if marks:
        parts.append("、".join(dict.fromkeys(marks)))
    return "，".join(parts)


def retention_warnings(
    pack: Pack, outlet_id: str, banned_terms: tuple[str, ...] = ()
) -> list[dict]:
    """想删禁用词时，逐项确认连带色差限定仍被保留。"""
    warnings = []
    for obligation in asset_obligations(pack, outlet_id):
        if not obligation.may_publish:
            continue
        if "系列色名" in obligation.retain:
            warnings.append(
                {
                    "asset": obligation.asset_id,
                    "outlet": outlet_id,
                    "retain": obligation.retain,
                    "banned_terms": list(banned_terms),
                    "issue": "删除系列色名会连带删掉同图对照关系，须保留该说明并改用样号/位置指认",
                    "must_keep": True,
                }
            )
        if any(word in obligation.retain for word in ("色差", "光源", "灯")):
            warnings.append(
                {
                    "asset": obligation.asset_id,
                    "outlet": outlet_id,
                    "retain": obligation.retain,
                    "banned_terms": list(banned_terms),
                    "issue": "色差限定与观感用词同句，删词时必须保留限定语",
                    "must_keep": True,
                }
            )
    return warnings


def channel_needs(pack: Pack, outlet_id: str) -> dict:
    """发布员需要的渠道约束摘要。"""
    outlet = pack.outlet(outlet_id)
    views = [view for view in pack.catalog if view.outlet == outlet_id]
    cards = [card_needs_self_contained_text(pack, view.id) for view in views]
    return {
        "outlet": outlet.id,
        "brand": outlet.brand,
        "market": outlet.market,
        "style": outlet.style,
        "phase": outlet.phase,
        "multi_variant": outlet.album,
        "crops": is_crop_style(outlet),
        "views": [
            {
                "id": view.id,
                "label": view.label,
                "sample": view.sample,
                "layout": view.layout,
                "draft": "草稿" in view.layout,
                "published": view.published.isoformat() if view.published else None,
            }
            for view in views
        ],
        "cards": cards,
        "assets": [
            {
                "asset": obligation.asset_id,
                "region": obligation.region,
                "retain": obligation.retain,
                "may_edit": obligation.may_edit,
                "may_publish": obligation.may_publish,
                "may_crop": obligation.may_crop,
                "reason": obligation.reason,
            }
            for obligation in asset_obligations(pack, outlet_id)
        ],
        "retention_warnings": retention_warnings(pack, outlet_id),
    }
