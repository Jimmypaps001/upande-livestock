# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""Serve the React livestock frontend at /livestock_app.

The bundle itself is built by ``frontend/`` (Vite) into
``upande_livestock/public/dist``; this page is the shell Frappe renders around
it. It does three things and nothing else:

* resolve the hashed entry filenames from Vite's manifest, so a new build busts
  the browser cache by URL rather than by a query string. A ``?v=`` suffix on
  the entry script would create two distinct module URLs — chunks import the
  entry by its bare hashed name while the <script> tag would carry the query —
  and the browser would instantiate React twice, crashing hooks;
* inline who is looking at it (name, roles, CSRF token) so the app does not pay
  a round-trip before its first paint;
* refuse Guest.

No data is prefetched here. Every feeding endpoint is a POST behind a
permission check, and the page's first useful question ("which herds have a
ration?") depends on the herd the operator picks, so there is nothing worth
inlining yet.
"""

import json
import os

import frappe

no_cache = 1


def _read_manifest():
	"""Vite's manifest, or an empty dict when the app has not been built."""
	manifest_path = os.path.join(
		frappe.get_app_path("upande_livestock"), "public", "dist", ".vite", "manifest.json"
	)
	if not os.path.exists(manifest_path):
		return {}
	try:
		with open(manifest_path, encoding="utf-8") as fh:
			return json.load(fh)
	except (OSError, ValueError):
		return {}


def get_context(context):
	if frappe.session.user == "Guest":
		raise frappe.PermissionError(frappe._("Login required"))

	context.no_cache = 1
	context.show_sidebar = 0

	manifest = _read_manifest()
	entry = manifest.get("index.html") or manifest.get("src/main.tsx") or {}
	js_file = entry.get("file") or "livestock.js"
	# `cssCodeSplit: false` emits one stylesheet the entry does not list under
	# its own `css` key — it lands under "style.css" instead, so look there
	# before falling back, or the page ships a <link> to a file that is not
	# there and renders unstyled.
	css_files = entry.get("css") or [
		manifest.get("style.css", {}).get("file") or "livestock.css"
	]

	context.livestock_js = "/assets/upande_livestock/dist/" + js_file
	context.livestock_css = "/assets/upande_livestock/dist/" + css_files[0]

	user_id = frappe.session.user
	user_doc = (
		frappe.db.get_value("User", user_id, ["full_name", "user_image"], as_dict=True) or {}
	)
	roles = list(frappe.get_roles(user_id) or [])
	# Frappe leaves 'Administrator' out of get_roles() for the Administrator
	# user — a special case that bypasses role checks — so surface it
	# explicitly, or a frontend role gate reads Administrator as role-less.
	if user_id == "Administrator" and "Administrator" not in roles:
		roles.append("Administrator")

	csrf_token = frappe.sessions.get_csrf_token()
	context.bootstrap_json = json.dumps(
		{
			"user": user_id,
			"full_name": user_doc.get("full_name") or user_id,
			"user_image": user_doc.get("user_image") or "",
			"site_name": frappe.local.site,
			"roles": roles,
			"csrf_token": csrf_token,
		}
	)
	context.csrf_token = csrf_token
	return context
