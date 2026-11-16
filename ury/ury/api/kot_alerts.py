"""The second way a kitchen error reminder reaches the register (see branch_realtime.remember_kot_alert).

The real-time message is lost on a register whose connection dropped (an iPad that slept). The register also asks every
half minute for the alerts of its branch it has not seen yet. Whoever works in a branch may ask; the branch is resolved
from the session, never from an argument.
"""

import frappe
from frappe import _

from ury.ury.api.branch_realtime import recent_kot_alerts


@frappe.whitelist(methods=["GET"])
def get_recent_kot_alerts(since=0):
	if frappe.session.user == "Guest":
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	from ury.ury_pos.api import getBranch

	return recent_kot_alerts(getBranch(), since)
