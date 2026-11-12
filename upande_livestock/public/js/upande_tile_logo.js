// Replays an app tile's logo on hover/focus, for the Upande apps whose mark is a pure-CSS play-once SVG.
// A copy of upande_production's public/js/upande_tile_logo.js, for the Livestock tile (apps do not
// import each other's assets).
//
// The desk draws app tiles as <img class="app-icon"> inside <a class="desktop-icon">. The SVG animates
// itself once when it loads and comes to rest as the plain Upande mark (see
// scripts/build_livestock_logo.py: livestock_logo.svg). An <img> cannot be replayed, so on
// mouseenter/focusin the SVG text (fetched once) is handed to the same <img> as a fresh Blob URL, which
// restarts the CSS. The <img> is never swapped for inline SVG, so the tile keeps its size and its HD
// rendering (a vector drawn by the browser at the screen's own resolution, at any zoom). Old blob URLs
// are revoked. With reduced motion nothing is touched.
//
// On a site that also runs upande_production, its own copy of this script is loaded too. Each copy
// keeps its own guard and wires only its own app's tiles (production's matches its three apps, this
// one /assets/upande_livestock/), and a tile already wired (data-logo-src) is never wired again, so
// the two never handle one tile twice and neither stops the other from running.
(function () {
	var TILE = /^\/assets\/upande_livestock\/.*_logo\.svg(\?.*)?$/;

	if (window.__upandeTileLogoLivestock) return;
	window.__upandeTileLogoLivestock = true;
	if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
	if (!window.fetch || !window.URL || !URL.createObjectURL || !window.Blob) return;

	var cache = {}; // src -> Promise<text>

	function load(src) {
		if (!cache[src]) {
			cache[src] = fetch(src, { credentials: "same-origin" }).then(function (r) {
				if (!r.ok) throw new Error(r.status);
				return r.text();
			});
			cache[src].catch(function () {
				delete cache[src];
			});
		}
		return cache[src];
	}

	function path(src) {
		try {
			return new URL(src, window.location.href).pathname;
		} catch (_) {
			return "";
		}
	}

	function replay(img) {
		var src = img.getAttribute("data-logo-src");
		if (!src) return;
		load(src)
			.then(function (text) {
				if (!img.isConnected) return;
				var old = img.getAttribute("data-logo-play");
				var url = URL.createObjectURL(new Blob([text], { type: "image/svg+xml" }));
				img.setAttribute("data-logo-play", url);
				img.src = url;
				if (old) URL.revokeObjectURL(old);
			})
			.catch(function () {
				// keep the resting mark
			});
	}

	function wire(img) {
		if (img.getAttribute("data-logo-src")) return;
		var src = img.getAttribute("src") || "";
		var p = path(src);
		if (!TILE.test(p)) return;
		img.setAttribute("data-logo-src", p);
		img.setAttribute("data-logo-animated", "1");
		var tile = img.closest(".desktop-icon") || img.parentElement;
		var on = function () {
			replay(img);
		};
		tile.addEventListener("mouseenter", on);
		tile.addEventListener("focusin", on);
		load(p).catch(function () {});
	}

	function scan() {
		var imgs = document.querySelectorAll(".desktop-icon img.app-icon");
		for (var i = 0; i < imgs.length; i++) wire(imgs[i]);
	}

	var queued = false;
	function onMutate() {
		if (queued) return;
		queued = true;
		requestAnimationFrame(function () {
			queued = false;
			scan();
		});
	}
	function start() {
		scan();
		new MutationObserver(onMutate).observe(document.body, { childList: true, subtree: true });
	}
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
	else start();
})();
