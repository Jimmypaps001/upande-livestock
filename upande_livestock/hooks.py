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
# app_include_css = "/assets/upande_livestock/css/upande_livestock.css"
# Debug: logs whether the "Upande Livestock" desk grid card is in boot + rendered.
app_include_js = "/assets/upande_livestock/js/livestock_desk.js?v=4"

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

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
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
		"dt": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Herds-custom_is_milking",
					"Herds-custom_is_calf_rearing",
					"Herds-custom_production_group",
					"Herds-custom_is_dry",
					"Herds-custom_herd_category",
					"Herds-custom_feed_account",
					"Herds-custom_vet_account",
					"Herds-custom_cost_center",
					"Animal Event-custom_calving_outcome",
					"Animal Event-custom_no_of_calves",
					"Animal Event-custom_calf_sex",
					"Animal Event-custom_related_pregnancy",
					"Animal Event-custom_status_after_test",
					"Animal Event-expected_calving_date",
					"Animal Event-pregnancy_check_due_date",
					"Animal Event-next_expected_heat",
					"Animal Event-ready_for_service_date",
					"Animal Event-custom_activity_cost",
					"Animal Event-custom_expense_account",
					"Animal Event-custom_cost_center",
					"Animal Event-custom_journal_entry",
					"Livestock Settings-custom_auto_create_journal_entry",
					"Livestock Settings-custom_default_company",
					"Livestock Settings-custom_default_credit_account",
					"Stock Entry-custom_milking_session",
					"Stock Entry-custom_cows_milked",
				],
			]
		],
	},
	{
		"dt": "Client Script",
		"filters": [
			[
				"name",
				"in",
				[
					"Control on Animal events",
					"Test on dynamic pregnancy",
					"Dynainamic fields on Animal event",
					"Milking Palour Checksheet",
					"Animal Event controller",
				],
			]
		],
	},
	{
		"dt": "Server Script",
		"filters": [
			[
				"name",
				"in",
				[
					"Updates animal status, creates alerts, and updates related events",
					"herd_movement_processor",
					"VALIDATION FOR SERVICE EVENTS",
					"Update Service from Diagnosis",
					"Get Animal Reproductive Summary",
					"CHECK OVERDUE PREGNANCY DIAGNOSES",
					"Get animals ready for service",
					"Get animals needing pregnancy check",
					"Number of animals in a Herd",
					"Livestock Auto Journal Entry",
					"Record Livestock Birth",
					"Scrap Livestock Asset",
					"Sell Livestock Asset",
					"Milk Recording After Submit - Stock Entry",
				],
			]
		],
	},
	{
		"dt": "Custom HTML Block",
		"filters": [["name", "in", ["Livestock Dashboard"]]],
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
# after_install = "upande_livestock.install.after_install"

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

# scheduler_events = {
# 	"all": [
# 		"upande_livestock.tasks.all"
# 	],
# 	"daily": [
# 		"upande_livestock.tasks.daily"
# 	],
# 	"hourly": [
# 		"upande_livestock.tasks.hourly"
# 	],
# 	"weekly": [
# 		"upande_livestock.tasks.weekly"
# 	],
# 	"monthly": [
# 		"upande_livestock.tasks.monthly"
# 	],
# }

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

