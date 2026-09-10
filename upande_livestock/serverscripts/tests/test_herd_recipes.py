import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import _base_for, tuned_bom
from upande_livestock.serverscripts.feeding.herd_recipes import herd_recipes


def _a_shared_standing_bom_herd_missed_by_custom_herd():
	"""A herd sharing its Herds.bom with another herd, picked so that the
	shared BOM's own `custom_herd` does NOT name this herd — the case a
	`custom_herd`-only lookup gets wrong. `custom_herd` may be blank (the
	original backfill rule) or may name the *other* herd of the pair (a later
	backfill rule attributing a shared BOM to whichever herd it judges fed
	first); either way this herd is the one a naive query would miss.
	Returns (herd_name, bom_name) or (None, None)."""
	rows = frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"])
	by_bom = {}
	for row in rows:
		by_bom.setdefault(row.bom, []).append(row.name)
	for bom, herds in by_bom.items():
		if len(herds) < 2:
			continue
		custom_herd = frappe.db.get_value("BOM", bom, "custom_herd")
		for herd in herds:
			if herd != custom_herd:
				return herd, bom
	return None, None


def _a_herd_with_mixed_uom_row():
	"""A herd whose standing BOM has at least one line where the recipe UOM
	differs from the item's stock UOM (hay on this site: 2-5 kg in the
	recipe, stocked in BALE at cf 0.07). Returns (herd, bom_name, BOM Item
	row) or (None, None, None)."""
	for row in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, fields=["name", "bom"]):
		for item in frappe.get_all(
			"BOM Item",
			filters={"parent": row.bom},
			fields=["item_code", "qty", "uom", "stock_qty", "stock_uom"],
		):
			if item.uom != item.stock_uom:
				return row.name, row.bom, item
	return None, None, None


class TestHerdRecipes(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_standing_ration_of_a_shared_bom_herd_comes_from_herds_bom(self):
		"""Herds.bom must answer this even for the herd of a shared pair that
		`custom_herd` does not name — a naive custom_herd-only implementation
		gets this case wrong."""
		herd, bom = _a_shared_standing_bom_herd_missed_by_custom_herd()
		if not herd:
			self.skipTest(
				"no shared-standing-BOM herd on kaitet.local is missed by custom_herd"
			)
		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		self.assertEqual(res["standing_bom"], bom)
		standing = [r for r in res["recipes"] if r["is_standing"]]
		self.assertEqual(len(standing), 1)
		self.assertEqual(standing[0]["bom_no"], bom)
		self.assertEqual(standing[0]["kind"], "Standing")

	def test_lines_come_back_in_recipe_uom_not_stock_uom(self):
		"""Hay is written as kg on every herd BOM checked but stocked in BALE
		at cf 0.07 — returning stock_qty/stock_uom here would feed the ~14x
		bug straight into a picker."""
		herd, bom, item = _a_herd_with_mixed_uom_row()
		if not herd:
			self.skipTest("no herd BOM on kaitet.local has a mixed-UOM line")
		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		standing = next(r for r in res["recipes"] if r["is_standing"])
		self.assertEqual(standing["bom_no"], bom)
		line = next(l for l in standing["lines"] if l["item_code"] == item.item_code)
		self.assertEqual(line["uom"], item.uom)
		self.assertAlmostEqual(flt(line["qty"]), flt(item.qty), places=4)
		self.assertNotAlmostEqual(flt(line["qty"]), flt(item.stock_qty), places=4)

	def test_a_missing_herd_is_refused(self):
		res = herd_recipes("Not A Real Herd On This Site")
		self.assertIn("error", res)

	def test_tuned_recipes_are_scoped_to_the_herd_and_come_back_newest_first(self):
		herd = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "name")
		base = frappe.get_doc("BOM", frappe.db.get_value("Herds", herd, "bom"))
		lines = [{"item_code": r.item_code, "qty": flt(r.qty)} for r in base.items]

		lines[0]["qty"] = flt(lines[0]["qty"]) + 3
		first = tuned_bom(herd, lines)

		lines2 = [dict(row) for row in lines]
		lines2[0]["qty"] = flt(lines2[0]["qty"]) + 5
		second = tuned_bom(herd, lines2)

		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		tuned_names = [r["bom_no"] for r in res["recipes"] if not r["is_standing"]]
		self.assertIn(first, tuned_names)
		self.assertIn(second, tuned_names)
		self.assertLess(
			tuned_names.index(second),
			tuned_names.index(first),
			"the newer tune should come before the older one",
		)
		# Only the two tunes just made are asserted to be labelled "Tuned".
		# This used to assert it of every non-standing recipe, which was true
		# only while tuning was the sole way to be non-standing; the picker now
		# also offers what the herd was actually fed, labelled "Previous". The
		# rule the test is really holding — a tuned BOM says it is one — is
		# unchanged.
		by_name = {r["bom_no"]: r for r in res["recipes"]}
		self.assertEqual(by_name[first]["kind"], "Tuned")
		self.assertEqual(by_name[second]["kind"], "Tuned")


def _a_herd_fed_more_than_one_recipe():
	"""A herd whose Work Orders cite two or more BOMs that are runnable for
	it — the case the picker was blind to. INCALF HEIFERS first, because that
	is the herd the farm reported it on (six recipes fed, one offered);
	otherwise whichever herd has the most history. (None, []) if this site has
	no such herd."""
	best = (None, [])
	for herd in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, pluck="name"):
		standing_item = frappe.db.get_value("BOM", frappe.db.get_value("Herds", herd, "bom"), "item")
		fed = frappe.db.sql(
			"""SELECT DISTINCT wo.bom_no FROM `tabWork Order` wo JOIN `tabBOM` b ON b.name = wo.bom_no
			   WHERE wo.custom_herd = %s AND wo.docstatus = 1
			     AND b.docstatus = 1 AND b.is_active = 1 AND b.item = %s""",
			(herd, standing_item),
			pluck=True,
		)
		if len(fed) < 2:
			continue
		if herd == "INCALF HEIFERS":
			return herd, fed
		if len(fed) > len(best[1]):
			best = (herd, fed)
	return best


def _the_most_fed_recipe(herd):
	"""(bom_no, times) for the recipe this herd was mixed most often."""
	row = frappe.db.sql(
		"""SELECT bom_no, COUNT(*) AS times FROM `tabWork Order`
		   WHERE custom_herd = %s AND docstatus = 1 AND IFNULL(bom_no, '') <> ''
		   GROUP BY bom_no ORDER BY times DESC LIMIT 1""",
		herd,
		as_dict=True,
	)
	return (row[0].bom_no, int(row[0].times)) if row else (None, 0)


class TestHerdRecipesOffersWhatWasActuallyFed(IntegrationTestCase):
	"""The picker's source of truth is the Work Order, not the `custom_herd`
	stamp.

	Only the six standing rations were ever stamped, so a picker built from
	stamps offered INCALF HEIFERS one recipe while its Work Orders showed six
	really mixed for it — -007 thirty times, -004 fourteen. These hold the
	endpoint to the history instead.
	"""

	def tearDown(self):
		frappe.db.rollback()

	def test_a_herd_is_offered_every_recipe_it_has_been_fed(self):
		herd, fed = _a_herd_fed_more_than_one_recipe()
		if not herd:
			self.skipTest("no herd on this site has been fed two runnable recipes")
		res = herd_recipes(herd)
		self.assertTrue(res["ok"], res.get("error"))
		offered = {r["bom_no"] for r in res["recipes"]}
		self.assertGreater(len(offered), 1, f"{herd} should be offered more than the standing ration")
		for bom in fed:
			self.assertIn(bom, offered, f"{herd} was fed {bom} but the picker does not offer it")

	def test_every_recipe_offered_is_one_a_run_would_accept(self):
		"""`_base_for` is the gate a chosen recipe passes on the way to a Work
		Order. A picker listing something that gate refuses is worse than one
		listing too few, so every herd on the site is held to it."""
		checked = 0
		for herd in frappe.get_all("Herds", filters={"bom": ["is", "set"]}, pluck="name"):
			res = herd_recipes(herd)
			if not res.get("ok"):
				continue
			for recipe in res["recipes"]:
				self.assertEqual(
					_base_for(herd, recipe["bom_no"]).name,
					recipe["bom_no"],
					f"{herd} is offered {recipe['bom_no']}, which _base_for would refuse",
				)
				# ERPNext's own rule: a Work Order refuses an inactive BOM.
				self.assertTrue(
					frappe.db.get_value("BOM", recipe["bom_no"], "is_active"),
					f"{herd} is offered inactive BOM {recipe['bom_no']}",
				)
				checked += 1
		self.assertGreater(checked, 0, "no herd on this site offered a recipe to check")

	def test_a_recipe_fed_thirty_times_is_one_option_carrying_its_count(self):
		herd, fed = _a_herd_fed_more_than_one_recipe()
		if not herd:
			self.skipTest("no herd on this site has been fed two runnable recipes")
		bom, times = _the_most_fed_recipe(herd)
		if times < 2:
			self.skipTest(f"{herd} has fed no recipe more than once")
		res = herd_recipes(herd)
		rows = [r for r in res["recipes"] if r["bom_no"] == bom]
		self.assertEqual(len(rows), 1, f"{bom} was fed {times} times and must appear once, not {len(rows)}")
		self.assertEqual(rows[0]["times_fed"], times)
		self.assertTrue(rows[0]["last_fed"], "a recipe that was fed must say when it last was")

	def test_the_standing_ration_leads_and_the_rest_follow_by_when_they_were_fed(self):
		herd, _fed = _a_herd_fed_more_than_one_recipe()
		if not herd:
			self.skipTest("no herd on this site has been fed two runnable recipes")
		res = herd_recipes(herd)
		self.assertTrue(res["recipes"][0]["is_standing"])
		self.assertEqual(res["recipes"][0]["bom_no"], res["standing_bom"])
		fed_dates = [r["last_fed"] for r in res["recipes"][1:] if r["last_fed"]]
		self.assertEqual(fed_dates, sorted(fed_dates, reverse=True), "most recently fed first")
		# Anything never fed sorts in behind everything that was.
		never = [i for i, r in enumerate(res["recipes"][1:]) if not r["last_fed"]]
		if never and fed_dates:
			self.assertGreater(min(never), len(fed_dates) - 1)

	def test_a_recipe_the_history_offers_can_be_tuned_from(self):
		"""The picker and `tuned_bom` have to agree: a recipe offered as a base
		must be usable as one, or the operator picks it and the submit refuses."""
		herd, fed = _a_herd_fed_more_than_one_recipe()
		if not herd:
			self.skipTest("no herd on this site has been fed two runnable recipes")
		standing = frappe.db.get_value("Herds", herd, "bom")
		base = next((b for b in fed if b != standing), None)
		if not base:
			self.skipTest(f"{herd} was fed nothing but its standing ration")
		lines = [
			{"item_code": r.item_code, "qty": flt(r.qty)}
			for r in frappe.get_doc("BOM", base).items
		]
		lines[0]["qty"] = flt(lines[0]["qty"]) + 1.5
		self.assertTrue(tuned_bom(herd, lines, base_bom=base))
