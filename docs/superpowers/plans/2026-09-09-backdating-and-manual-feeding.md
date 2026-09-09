# Backdating and Manual Feeding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an operator record any livestock event on the day it actually happened, and let them tune a herd's TMR by hand for a stated number of head on a stated day.

**Architecture:** One module, `serverscripts/common/backdate.py`, owns the whole concept of "backdated" — resolving the date, deciding whether a record is historical, checking the settings switch, stamping the flag. Guards and the four drug-issuing call sites ask it rather than deciding for themselves. No endpoint changes its signature: every write endpoint already accepts its own date. Manual feeding builds a real BOM (ERPNext gives no other route) and reuses the existing manufacture-and-issue engine.

**Tech Stack:** Frappe v15 / ERPNext, Python 3.10; React Native + Expo Router + TanStack Query for the handset; a Custom HTML Block for the desk.

**Spec:** `docs/superpowers/specs/2026-09-09-backdating-and-manual-feeding-design.md`

## Global Constraints

- Site for all testing: `kaitet.local`. Backend branch `kaitet-dairy`; mobile branch `kaitet-dairy-frappe16-clean` in `~/stive/code/reactnative/upande-livestock`.
- Test command: `bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.<module>`, run from `/home/ubuntu/stive/code/frappe15`.
- After editing any DocType JSON: `bench --site kaitet.local migrate`. A full migrate on this site aborts on a lending Server Script bug — if it does, use `bench --site kaitet.local migrate --skip-failing`.
- **Tabs, not spaces**, in all Python in this app. Existing files are tab-indented.
- Custom fields for this app's own doctypes go **into the DocType JSON**, never into `fixtures/custom_field.json`. Only Stock Entry still uses fixtures (see the note in `hooks.py`).
- One file per endpoint; the module is named for the endpoint it exposes. `tests/test_deployability.py` enforces this.
- Every whitelisted endpoint calls `guard(...)` or `guard_read(...)` from `common/envelope.py` and wraps its body in `run(...)`.
- Never `frappe.db.commit()` inside an endpoint body — `run()` relies on the rollback.
- gunicorn runs with `--preload`. **Any HTTP test of a modified module is meaningless until** `sudo supervisorctl restart frappe15-web:frappe15-frappe-web`.
- Warning copy, verbatim, on the mobile backdating page: *"This is a backdating page. You are not affecting stocks — apply wisely. The system will run through afterwards."*
- The amber colour for backdated marks and the Backdate control: `#B45309` on light, `#F59E0B` on dark.

---

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `serverscripts/common/backdate.py` | The only module that knows what "backdated" means |
| `serverscripts/feeding/_availability.py` | Pre-flight stock check as of a posting date; earliest workable date |
| `serverscripts/feeding/_tuned_bom.py` | Resolve a tuned recipe to a reusable BOM |
| `serverscripts/feeding/manual_feed.py` | The manual feeding endpoint |
| `patches/add_backdating_fields.py` | Reload the six doctypes after the JSON edits |
| `serverscripts/tests/test_backdate.py` … `test_manual_feed.py` | One test module per unit |
| `app/(tabs)/record/backdate/[type].tsx` | The mobile backdating page |
| `src/frappe/manualFeed.ts` | Mobile client for `manual_feed` |
| `components/BackdateButton.tsx` | The amber header control |

**Modified**

| File | Change |
|---|---|
| 7 DocType JSONs | New fields |
| `serverscripts/common/events.py` | Stamp the flag in `new_livestock_event` |
| `serverscripts/common/guards.py:356` | Early return in `check_guards` |
| `doctype/livestock_event/livestock_event.py:1047` | Early return in `post_stock_issue` |
| `doctype/livestock_health_case/livestock_health_case.py:12` | Early return in `on_submit` |
| `doctype/livestock_diagnosis/livestock_diagnosis.py:12` | Early return in `on_submit` |
| `serverscripts/husbandry/create_husbandry_event.py:60` | Skip the batch issue when backdated |
| `serverscripts/feeding/_engine.py` | `posting_date` throughout; drop the `today()` hardcode |
| `serverscripts/mobile/record_feeding.py` | A `manual` action |
| `fixtures/custom_html_block.json` | Backdate routes + manual configuration tab |

---

# Phase 1 — Backdating backend

### Task 1: Schema

**Files:**
- Modify: `upande_livestock/upande_livestock/doctype/livestock_settings/livestock_settings.json`
- Modify: `upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.json`
- Modify: `livestock_disposal/livestock_disposal.json`, `livestock_health_case/livestock_health_case.json`, `livestock_diagnosis/livestock_diagnosis.json`, `livestock_weight_record/livestock_weight_record.json`, `milk_recording/milk_recording.json`
- Create: `upande_livestock/patches/add_backdating_fields.py`
- Modify: `upande_livestock/patches.txt`
- Test: `upande_livestock/patches/test_add_backdating_fields.py`

**Interfaces:**
- Produces: fieldnames `custom_backdating_open` (Livestock Settings), `custom_is_backdated` (six record doctypes), `custom_unposted_drugs` and `custom_feed_mode` (Livestock Event only).

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/patches/test_add_backdating_fields.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase

MARKED = [
	"Livestock Event",
	"Livestock Disposal",
	"Livestock Health Case",
	"Livestock Diagnosis",
	"Livestock Weight Record",
	"Milk Recording",
]


class TestAddBackdatingFields(FrappeTestCase):
	def test_the_switch_exists_on_settings(self):
		meta = frappe.get_meta("Livestock Settings")
		self.assertTrue(
			meta.has_field("custom_backdating_open"),
			"Livestock Settings needs the backdating switch",
		)

	def test_every_marked_doctype_carries_the_flag(self):
		for doctype in MARKED:
			with self.subTest(doctype=doctype):
				self.assertTrue(
					frappe.get_meta(doctype).has_field("custom_is_backdated"),
					"{0} cannot be marked backdated".format(doctype),
				)

	def test_the_flag_is_read_only(self):
		"""Set by server code on the way in. A user editing it by hand would
		un-mark a historical record, or mark a live one, and the guards read it."""
		for doctype in MARKED:
			with self.subTest(doctype=doctype):
				field = frappe.get_meta(doctype).get_field("custom_is_backdated")
				self.assertEqual(field.read_only, 1)

	def test_event_carries_the_drug_and_feed_mode_fields(self):
		meta = frappe.get_meta("Livestock Event")
		self.assertTrue(meta.has_field("custom_unposted_drugs"))
		self.assertTrue(meta.has_field("custom_feed_mode"))
		self.assertEqual(
			meta.get_field("custom_feed_mode").options, "\nSystem\nManual"
		)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.patches.test_add_backdating_fields
```

Expected: FAIL — `Livestock Settings needs the backdating switch`.

- [ ] **Step 3: Add the switch to Livestock Settings**

In `livestock_settings.json`, append to `field_order` after `steamer_days_from_lactation`:

```json
"sb_backdating",
"custom_backdating_open"
```

and append to `fields`:

```json
{
 "fieldname": "sb_backdating",
 "fieldtype": "Section Break",
 "label": "Backdating"
},
{
 "default": "0",
 "description": "While this is on, backdated records skip the age, interval and duplicate guards. Today's records are always guarded. Turn it off once the history load is finished.",
 "fieldname": "custom_backdating_open",
 "fieldtype": "Check",
 "label": "Backdating Open"
}
```

- [ ] **Step 4: Add the flag to the six record doctypes**

In each of the six JSONs, append `"custom_is_backdated"` to `field_order` and this to `fields`:

```json
{
 "default": "0",
 "fieldname": "custom_is_backdated",
 "fieldtype": "Check",
 "in_list_view": 1,
 "label": "Backdated",
 "read_only": 1,
 "search_index": 1
}
```

`search_index` because the reconciliation pass and every list filter select on it.

In `livestock_event.json` only, also append `"custom_unposted_drugs"` and `"custom_feed_mode"` to `field_order` and:

```json
{
 "default": "0",
 "depends_on": "eval:doc.custom_unposted_drugs",
 "description": "Drug rows were recorded on this event but never issued from the store.",
 "fieldname": "custom_unposted_drugs",
 "fieldtype": "Check",
 "label": "Drugs Not Issued",
 "read_only": 1,
 "search_index": 1
},
{
 "depends_on": "eval:doc.event_type=='Feeding'",
 "fieldname": "custom_feed_mode",
 "fieldtype": "Select",
 "label": "Feed Mode",
 "options": "\nSystem\nManual",
 "read_only": 1
}
```

- [ ] **Step 5: Write the patch**

Create `upande_livestock/patches/add_backdating_fields.py`:

```python
"""Reload the doctypes that gained backdating fields.

No data migration. Every existing record keeps custom_is_backdated = 0, which
is the truth about them: they were entered live, on the day they happened.
"""

import frappe

DOCTYPES = [
	"livestock_settings",
	"livestock_event",
	"livestock_disposal",
	"livestock_health_case",
	"livestock_diagnosis",
	"livestock_weight_record",
	"milk_recording",
]


def execute():
	for name in DOCTYPES:
		frappe.reload_doc("upande_livestock", "doctype", name)
```

Append to `upande_livestock/patches.txt`:

```
upande_livestock.patches.add_backdating_fields
```

- [ ] **Step 6: Migrate and run the test**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local migrate
bench --site kaitet.local run-tests --module upande_livestock.patches.test_add_backdating_fields
```

Expected: 4 tests, OK.

- [ ] **Step 7: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add upande_livestock/upande_livestock/doctype upande_livestock/patches
git commit -m "feat(livestock): a record can say it was entered for a past day"
```

---

### Task 2: `common/backdate.py`

**Files:**
- Create: `upande_livestock/serverscripts/common/backdate.py`
- Test: `upande_livestock/serverscripts/tests/test_backdate.py`

**Interfaces:**
- Consumes: `custom_backdating_open` from Task 1.
- Produces:
  - `window_open() -> bool`
  - `resolve(payload: dict, date_key: str | None = None) -> tuple[str, bool]` — `(date, is_backdated)`
  - `assert_allowed(is_backdated: bool) -> None`
  - `stamp(doc, is_backdated: bool) -> None`
  - `suppresses_stock(doc_or_type, is_backdated: bool) -> bool`

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_backdate.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common import backdate


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


class TestBackdateResolve(FrappeTestCase):
	def test_explicit_event_date_wins(self):
		past = add_days(today(), -30)
		date, is_back = backdate.resolve({"event_date": past, "service_date": today()}, "service_date")
		self.assertEqual(str(date), past)
		self.assertTrue(is_back)

	def test_the_type_specific_date_is_used_when_there_is_no_event_date(self):
		past = add_days(today(), -10)
		date, is_back = backdate.resolve({"service_date": past}, "service_date")
		self.assertEqual(str(date), past)
		self.assertTrue(is_back)

	def test_no_date_at_all_means_today_and_not_backdated(self):
		date, is_back = backdate.resolve({}, "service_date")
		self.assertEqual(str(date), today())
		self.assertFalse(is_back)

	def test_todays_date_is_not_backdated(self):
		_, is_back = backdate.resolve({"event_date": today()}, None)
		self.assertFalse(is_back)

	def test_a_future_date_is_not_backdated(self):
		"""Forward-dating is a different problem with different rules. This
		module answers one question and must not quietly own that one too."""
		_, is_back = backdate.resolve({"event_date": add_days(today(), 5)}, None)
		self.assertFalse(is_back)

	def test_an_empty_string_date_falls_through_to_today(self):
		"""A form that clears its date field posts "", not a missing key."""
		date, is_back = backdate.resolve({"event_date": "", "service_date": ""}, "service_date")
		self.assertEqual(str(date), today())
		self.assertFalse(is_back)


class TestBackdateWindow(FrappeTestCase):
	def tearDown(self):
		_set_window(0)

	def test_window_reads_the_setting(self):
		_set_window(1)
		self.assertTrue(backdate.window_open())
		_set_window(0)
		self.assertFalse(backdate.window_open())

	def test_assert_allowed_passes_when_open(self):
		_set_window(1)
		backdate.assert_allowed(True)  # must not throw

	def test_assert_allowed_refuses_a_backdated_record_when_closed(self):
		_set_window(0)
		with self.assertRaises(frappe.ValidationError) as caught:
			backdate.assert_allowed(True)
		self.assertIn("Backdating is closed", str(caught.exception))

	def test_assert_allowed_ignores_a_live_record_when_closed(self):
		_set_window(0)
		backdate.assert_allowed(False)  # must not throw


class TestBackdateStock(FrappeTestCase):
	def test_feeding_still_moves_stock_when_backdated(self):
		"""Feeding is the single exception. It is the whole reason the rule is
		expressed as a function rather than a constant."""
		self.assertFalse(backdate.suppresses_stock("Feeding", True))

	def test_other_types_do_not_move_stock_when_backdated(self):
		for event_type in ("Deworming", "Vaccination", "Service"):
			with self.subTest(event_type=event_type):
				self.assertTrue(backdate.suppresses_stock(event_type, True))

	def test_nothing_is_suppressed_for_a_live_record(self):
		self.assertFalse(backdate.suppresses_stock("Deworming", False))

	def test_a_document_can_be_passed_instead_of_a_type(self):
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Deworming"
		self.assertTrue(backdate.suppresses_stock(doc, True))


class TestBackdateStamp(FrappeTestCase):
	def test_stamp_sets_the_flag(self):
		doc = frappe.new_doc("Livestock Event")
		backdate.stamp(doc, True)
		self.assertEqual(doc.custom_is_backdated, 1)

	def test_stamp_clears_the_flag_for_a_live_record(self):
		doc = frappe.new_doc("Livestock Event")
		doc.custom_is_backdated = 1
		backdate.stamp(doc, False)
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_stamp_is_silent_on_a_doctype_without_the_field(self):
		"""Called from shared helpers that also build documents which will never
		carry the field. A missing field is not an error."""
		doc = frappe.new_doc("Livestock Alert")
		backdate.stamp(doc, True)  # must not throw
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdate
```

Expected: FAIL — `No module named 'upande_livestock.serverscripts.common.backdate'`.

- [ ] **Step 3: Write the module**

Create `upande_livestock/serverscripts/common/backdate.py`:

```python
"""What "backdated" means, in one place.

A record is backdated when the day it describes is earlier than the day it was
entered. That is the only definition, and everything that cares — the guards,
the four drug-issuing call sites, the feeding engine — asks here rather than
deciding for itself. Two of them decided for themselves once and disagreed.

Backdating is a property of a *request*, not a separate API. Every write
endpoint in this package already accepts a date; none of them changes shape to
support this. What changes is that the date is now believed.

FORWARD DATES ARE NOT BACKDATING. A date in the future is a different problem
with different rules — a service booked for next week is a plan, not a
historical record — and answering for it here would silently give planning
records the guard exemption that history needs.
"""

import frappe
from frappe import _
from frappe.utils import getdate, today

# Feeding is the one backdated event that still moves stock: it is the whole
# point of the manual feeding build. Everything else records what happened and
# leaves the store alone, to be reconciled later from custom_unposted_drugs.
STOCK_MOVING_TYPES = {"Feeding"}


def window_open() -> bool:
	"""True while Livestock Settings says a history load is in progress."""
	return bool(frappe.db.get_single_value("Livestock Settings", "custom_backdating_open"))


def resolve(payload: dict, date_key: str = None) -> tuple:
	"""Return ``(date, is_backdated)`` for a write request.

	Precedence is `event_date`, then the type-specific date, then today —
	deliberately identical to ``common.events.new_livestock_event`` so that the
	date a record is stamped against and the date it is judged by cannot drift
	apart. An empty string counts as absent: a form that clears its date field
	posts "", not a missing key.
	"""
	payload = payload or {}
	raw = payload.get("event_date") or (payload.get(date_key) if date_key else None)
	if not raw:
		return today(), False
	date = getdate(raw)
	return str(date), date < getdate(today())


def assert_allowed(is_backdated: bool) -> None:
	"""Refuse a backdated write while the window is closed."""
	if is_backdated and not window_open():
		frappe.throw(
			_(
				"Backdating is closed. Ask a manager to turn on Backdating Open in "
				"Livestock Settings, or record this against today."
			)
		)


def stamp(doc, is_backdated: bool) -> None:
	"""Mark `doc` as backdated, or explicitly as not.

	Silent when the doctype has no such field — this is called from helpers that
	also build documents which will never carry it.
	"""
	if doc.meta.has_field("custom_is_backdated"):
		doc.custom_is_backdated = 1 if is_backdated else 0


def suppresses_stock(doc_or_type, is_backdated: bool) -> bool:
	"""True when this write must record its consumption without posting it."""
	if not is_backdated:
		return False
	event_type = getattr(doc_or_type, "event_type", doc_or_type)
	return event_type not in STOCK_MOVING_TYPES
```

- [ ] **Step 4: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdate
```

Expected: 16 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts/common/backdate.py upande_livestock/serverscripts/tests/test_backdate.py
git commit -m "feat(livestock): one place that knows what backdated means"
```

---

### Task 3: Stamp events as they are built

**Files:**
- Modify: `upande_livestock/serverscripts/common/events.py`
- Test: `upande_livestock/serverscripts/tests/test_backdated_events.py`

**Interfaces:**
- Consumes: `backdate.resolve`, `backdate.stamp`, `backdate.assert_allowed` from Task 2.
- Produces: `new_livestock_event(d, event_type, date_key=None)` now stamps `custom_is_backdated` and refuses a backdated build while the window is closed. Signature unchanged.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_backdated_events.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.common.events import new_livestock_event


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _operator():
	name = frappe.db.get_value("Employee", {"status": "Active"}, "name")
	if not name:
		raise AssertionError("kaitet.local has no active Employee to attribute events to")
	return name


class TestNewLivestockEventStamps(FrappeTestCase):
	def setUp(self):
		_set_window(1)
		self.operator = _operator()

	def tearDown(self):
		_set_window(0)

	def test_a_past_date_is_stamped(self):
		past = add_days(today(), -45)
		doc = new_livestock_event(
			{"event_date": past, "operator": self.operator}, "Deworming"
		)
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(str(doc.event_date), past)

	def test_today_is_not_stamped(self):
		doc = new_livestock_event({"operator": self.operator}, "Deworming")
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_the_type_specific_date_also_stamps(self):
		"""A form that sends only service_date must still be recognised as
		backdated — event_date is derived from it, so the two must agree."""
		past = add_days(today(), -60)
		doc = new_livestock_event(
			{"service_date": past, "operator": self.operator}, "Service", date_key="service_date"
		)
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(str(doc.event_date), past)

	def test_a_backdated_build_is_refused_when_the_window_is_closed(self):
		_set_window(0)
		with self.assertRaises(frappe.ValidationError) as caught:
			new_livestock_event(
				{"event_date": add_days(today(), -5), "operator": self.operator}, "Deworming"
			)
		self.assertIn("Backdating is closed", str(caught.exception))

	def test_a_live_build_is_unaffected_when_the_window_is_closed(self):
		_set_window(0)
		doc = new_livestock_event({"operator": self.operator}, "Deworming")
		self.assertEqual(doc.custom_is_backdated, 0)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_events
```

Expected: FAIL — `custom_is_backdated` is 0 where 1 was expected.

- [ ] **Step 3: Wire it in**

In `upande_livestock/serverscripts/common/events.py`, replace the import block and the body of `new_livestock_event`:

```python
import frappe

from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.common.employee import employee_or_throw


def new_livestock_event(d, event_type, date_key=None):
	"""Build an unsaved Livestock Event of `event_type`.

	`event_date` is the canonical date for every event type: livestock_guards.py
	keys its age and interval rules on it, and the desk form relabels it per type
	("Service Date", "Movement Date", "Diagnosis Date"). A form that collects only
	the type-specific date therefore passes `date_key` so that date also becomes
	`event_date`. Without it a backdated entry stored the right `service_date` and
	an `event_date` of today, leaving the two out of step and the interval guards
	reading the wrong day.

	The same date decides whether this is a historical record. `backdate.resolve`
	uses exactly the precedence above, so the date the event carries and the date
	it is judged by are the same date by construction rather than by agreement.
	"""
	event_date, is_backdated = backdate.resolve(d, date_key)
	backdate.assert_allowed(is_backdated)

	doc = frappe.new_doc("Livestock Event")
	doc.animal = d.get("animal")
	doc.event_type = event_type
	doc.event_date = event_date
	doc.operator = employee_or_throw(d.get("operator"))
	doc.remarks = d.get("remarks")
	backdate.stamp(doc, is_backdated)
	return doc
```

Note the `from frappe.utils import today` import is now unused — remove it.

- [ ] **Step 4: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_events
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_operations
```

Expected: both OK. `test_operations` covers the existing date-precedence behaviour and must not regress.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts/common/events.py upande_livestock/serverscripts/tests/test_backdated_events.py
git commit -m "feat(livestock): an event knows it was recorded for a past day"
```

---

### Task 4: Guards stand down for backdated rows

**Files:**
- Modify: `upande_livestock/serverscripts/common/guards.py` (the `check_guards` function at line 356)
- Test: `upande_livestock/serverscripts/tests/test_backdated_guards.py`

**Interfaces:**
- Consumes: `backdate.window_open` from Task 2; `custom_is_backdated` from Task 1.
- Produces: no signature change. `check_guards(doc)` returns early for a backdated doc while the window is open.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_backdated_guards.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.serverscripts.common.guards import check_guards


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


class TestBackdatedGuards(FrappeTestCase):
	"""Deworming carries a minimum-interval rule. Two of them close together
	must be refused for a live entry and allowed for a historical one."""

	def setUp(self):
		_set_window(0)
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"animal_name": "GUARDTEST",
				"tag_number": frappe.generate_hash(length=10),
				"date_of_birth": add_months(today(), -36),
				"sex": "Female",
			}
		).insert(ignore_permissions=True)
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def tearDown(self):
		_set_window(0)
		frappe.db.rollback()

	def _event(self, event_date, backdated=0):
		doc = frappe.get_doc(
			{
				"doctype": "Livestock Event",
				"animal": self.animal.name,
				"event_type": "Deworming",
				"event_date": event_date,
				"operator": self.operator,
				"custom_is_backdated": backdated,
			}
		)
		return doc

	def _anchor(self, event_date):
		doc = self._event(event_date)
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc

	def test_a_live_event_too_soon_is_still_refused(self):
		"""The exemption must not leak into today's entries — that is the whole
		reason it keys on the flag rather than on the window alone."""
		self._anchor(add_days(today(), -2))
		with self.assertRaises(frappe.ValidationError):
			check_guards(self._event(today()))

	def test_a_backdated_event_too_soon_passes_while_the_window_is_open(self):
		_set_window(1)
		self._anchor(add_days(today(), -100))
		check_guards(self._event(add_days(today(), -98), backdated=1))  # must not throw

	def test_a_backdated_event_is_still_guarded_when_the_window_is_closed(self):
		_set_window(0)
		self._anchor(add_days(today(), -100))
		with self.assertRaises(frappe.ValidationError):
			check_guards(self._event(add_days(today(), -98), backdated=1))

	def test_a_live_event_is_unaffected_by_an_open_window(self):
		_set_window(1)
		self._anchor(add_days(today(), -2))
		with self.assertRaises(frappe.ValidationError):
			check_guards(self._event(today()))
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_guards
```

Expected: FAIL on `test_a_backdated_event_too_soon_passes_while_the_window_is_open` — a ValidationError is raised.

- [ ] **Step 3: Add the early return**

In `upande_livestock/serverscripts/common/guards.py`, add the import at the top of the import block:

```python
from upande_livestock.serverscripts.common import backdate
```

and replace `check_guards`:

```python
def check_guards(doc):
	"""Run every guard that applies to this event's type.

	A backdated record skips them all while the backdating window is open. The
	rules here describe how a herd is *managed* — serve no younger than fifteen
	months, do not deworm twice in a fortnight — and history does not always
	comply. Refusing it would mean the books can never be made to match what
	happened. Closing the window puts every rule back, including over the
	history that was loaded, so this is an amnesty with an end date rather than
	a permanent hole.

	The exemption keys on the flag, not on the window alone: an entry made for
	today while a load is in progress is a live entry and stays guarded.
	"""
	if not doc.event_type or not doc.animal:
		return
	if doc.get("custom_is_backdated") and backdate.window_open():
		return
	_check_age(doc)
	_check_age_window(doc)
	_check_interval(doc)
	_check_duplicate(doc)
```

- [ ] **Step 4: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_guards
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_livestock_guards
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_livestock_new_guards
```

Expected: all three OK. The two existing guard suites must not regress.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts/common/guards.py upande_livestock/serverscripts/tests/test_backdated_guards.py
git commit -m "feat(livestock): history does not have to obey rules written for today"
```

---

### Task 5: Drugs are recorded, not issued

**Files:**
- Modify: `upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py` (`post_stock_issue`, line 1047)
- Modify: `upande_livestock/upande_livestock/doctype/livestock_health_case/livestock_health_case.py` (`on_submit`, line 12)
- Modify: `upande_livestock/upande_livestock/doctype/livestock_diagnosis/livestock_diagnosis.py` (`on_submit`, line 12)
- Modify: `upande_livestock/serverscripts/husbandry/create_husbandry_event.py` (line 60)
- Test: `upande_livestock/serverscripts/tests/test_backdated_drugs.py`

**Interfaces:**
- Consumes: `backdate.suppresses_stock` from Task 2; `custom_unposted_drugs` from Task 1.
- Produces: a backdated drug-consuming event carries its `drug_issues` rows, has `custom_unposted_drugs = 1`, has no `stock_entry`, and leaves `Bin` untouched.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_backdated_drugs.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, flt, today

from upande_livestock.serverscripts.common import stock as livestock_stock
from upande_livestock.serverscripts.husbandry.create_husbandry_event import create_husbandry_event


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _bin_qty(item, warehouse):
	return flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": warehouse}, "actual_qty"))


class TestBackdatedDrugs(FrappeTestCase):
	def setUp(self):
		_set_window(1)
		self.warehouse = livestock_stock.drug_warehouse()
		row = frappe.db.sql(
			"""SELECT item_code FROM `tabBin`
			   WHERE warehouse = %s AND actual_qty > 10 LIMIT 1""",
			(self.warehouse,),
			as_dict=True,
		)
		if not row:
			self.skipTest("no drug stock on kaitet.local to test against")
		self.item = row[0].item_code
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"animal_name": "DRUGTEST",
				"tag_number": frappe.generate_hash(length=10),
				"date_of_birth": add_months(today(), -30),
				"sex": "Female",
			}
		).insert(ignore_permissions=True)
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def tearDown(self):
		_set_window(0)
		frappe.db.rollback()

	def _deworm(self, event_date):
		return create_husbandry_event(
			{
				"event_type": "Deworming",
				"animal": self.animal.name,
				"event_date": event_date,
				"operator": self.operator,
				"drugs": [
					{"item_code": self.item, "qty": 2, "source_warehouse": self.warehouse}
				],
			}
		)

	def test_a_backdated_treatment_leaves_the_store_alone(self):
		before = _bin_qty(self.item, self.warehouse)
		res = self._deworm(add_days(today(), -40))
		self.assertNotIn("error", res, res.get("error"))
		self.assertEqual(_bin_qty(self.item, self.warehouse), before)

	def test_a_backdated_treatment_posts_no_stock_entry(self):
		res = self._deworm(add_days(today(), -40))
		self.assertEqual(res.get("stock_entry"), "")
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertFalse(event.stock_entry)

	def test_the_drug_rows_survive_for_the_reconciliation(self):
		"""The quantities are the whole point — dropping them would make the
		later reconciliation pass impossible."""
		res = self._deworm(add_days(today(), -40))
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(len(event.drug_issues), 1)
		self.assertEqual(event.drug_issues[0].item_code, self.item)
		self.assertEqual(flt(event.drug_issues[0].qty), 2.0)

	def test_the_event_is_flagged_for_the_reconciliation(self):
		res = self._deworm(add_days(today(), -40))
		event = frappe.get_doc("Livestock Event", res["name"])
		self.assertEqual(event.custom_unposted_drugs, 1)
		self.assertEqual(event.custom_is_backdated, 1)

	def test_a_live_treatment_still_issues(self):
		"""The suppression must not leak into today's work."""
		before = _bin_qty(self.item, self.warehouse)
		res = self._deworm(today())
		self.assertNotIn("error", res, res.get("error"))
		self.assertTrue(res.get("stock_entry"))
		self.assertEqual(_bin_qty(self.item, self.warehouse), before - 2)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_drugs
```

Expected: FAIL — the store balance drops on a backdated treatment.

- [ ] **Step 3: Suppress the batch issue in the husbandry endpoint**

In `upande_livestock/serverscripts/husbandry/create_husbandry_event.py`, add to the imports:

```python
from upande_livestock.serverscripts.common import backdate
```

and replace the `stock_entry = None` block (currently lines 48-67):

```python
		# One Material Issue for the whole round, not one per animal. Dosing is
		# entered per animal — 2 ml a cow across 119 cows — so the store sees a
		# single line of 238 ml, which is both what left the shelf and what the
		# storekeeper can reconcile. The events are then stamped with that entry,
		# and LivestockEvent.post_stock_issue's `self.stock_entry` guard stops each
		# one posting again.
		#
		# A backdated round posts nothing. The drug rows are still written onto
		# every event and flagged, so the quantities survive for a reconciliation
		# pass, but the store's balance is not rewritten months after the fact.
		_, is_backdated = backdate.resolve(d)
		unposted = backdate.suppresses_stock(event_type, is_backdated)
		stock_entry = None
		if drugs and not unposted:
			rows = [
				{
					"item_code": drug["item_code"],
					"qty": drug["qty"] * len(animals),
					"warehouse": drug["source_warehouse"],
					"batch_no": drug.get("batch_no"),
					"uom": drug.get("uom"),
				}
				for drug in drugs
			]
			stock_entry = livestock_stock.issue_items(
				rows,
				remarks="Livestock {0} - {1} animal(s)".format(event_type, len(animals)),
				posting_date=d.get("event_date"),
				employee=d.get("operator"),
				# So the ledger says "Deworming", not "Material Issue".
				what=event_type,
			)

		created = []
		for animal in animals:
			doc = new_livestock_event(dict(d, animal=animal), event_type)
			for drug in drugs:
				doc.append("drug_issues", dict(drug, stock_entry_ref=stock_entry))
			if stock_entry:
				doc.stock_entry = stock_entry
			if unposted and drugs:
				doc.custom_unposted_drugs = 1
			doc.insert()
			doc.submit()
			created.append(doc.name)
```

- [ ] **Step 4: Suppress the per-document issue in `post_stock_issue`**

In `upande_livestock/upande_livestock/doctype/livestock_event/livestock_event.py`, add to the imports:

```python
from upande_livestock.serverscripts.common import backdate
```

and add a third early return in `post_stock_issue`, immediately after the `self.reference_doctype` return (currently line 1069):

```python
		# A backdated event records what was consumed without moving it. The
		# store's balance today is the result of what has actually been issued
		# from it; rewriting it for a treatment given in March would make the
		# shelf and the ledger disagree in the present to make them agree in the
		# past. The rows stay on the document and the flag marks them, so a
		# reconciliation can post them deliberately later.
		if backdate.suppresses_stock(self, self.get("custom_is_backdated")):
			if self.get("drug_issues") or self.get("semen_item"):
				self.db_set("custom_unposted_drugs", 1, update_modified=False)
			return
```

- [ ] **Step 5: Suppress it in the two health doctypes**

In `livestock_health_case.py`, add the import and an early return at the top of `on_submit` (before the `pending` list is built at line 43):

```python
from upande_livestock.serverscripts.common import backdate
```

```python
		if self.get("custom_is_backdated"):
			self.db_set("drug_stock_entry", None, update_modified=False)
			return
```

In `livestock_diagnosis.py`, add the same import and an early return immediately after the existing `if self.stock_entry: return` (line 29):

```python
		if self.get("custom_is_backdated"):
			return
```

- [ ] **Step 6: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_drugs
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_drug_issuing
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_livestock_stock
```

Expected: all three OK.

- [ ] **Step 7: Commit**

```bash
git add upande_livestock/upande_livestock/doctype upande_livestock/serverscripts/husbandry upande_livestock/serverscripts/tests/test_backdated_drugs.py
git commit -m "feat(livestock): a backdated treatment records the drug without moving it"
```

---

### Task 6: Stamp the five non-event doctypes

**Files:**
- Modify: `upande_livestock/serverscripts/milking/create_milk_recording.py`, `weights/create_weight_record.py`, `health/create_health_case.py`, `health/create_check_up.py`, `disposal/record_disposal.py`
- Test: `upande_livestock/serverscripts/tests/test_backdated_records.py`

**Interfaces:**
- Consumes: `backdate.resolve`, `backdate.assert_allowed`, `backdate.stamp` from Task 2.
- Produces: each of the five endpoints stamps its document.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_backdated_records.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_months, today

from upande_livestock.serverscripts.weights.create_weight_record import create_weight_record
from upande_livestock.serverscripts.milking.create_milk_recording import create_milk_recording


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


class TestBackdatedRecords(FrappeTestCase):
	def setUp(self):
		_set_window(1)
		self.animal = frappe.get_doc(
			{
				"doctype": "Animal",
				"animal_name": "RECTEST",
				"tag_number": frappe.generate_hash(length=10),
				"date_of_birth": add_months(today(), -30),
				"sex": "Female",
			}
		).insert(ignore_permissions=True)
		self.operator = frappe.db.get_value("Employee", {"status": "Active"}, "name")

	def tearDown(self):
		_set_window(0)
		frappe.db.rollback()

	def test_a_backdated_weight_is_stamped(self):
		past = add_days(today(), -20)
		res = create_weight_record(
			{
				"animal": self.animal.name,
				"weight_date": past,
				"weight_kg": 410,
				"operator": self.operator,
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		doc = frappe.get_doc("Livestock Weight Record", res["name"])
		self.assertEqual(doc.custom_is_backdated, 1)
		self.assertEqual(str(doc.weight_date), past)

	def test_a_live_weight_is_not_stamped(self):
		res = create_weight_record(
			{
				"animal": self.animal.name,
				"weight_date": today(),
				"weight_kg": 410,
				"operator": self.operator,
			}
		)
		doc = frappe.get_doc("Livestock Weight Record", res["name"])
		self.assertEqual(doc.custom_is_backdated, 0)

	def test_a_backdated_milk_recording_is_stamped(self):
		past = add_days(today(), -7)
		res = create_milk_recording(
			{
				"herd": frappe.db.get_value("Herds", {}, "name"),
				"recording_date": past,
				"milking_time": "06:00:00",
				"quantity": 120,
				"operator": self.operator,
			}
		)
		self.assertNotIn("error", res, res.get("error"))
		doc = frappe.get_doc("Milk Recording", res["name"])
		self.assertEqual(doc.custom_is_backdated, 1)

	def test_a_backdated_record_is_refused_when_the_window_is_closed(self):
		_set_window(0)
		res = create_weight_record(
			{
				"animal": self.animal.name,
				"weight_date": add_days(today(), -20),
				"weight_kg": 410,
				"operator": self.operator,
			}
		)
		self.assertIn("error", res)
		self.assertIn("Backdating is closed", res["error"])
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_records
```

Expected: FAIL — `custom_is_backdated` is 0.

- [ ] **Step 3: Stamp each of the five**

The change is the same shape in each. In `weights/create_weight_record.py`, add the import:

```python
from upande_livestock.serverscripts.common import backdate
```

and replace the line `doc.weight_date = d.get("weight_date") or today()`:

```python
		weight_date, is_backdated = backdate.resolve(d, "weight_date")
		backdate.assert_allowed(is_backdated)
		doc.weight_date = weight_date
		backdate.stamp(doc, is_backdated)
```

Apply the identical pattern with these date keys:

| File | Date key | Line to replace |
|---|---|---|
| `weights/create_weight_record.py` | `weight_date` | `doc.weight_date = d.get("weight_date") or today()` |
| `milking/create_milk_recording.py` | `recording_date` | `doc.recording_date = d.get("recording_date") or today()` |
| `health/create_health_case.py` | `opened_date` | `doc.opened_date = d.get("opened_date") or today()` |
| `health/create_check_up.py` | `diagnosis_date` | `doc.diagnosis_date = d.get("diagnosis_date") or today()` |
| `disposal/record_disposal.py` | `disposal_date` | `doc.disposal_date = d.get("disposal_date") or today()` |

Remove the now-unused `today` import from any file where it becomes unused. Verify with:

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
ruff check upande_livestock/serverscripts/
```

- [ ] **Step 4: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_records
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_operations
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_milking
```

Expected: all OK.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts
git commit -m "feat(livestock): weights, milk, health and disposals carry the mark too"
```

---

# Phase 2 — Feeding backend

### Task 7: `feeding/_availability.py`

**Files:**
- Create: `upande_livestock/serverscripts/feeding/_availability.py`
- Test: `upande_livestock/serverscripts/tests/test_feed_availability.py`

**Interfaces:**
- Consumes: `_engine.resolve_requirement(bom_no, total_qty) -> (bom, lines)`; each line dict carries `item_code`, `item_name`, `required_qty`, `source_warehouse`, `uom`.
- Produces:
  - `shortfalls_on(bom_no, total_qty, posting_date) -> list[dict]` — each `{item_code, item_name, required, available, short, uom, warehouse}`
  - `earliest_workable_date(bom_no, total_qty, from_date, to_date) -> str | None`
  - `assert_can_cover_on(bom_no, total_qty, posting_date) -> None` — throws a message naming every short item and the earliest workable date.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_feed_availability.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from upande_livestock.serverscripts.feeding import _availability


def _a_herd_bom():
	name = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "bom")
	if not name:
		raise AssertionError("kaitet.local has no herd with a BOM")
	return name


class TestFeedAvailability(FrappeTestCase):
	def setUp(self):
		self.bom = _a_herd_bom()

	def test_a_long_past_date_is_short(self):
		"""The farm's stock history does not reach back a year, so every line
		must report short rather than silently pass."""
		short = _availability.shortfalls_on(self.bom, 100, add_days(today(), -365))
		self.assertTrue(short, "expected shortfalls a year before any stock existed")
		for row in short:
			self.assertIn("item_code", row)
			self.assertGreater(row["short"], 0)

	def test_today_matches_the_engine(self):
		"""Today's answer must agree with resolve_requirement, which reads Bin.
		Two different answers for the same day is the bug this guards."""
		from upande_livestock.serverscripts.feeding._engine import resolve_requirement

		_, lines = resolve_requirement(self.bom, 100)
		engine_short = {ln["item_code"] for ln in lines if ln["short_qty"] > 0}
		ours = {r["item_code"] for r in _availability.shortfalls_on(self.bom, 100, today())}
		self.assertEqual(ours, engine_short)

	def test_assert_names_every_short_item_and_a_date(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			_availability.assert_can_cover_on(self.bom, 100, add_days(today(), -365))
		message = str(caught.exception)
		self.assertIn("store held", message)
		self.assertIn("Nothing was posted", message)

	def test_assert_passes_when_the_stores_can_cover_it(self):
		"""A trivially small run against today must not throw."""
		_availability.assert_can_cover_on(self.bom, 0.001, today())

	def test_earliest_workable_date_is_none_when_never_workable(self):
		self.assertIsNone(
			_availability.earliest_workable_date(
				self.bom, 10 ** 9, add_days(today(), -30), today()
			)
		)

	def test_earliest_workable_date_finds_today_for_a_tiny_run(self):
		found = _availability.earliest_workable_date(
			self.bom, 0.001, add_days(today(), -30), today()
		)
		self.assertIsNotNone(found)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_feed_availability
```

Expected: FAIL — no module `_availability`.

- [ ] **Step 3: Write the module**

Create `upande_livestock/serverscripts/feeding/_availability.py`:

```python
"""Can this feed run post on that day, and if not, when could it?

`_engine.resolve_requirement` prices a run against `Bin`, which holds today's
balance and nothing else. A backdated run has to be judged against the ledger as
it stood on the day, which is what `get_stock_balance` answers.

Relying on ERPNext's own NegativeStockError instead was tried and is not good
enough for this screen: it names the first item it trips over, gives no date, and
by the time it fires a Work Order and a transfer have already been written and
have to be rolled back. This runs first and writes nothing.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate

from erpnext.stock.utils import get_stock_balance

from upande_livestock.serverscripts.feeding._engine import resolve_requirement

# How far back to look for a workable day before giving up. A farm loading a
# season of history does not benefit from being told about a date eight months
# ago that it cannot use either.
SEARCH_DAYS = 90


def shortfalls_on(bom_no, total_qty, posting_date):
	"""Rows the stores could not cover on `posting_date`. Read-only."""
	_, lines = resolve_requirement(bom_no, total_qty)
	day = getdate(posting_date)
	short = []
	for line in lines:
		required = flt(line["required_qty"])
		if required <= 0:
			continue
		warehouse = line["source_warehouse"]
		if not warehouse:
			continue
		have = flt(get_stock_balance(line["item_code"], warehouse, day))
		if have + 1e-9 < required:
			short.append(
				{
					"item_code": line["item_code"],
					"item_name": line["item_name"],
					"warehouse": warehouse,
					"required": required,
					"available": have,
					"short": required - have,
					"uom": line["uom"] or "",
				}
			)
	return short


def earliest_workable_date(bom_no, total_qty, from_date, to_date):
	"""The first day in the range on which every line is covered, or None.

	Walks forward rather than back: the answer a user needs is the earliest day
	that works, and stock generally accumulates, so the first hit is the answer.
	"""
	day = getdate(from_date)
	last = getdate(to_date)
	while day <= last:
		if not shortfalls_on(bom_no, total_qty, day):
			return str(day)
		day = getdate(add_days(day, 1))
	return None


def assert_can_cover_on(bom_no, total_qty, posting_date):
	"""Throw a message a farm worker can act on, or return silently."""
	short = shortfalls_on(bom_no, total_qty, posting_date)
	if not short:
		return

	lines = "\n".join(
		_("{0}: needed {1:,.2f} {2}, store held {3:,.2f}").format(
			row["item_name"], row["required"], row["uom"], row["available"]
		)
		for row in short
	)
	workable = earliest_workable_date(
		bom_no, total_qty, posting_date, add_days(getdate(posting_date), SEARCH_DAYS)
	)
	when = (
		_("Earliest date this run works: {0}.").format(workable)
		if workable
		else _("No date in the next {0} days covers it.").format(SEARCH_DAYS)
	)
	frappe.throw(
		_("This feed run cannot post on {0}.\n\n{1}\n\n{2}\n\nNothing was posted.").format(
			getdate(posting_date), lines, when
		),
		title=_("Not enough stock on that day"),
	)
```

- [ ] **Step 4: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_feed_availability
```

Expected: 6 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts/feeding/_availability.py upande_livestock/serverscripts/tests/test_feed_availability.py
git commit -m "feat(livestock): tell the operator which day the feed run would work"
```

---

### Task 8: A feed run posts on the day it happened

**Files:**
- Modify: `upande_livestock/serverscripts/feeding/_engine.py` (`_run_manufacture`, `manufacture_herd_feed`, `feed_herd`, `_issue_feed`, `_record_feeding_event`)
- Modify: `upande_livestock/serverscripts/feeding/manufacture_feed.py`, `feeding/issue_feed.py`, `mobile/record_feeding.py` — pass `posting_date` through
- Test: `upande_livestock/serverscripts/tests/test_backdated_feeding.py`

**Interfaces:**
- Consumes: `_availability.assert_can_cover_on` from Task 7; `backdate` from Task 2.
- Produces:
  - `manufacture_herd_feed(herd, allow_shortage=False, employee=None, portion=1.0, posting_date=None, bom_no=None, heads=None, feed_mode="System")`
  - `_run_manufacture(production_item, bom_no, qty, herd=None, heads=None, allow_shortage=False, posting_date=None)`
  - `_issue_feed(herd, bom, qty, employee, posting_date=None, feed_mode="System")`
  - `_record_feeding_event(herd, item, qty, uom, employee, stock_entry, event_date=None, feed_mode="System")`

  `bom_no`, `heads` and `feed_mode` are added here so Task 10 needs no further change to this file.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_backdated_feeding.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from upande_livestock.serverscripts.feeding import _engine


def _set_window(value):
	frappe.db.set_single_value("Livestock Settings", "custom_backdating_open", value)


def _a_feedable_herd():
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.bom and (row.number_of_animals or 0) > 0:
			info = _engine.get_herd_feeding_program(row.name)
			if info["can_manufacture"]:
				return row.name
	return None


class TestBackdatedFeeding(FrappeTestCase):
	def setUp(self):
		_set_window(1)
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")

	def tearDown(self):
		_set_window(0)
		frappe.db.rollback()

	def test_a_run_dated_before_the_stock_existed_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as caught:
			_engine.manufacture_herd_feed(
				self.herd, portion=0.1, posting_date=add_days(today(), -365)
			)
		self.assertIn("cannot post on", str(caught.exception))

	def test_a_refused_run_leaves_nothing_behind(self):
		"""The check has to run before the Work Order, not after — a half-built
		run reads as feed sitting in the store that is not there."""
		before = frappe.db.count("Work Order")
		try:
			_engine.manufacture_herd_feed(
				self.herd, portion=0.1, posting_date=add_days(today(), -365)
			)
		except frappe.ValidationError:
			pass
		self.assertEqual(frappe.db.count("Work Order"), before)

	def test_manufacture_and_issue_share_the_posting_date(self):
		res = _engine.manufacture_herd_feed(self.herd, portion=0.05, posting_date=today())
		dates = {
			frappe.db.get_value("Stock Entry", res[key], "posting_date")
			for key in ("transfer_stock_entry", "manufacture_stock_entry", "issue_stock_entry")
		}
		self.assertEqual(len(dates), 1, "the three entries must land on one day")

	def test_the_feeding_event_carries_the_run_date_not_today(self):
		"""_record_feeding_event used to hardcode today(), which put every
		backdated run on the wrong day of the herd's timeline."""
		res = _engine.manufacture_herd_feed(self.herd, portion=0.05, posting_date=today())
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(str(event.event_date), today())

	def test_a_system_run_is_labelled_system(self):
		res = _engine.manufacture_herd_feed(self.herd, portion=0.05, posting_date=today())
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "System")

	def test_no_posting_date_still_works(self):
		"""Every existing caller passes nothing. They must keep working."""
		res = _engine.manufacture_herd_feed(self.herd, portion=0.05)
		self.assertTrue(res["issue_stock_entry"])
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_feeding
```

Expected: FAIL — `manufacture_herd_feed() got an unexpected keyword argument 'posting_date'`.

- [ ] **Step 3: Thread `posting_date` through `_run_manufacture`**

In `_engine.py`, add to the imports:

```python
from upande_livestock.serverscripts.common import backdate
from upande_livestock.serverscripts.feeding import _availability
```

Replace the signature and body of `_run_manufacture`:

```python
def _run_manufacture(production_item, bom_no, qty, herd=None, heads=None, allow_shortage=False, posting_date=None):
	"""Work Order -> Material Transfer for Manufacture -> Manufacture.

	One route for both stages. WIP and FG are both the feed store; each required
	item is sourced from the warehouse ``_pick_source`` chose, which is the same
	warehouse the availability check reported on.

	`posting_date` puts the whole run on a past day. All three documents take it,
	because a transfer dated today feeding a manufacture dated in March is not a
	run that happened — it is two runs that disagree.
	"""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Nothing to manufacture — quantity must be greater than zero.")

	store = _feed_store()
	company = _company()
	lines = _assert_can_cover(production_item, bom_no, qty, allow_shortage)
	source_of = {ln["item_code"]: ln["source_warehouse"] for ln in lines}

	wo = frappe.new_doc("Work Order")
	wo.production_item = production_item
	wo.bom_no = bom_no
	wo.qty = qty
	# Set explicitly rather than leaning on the field's `fetch_from`. That fetch
	# stopped firing server-side somewhere after frappe 16.26, so a Work Order
	# built through the API kept the "Nos" default — and Nos is a whole-number
	# UOM, so ERPNext refused every fractional batch ("Qty To Manufacture (319.8)
	# cannot be a fraction"). Feed is measured in kilograms and is fractional by
	# nature, so this has to be right, not merely usually right.
	wo.stock_uom = frappe.db.get_value("Item", production_item, "stock_uom")
	wo.company = company
	wo.fg_warehouse = store
	wo.wip_warehouse = store
	wo.transfer_material_against = "Work Order"
	wo.use_multi_level_bom = 0
	wo.skip_transfer = 0
	if posting_date:
		wo.planned_start_date = "{0} 06:00:00".format(posting_date)
	if herd and wo.meta.has_field("custom_herd"):
		wo.custom_herd = herd
	if heads and wo.meta.has_field("custom_no_of_cows"):
		wo.custom_no_of_cows = heads
	wo.insert(ignore_permissions=True)

	for row in wo.required_items:
		row.source_warehouse = source_of.get(row.item_code) or store
	wo.save(ignore_permissions=True)
	wo.submit()

	def _dated(stock_entry):
		if posting_date:
			stock_entry.set_posting_time = 1
			stock_entry.posting_date = posting_date
		return stock_entry

	transfer = _dated(frappe.get_doc(make_stock_entry(wo.name, "Material Transfer for Manufacture", qty)))
	transfer.insert(ignore_permissions=True)
	transfer.submit()

	manufacture = _dated(frappe.get_doc(make_stock_entry(wo.name, "Manufacture", qty)))
	manufacture.insert(ignore_permissions=True)
	manufacture.submit()

	return {
		"work_order": wo.name,
		"production_item": production_item,
		"bom_no": bom_no,
		"produced_qty": qty,
		"store": store,
		"posting_date": posting_date or today(),
		"transfer_stock_entry": transfer.name,
		"manufacture_stock_entry": manufacture.name,
	}
```

- [ ] **Step 4: Thread it through the three feeding functions**

Replace `manufacture_herd_feed` (keeping its existing docstring, with the two new paragraphs below appended):

```python
def manufacture_herd_feed(
	herd,
	allow_shortage=False,
	employee=None,
	portion=1.0,
	posting_date=None,
	bom_no=None,
	heads=None,
	feed_mode="System",
):
	"""Manufacture the herd's TMR and issue the whole batch to that herd.

	Total produced = heads * BOM.quantity; every raw material and the
	concentrate scale by head count. Refuses to run short unless explicitly
	overridden, because the transfer would otherwise post negative stock.

	`employee` attributes the issue; it defaults to the Employee linked to the
	logged-in user, which is what the block sends. That is attribution, not a
	quantity — there is still nothing to choose about how much goes out.

	The batch is issued in the same call, in full. Exactly what this run
	produced goes out — an earlier balance is left alone rather than swept up,
	so each batch reconciles against its own issue. That is the rule this
	function is built on: mixed feed never sits in the store, because it has
	already been eaten by the time anyone would count it.

	`portion` is how a farm that feeds twice a day records it: 0.5 mixes and
	issues half the day's ration, and two such runs make the day. It does not
	break the rule above — each run still issues everything it produced — and a
	day whose portions do not sum to 1 is a real day that happened, not an error
	to refuse. `feed_day_status` is what tells the screen how much of the day is
	left; nothing here enforces it.

	`bom_no` and `heads` override what the herd says. Manual feeding supplies
	both: a tuned recipe, and the number of head actually at the trough, which
	is not always the number on the herd record.

	`posting_date` puts the run on a past day. Availability is then judged
	against the ledger as it stood then, before anything is written, so a run
	that cannot post is refused with a date the operator can act on rather than
	an ERPNext error after two documents already exist.

	Nothing is committed here. The manufacture and the issue have to stand or
	fall together, and envelope.run() relies on the rollback.
	"""
	# When the caller states a head count, do not let _herd_bom refuse the run
	# for the herd's own count being zero. A herd record that says 0 while eight
	# animals stand at the trough is exactly the situation manual feeding is for,
	# and the operator has just told us the real number.
	if heads:
		bom = frappe.get_doc("BOM", bom_no or frappe.db.get_value("Herds", herd, "bom"))
		if not bom.name:
			frappe.throw(_("Herd {0} has no BOM linked.").format(herd))
	else:
		herd_doc, bom, herd_heads = _herd_bom(herd)
		if bom_no:
			bom = frappe.get_doc("BOM", bom_no)
		heads = herd_heads
	heads = int(heads)
	if heads <= 0:
		frappe.throw(_("Enter how many animals were fed."))
	per_head = flt(bom.quantity) or 1.0
	portion = flt(portion) or 1.0
	if portion <= 0:
		frappe.throw(_("A feeding run has to be for more than nothing."))
	total_qty = per_head * heads * portion

	# Availability first — it writes nothing, and a shortage is the more useful
	# thing to be told about. The operator is then resolved before anything
	# posts: finding that out afterwards would leave a manufactured batch with
	# no way to move it out, a half-done state that reads as feed in the store.
	if posting_date and getdate(posting_date) < getdate(today()):
		_availability.assert_can_cover_on(bom.name, total_qty, posting_date)
	else:
		_assert_can_cover(bom.item, bom.name, total_qty, frappe.parse_json(allow_shortage))
	employee = _operator_or_throw(employee)

	res = _run_manufacture(
		bom.item,
		bom.name,
		total_qty,
		herd=herd,
		heads=heads,
		allow_shortage=frappe.parse_json(allow_shortage),
		posting_date=posting_date,
	)
	issue = _issue_feed(herd, bom, total_qty, employee, posting_date=posting_date, feed_mode=feed_mode)
	res.update(
		{
			"heads": heads,
			"per_head_qty": per_head,
			"portion": portion,
			"uom": bom.uom,
			"feed_mode": feed_mode,
			"issued_qty": issue["issued_qty"],
			"issue_stock_entry": issue["stock_entry"],
			"livestock_event": issue["livestock_event"],
			"employee": employee,
		}
	)
	return res
```

Add `getdate` to the `frappe.utils` import at the top of the file:

```python
from frappe.utils import flt, getdate, today
```

- [ ] **Step 5: Date the issue and the event**

Replace `feed_herd`, `_issue_feed` and `_record_feeding_event`:

```python
def feed_herd(herd, qty, employee=None, posting_date=None):
	"""Issue `qty` of a herd's TMR out of the store.

	Not the normal path any more — manufacturing issues its own batch. This
	stays for corrections and for clearing a balance left by an earlier run.
	"""
	qty = flt(qty)
	if qty <= 0:
		frappe.throw("Enter a quantity greater than zero.")
	herd_doc, bom, heads = _herd_bom(herd)
	return _issue_feed(herd, bom, qty, _operator_or_throw(employee), posting_date=posting_date)


def _issue_feed(herd, bom, qty, employee, posting_date=None, feed_mode="System"):
	"""Post the Material Issue and put the feeding on the herd's timeline."""
	store = _feed_store()
	company = _company()
	item = bom.item
	emp_name = frappe.db.get_value("Employee", employee, "employee_name")

	se = frappe.new_doc("Stock Entry")
	# Named rather than generic — see livestock_stock.STOCK_ENTRY_TYPES.
	se.stock_entry_type = livestock_stock.stock_entry_type_for("Feeding")
	se.purpose = "Material Issue"
	se.company = company
	if posting_date:
		se.set_posting_time = 1
		se.posting_date = posting_date
	if se.meta.has_field("custom_employee"):
		se.custom_employee = employee
	if se.meta.has_field("custom_employee_data"):
		emp_row = se.append("custom_employee_data", {})
		emp_row.employee = employee
		emp_row.employee_name = emp_name
	row = se.append("items", {})
	row.item_code = item
	row.qty = qty
	row.s_warehouse = store
	se.remarks = "Animal feeding - {0} - {1} - {2} {3}".format(herd, item, qty, bom.uom or "")
	se.insert(ignore_permissions=True)
	se.submit()
	# No frappe.db.commit() here: it stranded the Stock Entry when the Livestock
	# Event below failed, and defeats the rollback envelope.run() relies on.
	# The request (or the caller) owns the commit.

	event = _record_feeding_event(
		herd, item, qty, bom.uom, employee, se.name, event_date=posting_date, feed_mode=feed_mode
	)

	return {
		"stock_entry": se.name,
		"livestock_event": event,
		"herd": herd,
		"production_item": item,
		"issued_qty": qty,
		"uom": bom.uom,
		"store": store,
		"employee": employee,
	}


def _record_feeding_event(herd, item, qty, uom, employee, stock_entry, event_date=None, feed_mode="System"):
	"""Put the feeding on the herd's timeline as a Feeding Livestock Event.

	Herd-level, with no animal: feed goes to a trough, not to one cow, and
	LivestockEvent.validate() has a matching exemption for exactly this case. One
	event per animal would mean 119 identical rows for a single feed issue.

	`event_date` used to be hardcoded to today, which put every backdated run on
	the wrong day of the herd's timeline while its Stock Entry sat on the right
	one — the two records of the same act disagreeing.

	The event is best-effort. The feed has physically left the store once the Stock
	Entry submits, so a timeline write that fails must not roll that back and leave
	the books disagreeing with the yard — it warns instead.
	"""
	event_date = event_date or today()
	try:
		doc = frappe.new_doc("Livestock Event")
		doc.event_type = "Feeding"
		doc.event_date = event_date
		doc.current_herd = herd
		doc.operator = employee
		doc.stock_entry = stock_entry
		doc.custom_feed_mode = feed_mode
		backdate.stamp(doc, getdate(event_date) < getdate(today()))
		doc.remarks = "Feed issued: {0} {1} of {2}".format(qty, uom or "", item)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		doc.submit()
		return doc.name
	except Exception as e:
		frappe.log_error(message=frappe.get_traceback(), title="Livestock feeding event failed")
		frappe.msgprint(
			"Feed was issued ({0}), but the Feeding event was not recorded: {1}".format(stock_entry, str(e)),
			alert=True,
			indicator="orange",
		)
		return None
```

- [ ] **Step 6: Pass the date through the three callers**

In `feeding/manufacture_feed.py`, `feeding/issue_feed.py` and `mobile/record_feeding.py`, read `posting_date` from the payload and pass it on. In `mobile/record_feeding.py`, the `manufacture` branch becomes:

```python
	if action == "manufacture":
		return _engine.manufacture_herd_feed(
			d.get("herd"),
			portion=d.get("portion") or 1.0,
			posting_date=d.get("posting_date"),
		)
```

- [ ] **Step 7: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_backdated_feeding
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_feeding_program
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_feed_day
```

Expected: all OK.

- [ ] **Step 8: Commit**

```bash
git add upande_livestock/serverscripts/feeding upande_livestock/serverscripts/mobile upande_livestock/serverscripts/tests/test_backdated_feeding.py
git commit -m "feat(livestock): a feed run posts on the day the cows were fed"
```

---

### Task 9: `feeding/_tuned_bom.py`

**Files:**
- Create: `upande_livestock/serverscripts/feeding/_tuned_bom.py`
- Test: `upande_livestock/serverscripts/tests/test_tuned_bom.py`

**Interfaces:**
- Produces: `tuned_bom(herd: str, lines: list[dict]) -> str` — a submitted BOM name. Each line is `{"item_code": str, "qty": float}`.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_tuned_bom.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom


def _a_herd():
	name = frappe.db.get_value("Herds", {"bom": ["is", "set"]}, "name")
	if not name:
		raise AssertionError("kaitet.local has no herd with a BOM")
	return name


class TestTunedBom(FrappeTestCase):
	def setUp(self):
		self.herd = _a_herd()
		self.base = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [
			{"item_code": row.item_code, "qty": flt(row.qty)} for row in self.base.items
		]

	def tearDown(self):
		frappe.db.rollback()

	def _tuned(self):
		lines = [dict(row) for row in self.lines]
		lines[0]["qty"] = flt(lines[0]["qty"]) + 3
		return lines

	def test_it_creates_a_submitted_bom(self):
		name = tuned_bom(self.herd, self._tuned())
		doc = frappe.get_doc("BOM", name)
		self.assertEqual(doc.docstatus, 1)
		self.assertEqual(doc.item, self.base.item)

	def test_the_bom_is_active_but_not_default(self):
		"""ERPNext refuses a Work Order against an inactive BOM — verified on
		this site. is_default = 0 is what keeps it out of the herd's way."""
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, self._tuned()))
		self.assertEqual(doc.is_active, 1)
		self.assertEqual(doc.is_default, 0)

	def test_the_herds_own_bom_is_untouched(self):
		tuned_bom(self.herd, self._tuned())
		self.assertEqual(frappe.db.get_value("Herds", self.herd, "bom"), self.base.name)
		self.assertEqual(
			frappe.db.get_value("Item", self.base.item, "default_bom"), self.base.name
		)

	def test_the_tuned_quantities_land_on_the_bom(self):
		lines = self._tuned()
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		got = {row.item_code: flt(row.qty) for row in doc.items}
		for line in lines:
			self.assertAlmostEqual(got[line["item_code"]], flt(line["qty"]), places=4)

	def test_an_identical_tune_is_reused(self):
		"""A farm that mixes the same correction every morning must not
		accumulate a BOM a day."""
		lines = self._tuned()
		first = tuned_bom(self.herd, lines)
		second = tuned_bom(self.herd, [dict(row) for row in lines])
		self.assertEqual(first, second)

	def test_a_different_tune_makes_a_different_bom(self):
		first = tuned_bom(self.herd, self._tuned())
		other = self._tuned()
		other[0]["qty"] = flt(other[0]["qty"]) + 7
		self.assertNotEqual(tuned_bom(self.herd, other), first)

	def test_an_untuned_recipe_returns_the_herds_own_bom(self):
		"""Nothing changed means nothing to create."""
		self.assertEqual(tuned_bom(self.herd, self.lines), self.base.name)

	def test_an_empty_line_list_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			tuned_bom(self.herd, [])

	def test_a_zero_quantity_line_is_dropped(self):
		lines = [dict(row) for row in self.lines]
		lines[0]["qty"] = 0
		doc = frappe.get_doc("BOM", tuned_bom(self.herd, lines))
		self.assertNotIn(lines[0]["item_code"], [row.item_code for row in doc.items])
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_tuned_bom
```

Expected: FAIL — no module `_tuned_bom`.

- [ ] **Step 3: Write the module**

Create `upande_livestock/serverscripts/feeding/_tuned_bom.py`:

```python
"""Turn a hand-tuned recipe into something ERPNext will manufacture.

There is no shorter route. Two were tried on this site and both fail:

  * A Work Order against an inactive BOM is refused outright —
    "BOM ... must be active".
  * Hand-editing ``Work Order.required_items[].required_qty`` does not survive
    the save. ``Work Order.validate`` calls ``set_required_items(reset_only_qty=…)``
    and puts the BOM's numbers back. Set 300 to 1299, save, read 300.

So a tuned recipe has to be a real, active, submitted BOM. What it must NOT be
is the herd's default: ``is_default = 0`` keeps it out of every herd picker and
leaves ``Item.default_bom`` and ``Herds.bom`` pointing where they did.

Identical tunes are reused. A farm correcting the same way every morning would
otherwise accumulate a BOM a day, and the BOM list on the live site is already
fifteen revisions deep on one item.
"""

import frappe
from frappe import _
from frappe.utils import flt


def _signature(lines):
	"""A stable key for a set of (item, qty) pairs, order-independent."""
	return tuple(sorted((row["item_code"], round(flt(row["qty"]), 4)) for row in lines))


def _clean(lines):
	out = []
	for row in lines or []:
		item = (row.get("item_code") or "").strip()
		qty = flt(row.get("qty"))
		if item and qty > 0:
			out.append({"item_code": item, "qty": qty})
	return out


def _existing_match(item, signature):
	"""A submitted non-default BOM for `item` whose lines match, or None."""
	for row in frappe.get_all(
		"BOM",
		filters={"item": item, "docstatus": 1, "is_default": 0, "is_active": 1},
		fields=["name"],
		order_by="creation desc",
	):
		lines = frappe.get_all(
			"BOM Item", filters={"parent": row.name}, fields=["item_code", "qty"]
		)
		if _signature([{"item_code": r.item_code, "qty": r.qty} for r in lines]) == signature:
			return row.name
	return None


def tuned_bom(herd, lines):
	"""Return a BOM name that makes the herd's feed item to `lines`.

	Returns the herd's own BOM unchanged when the tune matches it — a screen
	that submits without editing anything should not mint a duplicate.
	"""
	lines = _clean(lines)
	if not lines:
		frappe.throw(_("A feed run needs at least one ingredient."))

	base_name = frappe.db.get_value("Herds", herd, "bom")
	if not base_name:
		frappe.throw(_("Herd {0} has no BOM linked.").format(herd))
	base = frappe.get_doc("BOM", base_name)

	signature = _signature(lines)
	if _signature([{"item_code": r.item_code, "qty": r.qty} for r in base.items]) == signature:
		return base.name

	found = _existing_match(base.item, signature)
	if found:
		return found

	doc = frappe.copy_doc(base)
	doc.is_active = 1  # ERPNext refuses a Work Order against anything else
	doc.is_default = 0
	doc.set("items", [])
	for row in lines:
		item = frappe.get_cached_doc("Item", row["item_code"])
		doc.append(
			"items",
			{
				"item_code": row["item_code"],
				"item_name": item.item_name,
				"qty": row["qty"],
				"uom": item.stock_uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": 1,
			},
		)
	doc.insert(ignore_permissions=True)
	doc.submit()
	return doc.name
```

- [ ] **Step 4: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_tuned_bom
```

Expected: 9 tests, OK.

- [ ] **Step 5: Commit**

```bash
git add upande_livestock/serverscripts/feeding/_tuned_bom.py upande_livestock/serverscripts/tests/test_tuned_bom.py
git commit -m "feat(livestock): a hand-tuned ration becomes a BOM the herd never sees"
```

---

### Task 10: `feeding/manual_feed.py`

**Files:**
- Create: `upande_livestock/serverscripts/feeding/manual_feed.py`
- Modify: `upande_livestock/serverscripts/mobile/record_feeding.py` — add a `manual` action
- Test: `upande_livestock/serverscripts/tests/test_manual_feed.py`

**Interfaces:**
- Consumes: `tuned_bom` (Task 9); `manufacture_herd_feed(..., bom_no=, heads=, feed_mode=)` (Task 8).
- Produces: `manual_feed(payload)` — payload `{herd, lines, heads, posting_date, portion, employee}`.

- [ ] **Step 1: Write the failing test**

Create `upande_livestock/serverscripts/tests/test_manual_feed.py`:

```python
import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt, today

from upande_livestock.serverscripts.feeding._engine import get_herd_feeding_program
from upande_livestock.serverscripts.feeding.manual_feed import manual_feed


def _a_feedable_herd():
	for row in frappe.get_all("Herds", fields=["name", "bom", "number_of_animals"]):
		if row.bom and (row.number_of_animals or 0) > 0:
			if get_herd_feeding_program(row.name)["can_manufacture"]:
				return row.name
	return None


class TestManualFeed(FrappeTestCase):
	def setUp(self):
		self.herd = _a_feedable_herd()
		if not self.herd:
			self.skipTest("no herd on kaitet.local can currently be fed")
		bom = frappe.get_doc("BOM", frappe.db.get_value("Herds", self.herd, "bom"))
		self.lines = [
			{"item_code": r.item_code, "qty": flt(r.qty) * 0.02} for r in bom.items
		]

	def tearDown(self):
		frappe.db.rollback()

	def test_it_feeds_and_returns_the_documents(self):
		res = manual_feed({"herd": self.herd, "lines": self.lines, "heads": 2})
		self.assertNotIn("error", res, res.get("error"))
		self.assertTrue(res["work_order"])
		self.assertTrue(res["issue_stock_entry"])

	def test_the_head_count_drives_the_quantity(self):
		"""Not Herds.number_of_animals — the operator says how many were at the
		trough, which is the whole point of the field."""
		two = manual_feed({"herd": self.herd, "lines": self.lines, "heads": 2})
		frappe.db.rollback()
		four = manual_feed({"herd": self.herd, "lines": self.lines, "heads": 4})
		self.assertAlmostEqual(four["produced_qty"], two["produced_qty"] * 2, places=3)

	def test_the_event_is_labelled_manual(self):
		res = manual_feed({"herd": self.herd, "lines": self.lines, "heads": 2})
		event = frappe.get_doc("Livestock Event", res["livestock_event"])
		self.assertEqual(event.custom_feed_mode, "Manual")

	def test_a_missing_head_count_is_refused(self):
		res = manual_feed({"herd": self.herd, "lines": self.lines, "heads": 0})
		self.assertIn("error", res)
		self.assertIn("how many animals", res["error"])

	def test_no_lines_is_refused(self):
		res = manual_feed({"herd": self.herd, "lines": [], "heads": 2})
		self.assertIn("error", res)
		self.assertIn("at least one ingredient", res["error"])

	def test_it_posts_on_the_given_date(self):
		res = manual_feed(
			{"herd": self.herd, "lines": self.lines, "heads": 2, "posting_date": today()}
		)
		self.assertEqual(
			str(frappe.db.get_value("Stock Entry", res["issue_stock_entry"], "posting_date")),
			today(),
		)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_manual_feed
```

Expected: FAIL — no module `manual_feed`.

- [ ] **Step 3: Write the endpoint**

Create `upande_livestock/serverscripts/feeding/manual_feed.py`:

```python
"""Feed a herd a recipe the operator wrote, for a head count they counted.

The system path answers "what does this herd's BOM say, times how many animals
the herd record claims". Both halves of that are sometimes wrong on the day: the
store is out of canola and the mixer used more wheat bran, or forty of the fifty
cows were out at the far paddock. This lets the operator say what actually
happened and posts that.

It is the same engine underneath — a Work Order, a transfer, a manufacture and
an issue, all on one posting date. Only the recipe and the head count come from
the request instead of from the herd.
"""

import frappe
from frappe import _

from upande_livestock.serverscripts.common.envelope import as_dict, guard, run
from upande_livestock.serverscripts.feeding._engine import manufacture_herd_feed
from upande_livestock.serverscripts.feeding._tuned_bom import tuned_bom


@frappe.whitelist()
def manual_feed(payload):
	"""Mix and issue a tuned ration. See the module docstring."""

	def go():
		guard("Stock Entry")
		d = as_dict(payload)

		herd = d.get("herd")
		if not herd:
			frappe.throw(_("Choose a herd."))
		heads = int(frappe.utils.flt(d.get("heads")))
		if heads <= 0:
			frappe.throw(_("Enter how many animals were fed."))

		bom_no = tuned_bom(herd, d.get("lines"))
		return manufacture_herd_feed(
			herd,
			employee=d.get("employee"),
			portion=d.get("portion") or 1.0,
			posting_date=d.get("posting_date"),
			bom_no=bom_no,
			heads=heads,
			feed_mode="Manual",
		)

	return run(go, "livestock manual_feed failed")
```

- [ ] **Step 4: Route it from the handset**

In `upande_livestock/serverscripts/mobile/record_feeding.py`, add to the imports:

```python
from upande_livestock.serverscripts.feeding.manual_feed import manual_feed as _manual_feed
```

and add the branch alongside the existing actions:

```python
	if action == "manual":
		return _manual_feed(
			{
				"herd": d.get("herd"),
				"lines": d.get("lines"),
				"heads": d.get("heads"),
				"portion": d.get("portion"),
				"posting_date": d.get("posting_date"),
				"employee": d.get("employee"),
			}
		)
```

- [ ] **Step 5: Run the tests**

```bash
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_manual_feed
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_mobile
bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_deployability
```

Expected: all OK. `test_deployability` checks every endpoint is guarded and every mobile route resolves.

- [ ] **Step 6: Commit**

```bash
git add upande_livestock/serverscripts/feeding/manual_feed.py upande_livestock/serverscripts/mobile/record_feeding.py upande_livestock/serverscripts/tests/test_manual_feed.py
git commit -m "feat(livestock): feed what was actually mixed, to the animals actually there"
```

---

### Task 11: Full backend sweep

**Files:**
- Test: the whole suite

- [ ] **Step 1: Restart the workers**

gunicorn runs with `--preload`, so every module changed above is stale in the running workers.

```bash
sudo supervisorctl restart frappe15-web:frappe15-frappe-web
```

- [ ] **Step 2: Run every livestock test module**

```bash
cd /home/ubuntu/stive/code/frappe15
for m in backdate backdated_events backdated_guards backdated_drugs backdated_records \
         feed_availability backdated_feeding tuned_bom manual_feed \
         envelope choices animal operations mobile milking feed_day feeding_program \
         livestock_guards livestock_new_guards livestock_stock drug_issuing \
         herd_movement eligibility_alerts livestock_event_link livestock_timings \
         calf_birth book_numbers workspace deployability; do
  echo "=== $m ==="
  bench --site kaitet.local run-tests --module upande_livestock.serverscripts.tests.test_$m 2>&1 | tail -3
done
```

Expected: `OK` for each. `test_each_calf_is_routed_by_its_own_sex` in `test_calf_birth` is a known pre-existing failure (blank `female_calf_herd`/`male_calf_herd` in Livestock Settings) — record it as pre-existing, do not fix it here.

- [ ] **Step 3: Lint**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
ruff check upande_livestock/
```

Expected: clean. Unused `today` imports from Task 6 surface here.

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -A && git commit -m "chore(livestock): tidy imports left by the backdating pass"
```

---

# Phase 3 — Mobile

All work in `~/stive/code/reactnative/upande-livestock` on `kaitet-dairy-frappe16-clean`.

### Task 12: The client layer

**Files:**
- Modify: `src/frappe/animalEvent.ts` — `eventDate` already exists on `CommonInput`; confirm it reaches the wire
- Modify: `src/frappe/feeding.ts` — `posting_date` on `manufactureHerdFeed`
- Create: `src/frappe/manualFeed.ts`
- Create: `src/hooks/useManualFeed.ts`

**Interfaces:**
- Produces:
  - `manualFeed(input: ManualFeedInput): Promise<ManufactureResult>`
  - `ManualFeedInput = { herd: string; lines: { itemCode: string; qty: number }[]; heads: number; postingDate?: string; portion?: number; employee?: string }`
  - `manufactureHerdFeed(herd: string, portion?: number, postingDate?: string)`

- [ ] **Step 1: Add the posting date to feeding**

In `src/frappe/feeding.ts`, widen the action union and the manufacture call:

```ts
const callMethod = async <T = any>(
  action: "info" | "day" | "manufacture" | "issue" | "manual",
  args: Record<string, any>,
): Promise<T> => {
  const client = await getClient();
  const res = await client.post(`/api/method/${RECORD_FEEDING}`, {
    payload: { action, ...args },
  });
  return (res.data?.message ?? res.data) as T;
};

/** Stage A — mix the herd's TMR and issue it, all in one.
 *
 *  `portion` is the fraction of the day this run covers: the farm feeds twice,
 *  so 0.5 twice makes a day. Take it from `getFeedDayStatus` rather than
 *  assuming a half — a herd already fed once is owed the remainder.
 *
 *  `postingDate` backdates the whole run. The server refuses it if the store
 *  could not have covered it that day, and says which day would work. */
export const manufactureHerdFeed = (
  herd: string,
  portion = 1,
  postingDate?: string,
): Promise<ManufactureResult> =>
  callMethod("manufacture", { herd, portion, posting_date: postingDate });
```

- [ ] **Step 2: Write the manual feed client**

Create `src/frappe/manualFeed.ts`:

```ts
import { getClient } from "@/src/services/api";
import type { ManufactureResult } from "./feeding";

const RECORD_FEEDING =
  "upande_livestock.serverscripts.mobile.record_feeding.record_feeding";

export type ManualFeedLine = {
  itemCode: string;
  itemName?: string;
  qty: number;
  uom?: string;
};

export type ManualFeedInput = {
  herd: string;
  lines: ManualFeedLine[];
  /** How many animals were actually at the trough. Not the herd's head count —
   *  that is the number this screen exists to override. */
  heads: number;
  postingDate?: string;
  portion?: number;
  employee?: string;
};

/** Mix and issue a ration the operator tuned by hand.
 *
 *  The server builds a BOM from these lines (reusing one if this exact tune has
 *  been mixed before), runs the same Work Order route the system path uses, and
 *  labels the resulting Feeding event "Manual". */
export const manualFeed = async (
  input: ManualFeedInput,
): Promise<ManufactureResult> => {
  const client = await getClient();
  const res = await client.post(`/api/method/${RECORD_FEEDING}`, {
    payload: {
      action: "manual",
      herd: input.herd,
      heads: input.heads,
      portion: input.portion ?? 1,
      posting_date: input.postingDate,
      employee: input.employee,
      lines: input.lines.map((l) => ({ item_code: l.itemCode, qty: l.qty })),
    },
  });
  const message = res.data?.message ?? res.data;
  if (message?.error) throw new Error(message.error);
  return message as ManufactureResult;
};
```

- [ ] **Step 3: Write the hook**

Create `src/hooks/useManualFeed.ts`:

```ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { manualFeed, type ManualFeedInput } from "@/src/frappe/manualFeed";

export const useManualFeed = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: ManualFeedInput) => manualFeed(input),
    onSuccess: (_data, input) => {
      qc.invalidateQueries({ queryKey: ["feedDayStatus", input.herd] });
      qc.invalidateQueries({ queryKey: ["herdFeedInfo", input.herd] });
    },
  });
};
```

- [ ] **Step 4: Typecheck**

```bash
cd ~/stive/code/reactnative/upande-livestock
npx tsc --noEmit
```

Expected: clean.

- [ ] **Step 5: Commit**

```bash
git add src/frappe/feeding.ts src/frappe/manualFeed.ts src/hooks/useManualFeed.ts
git commit -m "feat(app): a client for hand-tuned feeding and for dated runs"
```

---

### Task 13: The backdate control and page

**Files:**
- Create: `components/BackdateButton.tsx`
- Create: `app/(tabs)/record/backdate/[type].tsx`
- Modify: `app/(tabs)/record/_layout.tsx` — register the route
- Modify: each screen under `app/(tabs)/record/events/` — add the header button

**Interfaces:**
- Consumes: `useCreateAnimalEvent` from `src/hooks/mutations`; `DateTimeField` from `components/DateTimeField`.
- Produces: `<BackdateButton type="Drying Off" />` renders the amber header control and routes to `/record/backdate/<type>`.

- [ ] **Step 1: Write the button**

Create `components/BackdateButton.tsx`:

```tsx
import { router } from "expo-router";
import React from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { useColors } from "@/src/hooks/useColors";
import { RADIUS } from "@/constants/theme";

/** Amber, because this is the control that takes you somewhere the normal
 *  rules do not apply. It should not read as one more neutral header action. */
export const BACKDATE_AMBER_LIGHT = "#B45309";
export const BACKDATE_AMBER_DARK = "#F59E0B";

export function BackdateButton({ type }: { type: string }) {
  const c = useColors();
  const amber = c.isDark ? BACKDATE_AMBER_DARK : BACKDATE_AMBER_LIGHT;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Backdate a ${type} record`}
      onPress={() =>
        router.push({
          pathname: "/(tabs)/record/backdate/[type]",
          params: { type },
        })
      }
      style={({ pressed }) => [
        styles.wrap,
        { borderColor: amber, opacity: pressed ? 0.6 : 1 },
      ]}
    >
      <Ionicons name="time-outline" size={15} color={amber} />
      <Text style={[styles.label, { color: amber }]}>Backdate</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderWidth: 1,
    borderRadius: RADIUS.pill ?? 999,
  },
  label: { fontSize: 12, fontWeight: "600" },
});
```

If `useColors()` exposes no `isDark`, read the scheme with `useColorScheme()` from `react-native` instead.

- [ ] **Step 2: Write the backdating page**

Create `app/(tabs)/record/backdate/[type].tsx`:

```tsx
import { useLocalSearchParams } from "expo-router";
import React, { useMemo, useState } from "react";
import { StyleSheet, Text, View } from "react-native";

import { AnimalPickerButton } from "@/components/AnimalPickerButton";
import { Button } from "@/components/Button";
import { DateField } from "@/components/DateTimeField";
import { Field, Input } from "@/components/Field";
import { Screen } from "@/components/Screen";
import { RADIUS } from "@/constants/theme";
import { useColors } from "@/src/hooks/useColors";
import { useOperator } from "@/src/hooks/useOperator";
import { useCreateAnimalEvent } from "@/src/hooks/mutations";
import { extractFrappeError, todayISO } from "@/src/services/api";
import type { Animal } from "@/types";
import {
  BACKDATE_AMBER_DARK,
  BACKDATE_AMBER_LIGHT,
} from "@/components/BackdateButton";

const WARNING =
  "This is a backdating page. You are not affecting stocks — apply wisely. " +
  "The system will run through afterwards.";

export default function Backdate() {
  const { type } = useLocalSearchParams<{ type: string }>();
  const c = useColors();
  const amber = c.isDark ? BACKDATE_AMBER_DARK : BACKDATE_AMBER_LIGHT;
  const s = useMemo(() => makeStyles(c, amber), [c, amber]);

  const { operator, missingMessage } = useOperator();
  const [selected, setSelected] = useState<Animal[]>([]);
  const [eventDate, setEventDate] = useState<string>(todayISO());
  const [remarks, setRemarks] = useState("");
  const [error, setError] = useState<string | null>(null);
  const record = useCreateAnimalEvent();

  const submit = async () => {
    setError(null);
    if (!selected.length) return setError("Choose at least one animal.");
    if (!operator) return setError(missingMessage ?? "No employee linked to you.");
    try {
      await record.mutateAsync({
        eventType: type as any,
        animal: selected[0].name,
        currentHerd: selected[0].herd ?? "",
        operator,
        eventDate,
        remarks,
      } as any);
    } catch (e) {
      setError(extractFrappeError(e));
    }
  };

  return (
    <Screen title={`Backdate · ${type}`}>
      <View style={s.warning}>
        <Text style={s.warningText}>{WARNING}</Text>
      </View>

      <Field label="Animal">
        <AnimalPickerButton selected={selected} onChange={setSelected} />
      </Field>

      <Field label="Date it happened">
        <DateField value={eventDate} onChange={setEventDate} />
      </Field>

      <Field label="Remarks">
        <Input value={remarks} onChangeText={setRemarks} multiline />
      </Field>

      {error ? <Text style={s.error}>{error}</Text> : null}

      <Button
        title={record.isPending ? "Recording…" : "Record"}
        onPress={submit}
        disabled={record.isPending}
      />
    </Screen>
  );
}

const makeStyles = (c: any, amber: string) =>
  StyleSheet.create({
    warning: {
      borderWidth: 1,
      borderColor: amber,
      borderRadius: RADIUS.md ?? 10,
      padding: 12,
      marginBottom: 16,
    },
    warningText: { color: amber, fontSize: 13, lineHeight: 19 },
    error: { color: c.danger, marginTop: 8, marginBottom: 8 },
  });
```

Check the export name in `components/DateTimeField.tsx` first — if the date-only export is named something other than `DateField`, use that name.

- [ ] **Step 3: Register the route**

In `app/(tabs)/record/_layout.tsx`, add alongside the existing `Stack.Screen` entries:

```tsx
<Stack.Screen name="backdate/[type]" options={{ title: "Backdate" }} />
```

- [ ] **Step 4: Put the button on every event screen**

In each of `dryoff.tsx`, `movement.tsx`, `service.tsx`, `pd.tsx`, `calving.tsx`, `diagnosis.tsx` and `[type].tsx`, import the button and pass it as the screen's header right. Where `Screen` accepts a `headerRight` prop:

```tsx
import { BackdateButton } from "@/components/BackdateButton";

// ...
<Screen title="Drying Off" headerRight={<BackdateButton type="Drying Off" />}>
```

If `Screen` has no such prop, add one:

```tsx
export function Screen({ title, headerRight, children }: ScreenProps) {
  // ... in the header row, after the title:
  {headerRight ?? null}
}
```

- [ ] **Step 5: Typecheck and run**

```bash
cd ~/stive/code/reactnative/upande-livestock
npx tsc --noEmit
npx expo start --clear
```

Open a record screen, confirm the amber Backdate control sits top-right, tap it, confirm the warning text is present and the date picker opens.

- [ ] **Step 6: Commit**

```bash
git add components app/\(tabs\)/record
git commit -m "feat(app): record an event for the day it happened"
```

---

### Task 14: The manual configuration tab

**Files:**
- Modify: `app/(tabs)/record/events/animal-feed.tsx`

- [ ] **Step 1: Add the tab and the warning**

Split the screen into two tabs, `System` and `Manual configuration`. The manual tab carries its own warning, distinct from the backdating one:

```tsx
const MANUAL_WARNING =
  "You are setting the recipe and the head count yourself. This moves real " +
  "stock out of the store — you are accountable for what you enter.";
```

The manual tab seeds its rows from `getHerdFeedInfo(herd).breakdown` and owns them from then on:

```tsx
type TunedRow = { itemCode: string; itemName: string; uom: string; qty: string };

function ManualTab({ herd }: { herd: string }) {
  const c = useColors();
  const s = useMemo(() => makeStyles(c), [c]);
  const amber = c.isDark ? BACKDATE_AMBER_DARK : BACKDATE_AMBER_LIGHT;
  const { data: info } = useHerdFeedInfo(herd);
  const { operator } = useOperator();
  const feed = useManualFeed();

  const [rows, setRows] = useState<TunedRow[] | null>(null);
  const [heads, setHeads] = useState("");
  const [date, setDate] = useState(todayISO());
  const [error, setError] = useState<string | null>(null);

  // Seed once, then leave the operator's edits alone. Re-seeding on every
  // refetch would wipe a half-typed recipe under their fingers.
  useEffect(() => {
    if (!info || rows) return;
    setRows(
      info.breakdown.map((b) => ({
        itemCode: b.itemCode,
        itemName: b.itemName,
        uom: b.uom,
        qty: String(b.perHeadQty),
      })),
    );
    setHeads(String(info.heads ?? ""));
  }, [info, rows]);

  const setQty = (itemCode: string, qty: string) =>
    setRows((prev) =>
      (prev ?? []).map((r) => (r.itemCode === itemCode ? { ...r, qty } : r)),
    );

  const addItem = (item: { name: string; item_name: string; stock_uom: string }) =>
    setRows((prev) =>
      (prev ?? []).some((r) => r.itemCode === item.name)
        ? prev
        : [
            ...(prev ?? []),
            { itemCode: item.name, itemName: item.item_name, uom: item.stock_uom, qty: "0" },
          ],
    );

  const submit = async () => {
    setError(null);
    const count = Number(heads);
    if (!count || count <= 0) return setError("Enter how many animals were fed.");
    const lines = (rows ?? [])
      .map((r) => ({ itemCode: r.itemCode, qty: Number(r.qty) }))
      .filter((l) => l.qty > 0);
    if (!lines.length) return setError("Enter a quantity for at least one ingredient.");
    try {
      await feed.mutateAsync({
        herd,
        lines,
        heads: count,
        postingDate: date,
        employee: operator ?? undefined,
      });
    } catch (e) {
      setError(extractFrappeError(e));
    }
  };

  return (
    <View>
      <View style={[s.warning, { borderColor: amber }]}>
        <Text style={[s.warningText, { color: amber }]}>{MANUAL_WARNING}</Text>
      </View>

      <SectionTitle>Per animal</SectionTitle>
      {(rows ?? []).map((r) => (
        <FieldRow key={r.itemCode} label={`${r.itemName} (${r.uom})`}>
          <Input
            value={r.qty}
            onChangeText={(v) => setQty(r.itemCode, v)}
            keyboardType="decimal-pad"
          />
        </FieldRow>
      ))}

      <FrappeSearchPicker
        doctype="Item"
        label="Add an ingredient"
        fields={["name", "item_name", "stock_uom"]}
        onSelect={addItem}
      />

      <Field label="Number of animals fed">
        <Input value={heads} onChangeText={setHeads} keyboardType="number-pad" />
      </Field>

      <Field label="Date fed">
        <DateField value={date} onChange={setDate} />
      </Field>

      {error ? <Text style={s.error}>{error}</Text> : null}

      <Button
        title={feed.isPending ? "Mixing…" : "Mix & feed"}
        onPress={submit}
        disabled={feed.isPending}
      />
    </View>
  );
}
```

`FrappeSearchPicker`'s prop names may differ — check `components/FrappeSearchPicker.tsx` and match them rather than the shape assumed above.

- [ ] **Step 2: Show the mode on the result**

On the success screen, render `Manual` or `System` from the result's `feed_mode`.

- [ ] **Step 3: Typecheck and exercise it**

```bash
npx tsc --noEmit
npx expo start --clear
```

Feed a herd through the manual tab with a head count different from the herd's, then confirm on the desk that the Stock Entry quantity matches `tuned per-head × heads`.

- [ ] **Step 4: Commit**

```bash
git add app/\(tabs\)/record/events/animal-feed.tsx
git commit -m "feat(app): mix what the store actually had, for the animals that were there"
```

---

### Task 15: Amber marks in the lists

**Files:**
- Modify: `src/frappe/animalEvent.ts` — add `custom_is_backdated` and `custom_feed_mode` to the list field sets
- Modify: `components/Timeline.tsx` and the records list

- [ ] **Step 1: Fetch the fields**

Add `"custom_is_backdated"` to every event list field array in `src/frappe/animalEvent.ts`, and `"custom_feed_mode"` where Feeding events are listed.

- [ ] **Step 2: Render the pill**

Where a timeline row is rendered, add:

```tsx
{row.custom_is_backdated ? <Pill label="Backdated" tone="amber" /> : null}
{row.custom_feed_mode === "Manual" ? <Pill label="Manual" tone="amber" /> : null}
```

If `Pill` has no `amber` tone, add one using `BACKDATE_AMBER_LIGHT` / `BACKDATE_AMBER_DARK`.

- [ ] **Step 3: Typecheck, then commit**

```bash
npx tsc --noEmit
git add src components
git commit -m "feat(app): a backdated row says so"
```

---

# Phase 4 — Desk

### Task 16: The Custom HTML Block

**Files:**
- Modify: `upande_livestock/fixtures/custom_html_block.json`

- [ ] **Step 1: Add the backdate control to each event form**

In the `Livestock Operations` block, add to each event form's header an amber `Backdate` button that reveals a date input and sets `payload.event_date`, plus the warning line:

```js
var BACKDATE_WARNING =
  "This is a backdating page. You are not affecting stocks — apply wisely. " +
  "The system will run through afterwards.";
```

Keep the existing `keepKeysInFields` keystroke guard on every new input — a new text input without it re-opens the desk search-bar bug.

- [ ] **Step 2: Add the manual configuration tab to the feed section**

A second tab beside the current feed tab, with the accountability warning, an editable row per BOM line, an item picker, a head-count input, a date input, and a submit that posts to:

```
upande_livestock.serverscripts.feeding.manual_feed.manual_feed
```

- [ ] **Step 3: Show the mode and the mark**

In the events list the block renders, add an amber `Backdated` badge when `custom_is_backdated` and a `Manual` badge when `custom_feed_mode === "Manual"`.

- [ ] **Step 4: Reload and test in a browser**

```bash
cd /home/ubuntu/stive/code/frappe15
bench --site kaitet.local migrate
sudo supervisorctl restart frappe15-web:frappe15-frappe-web
```

Open the Livestock Operations workspace as **Dickson Opicho** (not Administrator — role access is the thing being checked). Type into every new text input and confirm no keystroke reaches the desk search bar. Record a backdated event and confirm the amber badge appears.

- [ ] **Step 5: Commit**

```bash
cd /home/ubuntu/stive/code/frappe15/apps/upande_livestock
git add upande_livestock/fixtures/custom_html_block.json
git commit -m "feat(livestock): backdating and manual feeding on the desk too"
```

---

## Done when

- Every module in Task 11's sweep reports `OK` (with the one known pre-existing `test_calf_birth` failure recorded, not fixed).
- `ruff check upande_livestock/` is clean; `npx tsc --noEmit` is clean.
- A backdated deworming on the handset creates the event, keeps the drug rows, sets `custom_unposted_drugs`, and leaves `Bin` unchanged.
- A manual feed for a head count differing from the herd's posts a Stock Entry of `tuned per-head × heads`, on the chosen date, labelled `Manual`.
- A feed run dated before the stock existed is refused with the earliest workable date and leaves no Work Order behind.
- Turning `custom_backdating_open` off makes a backdated write refuse with "Backdating is closed".
