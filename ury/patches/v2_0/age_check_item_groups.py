"""Give the self ordering profiles that were made before the age check the alcohol group.

Only a profile with no group at all is changed; one that was set up by hand keeps what it has. The
group is the one the setup wizard makes (ury.setup.jp_tax.ALCOHOL_GROUP), and only where it exists.
"""

import frappe

from ury.setup.jp_tax import ALCOHOL_GROUP


def execute():
	if not frappe.db.exists("Item Group", ALCOHOL_GROUP):
		return
	for name in frappe.get_all("URY Self Ordering Profile", pluck="name"):
		if frappe.db.exists("URY Age Check Item Group", {"parent": name, "parenttype": "URY Self Ordering Profile"}):
			continue
		profile = frappe.get_doc("URY Self Ordering Profile", name)
		profile.flags.no_default_age_groups = True
		profile.append("age_check_item_groups", {"item_group": ALCOHOL_GROUP})
		profile.save(ignore_permissions=True)
