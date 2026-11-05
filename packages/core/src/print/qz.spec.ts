import { createHash } from 'node:crypto';
import { describe, expect, it, vi } from 'vitest';

import { createQzSigner, messageOf, qzCertificatePromise, sha256Hex } from './qz-security';

describe('messageOf', () => {
  it('takes the message of a Frappe answer', () => {
    expect(messageOf({ message: 'abc' })).toBe('abc');
    expect(messageOf({ data: { message: 'abc' } })).toBe('abc');
  });

  it('is not fooled by an answer without one', () => {
    expect(() => messageOf({})).toThrow();
    expect(() => messageOf(null)).toThrow();
    expect(() => messageOf({ message: '' })).toThrow();
  });
});

describe('sha256Hex', () => {
  it('is the SHA-256 QZ checks the signature against, for plain and for Japanese text', () => {
    for (const text of ['', 'abc', '{"call":"print","timestamp":1}', 'ご注文票 No. 17 ¥1,080（税込）', '😀']) {
      expect(sha256Hex(text)).toBe(createHash('sha256').update(text, 'utf8').digest('hex'));
    }
  });
});

describe('qzCertificatePromise', () => {
  it('hands QZ the certificate the server gave', async () => {
    const resolve = vi.fn();
    const reject = vi.fn();
    qzCertificatePromise(vi.fn().mockResolvedValue('-----BEGIN CERTIFICATE-----'))(resolve, reject);
    await vi.waitFor(() => expect(resolve).toHaveBeenCalledWith('-----BEGIN CERTIFICATE-----'));
    expect(reject).not.toHaveBeenCalled();
  });

  it('tells QZ why when it cannot', async () => {
    const resolve = vi.fn();
    const reject = vi.fn();
    qzCertificatePromise(() => Promise.reject(new Error('no certificate')))(resolve, reject);
    await vi.waitFor(() => expect(reject).toHaveBeenCalled());
    expect(String(reject.mock.calls[0][0])).toContain('no certificate');
    expect(resolve).not.toHaveBeenCalled();
  });
});

describe('createQzSigner', () => {
  const message = '{"call":"printers.getDefault","timestamp":1790000000000}';

  it('asks the server to sign the hash together with the message it was made of', async () => {
    const sign = vi.fn().mockResolvedValue('c2lnbmF0dXJl');
    const { hasher, signaturePromise } = createQzSigner(sign);
    const hash = hasher(message); // what QZ does with the message, then it asks for the signature of the hash
    const resolve = vi.fn();
    signaturePromise(hash)(resolve, vi.fn());
    await vi.waitFor(() => expect(resolve).toHaveBeenCalledWith('c2lnbmF0dXJl'));
    expect(hash).toBe(createHash('sha256').update(message).digest('hex'));
    expect(sign).toHaveBeenCalledWith(hash, message);
  });

  it('does not sign a hash it did not make (nothing to show the server)', async () => {
    const sign = vi.fn();
    const reject = vi.fn();
    createQzSigner(sign).signaturePromise('0'.repeat(64))(vi.fn(), reject);
    expect(reject).toHaveBeenCalled();
    expect(sign).not.toHaveBeenCalled();
  });

  it('signs a message once: the same hash cannot be asked for again', async () => {
    const sign = vi.fn().mockResolvedValue('sig');
    const { hasher, signaturePromise } = createQzSigner(sign);
    const hash = hasher(message);
    signaturePromise(hash)(vi.fn(), vi.fn());
    const reject = vi.fn();
    signaturePromise(hash)(vi.fn(), reject);
    expect(reject).toHaveBeenCalled();
    expect(sign).toHaveBeenCalledTimes(1);
  });

  it('tells QZ why when the server refuses', async () => {
    const { hasher, signaturePromise } = createQzSigner(() => Promise.reject(new Error('The request cannot be signed')));
    const reject = vi.fn();
    signaturePromise(hasher(message))(vi.fn(), reject);
    await vi.waitFor(() => expect(reject).toHaveBeenCalled());
    expect(String(reject.mock.calls[0][0])).toContain('cannot be signed');
  });

  it('does not keep every message it ever hashed', () => {
    const sign = vi.fn();
    const { hasher, signaturePromise } = createQzSigner(sign);
    const first = hasher('first');
    for (let i = 0; i < 100; i++) hasher(`m${i}`);
    const reject = vi.fn();
    signaturePromise(first)(vi.fn(), reject);
    expect(reject).toHaveBeenCalled();
  });
});
