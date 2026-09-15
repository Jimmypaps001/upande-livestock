# Copyright (c) 2026, Upande and contributors
# For license information, please see license.txt

"""No emoji anywhere in what this app says to people.

AN EMOJI IS NOT AN ICON. It is a font glyph: it renders as somebody else's
drawing at somebody else's weight, differs on every platform, reads as a cartoon
on a document people sign things from, and cannot take the colour of the thing
it is marking. This app had a cow's face on a pregnancy refusal and a siren on
an overdue check.

They were doing real work, so they were replaced rather than deleted — see
`public/icons/` and `serverscripts/common/notice.py`. This test is what stops
them coming back, one convenient paste at a time.
"""

import os
import re
import unittest

import frappe

#: The ranges that are pictures, built from code points rather than written out
#: as characters — a test that hunts for emoji must not carry specimens.
#:
#: Deliberately NOT every non-ASCII character: this codebase uses an en-dash and
#: curly quotes on purpose, an arrow is how a herd move is written, and a degree
#: sign is a temperature.
PICTURE_RANGES = (
	(0x1F000, 0x1FAFF),   # pictographs, transport, supplemental symbols
	(0x2600, 0x27BF),     # miscellaneous symbols and dingbats
	(0x2B00, 0x2BFF),     # the tick and cross family
	(0xFE0F, 0xFE0F),     # the variation selector that makes a glyph a picture
	(0x1F1E6, 0x1F1FF),   # regional indicators (flags)
)

EMOJI = re.compile(
	"[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in PICTURE_RANGES) + "]"
)

#: Where the app's own source lives. Built assets are excluded: they are the
#: compiled form of files this test already reads.
SKIP_DIRS = {"node_modules", "dist", "__pycache__", ".git", ".vite"}
READ = (".py", ".js", ".ts", ".tsx", ".json", ".html", ".md", ".css")


def _roots():
	"""Everything this app ships that a person can end up reading.

	The React frontend is a sibling of the Python package, not inside it, and it
	is where most of what a herdsman actually reads is written — a guard that
	only walked the Python would have let the next one straight in.
	"""
	app = frappe.get_app_path("upande_livestock")
	return [app, os.path.join(os.path.dirname(app), "frontend", "src")]


def _sources(root):
	for base, dirs, files in os.walk(root):
		dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
		for name in files:
			if name.endswith(READ):
				yield os.path.join(base, name)


class TestNothingSpeaksInEmoji(unittest.TestCase):
	def test_no_source_file_carries_one(self):
		roots = _roots()
		base_dir = os.path.dirname(frappe.get_app_path("upande_livestock"))
		offenders = []
		for path in [p for root in roots for p in _sources(root)]:
			try:
				text = open(path, encoding="utf-8").read()
			except (OSError, UnicodeDecodeError):
				continue
			for number, line in enumerate(text.splitlines(), start=1):
				found = EMOJI.findall(line)
				if found:
					offenders.append(
						"{0}:{1}: {2}".format(
							os.path.relpath(path, base_dir), number, "".join(found)
						)
					)
		self.assertEqual(
			offenders,
			[],
			"Emoji are not icons. Use serverscripts/common/notice.py and "
			"public/icons/ instead:\n" + "\n".join(offenders),
		)

	def test_the_icons_the_helper_offers_all_exist(self):
		"""A heading naming an icon nobody drew renders a broken image."""
		from upande_livestock.serverscripts.common.notice import ICONS

		icons = os.path.join(frappe.get_app_path("upande_livestock"), "public", "icons")
		for name in ICONS:
			self.assertTrue(
				os.path.exists(os.path.join(icons, name + ".svg")),
				"public/icons/{0}.svg is named in notice.ICONS and does not exist".format(name),
			)

	def test_an_icon_nobody_drew_is_refused_rather_than_rendered_broken(self):
		from upande_livestock.serverscripts.common.notice import icon

		with self.assertRaises(frappe.ValidationError):
			icon("tractor")
