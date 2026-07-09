<template>

  <div class="face-scanner">
    <!--
      Live camera view. Rendered only when getUserMedia is available (HTTPS or
      localhost). On non-secure LAN deployments the camera pane is not shown.
    -->
    <div
      v-if="canUseCamera"
      class="camera-pane"
    >
      <video
        ref="videoRef"
        class="camera-video"
        :class="{ hidden: status !== 'streaming' && status !== 'scanning' }"
        autoplay
        muted
        playsinline
      ></video>

      <!-- Viewfinder overlay -->
      <div
        v-if="status === 'streaming' || status === 'scanning'"
        class="viewfinder"
        aria-hidden="true"
      >
        <div class="viewfinder-frame"></div>
      </div>

      <!--
        Status / instruction overlay. Hidden when idle so a stopped scanner
        shows a plain pane rather than a stale "look at the camera" hint over
        a black (video-hidden) pane.
      -->
      <div
        v-if="status !== 'idle'"
        class="camera-status"
      >
        <KCircularLoader
          v-if="status === 'starting' || status === 'loading-models'"
          :delay="false"
        />
        <p>{{ statusMessage$() }}</p>
      </div>
    </div>

    <!-- Error states -->
    <UiAlert
      v-if="!canUseCamera"
      class="status-alert"
      type="error"
      :dismissible="false"
    >
      {{ secureContextRequired$() }}
    </UiAlert>
    <UiAlert
      v-else-if="status === 'permission-denied'"
      class="status-alert"
      type="error"
      :dismissible="false"
    >
      {{ cameraPermissionDenied$() }}
    </UiAlert>
    <UiAlert
      v-else-if="status === 'no-camera'"
      class="status-alert"
      type="error"
      :dismissible="false"
    >
      {{ cameraNotFound$() }}
    </UiAlert>
    <UiAlert
      v-else-if="status === 'unavailable'"
      class="status-alert"
      type="error"
      :dismissible="false"
    >
      {{ cameraUnavailable$() }}
    </UiAlert>
  </div>

</template>


<script>

  import { onBeforeUnmount, ref, computed } from 'vue';
  import { qrLoginStrings } from 'kolibri-common/strings/qrLoginStrings';
  import { faceLoginStrings } from 'kolibri-common/strings/faceLoginStrings';
  import cameraSupported from 'kolibri-common/utils/cameraSupported';
  import UiAlert from 'kolibri-design-system/lib/keen/UiAlert';
  import KCircularLoader from 'kolibri-design-system/lib/loaders/KCircularLoader';
  import { getHuman, detectSingleFace } from 'kolibri-common/utils/faceRecognition';

  // Milliseconds between detection attempts. Keeps CPU load reasonable on
  // low-resource devices while still feeling responsive.
  const DETECT_INTERVAL = 400;
  // A face must be present in this many consecutive frames before we emit an
  // embedding — rejects blurry/transitional captures cheaply.
  const STABLE_FRAMES = 3;

  export default {
    name: 'FaceScanner',
    components: { UiAlert, KCircularLoader },
    props: {
      // 'continuous' (default): auto-detect and emit once a face is stable
      // across frames — used for sign-in. 'manual': do not auto-detect; the
      // parent calls capture() (via template ref) to grab a single sample —
      // used for enrollment.
      manual: {
        type: Boolean,
        default: false,
      },
    },
    setup(props, { emit }) {
      const {
        cameraStarting$,
        secureContextRequired$,
        cameraPermissionDenied$,
        cameraNotFound$,
        cameraUnavailable$,
      } = qrLoginStrings;
      const { lookAtCamera$, loadingModels$ } = faceLoginStrings;

      const videoRef = ref(null);
      /**
       * Scanner lifecycle status:
       *   idle | starting | loading-models | streaming | scanning
       *   permission-denied | no-camera | unavailable
       */
      const status = ref('idle');

      let activeStream = null;
      let loopActive = false;
      let loopTimeout = null;
      // Set once models finish loading; used by capture() in manual mode.
      let loadedHuman = null;

      const canUseCamera = computed(() => cameraSupported());

      const statusMessage$ = computed(() => {
        if (status.value === 'starting') return cameraStarting$;
        if (status.value === 'loading-models') return loadingModels$;
        return lookAtCamera$;
      });

      async function start() {
        if (!canUseCamera.value) {
          status.value = 'unavailable';
          return;
        }
        // Re-entrancy guard: a second start() before the first settles would
        // overwrite activeStream (leaking the first MediaStream's tracks) and
        // spawn a duplicate detection loop sharing one loopTimeout handle.
        if (['starting', 'loading-models', 'streaming', 'scanning'].includes(status.value)) {
          return;
        }
        status.value = 'starting';
        try {
          const stream = await navigator.mediaDevices.getUserMedia({
            // Selfie camera: the person signing in is facing the screen.
            video: { facingMode: { ideal: 'user' } },
            audio: false,
          });
          activeStream = stream;
          const videoEl = videoRef.value;
          if (!videoEl) {
            // Component unmounted during await.
            teardownStream();
            return;
          }
          videoEl.srcObject = stream;
          await videoEl.play().catch(() => {
            // Autoplay can race; play() rejection is recoverable once the
            // stream has enough data, so we don't surface it as an error.
          });
          status.value = 'loading-models';
          const human = await getHuman();
          if (!activeStream) {
            // stop() was called while models were loading.
            return;
          }
          loadedHuman = human;
          status.value = 'scanning';
          // Signal readiness so a parent (e.g. the enrollment wizard) can
          // enable its capture control only once models are loaded.
          emit('ready');
          // In manual mode we wait for the parent to call capture(); otherwise
          // run the continuous detect-and-emit loop used for sign-in.
          if (!props.manual) {
            runDetectionLoop(human, videoEl);
          }
        } catch (err) {
          handleCameraError(err);
        }
      }

      /**
       * Grab a single face sample on demand (manual/enrollment mode). Emits
       * 'embedding' with the descriptor on success, or 'capture-error' with an
       * error code ('no-face' | 'multiple-faces' | 'low-quality' | 'not-ready').
       */
      async function capture() {
        const videoEl = videoRef.value;
        if (!loadedHuman || !videoEl || status.value !== 'scanning') {
          emit('capture-error', 'not-ready');
          return;
        }
        try {
          const result = await detectSingleFace(loadedHuman, videoEl);
          if (result.embedding) {
            emit('embedding', result.embedding);
          } else {
            emit('capture-error', result.error);
          }
        } catch (err) {
          emit('capture-error', 'low-quality');
        }
      }

      /**
       * Poll-based detection loop. Emits 'embedding' once a face has been
       * present for STABLE_FRAMES consecutive attempts, then stops so the
       * parent can prevalidate without duplicate submissions.
       */
      function runDetectionLoop(human, videoEl) {
        loopActive = true;
        let consecutive = 0;
        let lastEmbedding = null;
        const tick = async () => {
          if (!loopActive) return;
          try {
            const result = await detectSingleFace(human, videoEl);
            if (result.embedding) {
              consecutive += 1;
              lastEmbedding = result.embedding;
            } else {
              consecutive = 0;
              lastEmbedding = null;
            }
          } catch (err) {
            // detect() can throw on transient empty frames; just keep going.
            consecutive = 0;
          }
          // stop()/teardown may have run during the await above; don't emit
          // into a torn-down or navigated-away parent.
          if (!loopActive) return;
          if (consecutive >= STABLE_FRAMES && lastEmbedding) {
            loopActive = false;
            emit('embedding', lastEmbedding);
            return;
          }
          if (loopActive) {
            loopTimeout = setTimeout(tick, DETECT_INTERVAL);
          }
        };
        tick();
      }

      function handleCameraError(err) {
        const name = err && err.name;
        if (name === 'NotAllowedError' || name === 'SecurityError') {
          status.value = 'permission-denied';
        } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
          status.value = 'no-camera';
        } else {
          status.value = 'unavailable';
        }
        teardownStream();
      }

      function teardownStream() {
        loopActive = false;
        loadedHuman = null;
        if (loopTimeout) {
          clearTimeout(loopTimeout);
          loopTimeout = null;
        }
        if (activeStream) {
          for (const track of activeStream.getTracks()) {
            try {
              track.stop();
            } catch (err) {
              // ignore
            }
          }
          activeStream = null;
        }
      }

      function stop() {
        status.value = 'idle';
        teardownStream();
      }

      onBeforeUnmount(() => {
        stop();
      });

      return {
        videoRef,
        status,
        canUseCamera,
        statusMessage$,
        secureContextRequired$,
        cameraPermissionDenied$,
        cameraNotFound$,
        cameraUnavailable$,
        // eslint-disable-next-line vue/no-unused-properties -- called by parent via template ref
        start,
        // eslint-disable-next-line vue/no-unused-properties -- called by parent via template ref
        stop,
        // eslint-disable-next-line vue/no-unused-properties -- called by parent via template ref
        capture,
      };
    },
  };

</script>


<style lang="scss" scoped>

  .face-scanner {
    display: flex;
    flex-direction: column;
    gap: 16px;
    align-items: center;
    width: 100%;
  }

  .camera-pane {
    position: relative;
    width: 100%;
    max-width: 360px;
    aspect-ratio: 1 / 1;
    overflow: hidden;
    background-color: black;
    border-radius: 8px;
  }

  .camera-video {
    width: 100%;
    height: 100%;
    object-fit: cover;

    &.hidden {
      visibility: hidden;
    }
  }

  .viewfinder {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    pointer-events: none;
  }

  .viewfinder-frame {
    width: 60%;
    height: 75%;
    border: 2px solid rgba(255, 255, 255, 0.9);
    border-radius: 50%;
    box-shadow: 0 0 0 9999px rgba(0, 0, 0, 0.25);
  }

  .camera-status {
    position: absolute;
    right: 0;
    bottom: 8px;
    left: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    align-items: center;
    padding: 0 16px;
    text-align: center;
    pointer-events: none;

    p {
      margin: 0;
      font-size: 13px;
      color: rgba(255, 255, 255, 0.95);
    }
  }

  .status-alert {
    width: 100%;
    max-width: 360px;
  }

</style>
