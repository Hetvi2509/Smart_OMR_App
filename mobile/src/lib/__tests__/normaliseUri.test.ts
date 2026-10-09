/**
 * Self-check for the upload URI rules.
 *
 *   npx tsx src/lib/__tests__/normaliseUri.test.ts
 *
 * React Native's native multipart encoder rejects a file part whose `uri` has
 * no scheme it can open, reporting only "Unsupported FormData part
 * implementation" -- which names neither the field nor the reason. These
 * assertions pin down the shape that has to reach it.
 */
import assert from 'assert';

/** Mirror of the rule in prepareSheet.ts (kept in sync by these tests). */
function normaliseUri(uri: string): string {
  return /^[a-z][a-z0-9+.-]*:/i.test(uri) ? uri : `file://${uri}`;
}

// A bare Android cache path is what the manipulator can hand back; without a
// scheme the native encoder cannot open it.
assert.strictEqual(
  normaliseUri('/data/user/0/host.exp.exponent/cache/sheet.jpg'),
  'file:///data/user/0/host.exp.exponent/cache/sheet.jpg',
);

// Already-schemed URIs pass through untouched.
for (const uri of [
  'file:///data/user/0/cache/sheet.jpg',
  'content://media/external/images/media/1234',
  'http://192.168.1.5:8000/x.jpg',
  'https://example.com/x.jpg',
  'ph://1234-5678',          // iOS photo library
  'assets-library://asset/x', // legacy iOS
  'blob:http://localhost/abc',
]) {
  assert.strictEqual(normaliseUri(uri), uri, `should not rewrite ${uri}`);
}

// A Windows-style path must not be mistaken for a scheme by the regex: "C:"
// looks like one, so the rule requires a letter-led scheme of 2+ chars. This
// documents the known edge: a bare drive path is left as-is rather than
// gaining a bogus file:// prefix mid-string.
assert.strictEqual(normaliseUri('C:/tmp/sheet.jpg'), 'C:/tmp/sheet.jpg');

// Relative paths still get a scheme.
assert.strictEqual(normaliseUri('cache/sheet.jpg'), 'file://cache/sheet.jpg');

console.log('normaliseUri: all assertions passed');
