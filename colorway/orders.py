"""导购侧的改单判断：旧称、位置、生效时间与顾客确认。

三种来源分开记：设计师评语不直接改订单；渠道用词有上线时间；只有顾客在
某封来信里确认换成哪一块样，才动订单里的实物选择。后续“还是原来的”回到
该顾客最近一次确认的订单快照。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .comments import CommentReading, side_of_word
from .model import Pack, Request
from .names import resolve_term


@dataclass(frozen=True)
class OrderSnapshot:
    order: str
    view: str
    sample: str
    label: str
    at: datetime | None
    outlet: str
    market: str
    brand: str
    note: str = ""


@dataclass(frozen=True)
class SampleRef:
    sample: str
    origin: str
    position: str = ""


@dataclass
class ParsedRequest:
    id: str
    order: str
    received: datetime | None
    body: str
    terms: tuple[str, ...] = ()
    from_terms: tuple[str, ...] = ()
    target_terms: tuple[str, ...] = ()
    positions: tuple[str, ...] = ()
    target_sides: tuple[str, ...] = ()
    exclude_sides: tuple[str, ...] = ()
    cancel_samples: tuple[str, ...] = ()
    cancel_sides: tuple[str, ...] = ()
    marks: tuple[str, ...] = ()
    confirm: bool = False
    keep_original: bool = False
    reference: bool = False


@dataclass(frozen=True)
class Candidate:
    sample: str
    label: str
    status: str
    sources: tuple[str, ...]
    position: str = ""
    marks: tuple[str, ...] = ()
    effective: str = ""
    matches_marks: bool = True

    def describe(self) -> str:
        bits = [f"{self.sample}（{self.label}"]
        if self.position:
            bits.append(self.position)
        if self.marks:
            bits.append("、".join(self.marks))
        if self.effective:
            bits.append(self.effective)
        if self.status == "historical":
            bits.append("旧称")
        where = f"；依据 {'、'.join(self.sources)}" if self.sources else ""
        return "，".join(bits) + f"）{where}"


@dataclass
class Step:
    request: str
    received: datetime | None
    action: str
    detail: str
    candidates: tuple[Candidate, ...] = ()
    chosen: str = ""


@dataclass
class OrderResolution:
    order: str
    original: OrderSnapshot
    steps: list[Step] = field(default_factory=list)
    final_sample: str = ""
    final_label: str = ""
    status: str = "unchanged"
    confirmed_at: datetime | None = None
    pending_options: tuple[Candidate, ...] = ()

    @property
    def changed(self) -> bool:
        return self.final_sample != self.original.sample


POSITION_WORDS = (
    "左前", "右前", "左边", "右边", "左侧", "右侧", "图左", "图右",
    "前排靠左", "前排靠右", "后排靠左", "后排靠右",
)
MARK_WORDS = ("齿印", "记号", "材质纹", "样牌", "字号")
# 顾客说的“记号”通常就是订单备注里的齿印；只用于筛选和提示。
MARK_SYNONYMS = {"记号": ("记号", "齿印")}
EXCLUDE_MARKERS = ("并非", "不是", "不要", "不用改", "不选")
CANCEL_MARKERS = ("作废", "取消", "不算")
CONFIRM_MARKERS = ("确认", "就按")
KEEP_MARKERS = ("不换", "不改", "不变", "保留")
REFERENCE_MARKERS = ("原来的", "刚才确认", "之前确认", "下单时看到", "原单")
DIRECTION_MARKERS = ("换成", "换为", "改称", "改为", "换到")
SWAP_MARKERS = ("换",)


def order_snapshots(pack: Pack) -> dict[str, list[OrderSnapshot]]:
    grouped: dict[str, list[OrderSnapshot]] = {}
    for view in pack.order_views:
        catalog = pack.view(view.view)
        outlet = pack.outlet(catalog.outlet)
        grouped.setdefault(view.order, []).append(
            OrderSnapshot(
                order=view.order,
                view=view.view,
                sample=catalog.sample,
                label=catalog.label,
                at=view.at,
                outlet=outlet.id,
                market=outlet.market,
                brand=outlet.brand,
                note=view.customer_note,
            )
        )
    for snapshots in grouped.values():
        snapshots.sort(key=lambda snapshot: (snapshot.at is None, snapshot.at))
    return grouped


def layout_letter_for(pack: Pack, outlet_id: str, snapshots: list[OrderSnapshot]) -> str:
    for snapshot in snapshots:
        view = pack.view(snapshot.view)
        if view.layout_letter:
            return view.layout_letter
    for view in pack.catalog:
        if view.outlet == outlet_id and view.layout_letter:
            return view.layout_letter
    return ""


def canonical_side(word: str) -> str:
    """把所有位置词收成 left/right；否则无法和排位对上。"""
    return side_of_word(word)


def position_map(readings: list[CommentReading], brand: str, letter: str) -> dict[str, str]:
    """从拍摄组的排位记录得到 side → 样号。"""
    mapping: dict[str, str] = {}
    for reading in readings:
        if reading.brand != brand or f" {letter} " not in f" {reading.layout} ":
            continue
        for word, sample in reading.layout_samples:
            side = canonical_side(word)
            if side:
                mapping.setdefault(side, sample)
    return mapping


def position_label(side: str) -> str:
    return {"left": "左前", "right": "右前"}.get(side, "")


def sample_marks(pack: Pack, letter: str) -> dict[str, tuple[str, ...]]:
    """同一张拍摄图里，各样品可被顾客辨认的实物特征。"""
    marks: dict[str, list[str]] = {}
    for asset in pack.assets:
        if asset.layout != letter:
            continue
        sample = ""
        for part in asset.retain.replace("，", " ").split():
            if part.startswith("S") and part[1:].isdigit():
                sample = part
                break
        if not sample:
            continue
        for token in ("齿印", "样牌", "材质纹", "字号"):
            if token in asset.retain:
                marks.setdefault(sample, []).append(token)
    return {sample: tuple(dict.fromkeys(values)) for sample, values in marks.items()}


def known_terms(pack: Pack) -> tuple[str, ...]:
    terms = {view.label for view in pack.catalog} | {entry.name for entry in pack.glossary}
    return tuple(sorted((term for term in terms if term), key=len, reverse=True))


def positions_in(text: str) -> tuple[str, ...]:
    return tuple(word for word in POSITION_WORDS if word in text)


def sides_in(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(canonical_side(word) for word in positions_in(text) if canonical_side(word)))


def marks_in(text: str) -> tuple[str, ...]:
    return tuple(word for word in MARK_WORDS if word in text)


def clauses(body: str) -> list[str]:
    parts = body.replace("；", "。").replace("，", "。").replace("。", "\n").split("\n")
    return [part for part in parts if part]


def _sample_tokens(text: str) -> list[str]:
    found = []
    for token in text.replace("，", " ").replace("。", " ").split():
        token = token.strip("，。")
        if token.startswith("S") and token[1:].isdigit():
            found.append(token)
    return found


def parse_request(request: Request, vocabulary: tuple[str, ...]) -> ParsedRequest:
    """按子句解析：换向、位置、实物特征、排除和作废分别记。"""
    body = request.body
    parts = clauses(body)
    from_terms: list[str] = []
    target_terms: list[str] = []
    target_sides: list[str] = []
    exclude_sides: list[str] = []
    cancel_samples: list[str] = []
    cancel_sides: list[str] = []
    for clause in parts:
        clause_sides = sides_in(clause)
        direction = next((marker for marker in DIRECTION_MARKERS if marker in clause), "")
        if direction:
            before, _, after = clause.partition(direction)
            from_terms.extend(term for term in vocabulary if term in before)
            target_terms.extend(term for term in vocabulary if term in after)
            target_sides.extend(sides_in(after))
            continue
        if any(marker in clause for marker in CANCEL_MARKERS):
            explicit = _sample_tokens(clause)
            if explicit:
                cancel_samples.extend(explicit)
            else:
                cancel_sides.extend(clause_sides)
            continue
        if any(marker in clause for marker in EXCLUDE_MARKERS):
            if clause_sides:
                exclude_sides.extend(clause_sides)
            continue
        if "同名" in clause:
            # “同名的右前样”说的是位置，不是把该词当作目标。
            continue
        confirmish = any(marker in clause for marker in CONFIRM_MARKERS) or (
            "换" in clause and bool(clause_sides)
        )
        if confirmish:
            clause_terms = [term for term in vocabulary if term in clause]
            if clause_terms:
                target_terms.extend(clause_terms)
            target_sides.extend(clause_sides)
    keep = any(marker in body for marker in KEEP_MARKERS)
    confirm = any(marker in body for marker in CONFIRM_MARKERS) and not any(
        word in body for word in ("不确认", "没确认", "尚未确认")
    )
    return ParsedRequest(
        id=request.id,
        order=request.order,
        received=request.received,
        body=body,
        terms=tuple(dict.fromkeys(term for term in vocabulary if term in body)),
        from_terms=tuple(dict.fromkeys(from_terms)),
        target_terms=tuple(dict.fromkeys(target_terms)),
        positions=positions_in(body),
        target_sides=tuple(dict.fromkeys(target_sides)),
        exclude_sides=tuple(dict.fromkeys(exclude_sides)),
        cancel_samples=tuple(dict.fromkeys(cancel_samples)),
        cancel_sides=tuple(dict.fromkeys(cancel_sides)),
        marks=marks_in(body),
        confirm=confirm,
        keep_original=keep,
        reference=any(marker in body for marker in REFERENCE_MARKERS),
    )


def _label_for(pack: Pack, sample: str, market: str, brand: str) -> str:
    """给没有品牌词候选的样找当前叫法；找不到就空着。"""
    for view in pack.catalog:
        outlet = pack.outlet(view.outlet)
        if outlet.market == market and outlet.brand == brand and view.sample == sample:
            if "草稿" not in view.layout:
                return view.label
    return ""


def resolve_candidates(
    pack: Pack,
    request: ParsedRequest,
    snapshot: OrderSnapshot,
    side_lookup: dict[str, str],
    marks: dict[str, tuple[str, ...]],
) -> tuple[Candidate, ...]:
    """按市场、品牌、时点、位置和实物特征给出候选，不凭单一线索定案。"""
    found: dict[str, Candidate] = {}
    for term in request.target_terms:
        for candidate in resolve_term(
            pack,
            term,
            market=snapshot.market,
            as_of=request.received,
            brand=snapshot.brand,
        ):
            existing = found.get(candidate.sample)
            sources = set(existing.sources) if existing else set()
            sources.update(candidate.sources)
            found[candidate.sample] = Candidate(
                sample=candidate.sample,
                label=term,
                status=candidate.status,
                sources=tuple(sorted(sources)),
                position=position_label(_side_for(side_lookup, candidate.sample)),
                marks=marks.get(candidate.sample, ()),
                effective=_earliest_published(pack, term, candidate.sample, request.received),
            )
    for side in request.target_sides:
        sample = side_lookup.get(side)
        if not sample:
            continue
        existing = found.get(sample)
        label = existing.label if existing else (
            _label_for(pack, sample, snapshot.market, snapshot.brand) or snapshot.label
        )
        sources = set(existing.sources) if existing else set()
        sources.add(f"排位 {position_label(side)}")
        found[sample] = Candidate(
            sample=sample,
            label=label,
            status=existing.status if existing else "position",
            sources=tuple(sorted(sources)),
            position=position_label(side),
            marks=marks.get(sample, ()),
            effective=existing.effective if existing else "",
        )
    candidates = list(found.values())
    wanted = {
        alternative
        for mark in request.marks
        for alternative in MARK_SYNONYMS.get(mark, (mark,))
    }
    marked = [
        Candidate(
            sample=candidate.sample,
            label=candidate.label,
            status=candidate.status,
            sources=candidate.sources,
            position=candidate.position,
            marks=candidate.marks,
            effective=candidate.effective,
            matches_marks=bool(wanted) and any(mark in wanted for mark in candidate.marks),
        )
        for candidate in candidates
    ]
    excluded_samples = set(request.cancel_samples)
    for side in (*request.exclude_sides, *request.cancel_sides):
        if side in side_lookup:
            excluded_samples.add(side_lookup[side])
    marked = [candidate for candidate in marked if candidate.sample not in excluded_samples]
    return tuple(
        sorted(
            marked,
            key=lambda candidate: (not candidate.matches_marks, candidate.sample),
        )
    )


def _side_for(mapping: dict[str, str], sample: str) -> str:
    for side, value in mapping.items():
        if value == sample:
            return side
    return ""


def _earliest_published(pack: Pack, term: str, sample: str, as_of: datetime | None) -> str:
    times = [
        view.published
        for view in pack.catalog
        if view.label == term
        and view.sample == sample
        and view.published
        and "草稿" not in view.layout
        and (as_of is None or view.published <= as_of)
    ]
    if not times:
        return ""
    return min(times).strftime("%Y-%m-%d %H:%M")


def _reaffirm(snapshot: OrderSnapshot, request_id: str, received: datetime | None, note: str = "") -> Step:
    detail = f"沿用已确认的 {snapshot.label} / {snapshot.sample}，不改实物选择"
    if note:
        detail = f"{detail}（{note}）"
    return Step(
        request=request_id,
        received=received,
        action="reaffirm",
        detail=detail,
        chosen=snapshot.sample,
    )


def resolve_order(
    pack: Pack,
    order: str,
    readings: list[CommentReading],
    snapshots: list[OrderSnapshot],
    requests: list[Request],
) -> OrderResolution:
    original = snapshots[0]
    latest = snapshots[-1]
    letter = layout_letter_for(pack, latest.outlet, snapshots)
    side_lookup = position_map(readings, latest.brand, letter)
    marks = sample_marks(pack, letter)
    vocabulary = known_terms(pack)

    state_sample = latest.sample
    state_label = latest.label
    confirmed = latest
    status = "unchanged"
    pending: tuple[Candidate, ...] = ()
    resolution = OrderResolution(order=order, original=original)

    for request in sorted(requests, key=lambda item: (item.received is None, item.received)):
        parsed = parse_request(request, vocabulary)
        if parsed.from_terms:
            expected = {
                candidate.sample
                for term in parsed.from_terms
                for candidate in resolve_term(
                    pack, term, market=confirmed.market, as_of=parsed.received, brand=confirmed.brand
                )
            }
            if expected and confirmed.sample not in expected:
                resolution.steps.append(
                    Step(
                        request=request.id,
                        received=request.received,
                        action="mismatch",
                        detail=(
                            f"来信说的是把 {'、'.join(parsed.from_terms)} 换掉，但这单当时确认的是 "
                            f"{confirmed.label} / {confirmed.sample}；先核对再改。"
                        ),
                    )
                )
                continue
        if parsed.keep_original or (parsed.reference and not parsed.target_terms and not parsed.target_sides):
            resolution.steps.append(
                _reaffirm(confirmed, request.id, request.received, "顾客指向已确认的订单")
            )
            state_sample, state_label = confirmed.sample, confirmed.label
            continue
        if (
            parsed.received is not None
            and confirmed.at is not None
            and parsed.received < confirmed.at
        ):
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="too_early",
                    detail="来信早于该订单快照，不能据此改派",
                )
            )
            continue
        candidates = resolve_candidates(pack, parsed, confirmed, side_lookup, marks)
        if not candidates:
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="clarify",
                    detail="没有能在该市场、该时点指到实物的候选，请顾客补充位置或样号",
                )
            )
            continue
        chosen = candidates[0]
        if len(candidates) > 1:
            pending = candidates
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="ambiguous",
                    detail=(
                        "该词在当前市场同时指到多样，先给顾客能分出实物的选项："
                        + "；".join(candidate.describe() for candidate in candidates)
                    ),
                    candidates=candidates,
                )
            )
            continue
        wanted = {
            alternative
            for mark in parsed.marks
            for alternative in MARK_SYNONYMS.get(mark, (mark,))
        }
        if wanted and not chosen.matches_marks:
            pending = candidates
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="clarify",
                    detail=(
                        f"顾客说的实物特征（{'、'.join(parsed.marks)}）和 "
                        f"{chosen.sample} 对不上，先确认是哪一块样再改单"
                    ),
                    candidates=candidates,
                )
            )
            continue
        if parsed.confirm and chosen.sample == confirmed.sample:
            # 顾客再次指向已确认的样，就不再动订单，也不另立快照。
            pending = ()
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="reaffirm",
                    detail=(
                        f"与已确认的 {confirmed.label} / {confirmed.sample} 一致，"
                        "订单实物选择不变"
                    ),
                    candidates=candidates,
                    chosen=chosen.sample,
                )
            )
        elif parsed.confirm:
            previous = confirmed
            state_sample, state_label = chosen.sample, chosen.label
            status = "changed" if chosen.sample != original.sample else "unchanged"
            confirmed = OrderSnapshot(
                order=previous.order,
                view=previous.view,
                sample=chosen.sample,
                label=chosen.label,
                at=request.received or previous.at,
                outlet=previous.outlet,
                market=previous.market,
                brand=previous.brand,
                note=f"{request.id} 顾客确认",
            )
            pending = ()
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="confirmed",
                    detail=(
                        f"顾客确认从 {previous.label} / {previous.sample} 换成 "
                        f"{chosen.label} / {chosen.sample}"
                    ),
                    candidates=candidates,
                    chosen=chosen.sample,
                )
            )
        else:
            pending = candidates
            resolution.steps.append(
                Step(
                    request=request.id,
                    received=request.received,
                    action="intent",
                    detail=(
                        f"顾客表达换到 {chosen.label} / {chosen.sample}，尚未确认；"
                        "回复请其确认后再改订单"
                    ),
                    candidates=candidates,
                )
            )
    resolution.final_sample = state_sample
    resolution.final_label = state_label
    resolution.status = status if state_sample != latest.sample else "unchanged"
    if pending:
        resolution.status = "pending"
        resolution.pending_options = pending
    resolution.confirmed_at = confirmed.at
    return resolution


def resolve_all(pack: Pack, readings: list[CommentReading]) -> list[OrderResolution]:
    snapshots = order_snapshots(pack)
    resolution = []
    for order, views in snapshots.items():
        requests = [request for request in pack.requests if request.order == order]
        resolution.append(resolve_order(pack, order, readings, views, requests))
    return resolution


def committed_lookup(pack: Pack, order: str) -> dict | None:
    """顾客下单时看到的色名和它对应的实物，附可能改写指向的新词。"""
    snapshots = order_snapshots(pack).get(order)
    if not snapshots:
        return None
    first = snapshots[0]
    same_term_elsewhere = [
        {
            "term": use.term,
            "sample": use.sample,
            "status": use.status,
            "source": use.source,
        }
        for use in _term_uses(pack, first.label, first.market)
        if use.sample != first.sample and use.brand == first.brand
    ]
    # 同一块样被同品牌的别的词指到时，顾客换词不能改变已承诺实物。
    colliding_terms = []
    for use in _term_uses_for_sample(pack, first.sample, first.market):
        if use.term == first.label or use.brand != first.brand:
            continue
        other_samples = {
            other.sample
            for other in _term_uses(pack, use.term, first.market)
            if other.sample != first.sample and other.brand == first.brand
        }
        if other_samples:
            colliding_terms.append(
                {
                    "term": use.term,
                    "resolves_to": sorted(other_samples),
                    "source": use.source,
                }
            )
    instruction = "顾客说“下单时看到的颜色”时按 seen_sample 履约。"
    if same_term_elsewhere:
        instruction += " 该词另有指向别的样的用法，不能据此改派。"
    if colliding_terms:
        instruction += (
            " 该样另有一个词同时指到别的样，"
            "把已承诺颜色写成新词时不能换成另一块样。"
        )
    return {
        "order": order,
        "seen_label": first.label,
        "seen_sample": first.sample,
        "seen_view": first.view,
        "new_use_of_same_term": same_term_elsewhere,
        "colliding_terms": colliding_terms,
        "instruction": instruction,
    }


def _term_uses(pack: Pack, term: str, market: str):
    from .names import all_name_uses

    return [use for use in all_name_uses(pack) if use.term == term and use.market == market]


def _term_uses_for_sample(pack: Pack, sample: str, market: str):
    from .names import all_name_uses

    return [
        use for use in all_name_uses(pack) if use.sample == sample and use.market == market
    ]
