"""Pure herd <-> paddock logic (stdlib only): who stands where, whether the paddocks are
enough to rotate, and where a herd's feed should go. The data layer feeds it rows."""

import json
import math

# A readable categorical palette; herds take colours in sorted-name order so a herd keeps its
# colour as long as the set of herds does not change.
PALETTE = ["#2f7d4f", "#d08a1e", "#3b6fb6", "#b5483a", "#7a57a6", "#2a9d9a", "#8a8f2a", "#c2547f",
           "#5b7083", "#a8672e"]
RESTING = "#9aa59a"


def herd_colours(herds):
	return {h: PALETTE[i % len(PALETTE)] for i, h in enumerate(sorted(set(herds)))}


def rotation_check(paddocks, grazing_herds, graze_days, rest_days):
	"""Are there enough paddocks for the grazing herds to rotate?

	A herd grazes one paddock for `graze_days` and each paddock then needs `rest_days` of regrowth,
	so a herd cycles through 1 + ceil(rest / graze) paddocks. With p paddocks and h herds each paddock
	rests (p / h - 1) * graze_days between grazings.
	"""
	graze = max(1, int(graze_days or 0))
	rest = max(0, int(rest_days or 0))
	per_need = 1 + math.ceil(rest / graze)
	if not grazing_herds:
		return {"paddocks": paddocks, "grazing_herds": 0, "per_herd": None, "needed_per_herd": per_need,
		        "needed_total": 0, "shortfall": 0, "rest_days": None, "target_rest_days": rest,
		        "graze_days": graze, "enough": True, "message": "No herds graze on paddocks."}
	per_herd = round(paddocks / grazing_herds, 2)
	needed = per_need * grazing_herds
	rest_got = max(0.0, (paddocks / grazing_herds - 1) * graze)
	enough = paddocks >= needed
	if enough:
		message = (f"{paddocks} paddocks for {grazing_herds} grazing herds ({per_herd} each): enough to "
		           f"rest each paddock {rest} days between {graze}-day grazings.")
	else:
		message = (f"{paddocks} paddocks for {grazing_herds} grazing herds is {per_herd} per herd: each "
		           f"paddock rests about {rest_got:.1f} days between {graze}-day grazings, against {rest} "
		           f"wanted. Rotation needs {per_need} per herd, {needed} in all ({needed - paddocks} more).")
	return {"paddocks": paddocks, "grazing_herds": grazing_herds, "per_herd": per_herd,
	        "needed_per_herd": per_need, "needed_total": needed, "shortfall": max(0, needed - paddocks),
	        "rest_days": round(rest_got, 1), "target_rest_days": rest, "graze_days": graze,
	        "enough": enough, "message": message}


def place_herds(places, herds):
	"""Each place with the herds standing on it. `places`: [{warehouse, kind, area_ha, geojson}],
	`herds`: [{herd, paddock, heads}]."""
	out = []
	for pl in places:
		here = [{"herd": h["herd"], "heads": h.get("heads") or 0} for h in herds if h.get("paddock") == pl["warehouse"]]
		heads = sum(h["heads"] for h in here)
		ha = pl.get("area_ha")
		out.append({**pl, "herds": here, "heads": heads, "state": "occupied" if here else "resting",
		            "head_per_ha": round(heads / ha, 1) if here and ha else None})
	return out


def unplaced(places, herds):
	known = {pl["warehouse"] for pl in places}
	return [h["herd"] for h in herds if h.get("paddock") not in known]


def feed_destination(paddock, store):
	"""Where a herd's mixed feed ends up: its paddock when it has one, else the store it was made in."""
	return paddock or store


def needs_transfer(paddock, store):
	return bool(paddock) and paddock != store


def _ring_area_m2(ring):
	if len(ring) < 4:
		return 0.0
	lat0 = sum(p[1] for p in ring) / len(ring)
	kx = 111320.0 * math.cos(math.radians(lat0))
	ky = 110574.0
	pts = [(p[0] * kx, p[1] * ky) for p in ring]
	s = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:]))
	return abs(s) / 2.0


def area_ha(geojson):
	"""Hectares from a FeatureCollection: its `area_ha` property, else the polygon's own area."""
	if isinstance(geojson, str):
		try:
			geojson = json.loads(geojson)
		except ValueError:
			return None
	total = 0.0
	found = False
	for f in (geojson or {}).get("features") or []:
		props = f.get("properties") or {}
		if props.get("area_ha"):
			return float(props["area_ha"])
		geom = f.get("geometry") or {}
		if geom.get("type") == "Polygon":
			polys = [geom["coordinates"]]
		elif geom.get("type") == "MultiPolygon":
			polys = geom["coordinates"]
		else:
			continue
		for poly in polys:
			if poly:
				found = True
				total += _ring_area_m2(poly[0]) - sum(_ring_area_m2(h) for h in poly[1:])
	return round(total / 10000.0, 4) if found else None
