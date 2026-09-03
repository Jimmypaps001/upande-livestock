# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Versioning for the bundles: how the phone skips a payload it already has.

A bundle exists to collapse many round-trips into one. That saving is undone if
the phone re-downloads the same payload every time it opens a screen, so each
bundle carries a `version` — a digest of the rows behind it. The client sends
back the version it holds; if nothing has changed since, it gets
`{"unchanged": True}` and nothing else.

The digest is computed from the `modified` timestamps and row counts of the
doctypes a bundle reads, not from the rendered payload, so it can be answered
without building the payload at all. A count is included because a deletion
lowers the count while leaving MAX(modified) untouched.

Deliberately not Redis-backed. upande_scp caches its bundles because a farm
bundle costs 176 queries to build; these cost a handful, and a cache would add
an invalidation contract to get wrong for no measurable gain. If a bundle here
ever grows that expensive, cache it then.
"""

import hashlib

import frappe


def digest(doctypes: list[str]) -> str:
	"""A short digest of the current state of `doctypes`.

	Changes whenever a row in any of them is added, edited or removed.
	"""
	parts = []
	for doctype in sorted(doctypes):
		if not frappe.db.table_exists(doctype):
			parts.append(f"{doctype}:absent")
			continue
		row = frappe.db.sql(
			f"SELECT COUNT(*), IFNULL(MAX(modified), '') FROM `tab{doctype}`"
		)[0]
		parts.append(f"{doctype}:{row[0]}:{row[1]}")
	return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def unchanged(version, current: str) -> bool:
	"""Whether the client already holds this exact payload."""
	return bool(version) and str(version) == current
