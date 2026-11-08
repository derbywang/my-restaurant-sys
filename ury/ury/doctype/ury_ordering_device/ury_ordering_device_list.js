// A tablet reports every few seconds while it waits and every 20 seconds while the guests order (`last_reported_at`; not `last_seen`: Frappe leaves a field with `_seen` in its name out of list queries):
// one that has not reported for 5 minutes is switched off, out of the network, or its page is closed.
frappe.listview_settings["URY Ordering Device"] = {
	add_fields: ["enabled", "last_reported_at"],
	get_indicator(doc) {
		if (!doc.enabled) return [__("Stopped"), "gray", "enabled,=,0"];
		const silent =
			!doc.last_reported_at ||
			moment(frappe.datetime.now_datetime()).diff(moment(doc.last_reported_at), "minutes") >= 5;
		return silent
			? [__("No report for 5 minutes"), "red", "enabled,=,1"]
			: [__("Reporting"), "green", "enabled,=,1"];
	},
};
