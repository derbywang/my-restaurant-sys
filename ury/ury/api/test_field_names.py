"""No field of ours has a name that Frappe takes for one of its optional columns.

`set_optional_columns` in frappe/model/db_query.py leaves a field out of every list query (`get_list`, `get_all`, the Desk
lists and reports) when its name contains `_user_tags`, `_comments`, `_assign`, `_liked_by` or `_seen` and the table has no
such column: `last_seen` was never shown in the list of the devices. See docs/frappe-optional-columns.md.
"""

import glob
import json
import os
import unittest

OPTIONAL = ("_user_tags", "_comments", "_assign", "_liked_by", "_seen")
APP = os.path.join(os.path.dirname(__file__), "..", "..")
# known and checked: POS Invoice has the `_comments` column, so the field is not dropped (it must stay in the table)
ALLOWED = {("POS Invoice", "custom_comments")}


def names():
	for path in glob.glob(os.path.join(APP, "**", "doctype", "**", "*.json"), recursive=True):
		with open(path, encoding="utf8") as f:
			doc = json.load(f)
		if isinstance(doc, dict):
			for field in doc.get("fields", []):
				yield doc.get("name"), field.get("fieldname", "")
	with open(os.path.join(APP, "fixtures", "custom_field.json"), encoding="utf8") as f:
		for field in json.load(f):
			yield field.get("dt"), field.get("fieldname", "")


class TestFieldNames(unittest.TestCase):
	def test_no_field_name_contains_the_name_of_an_optional_column(self):
		found = sorted(
			(doctype, name)
			for doctype, name in names()
			if any(o in name for o in OPTIONAL) and (doctype, name) not in ALLOWED
		)
		self.assertEqual(found, [], "Frappe would leave these out of its list queries (docs/frappe-optional-columns.md)")
