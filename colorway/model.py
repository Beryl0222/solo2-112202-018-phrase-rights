"""读取并持有资料行；所有结论都引用原始记录号。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

from pack_check import DEFAULT_DATA, read_tables


def parse_time(value: str) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Glossary:
    id: str
    brand: str
    market: str
    sample: str
    name: str
    photo_right: str

    @property
    def is_historical(self) -> bool:
        return "旧" in self.photo_right

    @property
    def layout_letter(self) -> str:
        head = self.photo_right.split()[0] if self.photo_right else ""
        return head if head in ("N", "M") else ""


@dataclass(frozen=True)
class Outlet:
    id: str
    brand: str
    market: str
    style: str
    phase: str
    orders: str

    @property
    def crops(self) -> bool:
        return "裁" in self.style or "分图卡" in self.style

    @property
    def album(self) -> bool:
        return "图册" in self.style or "整页" in self.style

    @property
    def published(self) -> bool:
        return self.phase == "已上架"


@dataclass(frozen=True)
class Asset:
    id: str
    layout: str
    region: str
    retain: str

    @property
    def position(self) -> str:
        return self.region.split()[-1]

    @property
    def slot(self) -> str:
        return self.region.split()[0]


@dataclass(frozen=True)
class CatalogView:
    id: str
    outlet: str
    published: datetime | None
    label: str
    sample: str
    layout: str

    @property
    def layout_letter(self) -> str:
        for token in re.split(r"[^0-9A-Za-z一-鿿]+", self.layout):
            if token in ("N", "M"):
                return token
        for token in self.layout.split():
            if token in ("N", "M"):
                return token
        return ""

    @property
    def is_whole(self) -> bool:
        return any(word in self.layout for word in ("整图", "整页", "整张", "全图"))

    @property
    def positions(self) -> tuple[str, ...]:
        return tuple(word for word in ("左下", "右下", "左侧", "右侧") if word in self.layout)


@dataclass(frozen=True)
class OrderView:
    id: str
    order: str
    view: str
    at: datetime | None
    customer_note: str


@dataclass(frozen=True)
class Request:
    id: str
    order: str
    received: datetime | None
    body: str


@dataclass
class Pack:
    glossary: list[Glossary]
    outlets: list[Outlet]
    assets: list[Asset]
    catalog: list[CatalogView]
    order_views: list[OrderView]
    requests: list[Request]

    @classmethod
    def load(cls, directory: Path | str = DEFAULT_DATA) -> "Pack":
        tables = read_tables(Path(directory))
        return cls(
            glossary=[Glossary(**row) for row in tables["glossary.tsv"]],
            outlets=[Outlet(**row) for row in tables["outlets.tsv"]],
            assets=[Asset(**row) for row in tables["assets.tsv"]],
            catalog=[
                CatalogView(
                    id=row["id"],
                    outlet=row["outlet"],
                    published=parse_time(row["published"]),
                    label=row["label"],
                    sample=row["sample"],
                    layout=row["layout"],
                )
                for row in tables["catalog_views.tsv"]
            ],
            order_views=[
                OrderView(
                    id=row["id"],
                    order=row["order"],
                    view=row["view"],
                    at=parse_time(row["at"]),
                    customer_note=row["customer_note"],
                )
                for row in tables["order_views.tsv"]
            ],
            requests=[
                Request(
                    id=row["id"],
                    order=row["order"],
                    received=parse_time(row["received"]),
                    body=row["body"],
                )
                for row in tables["requests.tsv"]
            ],
        )

    def outlet(self, outlet_id: str) -> Outlet:
        return next(outlet for outlet in self.outlets if outlet.id == outlet_id)

    def view(self, view_id: str) -> CatalogView:
        return next(view for view in self.catalog if view.id == view_id)

    def assets_for(self, layout: str) -> list[Asset]:
        return [asset for asset in self.assets if asset.layout == layout]

    def markets(self) -> tuple[str, ...]:
        names = {entry.market for entry in self.glossary} | {outlet.market for outlet in self.outlets}
        return tuple(sorted(names))
