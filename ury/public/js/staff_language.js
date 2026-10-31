// "Language" entry in the Desk user menu (top right). The choice is saved on the
// logged-in user's User.language by ury.ury.api.language.set_staff_language.
(() => {
	const ACTION = "frappe.ury.staff_language.open()";

	frappe.ury = frappe.ury || {};
	frappe.ury.staff_language = {
		async open() {
			const { message: options } = await frappe.call("ury.ury.api.language.get_language_options");
			const current = (options.find((o) => o.code === frappe.boot.lang) || {}).label;

			const dialog = new frappe.ui.Dialog({
				title: __("Language"),
				fields: [
					{
						fieldname: "language",
						fieldtype: "Select",
						label: __("Language"),
						options: options.map((o) => o.label),
						default: current,
					},
				],
				primary_action_label: __("Change"),
				async primary_action({ language }) {
					const chosen = options.find((o) => o.label === language);
					if (!chosen || chosen.code === frappe.boot.lang) {
						dialog.hide();
						return;
					}
					dialog.disable_primary_action();
					try {
						await frappe.call("ury.ury.api.language.set_staff_language", { lang: chosen.code });
						window.location.reload();
					} catch (e) {
						dialog.enable_primary_action();
					}
				},
			});
			dialog.show();
		},
	};

	// Desk is a single-page app and this file is loaded once per page load, but
	// guard on the action anyway so the entry can never be added twice.
	const items = frappe.boot && frappe.boot.navbar_settings && frappe.boot.navbar_settings.settings_dropdown;
	if (!items || items.some((item) => item.action === ACTION)) return;

	const entry = { item_label: "Language", item_type: "Action", action: ACTION, is_standard: 0, hidden: 0 };
	const logout = items.findIndex((item) => (item.action || "").startsWith("frappe.app.logout"));
	// Sit above the separator that precedes "Log out".
	const at = logout > 0 && items[logout - 1].item_type === "Separator" ? logout - 1 : logout;
	items.splice(at < 0 ? items.length : at, 0, entry);
})();
