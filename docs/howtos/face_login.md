.. _face-login-howto:

==============================
Face recognition sign-in
==============================

This how-to explains how to enable and operate **face recognition sign-in**
for a Kolibri facility. Face sign-in lets a user sign in by facing the device
camera instead of typing a username and password (or in addition to the QR and
picture-password methods).

When it is enabled and the device has a usable camera, face sign-in becomes the
**default** sign-in method; QR, picture password, and username/password remain
available as secondary options linked from the face sign-in page.

How it works
============

- The **browser** captures a camera frame and computes a face *embedding* (a
  numeric descriptor vector) locally using a WebAssembly model
  (``@vladmandic/human``). No face image is ever uploaded; only the embedding
  is sent to the server.
- The **Kolibri server** compares the probe embedding against the embeddings of
  enrolled users in that facility (1:N nearest-neighbour with a cosine-distance
  threshold) and returns the single best match, if any.
- The recognised name is shown for **explicit confirmation** ("Is this you,
  *Name*?") before a session is created — reusing the same prevalidate/confirm
  flow as QR sign-in.

Everything runs **offline**. The model files are served as Kolibri static
assets (``kolibri/plugins/user_auth/static/assets/faceModels/``); no cloud
service is contacted. This is why embeddings are computed in the browser rather
than the server: it keeps heavyweight ML libraries out of the Python backend
(which must package for Android and low-resource devices) and keeps the raw
face on the device.

A plain RGB webcam or built-in laptop/tablet camera is sufficient — no infrared
or depth hardware (as used by Windows Hello) is required or used. Windows Hello
is an operating-system account login and cannot authenticate a Kolibri
``FacilityUser``.

Enabling face sign-in
=====================

1. Sign in as a facility admin or super admin.
2. Go to **Facility → Settings**.
3. Check **"Allow users to sign in with face recognition"** and save.

The setting is **off by default**. Enabling it does not disable any other
sign-in method.

Enrolling users
===============

Face login must be **enabled for the facility** (above) before anyone can be
enrolled — the enrollment API rejects requests for facilities where the feature
is off. Unlike QR tokens, face data cannot be bulk-assigned; each user is
enrolled individually with a short capture wizard:

- **Self-enrollment:** a user signs in (with password or QR), goes to their
  **Profile** page, and chooses **"Set up face sign-in"**.
- The wizard captures **3 samples** across slight pose variations, computes the
  embeddings in the browser, and requires a **consent acknowledgement** before
  saving.
- To remove enrollment, choose **"Remove face sign-in"** on the same page.

.. note::

   The enrollment API also permits a facility admin or super admin to enroll
   (or remove) another user's face, but the only shipped UI is self-enrollment
   on the Profile page. An admin-facing enrollment surface (e.g. in the
   facility user editor) is a planned follow-up.

.. note::

   Consent is a hard requirement in the enrollment API: the request is rejected
   unless the enroller confirms consent has been obtained. See "Privacy and
   consent" below.

Reliability
===========

Face recognition is 1:N identification, which is inherently riskier than 1:1
verification (unlocking your own phone). Several measures make it dependable
enough for a classroom of up to a few hundred users:

- **Multi-sample enrollment** — matching against a user's *nearest* sample
  greatly reduces false rejects from lighting/pose/glasses.
- **Ambiguity margin** — a match is accepted only when the best candidate is
  both close enough (``FACE_LOGIN_DISTANCE_THRESHOLD``) **and** clearly closer
  than the runner-up (``FACE_LOGIN_DISTANCE_MARGIN``). Near-ties (e.g. siblings)
  are rejected rather than guessed.
- **Multi-frame capture** — the scanner requires a face to be stable across
  several frames before submitting.
- **Mandatory confirmation** — even a wrong match becomes "wrong name shown,
  tap No" instead of a wrong login.

Tuning the thresholds
---------------------

Both thresholds are configurable via ``kolibri.utils.options`` (the ``[Auth]``
section of ``options.ini`` or the corresponding environment variables), so a
deployment can tighten or loosen matching without a code change:

.. code-block:: ini

   [Auth]
   # Maximum cosine distance for a match (lower = stricter)
   FACE_LOGIN_DISTANCE_THRESHOLD = 0.4
   # Minimum gap to the runner-up user (higher = rejects more ambiguous matches)
   FACE_LOGIN_DISTANCE_MARGIN = 0.05

Privacy, consent, and data handling
===================================

Face data is biometric data, and users are frequently minors. The
implementation is built around minimising and localising that data:

- **Embeddings only, never images.** The stored value is a non-reversible
  numeric descriptor; raw photos are not retained.
- **Device-local, never synced.** Enrollment is stored in a non-syncable
  ``FacilityUserFaceData`` model, so biometric templates never propagate to
  other servers or to the Kolibri Data Portal via Morango. Face sign-in
  therefore only works on the server where the user enrolled.
- **No demographic inference.** The recognition engine is configured to emit
  only the face descriptor — age/gender/emotion inference is disabled.
- **Consent required.** Enrollment records a consent acknowledgement.
  Deployments must obtain appropriate consent (parental/guardian consent for
  minors) per applicable law (e.g. GDPR, COPPA, BIPA) before enrolling anyone.
- **Audit trail.** Every face sign-in attempt is logged (facility and matched
  user id, or "did not match") — never the embedding itself.

Known limitations
=================

- **Camera requires a secure context.** ``getUserMedia`` only works over HTTPS
  or ``localhost``. On a plain-HTTP LAN deployment (e.g. tablets connecting to
  ``http://192.168.x.x``) the camera is unavailable, and the sign-in flow falls
  back to the non-face default. This is the same limitation as QR scanning.
- **No liveness detection (v1).** A printed photo could potentially fool
  recognition. This is mitigated by the confirmation step and audit logging;
  passive liveness (e.g. blink detection) is a candidate for a future version.
- **Accuracy varies** by lighting and across demographics. Keep the
  username/password fallback available and prominent.
- **Re-enrollment on model change.** Embeddings are stored with an
  ``embedding_version``. If the descriptor model is upgraded (version bumped),
  existing enrollments are ignored at match time and users must re-enroll.
