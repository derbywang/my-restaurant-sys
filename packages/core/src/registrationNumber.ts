/** 適格請求書発行事業者の登録番号: "T" followed by 13 digits. */
const REGISTRATION_NUMBER = /^T\d{13}$/;

export function isRegistrationNumber(value: string | null | undefined): boolean {
  return REGISTRATION_NUMBER.test((value ?? '').trim());
}
