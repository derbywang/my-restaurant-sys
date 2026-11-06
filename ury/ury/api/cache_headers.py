"""Pages and ordering calls are never cached by a browser, a tablet or Cloudflare.

The HTML of /order holds the CSRF token and names the JS and CSS files of the build that is current, so a copy kept
anywhere is wrong after the next deploy (a blank page: the old files are gone) or for the next visitor. Frappe's
`no_cache = 1` in a page module only stops Frappe caching the rendered page; it sets no HTTP header. This hook
sets `Cache-Control: no-store` on the pages of the apps and on the calls of the ordering page.

The files under /assets have names with a hash of their content, so they may be cached for a long time and are
left alone (their headers are set by nginx, see docs/design/self-order-design.md, 9.2).
"""

NO_STORE = "no-store"

# the pages of the apps: the path itself and everything below it
PAGES = ("/order", "/pos", "/mosaic", "/ury")
# the calls of the ordering page (GET calls such as the menu and the order must not be kept either)
CALLS = "/api/method/ury.ury.api.self_ordering."


def is_uncached(path):
	if not isinstance(path, str):
		return False
	if path.startswith(CALLS):
		return True
	return any(path == page or path.startswith(page + "/") for page in PAGES)


def after_request(response, request):
	"""Frappe `after_request` hook."""
	if is_uncached(getattr(request, "path", None)):
		response.headers["Cache-Control"] = NO_STORE
