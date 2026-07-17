// Debug helper: on every desk page, report whether the "Upande Livestock"
// desk grid card is (a) present in the boot data and (b) actually rendered
// into the DOM. Logs to the browser console so we can tell a data problem
// from a render problem. Safe to remove once the grid card is confirmed.
(function () {
	function check() {
		try {
			var icons = (window.frappe && frappe.boot && frappe.boot.desktop_icons) || [];
			var inBoot = icons.some(function (d) {
				return d && d.label === "Upande Livestock";
			});

			// Scan the rendered DOM for any node that references the card.
			var candidates = Array.prototype.slice.call(
				document.querySelectorAll(
					"[data-name],[data-app-route],.app-item,.desktop-icon,.dropdown-menu-item,.app-logo,.workspace-icon,a,div"
				)
			);
			var node = candidates.find(function (n) {
				var hay =
					(n.getAttribute && (n.getAttribute("data-name") || "") + " " + (n.getAttribute("data-app-route") || "")) +
					" " +
					(n.textContent || "");
				return /upande\s*livestock/i.test(hay);
			});

			console.log(
				"%c[Upande Livestock desk-icon]",
				"color:#228883;font-weight:bold",
				"| in boot.desktop_icons:",
				inBoot,
				"| RENDERED in DOM:",
				!!node,
				node || "(no matching node)"
			);
		} catch (e) {
			console.log("[Upande Livestock desk-icon] check failed:", e);
		}
	}

	if (window.frappe && frappe.after_ajax) {
		frappe.after_ajax(function () {
			setTimeout(check, 1500);
		});
	} else {
		window.addEventListener("load", function () {
			setTimeout(check, 1500);
		});
	}
})();
