const STATUS_LABELS = {
  registered: "Registered",
  waitlisted: "Waitlisted",
  invited: "Invited",
  withdrawn: "Withdrawn",
};

export function managedRegistrationStatusLabel(status) {
  return STATUS_LABELS[status] ?? status.replaceAll("_", " ");
}

function csvField(value) {
  let text = String(value ?? "");
  if (/^[\t\r ]*[=+\-@]/.test(text)) text = `'${text}`;
  return `"${text.replaceAll('"', '""')}"`;
}

export function buildManagedRegistrationsCsv(registrations, includeContactDetails) {
  const headers = includeContactDetails
    ? ["Full name", "Email", "Phone", "Status"]
    : ["Full name", "Status"];
  const rows = registrations.map((registration) =>
    includeContactDetails
      ? [
          registration.full_name,
          registration.email,
          registration.phone_number,
          managedRegistrationStatusLabel(registration.status),
        ]
      : [registration.full_name, managedRegistrationStatusLabel(registration.status)],
  );
  const csvRows = [headers, ...rows].map((row) => row.map(csvField).join(","));
  return `\uFEFF${csvRows.join("\r\n")}`;
}
