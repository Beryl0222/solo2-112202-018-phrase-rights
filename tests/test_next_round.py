"""处理下一批资料的测试：换一个资料包目录仍可运行，编号和来源不被写死。"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from colorway.compile import build_workspace, write_workspace

MATERIALS = Path(__file__).resolve().parent.parent / "materials"


def read_rows(path: Path) -> list[list[str]]:
    return [line.split("\t") for line in path.read_text(encoding="utf-8").splitlines()]


def write_rows(path: Path, rows: list[list[str]]) -> None:
    path.write_text("\n".join("\t".join(row) for row in rows) + "\n", encoding="utf-8")


class NextRoundTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name) / "materials"
        shutil.copytree(MATERIALS, self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def test_new_market_and_comment_flow_without_code_changes(self):
        glossary = read_rows(self.directory / "glossary.tsv")
        glossary.append(
            ["G6", "石渡", "南区", "S1", "Aqua Roca", "N 左下可叠字，中心不可"]
        )
        write_rows(self.directory / "glossary.tsv", glossary)

        outlets = read_rows(self.directory / "outlets.tsv")
        outlets.append(["O4", "石渡", "南区", "自动裁图成独立卡", "待上架", ""])
        write_rows(self.directory / "outlets.tsv", outlets)

        catalog = read_rows(self.directory / "catalog_views.tsv")
        catalog.append(
            ["CV7", "O4", "2026-11-01T09:00", "Aqua Roca", "S1", "N 左下卡"]
        )
        write_rows(self.directory / "catalog_views.tsv", catalog)

        comments = read_rows(self.directory / "comments.tsv")
        comments.append(
            ["R5", "石渡", "照片 N 左前为 S1，右前为 S2", "暖", "", "南区先按 Aqua Roca 报样"]
        )
        write_rows(self.directory / "comments.tsv", comments)

        workspace = build_workspace(self.directory)
        self.assertIn("南区", workspace["markets"])
        south = workspace["release"]["localized_terms"]["by_market"]["南区"]
        self.assertTrue(any(row["sample"] == "S1" and "Aqua Roca" in row["publishable"] for row in south))
        self.assertIn("O4", workspace["outlets"])

    def test_new_request_reuses_existing_order_snapshot(self):
        requests = read_rows(self.directory / "requests.tsv")
        requests.append(["Q6", "P010", "2026-10-14T12:00", "还是原来的 Azul Piedra。"])
        write_rows(self.directory / "requests.tsv", requests)

        workspace = build_workspace(self.directory)
        p010 = next(order for order in workspace["orders"] if order["order"] == "P010")
        self.assertEqual(p010["status"], "unchanged")
        self.assertEqual(p010["final_sample"], "S2")
        self.assertEqual(p010["steps"][-1]["request"], "Q6")

    def test_workspace_is_serializable_for_downstream_teams(self):
        destination = Path(self.temporary.name) / "out" / "workspace.json"
        write_workspace(self.directory, destination)
        payload = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(payload["sources"]["requests.tsv"], 5)
        self.assertTrue(payload["comments"]["ambiguities"])
        self.assertTrue(payload["editorial"]["draft_views"])


if __name__ == "__main__":
    unittest.main()
