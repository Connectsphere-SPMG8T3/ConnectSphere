export function serverFieldErrors(detail, fieldValues) {
  const errors = {};
  for (const { loc, msg } of detail) {
    const name = loc?.[loc.length - 1];
    if (name in fieldValues && !errors[name]) errors[name] = msg;
  }
  return errors;
}
