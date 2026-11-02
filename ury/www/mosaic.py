import frappe
from frappe.utils import cint

no_cache = 1


def get_context(context):
	"""For the realtime connection of the kitchen display: on the development server
	(`bench start`) Socket.IO listens on its own port, in production behind nginx it does not."""
	context.dev_server = cint(getattr(frappe.local, "dev_server", 0))
	context.socketio_port = cint(frappe.conf.get("socketio_port"))
	return context
