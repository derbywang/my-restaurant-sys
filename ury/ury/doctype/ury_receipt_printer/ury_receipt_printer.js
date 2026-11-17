frappe.ui.form.on("URY Receipt Printer", {
	refresh(frm) {
		if (frm.is_new()) return;
		// 「テスト印刷」: a page with a frame as wide as the paper width of the settings (docs/deploy/printer.md, section 13)
		frm.add_custom_button(__("テスト印刷"), () => {
			if (frm.is_dirty()) {
				frappe.msgprint({ title: __("テスト印刷"), message: __("先に保存してください。（保存した設定で印刷します）"), indicator: "orange" });
				return;
			}
			frappe.call({
				method: "ury.ury.api.receipt_print.print_test_page",
				args: { printer: frm.doc.name },
				freeze: true,
				freeze_message: __("テストページを印刷しています…"),
				callback(r) {
					const answer = r.message || {};
					frappe.msgprint({
						title: answer.ok ? __("テスト印刷") : __("印刷できませんでした"),
						message: answer.ok
							? __("テストページを印刷しました。枠の左右が紙の端まで見えれば、紙幅の設定は合っています。右が切れるときは設定が紙より広く、右が空くときは狭すぎます。")
							: answer.message,
						indicator: answer.ok ? "green" : "red",
					});
				},
			});
		});
	},
});
