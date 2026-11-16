"""Printing from the server to the receipt printer on the shop's network (2026-11-16).

The register is an iPad, which cannot run QZ Tray; the printer is a network printer (Epson TM-m30III-H). So the server
sends the receipt itself, and the cash drawer's pulse rides in the same job. Layers:

  bitmap     the receipt's HTML -> a black and white raster (wkhtmltoimage + Pillow)
  escpos     the bytes of the ESC/POS commands (raster, cut, drawer pulse)
  epos       the ePOS-Print XML of the same job, and the printer's answer
  transport  sending it: ePOS-Print over HTTP (the printer answers with its state), or raw ESC/POS on TCP 9100

Nothing here knows Frappe: it is plain Python, tested with fake printers (`test_printing_core`). The part that knows the
DocTypes (which printer, which invoice) is `ury/ury/api/receipt_print.py`.
"""
