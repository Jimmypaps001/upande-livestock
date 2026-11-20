# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Loss scenarios: the claim through Upande Asset, the sale waiting for it, write-off.

Claim creation is pinned against a stand-in for Upande Asset's Insurance Claim
(the real one needs a policy, an Asset and a company set-up); the test that
touches the real doctype skips when Upande Asset is not on the site.
"""

import unittest
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import today

from upande_livestock.serverscripts.common import asset_cover, loss
from upande_livestock.serverscripts.losses import loss_api
from upande_livestock.serverscripts.tests.test_operations import _make_cow, _purge

SETTING = "sale_waits_for"


def _scenario(name, outcome, claim=0, trigger="Injury", docs=(), **kw):
	doc = frappe.get_doc({
		"doctype": "Livestock Loss Scenario", "scenario_name": name, "trigger": trigger,
		"outcome": outcome, "claim_insurance": claim, "active": 1,
		"incident_type": kw.get("incident_type"), "loss_treatment": kw.get("loss_treatment"),
		"required_documents": [{"document_name": n, "mandatory": m} for n, m in docs],
	})
	return doc.insert(ignore_permissions=True)


class _Base(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("loss_tests")
		self.addCleanup(frappe.db.rollback, save_point="loss_tests")
		self.tag = "ZZ LOSS COW"
		_make_cow(self.tag)
		self.addCleanup(_purge, "Animal", self.tag)

	def loss_with_claim(self, status):
		sc = _scenario("ZZ sell", "Sell live")
		doc = frappe.get_doc({"doctype": "Livestock Loss", "animal": self.tag, "scenario": sc.name,
		                      "incident_date": today(), "status": "Awaiting claim", "claim": "CLM-X",
		                      "claim_status": status}).insert(ignore_permissions=True)
		return doc


class TestSaleGate(_Base):
	def gate(self, setting, claim_status):
		self.loss_with_claim(claim_status)
		frappe.db.set_single_value("Livestock Settings", SETTING, setting)
		with mock.patch.object(loss, "claim_state", return_value=claim_status):
			return loss.sale_gate_message(self.tag)

	def test_claim_recorded_blocks_a_draft_claim_only(self):
		self.assertIn("CLM-X", self.gate("Claim recorded", "Draft"))
		self.assertIsNone(self.gate("Claim recorded", "Recorded"))
		self.assertIsNone(self.gate("Claim recorded", "Under Assessment"))

	def test_insurer_approved_blocks_until_approved(self):
		self.assertTrue(self.gate("Insurer approved", "Recorded"))
		self.assertTrue(self.gate("Insurer approved", "Under Assessment"))
		self.assertIsNone(self.gate("Insurer approved", "Approved"))
		self.assertIsNone(self.gate("Insurer approved", "Settled"))

	def test_nothing_never_blocks(self):
		self.assertIsNone(self.gate("Nothing", "Draft"))

	def test_a_rejected_claim_does_not_block(self):
		self.assertIsNone(self.gate("Insurer approved", "Rejected"))

	def test_default_is_claim_recorded(self):
		frappe.db.set_single_value("Livestock Settings", SETTING, "")
		self.assertEqual(loss.required_status(), "Claim recorded")

	def test_no_loss_or_no_claim_is_never_blocked(self):
		frappe.db.set_single_value("Livestock Settings", SETTING, "Insurer approved")
		self.assertIsNone(loss.sale_gate_message(self.tag))

	def test_disposal_submit_is_refused_server_side(self):
		self.loss_with_claim("Draft")
		frappe.db.set_single_value("Livestock Settings", SETTING, "Claim recorded")
		d = frappe.get_doc({"doctype": "Livestock Disposal", "animal": self.tag, "disposal_type": "Sold",
		                    "disposal_date": today()}).insert(ignore_permissions=True)
		with mock.patch.object(loss, "claim_state", return_value="Draft"):
			with self.assertRaises(frappe.ValidationError) as cm:
				d.submit()
		self.assertIn("cannot be sold yet", str(cm.exception))
		with mock.patch.object(loss, "claim_state", return_value="Recorded"):
			d.before_submit()  # lets her go

	def test_only_accounts_may_change_the_gate(self):
		with mock.patch("frappe.get_roles", return_value=["Livestock Manager"]), \
		     mock.patch.object(frappe.session, "user", "someone@example.com"):
			with self.assertRaises(frappe.PermissionError):
				loss.assert_may_change_accounts(["sale_waits_for"])
			loss.assert_may_change_accounts(["custom_farm"])
		with mock.patch("frappe.get_roles", return_value=["Accounts Manager"]):
			loss.assert_may_change_accounts(["sale_invoice_alert_roles"])


class TestRecordLoss(_Base):
	def test_write_off_retires_the_animal_without_a_claim(self):
		sc = _scenario("ZZ death", "Write off", trigger="Death")
		out = loss_api.record_loss(animal=self.tag, scenario=sc.name, notes="found dead")
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(out["status"], "Closed")
		status, disabled = frappe.db.get_value("Animal", self.tag, ["status", "disabled"])
		self.assertEqual((status, disabled), ("Dead", 1))
		self.assertEqual(frappe.db.get_value("Livestock Disposal", out["disposal"], "disposal_type"),
		                 "Died — Natural Causes")

	def test_theft_is_written_off_as_stolen(self):
		sc = _scenario("ZZ theft", "Write off", trigger="Theft")
		out = loss_api.record_loss(animal=self.tag, scenario=sc.name)
		self.assertEqual(frappe.db.get_value("Animal", self.tag, "status"), "Transferred Out")
		self.assertEqual(frappe.db.get_value("Livestock Disposal", out["disposal"], "disposal_type"), "Stolen")

	def test_sale_waits_as_a_draft_while_the_claim_is_a_draft(self):
		sc = _scenario("ZZ salvage", "Sell for slaughter", claim=1, incident_type="Injury",
		               loss_treatment="Impairment")
		frappe.db.set_single_value("Livestock Settings", SETTING, "Claim recorded")
		fake = frappe._dict(name="CLM-FAKE", status="Draft")
		with mock.patch.object(loss, "create_claim", return_value=(fake, None)), \
		     mock.patch.object(loss, "missing_documents", return_value=[]), \
		     mock.patch.object(loss, "claim_state", return_value="Draft"):
			out = loss_api.record_loss(animal=self.tag, scenario=sc.name, customer=None, sale_price=5000)
		self.assertTrue(out.get("ok"), out)
		self.assertEqual(out["status"], "Awaiting claim")
		self.assertIn("cannot be sold yet", out["blocked"])
		self.assertEqual(frappe.db.get_value("Livestock Disposal", out["disposal"], "docstatus"), 0)
		self.assertEqual(frappe.db.get_value("Animal", self.tag, "status"), "Active")

	def test_claim_moving_on_releases_the_waiting_sale(self):
		sc = _scenario("ZZ salvage2", "Sell live")
		doc = frappe.get_doc({"doctype": "Livestock Loss", "animal": self.tag, "scenario": sc.name,
		                      "incident_date": today(), "status": "Awaiting claim", "claim": "CLM-Y",
		                      "claim_status": "Draft"}).insert(ignore_permissions=True)
		frappe.db.set_single_value("Livestock Settings", SETTING, "Claim recorded")
		with mock.patch.object(loss, "notify_step") as note:
			loss.claim_changed(frappe._dict(name="CLM-Y", status="Recorded"))
		self.assertEqual(frappe.db.get_value("Livestock Loss", doc.name, "status"), "Sale waiting")
		self.assertEqual(frappe.db.get_value("Livestock Loss", doc.name, "claim_status"), "Recorded")
		self.assertEqual(note.call_count, 2)

	def test_a_second_open_loss_is_refused(self):
		sc = _scenario("ZZ sell3", "Sell live")
		frappe.get_doc({"doctype": "Livestock Loss", "animal": self.tag, "scenario": sc.name,
		                "incident_date": today(), "status": "Sale waiting"}).insert(ignore_permissions=True)
		out = loss_api.record_loss(animal=self.tag, scenario=sc.name)
		self.assertIn("already has a loss", out.get("error", ""))

	def test_an_unknown_or_inactive_scenario_is_refused(self):
		self.assertIn("scenario", loss_api.record_loss(animal=self.tag, scenario="nope").get("error", "").lower())
		sc = _scenario("ZZ off", "Write off")
		sc.db_set("active", 0)
		self.assertIn("switched off", loss_api.record_loss(animal=self.tag, scenario=sc.name).get("error", ""))


class TestClaimThroughUpandeAsset(_Base):
	def test_claim_is_drafted_with_the_scenario_incident_type_and_checklist(self):
		sc = _scenario("ZZ claim", "Write off", claim=1, trigger="Death", incident_type="Death / Mortality",
		               loss_treatment="Total Loss", docs=[("Vet report", 1), ("Photo", 0)])
		made = {}

		class Claim(frappe._dict):
			def append(self, table, row):
				self.setdefault(table, []).append(row)

			def update(self, d):
				super().update(d)

			def insert(self):
				made.update(self)
				self.name = "CLM-1"

		real_new_doc = frappe.new_doc
		fake = Claim()
		fake["flags"] = frappe._dict()
		new_doc = lambda dt, *a, **k: fake if dt == "Insurance Claim" else real_new_doc(dt, *a, **k)  # noqa: E731
		doc = frappe.get_doc({"doctype": "Livestock Loss", "animal": self.tag, "scenario": sc.name,
		                      "incident_date": today(), "notes": "dead"}).insert(ignore_permissions=True)
		frappe.db.set_value("Animal", self.tag, "asset_link", "AST-FAKE")
		with mock.patch.object(asset_cover, "available", return_value=True), \
		     mock.patch("frappe.new_doc", new_doc), \
		     mock.patch.object(frappe.db, "get_value", side_effect=lambda dt, *a, **k: (
		         "AST-FAKE" if dt == "Animal" else "Test Co")):
			claim, note = loss.create_claim(doc, sc, [{"document_name": "Vet report", "attachment": "/files/v.pdf"}])
		self.assertIsNone(note)
		self.assertEqual(made["incident_type"], "Death / Mortality")
		self.assertEqual(made["loss_treatment"], "Total Loss")
		self.assertEqual(made["status"], "Draft")
		docs = {r["document_name"]: r for r in made["documents"]}
		self.assertEqual(docs["Vet report"]["attachment"], "/files/v.pdf")
		self.assertEqual(docs["Photo"]["mandatory"], 0)

	def test_no_claim_when_upande_asset_is_missing(self):
		sc = _scenario("ZZ claim2", "Write off", claim=1, incident_type="Injury", loss_treatment="Impairment")
		doc = frappe.get_doc({"doctype": "Livestock Loss", "animal": self.tag, "scenario": sc.name,
		                      "incident_date": today()}).insert(ignore_permissions=True)
		with mock.patch.object(asset_cover, "available", return_value=False):
			claim, note = loss.create_claim(doc, sc)
		self.assertIsNone(claim)
		self.assertIn("not installed", note)

	@unittest.skipUnless(asset_cover.available(), "Upande Asset insurance is not installed")
	def test_the_real_claim_doctype_has_what_we_set(self):
		meta = frappe.get_meta("Insurance Claim")
		for f in ("asset", "incident_date", "reported_date", "incident_type", "loss_treatment", "documents"):
			self.assertTrue(meta.has_field(f), f)


class TestScenarioRules(_Base):
	def test_total_loss_with_a_sale_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			_scenario("ZZ bad", "Sell live", claim=1, incident_type="Injury", loss_treatment="Total Loss")

	def test_a_claim_needs_an_incident_type(self):
		with self.assertRaises(frappe.ValidationError):
			_scenario("ZZ bad2", "Write off", claim=1, loss_treatment="Total Loss")

	def test_seeds_are_created_once_on_an_empty_site(self):
		frappe.db.delete("Livestock Loss Scenario")
		loss.ensure_loss_scenarios()
		names = set(frappe.get_all("Livestock Loss Scenario", pluck="name"))
		self.assertIn("Theft", names)
		self.assertIn("Low production cull", names)
		before = len(names)
		loss.ensure_loss_scenarios()
		self.assertEqual(frappe.db.count("Livestock Loss Scenario"), before)
