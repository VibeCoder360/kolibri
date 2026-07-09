/**
 * A secure context (HTTPS or localhost) is required for getUserMedia. Kolibri is
 * frequently deployed over plain HTTP on a LAN, so camera-based sign-in options
 * (QR scanning, face login) must check this before offering camera UI.
 */
export default function cameraSupported() {
  return Boolean(
    typeof window !== 'undefined' &&
      window.isSecureContext &&
      typeof navigator !== 'undefined' &&
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function',
  );
}
