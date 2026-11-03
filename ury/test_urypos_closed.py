"""The old Vue POS (/urypos) is closed: it has none of the Japan tax, merged-bill and change rules.

Nothing may open it: no page, no route rule, no build step, no link. Its source stays in `urypos/`
(it is upstream code) but it is not built or installed. Run on the test site only.
"""

import json
from pathlib import Path

import frappe
from frappe.website.page_renderers.not_found_page import NotFoundPage
from frappe.website.path_resolver import PathResolver

from ury.patches.v2_0 import remove_pos_v1_entry
from ury.setup.test_site import URYTestCase

APP = Path(frappe.get_app_path("ury")).parent
BLOCK = "POS V1"


def renderer_for(path):
	return PathResolver(path).resolve()[1]


class TestUryPosClosed(URYTestCase):
	def test_the_old_pos_page_is_not_found(self):
		for path in ("urypos", "urypos/Table", "urypos/Login"):
			self.assertIsInstance(renderer_for(path), NotFoundPage, path)

	def test_there_is_no_route_rule_or_page_for_it(self):
		routes = [rule["from_route"] for rule in frappe.get_hooks("website_route_rules")]
		self.assertFalse([r for r in routes if "urypos" in r])
		self.assertFalse((APP / "ury" / "www" / "urypos.html").exists())

	def test_the_build_and_install_do_not_touch_it(self):
		scripts = json.loads((APP / "package.json").read_text())["scripts"]
		for name, command in scripts.items():
			self.assertNotIn("urypos", command, name)
			self.assertNotIn("ury-pos-", command, name)

	def test_the_new_pos_has_no_link_to_it(self):
		source = (APP / "pos" / "src" / "components" / "ScreenSizeDialog.tsx").read_text()
		self.assertNotIn("urypos", source)

	def test_the_desk_workspace_has_no_link_to_it(self):
		workspace = json.loads((APP / "ury" / "ury" / "workspace" / "ury" / "ury.json").read_text())
		self.assertNotIn(BLOCK, workspace["content"])
		self.assertNotIn(BLOCK, [row["custom_block_name"] for row in workspace["custom_blocks"]])
		fixture = json.loads((APP / "ury" / "fixtures" / "custom_html_block.json").read_text())
		self.assertNotIn(BLOCK, [row["name"] for row in fixture])


class TestRemovePosV1Entry(URYTestCase):
	"""The patch takes the link out of a site that already has it. Nothing is committed."""

	def setUp(self):
		super().setUp()
		frappe.db.savepoint("pos_v1_entry")
		if not frappe.db.exists("Custom HTML Block", BLOCK):
			frappe.get_doc(
				{"doctype": "Custom HTML Block", "name": BLOCK, "html": '<a href="/urypos">POS V1</a>'}
			).insert(ignore_permissions=True)
		self.workspace = frappe.get_doc("Workspace", "URY")
		self.workspace.append("custom_blocks", {"custom_block_name": BLOCK, "label": BLOCK})
		content = json.loads(self.workspace.content or "[]")
		content.append({"id": "pv1", "type": "custom_block", "data": {"custom_block_name": BLOCK, "col": 2}})
		self.workspace.content = json.dumps(content)
		self.workspace.save(ignore_permissions=True)

	def tearDown(self):
		frappe.db.rollback(save_point="pos_v1_entry")
		super().tearDown()

	def test_the_block_and_its_place_on_the_workspace_are_removed(self):
		remove_pos_v1_entry.execute()

		self.assertFalse(frappe.db.exists("Custom HTML Block", BLOCK))
		workspace = frappe.get_doc("Workspace", "URY")
		self.assertNotIn(BLOCK, [row.custom_block_name for row in workspace.custom_blocks])
		self.assertNotIn(BLOCK, workspace.content)

	def test_the_other_blocks_stay(self):
		before = [row.custom_block_name for row in self.workspace.custom_blocks if row.custom_block_name != BLOCK]

		remove_pos_v1_entry.execute()

		workspace = frappe.get_doc("Workspace", "URY")
		self.assertEqual([row.custom_block_name for row in workspace.custom_blocks], before)
		for name in before:
			self.assertIn(name, workspace.content)

	def test_a_site_without_it_is_left_alone(self):
		remove_pos_v1_entry.execute()
		remove_pos_v1_entry.execute()  # the second run finds nothing and does not fail
