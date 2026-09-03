"""The alert kinds, named once.

`raise_alerts` writes them and `open_alerts` counts them, so neither owns the
list. A kind added in one place and not the other is a silently uncounted alert.
"""

KINDS = ("Bull Cull Due", "Move Due", "Move Overdue", "Cow Open Too Long")
