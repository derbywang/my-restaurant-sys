"""URY Receipt Printer."""

import frappe
from frappe.model.document import Document

from ury.printing.service import check_settings


class URYReceiptPrinter(Document):
	def validate(self):
		try:
			check_settings(self.address, self.protocol, self.port, self.paper_width, self.drawer_pin, self.drawer_pulse_ms)
		except ValueError as error:
			frappe.throw(str(error))
		self.address = self.address.strip()
