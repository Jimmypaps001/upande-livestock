# Livestock notice icons

Real icons, because emoji are not iconography. An emoji is a font glyph: it
renders as somebody else's drawing at somebody else's weight, differs on every
platform, reads as a cartoon in a document people sign things from, and cannot
be given the colour of the thing it is marking.

These are 24×24 line icons in the same shape language as the app's own
(lucide-style: 2px round strokes, `currentColor`), so a notice in the desk and a
notice in the React app look like they came from one farm.

`currentColor` is the point: the icon takes the colour of the text it sits
beside, so a warning in red text carries a red icon without a second asset.

Used from Python via `serverscripts/common/notice.py: icon()`, which is the only
place the path is written down.
