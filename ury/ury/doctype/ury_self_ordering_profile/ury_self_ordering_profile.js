// Copyright (c) 2026, Tridz Technologies Pvt. Ltd and contributors
// For license information, please see license.txt

frappe.ui.form.on("URY Self Ordering Profile", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Print table QR codes"), () => {
			if (!frm.doc.public_url) {
				frappe.msgprint(__("Set the Public URL first: it is written in the QR codes."));
				return;
			}
			// the codes are made on the server; the page is opened in a window of its own and printed from there
			frappe.call({
				method: "ury.ury.api.qr_print.table_qr_print_html",
				args: { profile: frm.doc.name },
				freeze: true,
				callback: (r) => {
					if (!r.message) return;
					const win = window.open("", "_blank");
					win.document.open();
					win.document.write(r.message);
					win.document.close();
					win.focus();
					win.print();
				},
			});
		});
	},
});
