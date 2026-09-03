app_name = "upande_livestock"
app_title = "Upande Livestock"
app_publisher = "Upande"
app_description = "Livestock management on ERPNext"
app_email = "dev@upande.com"
app_license = "mit"

# Logo shown on the desk app/workspace grid card.
app_logo_url = "/assets/upande_livestock/images/upande_logo.png"

# Also surface the app on the /apps launcher screen.
add_to_apps_screen = [
	{
		"name": "upande_livestock",
		"logo": "/assets/upande_livestock/images/upande_logo.png",
		"title": "Upande Livestock",
		"route": "/app/upande-livestock",
	}
]

# Permanent fix: on login, drop a stale per-user desktop grid layout that is
# missing a permitted icon, so the grid rebuilds natively from the boot (which
# includes newly-added app icons like Upande Livestock). See heal.py.
on_session_creation = ["upande_livestock.serverscripts.common.heal.clear_stale_desktop_layout"]

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "upande_livestock",
# 		"logo": "/assets/upande_livestock/logo.png",
# 		"title": "Upande Livestock",
# 		"route": "/upande_livestock",
# 		"has_permission": "upande_livestock.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# Poppins @font-face must live at document level: Custom HTML Blocks render in a
# Shadow DOM, where in-block @font-face is ignored. See livestock_fonts.css.
app_include_css = "/assets/upande_livestock/css/livestock_fonts.css"
# Debug: logs whether the "Upande Livestock" desk grid card is in boot + rendered.
app_include_js = "/assets/upande_livestock/js/livestock_desk.js?v=6"

# include js, css files in header of web template
# web_include_css = "/assets/upande_livestock/css/upande_livestock.css"
# web_include_js = "/assets/upande_livestock/js/upande_livestock.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "upande_livestock/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views — form scripts (ex Client Scripts, now versioned code)
doctype_js = {
	"Livestock Event": "public/js/livestock_event.js",
}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "upande_livestock/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "upande_livestock.utils.jinja_methods",
# 	"filters": "upande_livestock.utils.jinja_filters"
# }

# Fixtures
# --------
# Custom fields added to the standard Herds doctype for dairy KPI grouping and
# per-herd accounting overrides. Exported so they deploy to every site via migrate.
fixtures = [
	{
		# Only Stock Entry (an ERPNext core doctype) still carries livestock custom
		# fields — everything on our own doctypes (Herds, Livestock Event, Livestock
		# Settings) was folded into the DocType JSONs natively. The milk fields are
		# grouped in a "Milking" section that shows only for Milking stock entries;
		# the trailing section break keeps the following (non-livestock) fields
		# visible on other stock-entry types.
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Stock Entry-custom_milking_details_section",
					"Stock Entry-custom_milking_time",
					"Stock Entry-custom_cows_milked",
					"Stock Entry-custom_milking_end_section",
				],
			]
		],
	},
	# NOTE: Client Scripts and Server Scripts are no longer shipped as fixtures.
	# They now live in the codebase: form scripts under public/js/ (doctype_js),
	# doc-event logic in the doctype controllers (livestock_event / animal /
	# milk_recording), and API/scheduler logic in api/*.py and tasks.py.
	{
		"dt": "Custom HTML Block",
		"filters": [["name", "in", ["Livestock Dashboard", "Livestock Operations"]]],
	},
	{
		# Reference master data, not demo scaffolding: these are the dairy diseases a
		# Kenyan herd is actually managed against, and Livestock Diagnosis /
		# Livestock Health Case both link to them. Shipping them means a fresh site
		# has something to diagnose against instead of an empty dropdown.
		#
		# The drug store and its opening stock are deliberately NOT fixtures — they
		# post stock movements, so they live in demo/seed_test_stock.py and are run
		# by hand on test sites only.
		"dt": "Livestock Disease",
	},
	{
		# Desktop Icon = the card on the v16 desk app grid. Without it the
		# workspace exists and is reachable by URL but never shows on the grid.
		"dt": "Desktop Icon",
		"filters": [["name", "in", ["Upande Livestock"]]],
	},
]

# Installation
# ------------

# before_install = "upande_livestock.install.before_install"
after_install = "upande_livestock.install.after_install"

# Migration
# ---------
# Ensure the "Milking" Stock Entry Type exists before any migrate-time save of
# Livestock Settings (whose custom_milking_stock_entry_type defaults to
# "Milking"), and again afterwards as a safety net on redeploys.
#
# ensure_livestock_event_types runs only after_migrate: on a fresh site the
# Livestock Event Type table does not exist until model sync, so running it
# before_migrate would be a silent no-op (guarded by table_exists) anyway.
before_migrate = ["upande_livestock.install.ensure_milking_stock_entry_type"]
after_migrate = [
	"upande_livestock.install.ensure_milking_stock_entry_type",
	"upande_livestock.install.ensure_livestock_event_types",
	"upande_livestock.install.ensure_livestock_timing_defaults",
]

# Uninstallation
# ------------

# before_uninstall = "upande_livestock.uninstall.before_uninstall"
# after_uninstall = "upande_livestock.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "upande_livestock.utils.before_app_install"
# after_app_install = "upande_livestock.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "upande_livestock.utils.before_app_uninstall"
# after_app_uninstall = "upande_livestock.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "upande_livestock.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	# Ex "CHECK OVERDUE PREGNANCY DIAGNOSES" Server Script (Daily).
	"daily": [
		"upande_livestock.tasks.check_overdue_pregnancy_diagnoses",
		# Captures what should be said about herd movement. It records alerts; it
		# does not deliver them — that channel is still to be decided.
		"upande_livestock.herd_alerts.raise_alerts",
	],
}

# Testing
# -------

# before_tests = "upande_livestock.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "upande_livestock.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "upande_livestock.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["upande_livestock.utils.before_request"]
# after_request = ["upande_livestock.utils.after_request"]

# Job Events
# ----------
# before_job = ["upande_livestock.utils.before_job"]
# after_job = ["upande_livestock.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"upande_livestock.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []
