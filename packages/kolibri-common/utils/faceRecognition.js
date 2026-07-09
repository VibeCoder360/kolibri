/**
 * Thin wrapper around @vladmandic/human for face login.
 *
 * Everything runs in the browser — no face image ever leaves the device; only
 * the numeric descriptor (embedding) is sent to the Kolibri server for
 * matching. Model files are served as Kolibri static assets from
 * kolibri/plugins/user_auth/static/assets/faceModels/ (copied from the
 * @vladmandic/human npm package: blazeface detector + faceres descriptor; the
 * .bin weights are tracked via Git LFS), so recognition works fully offline —
 * verify no CDN requests in the network tab.
 */
import urls from 'kolibri/urls';

// Must equal CURRENT_EMBEDDING_VERSION in
// kolibri/core/auth/utils/face_embeddings.py. Bump both together when the
// descriptor model changes; enrolled users must then re-enroll.
export const EMBEDDING_VERSION = 1;

// Lazy singleton: the library is a separate webpack chunk loaded only when a
// face page is actually visited, and models load once per page lifetime.
let humanPromise = null;

export function getHuman() {
  if (!humanPromise) {
    humanPromise = import('@vladmandic/human')
      .then(({ default: Human }) => {
      const human = new Human({
        modelBasePath: urls.static('assets/faceModels/'),
        // webgl needs no extra asset files (unlike wasm) and auto-falls back
        // to the cpu backend on devices without GPU acceleration.
        backend: 'webgl',
        filter: { enabled: false },
        // Privacy: descriptor ONLY — demographic inference (age/gender/
        // emotion) stays disabled. Kolibri must not infer anything about the
        // person beyond the login match.
        face: {
          enabled: true,
          // maxDetected 2 so we can detect (and reject) multiple faces.
          detector: { rotation: false, maxDetected: 2 },
          mesh: { enabled: false },
          iris: { enabled: false },
          emotion: { enabled: false },
          antispoof: { enabled: false },
          liveness: { enabled: false },
          description: { enabled: true },
        },
        body: { enabled: false },
        hand: { enabled: false },
        object: { enabled: false },
        gesture: { enabled: false },
      });
      return human.load().then(() => human);
      })
      .catch(err => {
        // Don't cache a rejected load (e.g. model assets 404): otherwise every
        // subsequent getHuman() would return the same rejection and face login
        // would be permanently broken until a full page reload.
        humanPromise = null;
        throw err;
      });
  }
  return humanPromise;
}

/**
 * Encode an embedding as base64 little-endian float32 — the byte format
 * decode_embedding() on the server expects.
 * @param {number[]} values
 * @return {string}
 */
export function encodeEmbedding(values) {
  const buffer = new ArrayBuffer(values.length * 4);
  const view = new DataView(buffer);
  values.forEach((value, i) => view.setFloat32(i * 4, value, true));
  let binary = '';
  new Uint8Array(buffer).forEach(byte => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary);
}

/**
 * Detect exactly one usable face in the current video frame.
 *
 * @param {object} human A loaded Human instance from getHuman()
 * @param {HTMLVideoElement} videoEl
 * @return {Promise<{embedding: number[]}|{error: string}>} error is one of
 *   'no-face' | 'multiple-faces' | 'low-quality'
 */
export async function detectSingleFace(human, videoEl) {
  const result = await human.detect(videoEl);
  const faces = (result.face || []).filter(f => f.embedding && f.embedding.length);
  if (faces.length === 0) {
    return { error: 'no-face' };
  }
  if (faces.length > 1) {
    return { error: 'multiple-faces' };
  }
  const face = faces[0];
  // Quality gates: confident detection and a face large enough in frame that
  // the descriptor is meaningful. Bad captures are rejected here so they
  // never reach the server or the enrollment gallery.
  const [, , width, height] = face.box;
  if (
    face.boxScore < 0.6 ||
    width < videoEl.videoWidth * 0.2 ||
    height < videoEl.videoHeight * 0.2
  ) {
    return { error: 'low-quality' };
  }
  return { embedding: Array.from(face.embedding) };
}
