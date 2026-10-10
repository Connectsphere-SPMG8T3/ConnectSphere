const formatter = new Intl.DateTimeFormat("en-SG", {
  dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Singapore",
});

export function displaySafetyTime(value) {
  return value ? formatter.format(new Date(value)) : "Not provided";
}
