// What QZ Tray asks the page for before it prints: the certificate and a signature of every message.
// Both come from the server (`qz_certificate_text`, `signature_promise` in ury_print.py); the private key
// never reaches the browser. Kept apart from qz.ts so it can be tested without QZ.
//
// QZ's library does not give the signature function the message but its SHA-256. The server must see
// the message to decide whether it may sign it (QZ can also read files, use serial ports and USB), so
// the hash function QZ uses is replaced by one that remembers the message; the signature function then
// sends the message along with its hash, and the server checks that the hash is the message's.
import { KJUR } from 'jsrsasign';

type Resolve<T> = (value: T) => void;
type Reject = (reason?: string) => void;

/** The `message` of a Frappe answer (`{ message }`, or `{ data: { message } }`); throws when there is none. */
export function messageOf(response: unknown): string {
  const body = response as { message?: unknown; data?: { message?: unknown } } | null | undefined;
  const message = body?.message ?? body?.data?.message;
  if (typeof message !== 'string' || message === '') {
    throw new Error('The server did not give a QZ certificate or signature.');
  }
  return message;
}

/** SHA-256 of the text (UTF-8) as lower case hex, the way QZ's library writes it. */
export function sha256Hex(text: string): string {
  return KJUR.crypto.Util.sha256(text);
}

/** The shape of `qz.security.setCertificatePromise`. */
export function qzCertificatePromise(fetchCertificate: () => Promise<string>) {
  return (resolve: Resolve<string>, reject: Reject) => {
    fetchCertificate().then(resolve, (error) =>
      reject('Error fetching the QZ certificate: ' + String(error?.message ?? error))
    );
  };
}

const REMEMBERED = 50;

/**
 * The two functions QZ needs for signing: `hasher` (for `qz.api.setSha256Type`) hashes a message and
 * remembers it; `signaturePromise` (for `qz.security.setSignaturePromise`) asks the server to sign the hash
 * together with the message it was made of.
 */
export function createQzSigner(sign: (toSign: string, message: string) => Promise<string>) {
  const messages = new Map<string, string>();

  const hasher = (message: string): string => {
    const hash = sha256Hex(message);
    messages.set(hash, message);
    if (messages.size > REMEMBERED) {
      messages.delete(messages.keys().next().value as string); // the oldest: it was never signed
    }
    return hash;
  };

  const signaturePromise = (toSign: string) => (resolve: Resolve<string>, reject: Reject) => {
    const message = messages.get(toSign);
    messages.delete(toSign);
    if (message === undefined) {
      reject('Error signing the QZ message: the message is unknown.');
      return;
    }
    sign(toSign, message).then(resolve, (error) =>
      reject('Error signing the QZ message: ' + String(error?.message ?? error))
    );
  };

  return { hasher, signaturePromise };
}
