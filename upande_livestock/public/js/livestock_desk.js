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
