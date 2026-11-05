// The token of the QR code on a table is in the link: `/order/?<param>=<token>`. The name of the
// parameter is written once, in ury/ury/api/qr_link.json, which the server builds the link with
// (`qr_url` in self_ordering.py) and this page reads it with.
import qrLink from '../../../ury/ury/api/qr_link.json'

export const QR_TOKEN_PARAM: string = qrLink.param

/** The token in the query string of the page (`window.location.search`), or null. */
export function tokenFromSearch(search: string): string | null {
  const token = new URLSearchParams(search).get(QR_TOKEN_PARAM)
  return token ? token : null
}
