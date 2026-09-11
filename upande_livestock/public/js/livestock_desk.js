// Ensure the "Upande Livestock" card appears on the v16 desk grid.
//
// The desk grid (frappe/desk/page/desktop) renders from a per-user layout that
// pre-dates this app's Desktop Icon and filters it out, so the card never
// paints even though it's in frappe.boot.desktop_icons. Rather than patch
// Frappe core, this clones the rendered "Upande SCP" card, retargets it at the
// livestock workspace, and inserts it into the grid — repeatedly, so it
// survives re-renders/navigation.
(function () {
	var LABEL = "Upande Livestock";
	var LOGO = "/assets/upande_livestock/images/upande_logo.png";
	var ROUTE = "/desk/upande-livestock?sidebar=Upande%20Livestock";

	function permitted() {
		// frappe.boot.desktop_icons is built server-side by get_desktop_icons,
		// which applies the workspace roles + Workspace Sidebar is_item_allowed
		// permission checks. Only inject if this user is permitted (i.e. the
		// server put the icon in their boot) — so we respect roles, not bypass them.
		var icons = (window.frappe && frappe.boot && frappe.boot.desktop_icons) || [];
		return icons.some(function (d) {
			return d && d.label === LABEL && d.hidden != 1;
		});
	}

	function inject() {
		try {
			if (!permitted()) return; // user not allowed -> never inject
			// already present?
			if (document.querySelector('.desktop-icon[data-id="' + LABEL + '"]')) return;
			// find a rendered top-level card to clone (SCP, else the first one)
			var seed =
				document.querySelector('.icons > .desktop-icon[data-id="Upande SCP"]') ||
				document.querySelector('.icons-container > .icons > .desktop-icon') ||
				document.querySelector('.desktop-icon');
			if (!seed || !seed.parentElement) return;

			var clone = seed.cloneNode(true);
			clone.setAttribute("data-id", LABEL);
			clone.setAttribute("data-logo", LOGO);
			clone.setAttribute("data-icon", "agriculture");
			clone.setAttribute("href", ROUTE);
			clone.removeAttribute("target");

			var img = clone.querySelector("img.app-icon");
			if (img) { img.setAttribute("src", LOGO); img.setAttribute("alt", LABEL); }
			var title = clone.querySelector(".icon-title");
			if (title) { title.textContent = LABEL; title.setAttribute("data-original-title", LABEL); }
			// drop any nested folder contents copied from the seed
			var folder = clone.querySelector(".icon-container.folder-icon, .icons-container");
			if (folder) folder.remove();

			// navigate on click (cloned node has no JS listeners)
			clone.addEventListener("click", function (e) {
				e.preventDefault();
				window.location.href = ROUTE;
			});

			seed.parentElement.appendChild(clone);
			console.log("[ULD] injected Upande Livestock card into the desk grid");
		} catch (e) {
			console.log("[ULD] inject failed:", e);
		}
	}

	function start() {
		// try a few times as the grid renders / re-renders
		var n = 0;
		var t = setInterval(function () {
			inject();
			if (++n >= 12) clearInterval(t);
		}, 700);
		// and re-inject on SPA route changes into the desktop page
		if (window.frappe && frappe.router && frappe.router.on) {
			frappe.router.on("change", function () { setTimeout(inject, 600); });
		}
	}

	if (window.frappe && frappe.after_ajax) frappe.after_ajax(start);
	else window.addEventListener("load", start);
})();

(function () {
	// The cover that holds the desk while the livestock app loads.
	//
	// Frappe already does this for its own navigations; leaving the desk for
	// /livestock_app is a full document load, and without a cover the desk sits
	// there looking clickable for as long as the bundle takes. The app shell
	// raises the same cover on its own side, so the two page loads read as one
	// continuous transition rather than two separate blank moments.
	//
	// Everything is inline — no class, no stylesheet — because this runs as the
	// document is being torn down, and a rule in a stylesheet the browser is
	// discarding paints nothing.
	var ID = "lv-splash";

	window.__livestockSplash = function () {
		if (document.getElementById(ID)) return;
		var el = document.createElement("div");
		el.id = ID;
		el.setAttribute(
			"style",
			"position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;" +
				"justify-content:center;background:#ffffff"
		);
		var img = document.createElement("img");
		img.src = "/assets/upande_livestock/images/upande_mark.svg";
		img.alt = "Upande Livestock";
		img.setAttribute(
			"style",
"width:106px;height:auto;display:block"
		);
		el.appendChild(img);
		document.body.appendChild(el);
	};
})();

// Same-tab navigation for /livestock_app.
//
// Frappe hard-codes target="_blank" on every URL-type workspace-sidebar item
// (sidebar_item.html), so a sidebar link to the React app opens a new tab.
// Intercept those clicks and navigate in the current tab instead. Capture
// phase, so this wins before Frappe's own handler. Scoped to /livestock_app —
// every other link on the desk is left alone.
//
// The Livestock Dashboard's own launcher link is not a plain light-DOM
// anchor: Custom HTML Blocks render inside an *open* shadow root
// (frappe.create_shadow_element -> attachShadow({mode:"open"})). A listener
// on `document` still gets `e.target` retargeted to the shadow host for
// events that originate inside that shadow tree, so `e.target.closest(...)`
// never sees the anchor. `e.composedPath()` is not retargeted — it lists the
// real path, shadow DOM or not — so walk that instead of `e.target`.
(function () {
	// Paint the cover, then navigate on the next frame — assign location.href in
	// the same tick and the browser never paints what was just appended.
	function leave(href) {
		try { window.__livestockSplash(); } catch (_) {}
		requestAnimationFrame(function () {
			setTimeout(function () { window.location.href = href; }, 60);
		});
	}

	document.addEventListener(
		"click",
		function (e) {
			var path = typeof e.composedPath === "function" ? e.composedPath() : [e.target];
			var a = null;
			for (var i = 0; i < path.length; i++) {
				var el = path[i];
				if (el && el.tagName === "A" && el.hasAttribute && el.hasAttribute("href")) {
					a = el;
					break;
				}
			}
			if (!a) return;
			var href = a.getAttribute("href") || "";
			if (href.indexOf("/livestock_app") === 0) {
				e.preventDefault();
				e.stopPropagation();
				leave(href);
			}
		},
		true
	);
})();
