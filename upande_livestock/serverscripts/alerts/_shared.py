"""The alert kinds, named once — and what each one is about.

`raise_alerts` and `tasks` write them, `open_alerts` counts them and
`common/notifications` decides who hears about them, so none of those owns the
list. A kind added in one place and not the other is a silently uncounted alert.

CATEGORY_OF_KIND is the notifications page's taxonomy. It lives here, beside the
kinds, rather than on a column of its own on `Notification Log`: the category is
a property of the KIND, so copying it onto every delivered row would be a second
place for it to be wrong. `Notification Log.type` could not have carried it in
any case — that field is a fixed Frappe enum (Alert / Share / Assignment /
Mention / Energy Point) and "movement" is not one of its values.
"""

#: Movement and culling — an animal is in the wrong place, or has outstayed
#: its window.
MOVEMENT_KINDS = ("Bull Cull Due", "Move Due", "Move Overdue")

#: The breeding calendar — something is due, overdue, or has stalled.
BREEDING_KINDS = ("Cow Open Too Long", "Calving Due", "Pregnancy Check Overdue")

KINDS = MOVEMENT_KINDS + BREEDING_KINDS

CATEGORIES = ("movement", "breeding")

CATEGORY_OF_KIND = {
	**{k: "movement" for k in MOVEMENT_KINDS},
	**{k: "breeding" for k in BREEDING_KINDS},
}


def kinds_in_category(category):
	"""The kinds filed under `category`, or () for an unknown one.

	Returning empty rather than raising: a stale category in a bookmarked URL
	should show an empty list, not a 500.
	"""
	return tuple(k for k in KINDS if CATEGORY_OF_KIND.get(k) == category)
