import qz from 'qz-tray';
import { call } from '../frappe/client';
import { createQzSigner, messageOf, qzCertificatePromise } from './qz-security';

const CERTIFICATE_METHOD = 'ury.ury.api.ury_print.qz_certificate_text';
const SIGNATURE_METHOD = 'ury.ury.api.ury_print.signature_promise';

// QZ Tray trusts this site through the certificate it is given (the cashier PC has the same
// certificate as `override.crt`, see the deployment checklist); the signing key stays on the server,
// which signs only the calls printing needs.
let securityConfigured = false;

function configureSecurity() {
  if (securityConfigured) return;
  securityConfigured = true;

  const signer = createQzSigner(async (toSign, message) =>
    messageOf(await call.post(SIGNATURE_METHOD, { toSign, message }))
  );
  // before the first message is hashed (the type package declares the hasher's argument wrongly: it is the message text)
  qz.api.setSha256Type(signer.hasher as unknown as Parameters<typeof qz.api.setSha256Type>[0]);
  qz.security.setCertificatePromise(
    qzCertificatePromise(async () => messageOf(await call.get(CERTIFICATE_METHOD)))
  );
  qz.security.setSignatureAlgorithm('SHA512');
  qz.security.setSignaturePromise(signer.signaturePromise);
}

export async function loadQzPrinter(host: string): Promise<void> {
  configureSecurity();
  if (!qz.websocket.isActive()) {
    await qz.websocket.connect({ host, usingSecure: false });
  }
}

export function disconnectQzPrinter(): void {
  if (qz.websocket.isActive()) qz.websocket.disconnect();
}

export async function printWithQz(host: string, htmlToPrint: string): Promise<void> {
  await loadQzPrinter(host);
  const printer = await qz.printers.getDefault();
  const data = [{ type: 'html', format: 'plain', data: htmlToPrint }];
  const config = qz.configs.create(printer);
  await qz.print(config, data as any);
}
