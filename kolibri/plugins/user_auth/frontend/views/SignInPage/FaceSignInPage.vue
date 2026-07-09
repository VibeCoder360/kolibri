<template>

  <AuthBase
    ref="authBaseRef"
    :busy="busy"
  >
    <template #header-leading-actions>
      <AuthContextHeading
        class="landscape-auth-context-heading"
        :useBackAction="hasMultipleFacilities"
        :backLabel="coreString('changeLearningFacility')"
        :backTo="backTo"
      />
    </template>

    <AuthContextHeading
      :useBackAction="hasMultipleFacilities"
      :backLabel="coreString('changeLearningFacility')"
      :backTo="backTo"
    />

    <div class="face-page-body">
      <h2 class="scan-title">{{ faceSignInTitle$() }}</h2>
      <p
        class="scan-description"
        :style="{ color: $themeTokens.annotation }"
      >
        {{ faceSignInDescription$() }}
      </p>

      <UiAlert
        v-if="notRecognized"
        class="error-alert"
        type="error"
        :dismissible="false"
      >
        {{ notRecognized$() }}
      </UiAlert>

      <!--
        While a capture is being validated the scanner is stopped; show a
        "Recognizing…" loader in its place rather than a dead black camera pane.
      -->
      <div
        v-if="busy"
        class="recognizing"
      >
        <KCircularLoader :delay="false" />
        <p :style="{ color: $themeTokens.annotation }">{{ recognizing$() }}</p>
      </div>
      <FaceScanner
        v-show="!busy"
        ref="scannerRef"
        @embedding="prevalidate"
      />
    </div>

    <!-- The QR confirm modal is credential-agnostic ("Is this you, {name}?") -->
    <QRSignInConfirmModal
      v-if="showConfirmModal"
      :learnerName="confirmedLearnerName"
      @confirm="handleConfirm"
      @cancel="handleCancel"
    />
  </AuthBase>

</template>


<script>

  import { computed, onMounted, ref } from 'vue';
  import useUser from 'kolibri/composables/useUser';
  import redirectBrowser from 'kolibri/utils/redirectBrowser';
  import { OptionsForSignIn } from 'kolibri-common/constants/Auth';
  import { useRouter, useRoute } from 'vue-router/composables';
  import commonCoreStrings, { coreString } from 'kolibri/uiText/commonCoreStrings';
  import { useFacilitySelect } from 'kolibri-common/composables/useFacility';
  import useSnackbar from 'kolibri/composables/useSnackbar';
  import { faceLoginStrings } from 'kolibri-common/strings/faceLoginStrings';
  import FaceScanner from 'kolibri-common/components/FaceScanner';
  import { encodeEmbedding } from 'kolibri-common/utils/faceRecognition';
  import UiAlert from 'kolibri-design-system/lib/keen/UiAlert';
  import KCircularLoader from 'kolibri-design-system/lib/loaders/KCircularLoader';
  import AuthBase from '../AuthBase';
  import useAuthFlow from '../../composables/useAuthFlow';
  import useAuthWatcher from '../../composables/useAuthWatcher';
  import useAuthRouter from '../../composables/useAuthRouter';
  import AuthContextHeading from '../AuthContextHeading.vue';
  import QRSignInConfirmModal from './QRSignIn/QRSignInConfirmModal.vue';

  export default {
    name: 'FaceSignInPage',
    components: {
      AuthBase,
      AuthContextHeading,
      FaceScanner,
      KCircularLoader,
      QRSignInConfirmModal,
      UiAlert,
    },
    mixins: [commonCoreStrings],
    setup() {
      const router = useRouter();
      const route = useRoute();
      const { login } = useUser();
      const { createSnackbar } = useSnackbar();
      const {
        faceSignInTitle$,
        faceSignInDescription$,
        recognizing$,
        notRecognized$,
        documentTitle$,
      } = faceLoginStrings;
      const { nextParam, defaultRoute, getFacilitySelectionRoute } = useAuthRouter(route);
      const { hasMultipleFacilities, facilityId, signInOptions } = useAuthFlow();
      const { watchForFacilityChange, watchForFacilityConfigChange } = useAuthWatcher();
      const { setSelectedFacilityId } = useFacilitySelect();

      const busy = ref(false);
      const showConfirmModal = ref(false);
      const confirmedLearnerName = ref('');
      const submittedEmbedding = ref('');
      const notRecognized = ref(false);

      // Template refs for calling public methods on child components.
      const authBaseRef = ref(null);
      const scannerRef = ref(null);
      const backTo = computed(() => {
        return hasMultipleFacilities.value ? getFacilitySelectionRoute(false) : null;
      });

      watchForFacilityChange((newFacilityId, oldFacilityId) => {
        if (
          (!newFacilityId && oldFacilityId) ||
          !signInOptions.value.includes(OptionsForSignIn.FACE_LOGIN)
        ) {
          router.push(defaultRoute.value);
        }
      });

      watchForFacilityConfigChange(() => {
        if (!signInOptions.value.includes(OptionsForSignIn.FACE_LOGIN)) {
          router.push(defaultRoute.value);
        }
      });

      // Start the camera when the page mounts.
      onMounted(() => {
        if (scannerRef.value && scannerRef.value.start) {
          scannerRef.value.start();
        }
      });

      function restartScanner() {
        if (scannerRef.value && scannerRef.value.start) {
          scannerRef.value.start();
        }
      }

      /**
       * Pre-validates the captured embedding by calling login() with
       * prevalidate=true, which returns { full_name } without creating a
       * session. On success we show the confirm modal so the learner can
       * verify their identity — mandatory for face login, since a 1:N match
       * can be wrong.
       *
       * @param {number[]} embedding
       * @return {Promise<void>}
       */
      async function prevalidate(embedding) {
        if (busy.value) return; // ignore captures already in flight
        busy.value = true;
        notRecognized.value = false;
        setSelectedFacilityId(facilityId.value);
        // Stop scanning while we validate so we don't fire duplicate events.
        if (scannerRef.value && scannerRef.value.stop) {
          scannerRef.value.stop();
        }
        try {
          // encodeEmbedding is inside the try so an unexpected encoding error
          // can never leave the scanner stopped with busy stuck true.
          const encoded = encodeEmbedding(embedding);
          const { data, error } = await login(
            { face_embedding: encoded, facility: facilityId.value },
            true,
            false,
          );
          if (data) {
            submittedEmbedding.value = encoded;
            confirmedLearnerName.value = data.full_name;
            showConfirmModal.value = true;
          } else if (error) {
            await authBaseRef.value.shake();
            notRecognized.value = true;
            restartScanner();
          } else {
            // Neither data nor a mapped error (e.g. an unexpected response
            // shape): never leave the scanner stopped with no feedback.
            restartScanner();
          }
        } catch (error) {
          createSnackbar({
            text: coreString('defaultErrorMessage'),
            autoDismiss: true,
          });
          restartScanner();
        } finally {
          busy.value = false;
        }
      }

      async function handleConfirm() {
        busy.value = true;
        const sessionPayload = {
          facility: facilityId.value,
          face_embedding: submittedEmbedding.value,
        };
        if (nextParam.value) {
          sessionPayload['next'] = nextParam.value;
        }
        try {
          const { error } = await login(sessionPayload, false, false);
          if (error) {
            showConfirmModal.value = false;
            submittedEmbedding.value = '';
            confirmedLearnerName.value = '';
            await authBaseRef.value.shake();
            notRecognized.value = true;
            restartScanner();
          } else {
            showConfirmModal.value = false;
            redirectBrowser(nextParam.value || undefined);
          }
        } catch {
          createSnackbar({
            text: coreString('defaultErrorMessage'),
            autoDismiss: true,
          });
          restartScanner();
        } finally {
          busy.value = false;
        }
      }

      function handleCancel() {
        showConfirmModal.value = false;
        submittedEmbedding.value = '';
        confirmedLearnerName.value = '';
        // Tell the scanner to reset so it can accept a new capture.
        restartScanner();
      }

      return {
        // state
        busy,
        showConfirmModal,
        confirmedLearnerName,
        notRecognized,
        backTo,
        hasMultipleFacilities,
        // template refs
        authBaseRef,
        scannerRef,
        // actions
        prevalidate,
        handleConfirm,
        handleCancel,
        // strings
        faceSignInTitle$,
        faceSignInDescription$,
        recognizing$,
        notRecognized$,
        documentTitle$,
      };
    },
    metaInfo() {
      return { title: this.documentTitle$() };
    },
  };

</script>


<style lang="scss" scoped>

  .face-page-body {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
    margin-top: 16px;
  }

  .scan-title {
    margin: 0 0 8px;
    font-size: 20px;
    font-weight: 600;
    text-align: center;
  }

  .scan-description {
    margin: 0 0 24px;
    font-size: 14px;
    text-align: center;
  }

  .error-alert {
    width: 100%;
    max-width: 360px;
    margin-bottom: 16px;
    text-align: start;
  }

  .recognizing {
    display: flex;
    flex-direction: column;
    gap: 12px;
    align-items: center;
    justify-content: center;
    width: 100%;
    max-width: 360px;
    aspect-ratio: 1 / 1;

    p {
      margin: 0;
      font-size: 14px;
      text-align: center;
    }
  }

  .landscape-auth-context-heading {
    margin-top: 0;
  }

</style>
