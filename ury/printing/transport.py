"""Sending a job to the printer: ePOS-Print XML over HTTP, or raw ESC/POS on TCP 9100.

Both raise `PrinterError` whose message is a sentence for the cashier (Japanese). The ePOS-Print answer says what the
printer did (success, cover open, paper out); raw ESC/POS has no answer, so before the job a status request (DLE EOT 4,
the paper sensor) is sent and a printer that says its paper is out is not given the job."""

import socket
from urllib.parse import quote

from ury.printing import epos

EPOS_PATH = "/cgi-bin/epos/service.cgi?devid=%s&timeout=%d"
DEVICE_ID = "local_printer"
RAW_PORT = 9100
PAPER_OUT_BITS = 0x60  # DLE EOT 4: bits 5 and 6 are the paper roll sensor (end)


class PrinterError(Exception):
	"""What went wrong, as a sentence for the cashier."""


def _unreachable(address, error):
	return PrinterError("プリンター（%s）に接続できません。電源とネットワークを確認してください。（%s）" % (address, error))


def send_epos(address, xml, timeout=8, port=80, https=False, requester=None):
	"""POST the job; returns the printer's reply. `requester` replaces `requests.post` (tests)."""
	import requests

	host = address if ":" in address or port in (80, 443) else "%s:%d" % (address, port)
	url = "%s://%s%s" % ("https" if https else "http", host, EPOS_PATH % (quote(DEVICE_ID), int(timeout * 1000)))
	post = requester or requests.post
	try:
		response = post(
			url,
			data=xml.encode("utf-8"),
			headers={"Content-Type": "text/xml; charset=utf-8", "If-Modified-Since": "Thu, 01 Jan 1970 00:00:00 GMT"},
			timeout=timeout,
			verify=False,  # the printer's certificate is its own (docs/deploy/printer.md)
		)
	except requests.RequestException as error:
		raise _unreachable(address, type(error).__name__) from error
	if response.status_code != 200:
		raise PrinterError("プリンター（%s）がエラーを返しました（HTTP %d）。" % (address, response.status_code))
	reply = epos.parse_reply(response.text)
	if reply is None:
		raise PrinterError("プリンター（%s）の応答を読めません。" % address)
	if not reply.ok:
		raise PrinterError(reply.message)
	return reply


def send_raw(address, data, port=RAW_PORT, timeout=5, check_paper=True):
	"""Send the bytes. With `check_paper`: ask the paper sensor first (a printer that does not answer is not an error)."""
	try:
		with socket.create_connection((address, port), timeout=timeout) as connection:
			if check_paper:
				connection.sendall(b"\x10\x04\x04")
				connection.settimeout(1.0)
				try:
					answer = connection.recv(1)
				except socket.timeout:
					answer = b""
				connection.settimeout(timeout)
				if answer and answer[0] & PAPER_OUT_BITS:
					raise PrinterError(epos.MESSAGES["EPTR_REC_EMPTY"])
			connection.sendall(data)
	except PrinterError:
		raise
	except OSError as error:
		raise _unreachable(address, type(error).__name__) from error
