<template>

  <KModal
    :title="alreadyEnrolled ? removeFaceSignIn$() : setUpFaceSignIn$()"
    :submitText="alreadyEnrolled ? removeFaceSignIn$() : coreString('saveAction')"
    :cancelText="coreString('cancelAction')"
    :submitDisabled="submitDisabled"
    @submit="handleSubmit"
    @cancel="$emit('cancel')"
  >
    <template v-if="alreadyEnrolled">
      <p>{{ removeConfirmation$() }}</p>
    </template>

    <template v-else>
      <p class="instructions">
        {{ faceEnrollmentInstructions$({ total: TOTAL_SAMPLES }) }}
      </p>

      <FaceScanner
        ref="scannerRef"
        :manual="true"
        @ready="scannerReady = true"
        @embedding="onCapture"
        @capture-error="onCaptureError"
      />

      <p
        class="progress"
        :style="{ color: $themeTokens.annotation }"
      >
        {{ captureProgress$({ count: samples.length, total: TOTAL_SAMPLES }) }}
      </p>

      <KButton
        :text="captureSample$()"
        :primary="false"
        :disabled="!scannerReady || busy || capturing || samples.length >= TOTAL_SAMPLES"
        @click="captureSample"
      />
      <KButton
        v-if="samples.length"
        :text="startOver$()"
        appearance="basic-link"
        @click="reset"
      />

      <UiAlert
        v-if="captureError"
        type="error"
        :dismissible="false"
      >
        {{ captureError }}
      </UiAlert>

      <KCheckbox
        :checked="consent"
        :label="consentLabel$()"
        @change="consent = $event"
      />
    </template>
  </KModal>

</template>


<script>

  import { computed, onMounted, ref } from 'vue';
  import { coreString } from 'kolibri/uiText/commonCoreStrings';
  import useSnackbar from 'kolibri/composables/useSnackbar';
  import FacilityUserResource from 'kolibri-common/apiResources/FacilityUserResource';
  import { faceLoginStrings } from 'kolibri-common/strings/faceLoginStrings';
  import { encodeEmbedding, EMBEDDING_VERSION } from 'kolibri-common/utils/faceRecognition';
  import UiAlert from 'kolibri-design-system/lib/keen/UiAlert';
  import FaceScanner from 'kolibri-common/components/FaceScanner';

  // Number of face samples captured per user. Multiple samples across small
  // pose/expression variations markedly reduce false rejects at sign-in.
  const TOTAL_SAMPLES = 3;

  export default {
    name: 'FaceEnrollment',
    components: { FaceScanner, UiAlert },
    setup(props, { emit }) {
      const { createSnackbar } = useSnackbar();
      const {
        setUpFaceSignIn$,
        removeFaceSignIn$,
        faceEnrollmentInstructions$,
        captureSample$,
        captureProgress$,
        captureFailedNoFace$,
        captureFailedMultipleFaces$,
        captureFailedLowQuality$,
        consentLabel$,
        startOver$,
        enrollmentSaved$,
        enrollmentRemoved$,
        enrollmentFailed$,
        removeConfirmation$,
      } = faceLoginStrings;

      const scannerRef = ref(null);
      // Raw embeddings (arrays of floats); encoded to base64 only on save.
      const samples = ref([]);
      const consent = ref(false);
      const captureError = ref('');
      const busy = ref(false);
      // True once the scanner has loaded models and is ready to capture.
      const scannerReady = ref(false);
      // Guards against overlapping capture() calls from rapid clicks, which
      // would otherwise sample the same frame/pose multiple times.
      const capturing = ref(false);

      const submitDisabled = computed(() => {
        if (busy.value) {
          return true;
        }
        if (props.alreadyEnrolled) {
          return false;
        }
        return samples.value.length < TOTAL_SAMPLES || !consent.value;
      });

      onMounted(() => {
        // Only the capture UI needs the camera; the remove-confirmation view
        // does not.
        if (!props.alreadyEnrolled && scannerRef.value && scannerRef.value.start) {
          scannerRef.value.start();
        }
      });

      function captureSample() {
        if (capturing.value) {
          return;
        }
        captureError.value = '';
        if (scannerRef.value && scannerRef.value.capture) {
          capturing.value = true;
          scannerRef.value.capture();
        }
      }

      function onCapture(embedding) {
        capturing.value = false;
        if (samples.value.length < TOTAL_SAMPLES) {
          samples.value.push(embedding);
        }
      }

      function onCaptureError(code) {
        capturing.value = false;
        if (code === 'multiple-faces') {
          captureError.value = captureFailedMultipleFaces$();
        } else if (code === 'no-face') {
          captureError.value = captureFailedNoFace$();
        } else {
          captureError.value = captureFailedLowQuality$();
        }
      }

      function reset() {
        samples.value = [];
        captureError.value = '';
      }

      async function handleSubmit() {
        busy.value = true;
        try {
          if (props.alreadyEnrolled) {
            await FacilityUserResource.clearFace(props.userId);
            createSnackbar(enrollmentRemoved$());
          } else {
            await FacilityUserResource.enrollFace(
              props.userId,
              samples.value.map(encodeEmbedding),
              consent.value,
              EMBEDDING_VERSION,
            );
            createSnackbar(enrollmentSaved$());
          }
          emit('success');
        } catch (error) {
          createSnackbar(enrollmentFailed$());
        } finally {
          busy.value = false;
        }
      }

      return {
        TOTAL_SAMPLES,
        EMBEDDING_VERSION,
        scannerRef,
        samples,
        consent,
        captureError,
        busy,
        scannerReady,
        capturing,
        submitDisabled,
        captureSample,
        onCapture,
        onCaptureError,
        reset,
        handleSubmit,
        coreString,
        // strings
        setUpFaceSignIn$,
        removeFaceSignIn$,
        faceEnrollmentInstructions$,
        captureSample$,
        captureProgress$,
        consentLabel$,
        startOver$,
        removeConfirmation$,
      };
    },
    props: {
      userId: {
        type: String,
        required: true,
      },
      // When true, the modal offers to remove existing enrollment instead of
      // capturing new samples.
      alreadyEnrolled: {
        type: Boolean,
        default: false,
      },
    },
    emits: ['success', 'cancel'],
  };

</script>


<style lang="scss" scoped>

  .instructions {
    margin-top: 0;
  }

  .progress {
    margin: 12px 0 4px;
    font-size: 13px;
  }

</style>
