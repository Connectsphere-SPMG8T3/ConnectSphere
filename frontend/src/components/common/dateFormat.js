// The top bar's date reads as a sentence ("8th May 2025") rather than as a
// stamp, so the day carries an English ordinal suffix. Kept out of the
// component so it can be unit-tested on its own.
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export function ordinalSuffix(day) {
  // 11th–13th break the 1st/2nd/3rd pattern, so they are checked first.
  if (day >= 11 && day <= 13) return "th";
  return { 1: "st", 2: "nd", 3: "rd" }[day % 10] ?? "th";
}

export function formatFriendlyDate(date) {
  const day = date.getDate();
  return `${day}${ordinalSuffix(day)} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}
