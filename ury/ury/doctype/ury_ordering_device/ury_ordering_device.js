// Copyright (c) 2026, Tridz Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

// The button that sets up a table tablet: issues a new credential (the old one stops working) and shows the link
// and its QR code once. Open the link on the tablet (or scan the code with it): `/order/setup` keeps the device and
// the credential there and starts. The credential is in the part of the address after the #, which the server never gets.
frappe.ui.form.on("URY Ordering Device", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("発行（設定用 QR）"), () => {
			frappe.confirm(
				__("This makes a new credential: the tablet that has the old one stops working until it is set up again with the new link. Go on?"),
				() => {
					frappe.call({
						method: "ury.ury.api.self_ordering.issue_device_setup",
						args: { device: frm.doc.name },
						freeze: true,
						callback(r) {
							if (!r.message) return;
							const { link, svg } = r.message;
							const dialog = new frappe.ui.Dialog({
								title: __("設定用リンク"),
								fields: [
									{
										fieldtype: "HTML",
										fieldname: "body",
										options: `<div style="text-align:center">
											<div style="width:260px;margin:0 auto">${svg}</div>
											<p class="text-muted" style="margin-top:12px">${__("Shown once. Open it on the tablet, or scan the code with the tablet's camera.")}</p>
											<textarea class="form-control" rows="4" readonly style="font-size:12px">${frappe.utils.escape_html(link)}</textarea>
										</div>`,
									},
								],
								primary_action_label: __("Close"),
								primary_action() {
									dialog.hide();
								},
							});
							dialog.show();
						},
					});
				}
			);
		});
	},
});
