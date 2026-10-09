/** Parse a pasted answer key into {question: option}.
 *
 *  Accepts the shapes a teacher actually has to hand: a bare run of letters
 *  ("ABCD..."), comma/space separated letters, and numbered lines
 *  ("1. C", "2) A", "3 - D"). Digits 1-4 map onto the option labels, because
 *  printed keys often use numbers while the sheet is reported as A-D.
 *
 *  Kept free of any React Native import so it can be unit-tested directly.
 */
export function parseKeyText(
  text: string, options: string[],
): { answers: Record<number, string>; errors: string[] } {
  const answers: Record<number, string> = {};
  const errors: string[] = [];
  const valid = new Set(options.map((o) => o.toUpperCase()));
  const clean = text.trim();
  if (!clean) return { answers, errors };

  const numbered = clean.match(/^\s*\d+\s*[.):\-]/m);
  if (numbered) {
    clean.split(/[\n;]+/).forEach((line) => {
      const t = line.trim();
      if (!t) return;
      const m = t.match(/^(\d+)\s*[.):\-]?\s*([A-Za-z0-9]+)/);
      if (!m) { errors.push(`Could not read "${t}"`); return; }
      const q = parseInt(m[1], 10);
      const opt = normaliseOption(m[2], options);
      if (!opt || !valid.has(opt)) { errors.push(`Q${q}: "${m[2]}" is not a valid option`); return; }
      answers[q] = opt;
    });
    return { answers, errors };
  }

  // Unnumbered: a sequence, taken as question 1 upward.
  //
  // Keys are commonly written in groups ("CADB CADB CADB" or "AB C"), so each
  // whitespace/comma-separated group is split into its own letters. A purely
  // numeric group stays whole, because "12" there means option 12, not 1 then 2.
  const tokens = clean
    .split(/[\s,]+/)
    .filter(Boolean)
    .flatMap((group) =>
      /^\d+$/.test(group) || group.length === 1 ? [group] : group.split(''));

  tokens.forEach((tok, i) => {
    const opt = normaliseOption(tok, options);
    if (!opt || !valid.has(opt)) {
      errors.push(`Position ${i + 1}: "${tok}" is not a valid option`);
      return;
    }
    answers[i + 1] = opt;
  });
  return { answers, errors };
}

function normaliseOption(raw: string, options: string[]): string | null {
  const t = raw.trim().toUpperCase();
  if (!t) return null;
  if (/^\d+$/.test(t)) {
    const idx = parseInt(t, 10) - 1;
    return idx >= 0 && idx < options.length ? options[idx].toUpperCase() : null;
  }
  return t;
}

