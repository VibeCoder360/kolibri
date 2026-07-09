import { encodeEmbedding } from '../faceRecognition';

// faceRecognition.js imports kolibri/urls at module load (used by getHuman);
// encodeEmbedding itself does not need it, so stub the module.
jest.mock('kolibri/urls');

describe('encodeEmbedding', () => {
  it('produces the golden little-endian float32 base64 (cross-language contract)', () => {
    // This MUST equal GOLDEN_BASE64 in
    // kolibri/core/auth/test/test_face_embeddings.py. The browser encodes the
    // probe/enrollment embeddings and the Python server decodes them; if the
    // two byte formats ever diverge, enrollment silently stores vectors the
    // server cannot match. Pinning the same golden value on both sides guards
    // that contract.
    expect(encodeEmbedding([1.0, -2.0, 0.5, 0.0])).toBe('AACAPwAAAMAAAAA/AAAAAA==');
  });

  it('encodes an empty vector as an empty base64 string', () => {
    expect(encodeEmbedding([])).toBe('');
  });

  it('returns a string for typical descriptor values', () => {
    expect(typeof encodeEmbedding([0.1, 0.2, 0.3])).toBe('string');
  });
});
