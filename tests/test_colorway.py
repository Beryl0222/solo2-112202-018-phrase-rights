"""资料包的业务测试：评语、命名、发布、改单各一条主线。

资料使用虚构编号。测试只读 materials/，不依赖网络和第三方库。
"""
from __future__ import annotations

from pathlib import Path
import unittest

from colorway.comments import read_comments
from colorway.model import Pack
from colorway import design, editorial, names, orders, publication, release
from colorway.compile import build_workspace


class CommentReadingTest(unittest.TestCase):
    def setUp(self):
        self.pack = Pack.load()
        self.readings = {reading.comment_id: reading for reading in read_comments()}

    def test_viewing_condition_kept_apart_from_adopted_name(self):
        report = design.reading_summary(self.readings["R1"])
        self.assertEqual(report["viewing_conditions"]["light"], "暖")
        self.assertIn("左前青灰在灯下像石蓝", report["viewing_conditions"]["perception_phrases"])
        self.assertEqual(report["adopted_terms"], [])
        self.assertEqual(report["decision"], "deferred")
        physical = report["physical_reference"][0]
        self.assertEqual(physical["samples"], ["S1"])
        self.assertEqual(physical["side"], "left")

    def test_position_words_resolve_through_layout(self):
        report = design.reading_summary(self.readings["R2"])
        sides = {row["side"]: row["samples"] for row in report["physical_reference"]}
        self.assertEqual(sides["left"], ["S1"])
        self.assertEqual(sides["right"], ["S2"])

    def test_other_brand_series_name_stays_local(self):
        report = design.reading_summary(self.readings["R3"])
        adoption = report["adopted_terms"][0]
        self.assertIn("Azul Piedra", adoption["text"])
        self.assertEqual(adoption["samples"], ["S2"])
        # 澜湾的词没有写进石渡的命名。
        stone_terms = {
            entry.name for entry in self.pack.glossary if entry.brand == "石渡"
        }
        self.assertNotIn("Azul Piedra", stone_terms)

    def test_reply_chain_and_correction_scope(self):
        chains = design.comment_report(self.pack, list(self.readings.values()))["threads"]
        self.assertEqual(chains["R1"], ["R1", "R2", "R4"])
        correction = design.reading_summary(self.readings["R4"])
        self.assertIn("西区", correction["adopted_terms"][0]["text"])
        self.assertEqual(correction["adopted_terms"][0]["samples"], ["S2"])

    def test_local_only_reply_does_not_rename_other_brands(self):
        report = design.comment_report(self.pack, list(self.readings.values()))
        scoped = next(item for item in report["scoped_effects"] if item["comment"] == "R4")
        self.assertEqual(scoped["scoped_markets"], ["西区"])
        self.assertIn("北区", scoped["unchanged_markets"])
        self.assertIn("澜湾", scoped["unchanged_brands"])
        # 澜湾的正式名保持原样。
        self.assertEqual(
            [entry.name for entry in self.pack.glossary if entry.brand == "澜湾"],
            ["Azul Piedra"],
        )

    def test_conflicting_uses_need_designer_confirmation(self):
        report = design.comment_report(self.pack, list(self.readings.values()))
        ambiguous = {item["term"]: item for item in report["ambiguities"]}
        self.assertIn("浅岩", ambiguous)
        self.assertEqual(ambiguous["浅岩"]["samples"], ["S1", "S2"])
        self.assertEqual(ambiguous["浅岩"]["channels"], ["O1"])


class NameScopeTest(unittest.TestCase):
    def setUp(self):
        self.pack = Pack.load()

    def test_terms_that_only_live_in_one_brand(self):
        scope = names.term_scope(self.pack)
        self.assertEqual(scope["Azul Piedra"]["brands"], ["澜湾"])
        self.assertTrue(scope["Azul Piedra"]["single_market"])
        self.assertIn("Pizarra clara", scope)
        self.assertEqual(scope["Pizarra clara"]["markets"], {"西区": ["S1"]})

    def test_same_term_can_mean_two_samples(self):
        conflicts = names.name_conflicts(self.pack)
        multiple = [item for item in conflicts if item["kind"] == "term_multiple_samples"]
        self.assertTrue(any(item["term"] == "浅岩" and item["samples"] == ["S1", "S2"] for item in multiple))

    def test_timeline_flags_referent_change(self):
        timeline = names.term_timeline(self.pack, "浅岩", "西区")
        warning = [item for item in timeline if item.get("warning") == "term_referent_changed"]
        self.assertEqual(len(warning), 1)
        self.assertEqual(warning[0]["from"], "S1")
        self.assertEqual(warning[0]["to"], "S2")

    def test_resolution_respects_as_of(self):
        from datetime import datetime

        early = names.resolve_term(
            self.pack, "浅岩", "西区", as_of=datetime(2026, 10, 14, 10, 0), brand="石渡"
        )
        early_sources = {source for candidate in early for source in candidate.sources}
        # 10:00 时新换季页 CV6 还没上线；旧换季名 G5 仍作为旧称保留。
        self.assertNotIn("CV6", early_sources)
        self.assertIn("G5", early_sources)
        self.assertIn("CV2", early_sources)
        late = names.resolve_term(
            self.pack, "浅岩", "西区", as_of=datetime(2026, 10, 14, 11, 0), brand="石渡"
        )
        self.assertEqual([candidate.sample for candidate in late], ["S1", "S2"])
        late_sources = {source for candidate in late for source in candidate.sources}
        self.assertIn("CV6", late_sources)

    def test_drafts_never_become_customer_facing(self):
        drafts = names.resolve_term(
            self.pack, "石蓝", "北区", brand="石渡", include_drafts=False
        )
        self.assertEqual(drafts[0].sample, "S2")
        self.assertNotIn("CV4", drafts[0].sources)
        self.assertIn("formal", {use.status for use in drafts[0].uses})
        with_drafts = names.resolve_term(
            self.pack, "石蓝", "北区", brand="石渡", include_drafts=True
        )
        self.assertIn("draft", {use.status for use in with_drafts[0].uses})


class PublicationTest(unittest.TestCase):
    def setUp(self):
        self.pack = Pack.load()

    def test_crop_channel_needs_self_contained_card(self):
        card = publication.card_needs_self_contained_text(self.pack, "CV1")
        self.assertTrue(card["needs_text"])
        self.assertIn("齿印", card["suggested_text"])

    def test_brand_rights_are_per_layout(self):
        rights = publication.brand_rights(self.pack, "澜湾", "西区")
        self.assertTrue(rights["M"].may_crop)
        self.assertFalse(rights["N"].may_publish)

    def test_whole_only_photo_cannot_be_cropped(self):
        rights = publication.brand_rights(self.pack, "石渡", "北区")
        self.assertTrue(rights["N"].whole_only)
        self.assertFalse(rights["N"].may_crop)

    def test_retain_items_survive_banned_word_removal(self):
        warnings = publication.retention_warnings(self.pack, "O3", ("Azul Piedra",))
        self.assertTrue(warnings)
        self.assertTrue(all(item["must_keep"] for item in warnings))

    def test_shared_photo_permissions_do_not_cross_brands(self):
        obligations = {item.asset_id: item for item in publication.asset_obligations(self.pack, "O3")}
        self.assertFalse(obligations["A1"].may_publish)
        self.assertTrue(obligations["A3"].may_publish)


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.pack = Pack.load()

    def test_localization_never_promotes_other_brand_terms(self):
        rows = release.localized_terms(self.pack)["by_market"]["西区"]
        stone_s2 = next(row for row in rows if row["brand"] == "石渡" and row["sample"] == "S2")
        self.assertEqual(stone_s2["publishable"], ["Pizarra"])
        self.assertTrue(any("Azul Piedra" in item for item in stone_s2["blocked"]))

    def test_legacy_name_is_not_a_new_publish_term(self):
        rows = release.localized_terms(self.pack)["by_market"]["西区"]
        stone_s2 = next(row for row in rows if row["brand"] == "石渡" and row["sample"] == "S2")
        self.assertIn("浅岩", stone_s2["legacy_labels"])
        self.assertNotIn("浅岩", stone_s2["publishable"])

    def test_crop_channel_compares_marks_and_text(self):
        conflicts = release.crop_channel_conflicts(self.pack, "O1")
        same_label = next(item for item in conflicts if item["kind"] == "same_label_two_samples")
        self.assertEqual(same_label["label"], "浅岩")
        self.assertEqual(same_label["samples"], ["S1", "S2"])
        for option in same_label["compare"]:
            self.assertTrue(option["text"])

    def test_multiple_compliant_variants_for_album_channel(self):
        report = release.release_report(self.pack)["outlets"]["O1"]
        kinds = {variant["kind"] for variant in report["variants"]}
        self.assertEqual(kinds, {"individual_cards", "multi_variant_album"})
        cards = next(item for item in report["variants"] if item["kind"] == "individual_cards")
        self.assertIn("CV1", cards["card_texts"])
        # 草稿渠道不进入发布变体。
        draft_report = release.release_report(self.pack)["outlets"]["O2"]
        self.assertEqual(len(draft_report["variants"]), 1)
        self.assertEqual(draft_report["variants"][0]["kind"], "no_publishable_version")

    def test_non_publishable_is_spelled_out(self):
        blocked = release.non_publishable(self.pack, "O3")
        items = {item["item"] for item in blocked}
        self.assertIn("原片 A1（N）", items)
        self.assertIn("原片 A2（N）", items)


class EditorialTest(unittest.TestCase):
    def setUp(self):
        self.pack = Pack.load()

    def test_draft_and_live_views_differ(self):
        report = editorial.editorial_report(self.pack)
        self.assertEqual(report["draft_views"], ["CV4"])
        self.assertIn("CV1", report["published_views"])
        draft = next(item for item in report["views"] if item["view"] == "CV4")
        live = next(item for item in report["views"] if item["view"] == "CV1")
        self.assertEqual(draft["action"], "hold_draft")
        self.assertEqual(live["action"], "live_keep")

    def test_new_term_availability_by_market(self):
        report = editorial.editorial_report(self.pack)
        stone_blue = report["term_availability"]["石蓝"]
        self.assertEqual(stone_blue["markets"]["北区"]["draft_outlets"], ["O2"])
        self.assertEqual(stone_blue["markets"]["西区"]["live_outlets"], ["O1"])
        # 中岩 已由设计师提出并已上线 O1，但不在品牌正式名表里。
        midrock = report["term_availability"]["中岩"]
        self.assertIn("designer_proposal", midrock["statuses"])
        self.assertEqual(midrock["usable_now"], ["西区"])
        self.assertEqual(midrock["markets"]["西区"]["formal"], [])


class OrderResolutionTest(unittest.TestCase):
    def setUp(self):
        self.pack = Pack.load()
        self.readings = read_comments()
        self.results = {result.order: result for result in orders.resolve_all(self.pack, self.readings)}

    def test_short_request_uses_order_position_and_time(self):
        result = self.results["P007"]
        actions = [(step.request, step.action) for step in result.steps]
        self.assertIn(("Q1", "ambiguous"), actions)
        self.assertIn(("Q4", "confirmed"), actions)
        self.assertEqual(result.final_sample, "S1")

    def test_same_name_options_are_offered_before_switch(self):
        first = self.results["P007"].steps[0]
        self.assertEqual(first.action, "ambiguous")
        self.assertEqual({candidate.sample for candidate in first.candidates}, {"S1", "S2"})
        for candidate in first.candidates:
            self.assertTrue(candidate.position)
            self.assertTrue(candidate.describe())

    def test_switch_only_after_customer_confirmation(self):
        intent = next(step for step in self.results["P007"].steps if step.request == "Q2")
        self.assertEqual(intent.action, "intent")
        confirmed = next(step for step in self.results["P007"].steps if step.request == "Q4")
        self.assertEqual(confirmed.action, "confirmed")
        self.assertEqual(confirmed.chosen, "S1")

    def test_keep_original_returns_to_confirmed_snapshot(self):
        steps = {step.request: step for step in self.results["P007"].steps}
        # Q5 说的是“刚才确认的左前样”，回到 Q4 确认的订单快照，不重新选样。
        self.assertEqual(steps["Q5"].action, "reaffirm")
        self.assertEqual(steps["Q5"].chosen, "S1")
        p010 = self.results["P010"]
        self.assertEqual(p010.status, "unchanged")
        self.assertEqual(p010.final_sample, "S2")

    def test_committed_colour_is_protected_from_new_term(self):
        lookup = orders.committed_lookup(self.pack, "P007")
        self.assertEqual(lookup["seen_label"], "石蓝")
        self.assertEqual(lookup["seen_sample"], "S2")
        # 下单时石蓝只指 S2；后续同市场出现的新页把 S1 也挂成“浅岩”，
        # 但顾客已承诺的实物不改写。
        self.assertTrue(lookup["colliding_terms"])
        self.assertEqual(self.results["P007"].original.sample, "S2")


class WorkspaceTest(unittest.TestCase):
    def test_workspace_covers_every_source(self):
        workspace = build_workspace()
        self.assertEqual(
            set(workspace["sources"]),
            {
                "comments.tsv",
                "glossary.tsv",
                "outlets.tsv",
                "assets.tsv",
                "catalog_views.tsv",
                "order_views.tsv",
                "requests.tsv",
            },
        )
        self.assertTrue(workspace["orders"])
        self.assertTrue(workspace["release"]["art_links"])


if __name__ == "__main__":
    unittest.main()
