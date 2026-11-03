"""Take the link to the old POS (/urypos, "POS V1") off the URY workspace.

The old Vue POS is closed (it has none of the Japan tax, merged-bill and change rules), so the
"POS V1" block on the Desk home must not point to it. Deletes the Custom HTML Block and its place
on the workspace; the other blocks stay. A site without the block is left alone.
"""

import json

import frappe

BLOCK = "POS V1"


def execute():
	if frappe.db.exists("Workspace", "URY"):
		workspace = frappe.get_doc("Workspace", "URY")
		workspace.custom_blocks = [row for row in workspace.custom_blocks if row.custom_block_name != BLOCK]
		content = [
			block
			for block in json.loads(workspace.content or "[]")
			if block.get("data", {}).get("custom_block_name") != BLOCK
		]
		workspace.content = json.dumps(content, separators=(",", ":"))
		workspace.save(ignore_permissions=True)

	if frappe.db.exists("Custom HTML Block", BLOCK):
		frappe.delete_doc("Custom HTML Block", BLOCK, ignore_permissions=True, force=True)
