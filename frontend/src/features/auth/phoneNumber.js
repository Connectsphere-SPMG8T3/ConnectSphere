export const SINGAPORE_PHONE_ERROR = "Enter 8 digits, with an optional +65 country code.";

export function normalizeSingaporePhoneNumber(value) {
  const input = value.trim();
  if (!input) return null;

  let digits = input.replace(/[ -]/g, "");
  if (digits.startsWith("+65")) digits = digits.slice(3);
  if (!/^[0-9]{8}$/.test(digits)) return null;
  return `+65${digits}`;
}

export function formatSingaporePhoneNumber(value) {
  if (!value) return value;
  const normalized = normalizeSingaporePhoneNumber(value);
  return normalized ? `+65 ${normalized.slice(3)}` : value;
}

export function singaporePhoneError(value) {
  return value.trim() && !normalizeSingaporePhoneNumber(value) ? SINGAPORE_PHONE_ERROR : "";
}
