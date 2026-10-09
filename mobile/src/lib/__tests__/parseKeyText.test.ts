/**
 * Self-check for the answer-key import parser.
 *
 * Plain assertions, no test framework needed:
 *   npx tsx src/lib/__tests__/parseKeyText.test.ts
 */
import assert from 'assert';

import { parseKeyText } from '../parseKeyText';

const OPTS = ['A', 'B', 'C', 'D'];

// A bare run of letters is taken as question 1 upward.
{
  const { answers, errors } = parseKeyText('CADB', OPTS);
  assert.deepStrictEqual(answers, { 1: 'C', 2: 'A', 3: 'D', 4: 'B' });
  assert.strictEqual(errors.length, 0);
}

// Numbered lines, with the separators teachers actually type.
{
  const { answers, errors } = parseKeyText('1. C\n2) A\n3 - D', OPTS);
  assert.deepStrictEqual(answers, { 1: 'C', 2: 'A', 3: 'D' });
  assert.strictEqual(errors.length, 0);
}

// Numbered lines need not be contiguous or in order: a partial key is valid,
// and the server leaves the missing questions unscored.
{
  const { answers } = parseKeyText('10. B\n4. A', OPTS);
  assert.deepStrictEqual(answers, { 10: 'B', 4: 'A' });
}

// Digits map onto option positions, because printed keys often use 1-4.
{
  const { answers } = parseKeyText('1. 3\n2. 1', OPTS);
  assert.deepStrictEqual(answers, { 1: 'C', 2: 'A' });
}

// Comma- and space-separated sequences.
{
  assert.deepStrictEqual(parseKeyText('C, A, D', OPTS).answers, { 1: 'C', 2: 'A', 3: 'D' });
  assert.deepStrictEqual(parseKeyText('C A D', OPTS).answers, { 1: 'C', 2: 'A', 3: 'D' });
}

// Keys are often written in groups; each group splits into its own letters.
{
  const { answers, errors } = parseKeyText('CADB CADB', OPTS);
  assert.deepStrictEqual(answers,
    { 1: 'C', 2: 'A', 3: 'D', 4: 'B', 5: 'C', 6: 'A', 7: 'D', 8: 'B' });
  assert.strictEqual(errors.length, 0);
}

// A numeric group stays whole: "12" is option 12, not option 1 then 2.
{
  const { errors } = parseKeyText('12 1', OPTS);
  assert.strictEqual(errors.length, 1, 'option 12 is out of range for A-D');
}

// Lower case is accepted and normalised.
{
  assert.deepStrictEqual(parseKeyText('cad', OPTS).answers, { 1: 'C', 2: 'A', 3: 'D' });
}

// An option outside the test's labels is reported, not silently stored --
// grading against a key containing "Z" would mark every student wrong.
{
  const { answers, errors } = parseKeyText('1. C\n2. Z', OPTS);
  assert.deepStrictEqual(answers, { 1: 'C' });
  assert.strictEqual(errors.length, 1);
}

// A 2-option sheet must reject C, which is valid only on a 4-option form.
{
  const { answers, errors } = parseKeyText('AB C', ['A', 'B']);
  assert.deepStrictEqual(answers, { 1: 'A', 2: 'B' });
  assert.strictEqual(errors.length, 1);
}

// Empty input is not an error, it is just nothing.
{
  const { answers, errors } = parseKeyText('   ', OPTS);
  assert.deepStrictEqual(answers, {});
  assert.strictEqual(errors.length, 0);
}

// Digit out of range for the option list.
{
  const { errors } = parseKeyText('1. 9', OPTS);
  assert.strictEqual(errors.length, 1);
}

console.log('parseKeyText: all assertions passed');
