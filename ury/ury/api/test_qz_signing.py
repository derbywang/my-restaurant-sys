"""QZ Tray signing: the server signs, the private key never reaches the browser, and the server
signs only what printing needs.

QZ Tray can also read and write files of the cashier's PC, use serial ports and USB devices, and send
raw data to any host. The register must not be a way to ask for that: the server signs a QZ message only
if it is one of a few calls for printing, with a printer given by name and inline content (see
`ury.ury.api.ury_print`). QZ hands the signature function the SHA-256 of the message, not the message,
so the register sends the message along and the server checks that it is the one the hash was made of.
Run on the test site only.
"""

import base64
import hashlib
import json
import shutil
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from ury.setup.test_site import CAPTAIN, CASHIER, MANAGER, URYTestCase, as_user
from ury.ury.api.ury_print import qz_certificate_text, signature_promise

# what QZ Tray's library puts in `options` of a print (qz-tray.js 2.3.0, `defaultConfig`)
QZ_DEFAULT_OPTIONS = {
	"bounds": None,
	"colorType": "color",
	"copies": 1,
	"density": 0,
	"duplex": False,
	"fallbackDensity": None,
	"interpolation": "bicubic",
	"jobName": None,
	"legacy": False,
	"margins": 0,
	"orientation": None,
	"paperThickness": None,
	"printerTray": None,
	"rasterize": False,
	"rotation": 0,
	"scaleContent": True,
	"size": None,
	"units": "in",
	"forceRaw": False,
	"encoding": None,
	"spool": None,
}
HTML = {"type": "html", "format": "plain", "data": "<html><body>ご注文票</body></html>"}
PIXEL = {"type": "pixel", "format": "html", "flavor": "plain", "data": "<html></html>"}


def now_ms(minutes=0):
	return int((datetime.now() + timedelta(minutes=minutes)).timestamp() * 1000)


def qz_message(call="printers.getDefault", params=None, timestamp=None, **extra):
	"""The message as QZ's library stringifies it for signing, and the hash it hands to the signature function."""
	obj = {"call": call}
	if params is not None:
		obj["params"] = params
	obj["timestamp"] = now_ms() if timestamp is None else timestamp
	obj.update(extra)
	text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
	return hashlib.sha256(text.encode()).hexdigest(), text


def print_params(printer=None, data=None, options=None):
	return {
		"printer": {"name": "Receipt Printer"} if printer is None else printer,
		"options": dict(QZ_DEFAULT_OPTIONS) if options is None else options,
		"data": [HTML] if data is None else data,
	}


def make_key_and_certificate():
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ury-pos")])
	cert = (
		x509.CertificateBuilder()
		.subject_name(name)
		.issuer_name(name)
		.public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(datetime.utcnow() - timedelta(days=1))
		.not_valid_after(datetime.utcnow() + timedelta(days=30))
		.sign(key, hashes.SHA256())
	)
	return (
		key,
		key.private_bytes(
			serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
		),
		cert.public_bytes(serialization.Encoding.PEM).decode(),
	)


class QzCase(URYTestCase):
	def setUp(self):
		super().setUp()
		self.folder = f"qz_test_{uuid.uuid4().hex[:8]}"
		root = frappe.get_site_path("private", self.folder)
		shutil.os.makedirs(root, exist_ok=True)
		self.addCleanup(shutil.rmtree, root, True)
		self.key, key_pem, self.certificate = make_key_and_certificate()
		with open(f"{root}/key.pem", "wb") as f:
			f.write(key_pem)
		with open(f"{root}/cert.txt", "w") as f:
			f.write(self.certificate)
		self.config = {
			"qz_private_key": f"{self.folder}/key.pem",
			"qz_certificate_file": f"{self.folder}/cert.txt",
		}
		patcher = patch("ury.ury.api.ury_print.frappe.get_site_config", side_effect=lambda: dict(self.config))
		patcher.start()
		self.addCleanup(patcher.stop)

	def sign(self, user, message=None):
		to_sign, text = message or qz_message()
		with as_user(user):
			return signature_promise(to_sign, text)

	def refuse(self, message, msg=""):
		with self.assertRaises(frappe.ValidationError, msg=msg):
			self.sign(CASHIER, message)


class TestSigning(QzCase):
	def test_the_signature_is_the_one_qz_checks(self):
		to_sign, text = qz_message()
		signature = base64.b64decode(self.sign(CASHIER, (to_sign, text)))
		# raises when it does not verify: SHA512 with RSA (PKCS#1 v1.5) of what QZ handed over, the hash
		self.key.public_key().verify(signature, to_sign.encode(), padding.PKCS1v15(), hashes.SHA512())

	def test_whoever_may_print_a_bill_may_ask(self):
		for user in (CASHIER, MANAGER, CAPTAIN, "Administrator"):
			self.assertTrue(self.sign(user), user)

	def test_a_user_who_may_not_print_a_bill_may_not(self):
		user = "noprint@test.local"
		if not frappe.db.exists("User", user):
			frappe.get_doc(
				{"doctype": "User", "email": user, "first_name": "No Print", "send_welcome_email": 0, "roles": []}
			).insert(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			self.sign(user)

	def test_a_guest_may_not(self):
		with self.assertRaises(frappe.PermissionError):
			self.sign("Guest")
		with as_user("Guest"), self.assertRaises(frappe.PermissionError):
			qz_certificate_text()

	def test_without_a_key_it_says_so(self):
		self.config.pop("qz_private_key")
		with self.assertRaises(frappe.ValidationError):
			self.sign(CASHIER)

	def test_a_key_path_cannot_leave_the_private_folder(self):
		self.config["qz_private_key"] = "../site_config.json"
		with self.assertRaises(frappe.ValidationError):
			self.sign(CASHIER)


class TestTheMessageIsTheOneTheHashWasMadeOf(QzCase):
	def test_a_message_that_does_not_match_the_hash_is_refused(self):
		to_sign, text = qz_message()
		_other_hash, other_text = qz_message("printers.find", {"query": "x"})
		with self.assertRaises(frappe.ValidationError):
			signature_promise(to_sign, other_text)

	def test_a_hash_of_something_else_is_refused(self):
		_h, text = qz_message()
		with self.assertRaises(frappe.ValidationError):
			signature_promise(hashlib.sha256(b"file.read").hexdigest(), text)

	def test_no_message_or_no_hash_is_refused(self):
		to_sign, text = qz_message()
		for args in ((to_sign, None), (to_sign, ""), (None, text), ("", text), (None, None)):
			with self.assertRaises(frappe.ValidationError, msg=repr(args)[:40]):
				signature_promise(*args)

	def test_a_message_that_is_not_a_json_object_is_refused(self):
		for text in ("not json", json.dumps(["a"]), json.dumps("a"), json.dumps({"x": 1})):
			self.refuse((hashlib.sha256(text.encode()).hexdigest(), text), text)

	def test_a_huge_message_is_refused(self):
		_h, text = qz_message("print", print_params(data=[{**HTML, "data": "x" * (3 * 1024 * 1024)}]))
		self.refuse((hashlib.sha256(text.encode()).hexdigest(), text))

	def test_the_message_may_hold_nothing_but_call_params_and_timestamp(self):
		self.refuse(qz_message(uid="abc"))
		self.refuse(qz_message(signature="x"))


class TestOnlyPrintingCalls(QzCase):
	def test_these_calls_are_signed(self):
		for message in (
			qz_message("getVersion"),
			qz_message("printers.getDefault"),
			qz_message("printers.find", {"query": "Receipt"}),
			qz_message("print", print_params()),
		):
			self.assertTrue(self.sign(CASHIER, message), message[1][:40])

	def test_everything_else_is_refused(self):
		denied = [
			"file.list", "file.read", "file.write", "file.remove", "file.startListening", "file.stopListening",
			"serial.findPorts", "serial.openPort", "serial.sendData", "serial.closePort",
			"usb.listDevices", "usb.claimDevice", "usb.sendData", "usb.readData", "usb.openStream",
			"hid.listDevices", "hid.claimDevice", "hid.sendData", "hid.sendFeatureReport",
			"socket.openPort", "socket.sendData", "socket.closePort",
			"networking.device", "networking.devices", "networking.hostname",
			"websocket.getNetworkInfo",
			"printers.clearQueue", "printers.detail", "printers.getStatus",
			"printers.startListening", "printers.stopListening",
			"something.new", "", "Print", "PRINT", " print", "print ", "printers.getdefault",
		]
		for call in denied:
			self.refuse(qz_message(call, {}), call)

	def test_a_message_without_a_call_is_refused(self):
		text = json.dumps({"params": {}, "timestamp": now_ms()})
		self.refuse((hashlib.sha256(text.encode()).hexdigest(), text))


class TestTheTimeOfTheMessage(QzCase):
	def test_a_message_of_now_and_of_a_few_minutes_ago_is_signed(self):
		for minutes in (0, -9, 9):
			self.assertTrue(self.sign(CASHIER, qz_message(timestamp=now_ms(minutes))), minutes)

	def test_an_old_or_a_future_message_is_refused(self):
		for minutes in (-11, -600, 11, 600):
			self.refuse(qz_message(timestamp=now_ms(minutes)), str(minutes))

	def test_a_message_without_a_usable_time_is_refused(self):
		for timestamp in ("1790000000000", 1.5e12 + 0.5, True, [], {}):
			obj = {"call": "printers.getDefault", "timestamp": timestamp}
			text = json.dumps(obj)
			self.refuse((hashlib.sha256(text.encode()).hexdigest(), text), repr(timestamp))
		text = json.dumps({"call": "printers.getDefault"})
		self.refuse((hashlib.sha256(text.encode()).hexdigest(), text), "no time")


class TestWhatMayBePrinted(QzCase):
	def printing(self, **kwargs):
		return qz_message("print", print_params(**kwargs))

	def test_the_printer_is_given_by_name_only(self):
		self.assertTrue(self.sign(CASHIER, self.printing()))
		for printer in (
			{"host": "192.168.1.50", "port": 9100},
			{"name": "Receipt Printer", "host": "192.168.1.50", "port": 9100},
			{"file": "C:/Users/x/out.txt"},
			{"name": "Receipt Printer", "file": "x"},
			{"name": ""},
			{"name": 5},
			{"name": ["a"]},
			{},
			"Receipt Printer",
			None,
		):
			self.refuse(qz_message("print", {**print_params(), "printer": printer}), repr(printer))

	def test_a_print_without_a_printer_is_refused(self):
		params = print_params()
		del params["printer"]
		self.refuse(qz_message("print", params))

	def test_the_content_is_given_inline_as_html(self):
		for data in ([HTML], [PIXEL], [HTML, HTML]):
			self.assertTrue(self.sign(CASHIER, self.printing(data=data)))

	def test_a_file_or_url_or_raw_data_or_anything_else_is_refused(self):
		refused = [
			{"type": "html", "format": "file", "data": "C:/secret.html"},
			{"type": "html", "format": "plain", "flavor": "file", "data": "C:/secret.html"},
			{"type": "pixel", "format": "html", "flavor": "file", "data": "https://example.com/x"},
			{"type": "pixel", "format": "html", "flavor": "xml", "data": "<x/>"},
			{"type": "pixel", "format": "html", "flavor": "base64", "data": "AAAA"},
			{"type": "pixel", "format": "pdf", "flavor": "file", "data": "C:/x.pdf"},
			{"type": "pixel", "format": "image", "flavor": "base64", "data": "AAAA"},
			{"type": "pixel", "format": "image", "flavor": "plain", "data": "x"},
			{"type": "pdf", "format": "plain", "data": "x"},
			{"type": "image", "format": "plain", "data": "x"},
			{"type": "raw", "format": "command", "flavor": "plain", "data": "\x1bp\x00\x19\xfa"},
			{"type": "raw", "format": "plain", "data": "hello"},
			{"type": "raw", "format": "image", "flavor": "base64", "data": "AAAA"},
			{"type": "html", "data": "<html></html>"},
			{"format": "plain", "data": "x"},
			{"type": "html", "format": "plain"},
			{"type": "html", "format": "plain", "data": 5},
			{**HTML, "options": {"overlay": "C:/secret.png"}},
			"just a string",
			5,
			None,
		]
		for entry in refused:
			self.refuse(self.printing(data=[entry]), repr(entry)[:50])

	def test_one_bad_entry_spoils_the_whole_print(self):
		self.refuse(self.printing(data=[HTML, {"type": "raw", "format": "command", "data": "x"}]))

	def test_there_must_be_content_in_a_list(self):
		for data in ([], "x", {"a": 1}, None):
			params = print_params()
			params["data"] = data
			self.refuse(qz_message("print", params), repr(data))

	def test_the_content_may_not_be_huge(self):
		self.refuse(self.printing(data=[{**HTML, "data": "x" * (2 * 1024 * 1024 + 1)}]))


class TestPrintOptions(QzCase):
	def printing(self, **changes):
		return qz_message("print", print_params(options={**QZ_DEFAULT_OPTIONS, **changes}))

	def test_the_options_the_library_sends_by_default_are_signed(self):
		self.assertTrue(self.sign(CASHIER, qz_message("print", print_params(options=dict(QZ_DEFAULT_OPTIONS)))))

	def test_a_print_with_no_options_at_all_is_signed(self):
		self.assertTrue(self.sign(CASHIER, qz_message("print", print_params(options={}))))

	def test_copies_and_the_name_of_the_job_may_be_set(self):
		self.assertTrue(self.sign(CASHIER, self.printing(copies=2, jobName="ご注文票")))

	def test_the_layout_options_may_be_set(self):
		self.assertTrue(
			self.sign(CASHIER, self.printing(margins=0.2, orientation="portrait", size={"width": 80, "height": 200}, units="mm", rasterize=True))
		)

	def test_the_options_that_reach_beyond_printing_are_refused(self):
		for changes in (
			{"forceRaw": True},
			{"altPrinting": True},
			{"legacy": True},
			{"spool": {"size": 5}},
			{"bounds": {"x": 0}},
			{"encoding": "Cp437"},
		):
			self.refuse(self.printing(**changes), repr(changes))

	def test_an_option_the_library_does_not_have_is_refused(self):
		self.refuse(self.printing(command="rm -rf /"))

	def test_copies_must_be_a_small_number(self):
		for copies in (0, -1, 101, "2", 1.5, None, True):
			self.refuse(self.printing(copies=copies), repr(copies))

	def test_the_name_of_the_job_must_be_short_text(self):
		for job_name in (5, ["a"], "x" * 201):
			self.refuse(self.printing(jobName=job_name), repr(job_name)[:20])

	def test_options_must_be_an_object(self):
		for options in ("x", [], 5):
			params = print_params()
			params["options"] = options
			self.refuse(qz_message("print", params), repr(options))


class TestTheCertificate(QzCase):
	def test_the_certificate_is_given_as_text(self):
		with as_user(CASHIER):
			self.assertEqual(qz_certificate_text().strip(), self.certificate.strip())

	def test_the_certificate_path_cannot_leave_the_private_folder(self):
		self.config["qz_certificate_file"] = "../site_config.json"
		with as_user(CASHIER), self.assertRaises(frappe.ValidationError):
			qz_certificate_text()

	def test_without_a_certificate_it_says_so(self):
		self.config.pop("qz_certificate_file")
		with as_user(CASHIER), self.assertRaises(frappe.ValidationError):
			qz_certificate_text()
