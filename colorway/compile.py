"""汇总工作底稿：每条结论带来源记录。"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path

from . import design, editorial, names, orders, publication, release
from .comments import read_comments
from .model import Pack

DEFAULT_DATA = Path(__file__).resolve().parent.parent / "materials"


def _serialize(value):
    if is_dataclass(value):
        return _serialize(asdict(value))
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return value


def build_workspace(directory: Path | str | None = None) -> dict:
    pack = Pack.load(directory or DEFAULT_DATA)
    readings = read_comments(directory=directory)
    order_results = orders.resolve_all(pack, readings)
    return {
        "markets": list(pack.markets()),
        "sources": describe_sources(pack, directory),
        "comments": _serialize(design.comment_report(pack, readings)),
        "names": _serialize(
            {
                "all_uses": names.all_name_uses(pack),
                "formal": names.formal_names(pack),
                "historical": names.historical_names(pack),
                "conflicts": names.name_conflicts(pack),
                "scope": names.term_scope(pack),
                "timelines": {
                    f"{market}/{term}": names.term_timeline(pack, term, market)
                    for market in pack.markets()
                    for term in sorted(
                        {use.term for use in names.all_name_uses(pack) if use.market == market}
                    )
                },
            }
        ),
        "release": release.release_report(pack),
        "editorial": editorial.editorial_report(pack),
        "outlets": {
            outlet.id: _serialize(
                {
                    "terms": names.terms_for_outlet(pack, outlet.id),
                    "requirements": publication.channel_needs(pack, outlet.id),
                }
            )
            for outlet in pack.outlets
        },
        "orders": [_serialize(result) for result in order_results],
        "order_lookup": {
            order: orders.committed_lookup(pack, order) for order in orders.order_snapshots(pack)
        },
    }


def describe_sources(pack: Pack, directory: Path | str | None = None) -> dict:
    return {
        "comments.tsv": len(read_comments(directory=directory)),
        "glossary.tsv": len(pack.glossary),
        "outlets.tsv": len(pack.outlets),
        "assets.tsv": len(pack.assets),
        "catalog_views.tsv": len(pack.catalog),
        "order_views.tsv": len(pack.order_views),
        "requests.tsv": len(pack.requests),
    }


def _json_ready(value):
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def write_workspace(directory: Path | str | None, destination: Path | str) -> Path:
    workspace = build_workspace(directory)
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(_json_ready(workspace), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
