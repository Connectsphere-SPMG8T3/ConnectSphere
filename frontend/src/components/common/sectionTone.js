// Dashboard section headings take the Bauhaus primaries in page order: red,
// blue, yellow, then round again, so neighbouring sections always differ.
export const SECTION_TONES = ["red", "blue", "yellow"];

export function sectionTone(index) {
  return SECTION_TONES[index % SECTION_TONES.length];
}
