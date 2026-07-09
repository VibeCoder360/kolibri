import { render, screen, fireEvent } from '@testing-library/vue';
import { ref } from 'vue';
import useUser, { useUserMock } from 'kolibri/composables/useUser'; // eslint-disable-line import-x/named
import { OptionsForSignIn } from 'kolibri-common/constants/Auth';
import { faceLoginStrings } from 'kolibri-common/strings/faceLoginStrings';
import { qrLoginStrings } from 'kolibri-common/strings/qrLoginStrings';
import redirectBrowser from 'kolibri/utils/redirectBrowser';
import { useRoute, useRouter } from 'vue-router/composables';
import useAuthFlow from '../../../composables/useAuthFlow';
import useAuthWatcher from '../../../composables/useAuthWatcher';
import useAuthRouter from '../../../composables/useAuthRouter';
import FaceSignInPage from '../FaceSignInPage.vue';

jest.mock('kolibri/composables/useUser');
jest.mock('kolibri/composables/useSnackbar');
jest.mock('kolibri/utils/redirectBrowser');
jest.mock('kolibri/urls');
jest.mock('kolibri/client');
// The face recognition engine (human.js + camera) is exercised in FaceScanner;
// here we only care about the embedding -> prevalidate -> confirm flow, so we
// stub the module and the scanner component.
jest.mock('kolibri-common/utils/faceRecognition', () => ({
  __esModule: true,
  EMBEDDING_VERSION: 1,
  encodeEmbedding: jest.fn(() => 'ENCODED_EMBEDDING'),
  getHuman: jest.fn(),
  detectSingleFace: jest.fn(),
}));
jest.mock('kolibri-plugin-data', () => ({
  __esModule: true,
  default: {
    allowRemoteAccess: true,
    oidcProviderEnabled: false,
    allowGuestAccess: false,
    deviceUnusableReason: null,
  },
}));

jest.mock('../../../composables/useAuthFlow');
jest.mock('../../../composables/useAuthRouter');
jest.mock('../../../composables/useAuthWatcher');
jest.mock('vue-router/composables');
// The real confirm modal calls this on mount; no-op it in tests.
jest.mock('kolibri-common/composables/useReturnFocusOnUnmount', () => ({
  __esModule: true,
  default: jest.fn(),
}));

// Stub that lets the test drive the scanner's `embedding` event and no-ops the
// start()/stop() template-ref methods the page calls.
const FaceScannerStub = {
  name: 'FaceScanner',
  methods: {
    start() {},
    stop() {},
  },
  template: `<button data-testid="emit-embedding" @click="$emit('embedding', [0.1, 0.2, 0.3])">emit</button>`,
};

// Stub the confirm modal with explicit confirm/cancel buttons so the test does
// not depend on KModal internals.
const ConfirmModalStub = {
  name: 'QRSignInConfirmModal',
  props: ['learnerName'],
  template: `<div data-testid="confirm-modal">
    <span data-testid="learner-name">{{ learnerName }}</span>
    <button data-testid="confirm" @click="$emit('confirm')">confirm</button>
    <button data-testid="cancel" @click="$emit('cancel')">cancel</button>
  </div>`,
};

function renderComponent({ login, realConfirmModal = false } = {}) {
  useRoute.mockReturnValue({ query: {} });
  useRouter.mockReturnValue({ push: jest.fn() });
  useUser.mockReturnValue(
    useUserMock({
      login: login || jest.fn(),
      isAppContext: true,
      isUserLoggedIn: false,
      userFacilityId: null,
      isSuperuser: false,
    }),
  );
  useAuthFlow.mockReturnValue({
    hasMultipleFacilities: ref(false),
    facilityId: ref('facility_1'),
    selectedFacility: ref({ id: 'facility_1', name: 'Facility 1' }),
    signInOptions: ref([OptionsForSignIn.FACE_LOGIN]),
    signInMethod: ref(OptionsForSignIn.FACE_LOGIN),
    canSignUp: ref(false),
  });
  useAuthWatcher.mockReturnValue({
    watchForFacilityChange: jest.fn(),
    watchForFacilityConfigChange: jest.fn(),
  });
  useAuthRouter.mockReturnValue({
    nextParam: ref(null),
    defaultRoute: ref({ name: 'SignInPage' }),
    faceSignInRoute: ref({ name: 'FaceSignInPage' }),
    qrSignInRoute: ref({ name: 'QRSignInPage' }),
    usernameSignInRoute: ref({ name: 'SignInPage' }),
    signUpRoute: ref({ name: 'SignUpPage' }),
    getFacilitySelectionRoute: jest.fn(),
  });

  // Always stub the scanner (camera/human.js); optionally keep the REAL
  // confirm modal so a test can catch regressions in it (e.g. a setup() crash
  // that renders the modal as nothing).
  const stubs = { FaceScanner: FaceScannerStub };
  if (!realConfirmModal) {
    stubs.QRSignInConfirmModal = ConfirmModalStub;
  }

  return render(FaceSignInPage, {
    routes: [
      { name: 'FaceSignInPage', path: '/face-signin' },
      { name: 'SignInPage', path: '/signin' },
    ],
    stubs,
  });
}

describe('FaceSignInPage', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'isSecureContext', {
      value: true,
      configurable: true,
      writable: true,
    });
    window.matchMedia = jest.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    }));
  });

  it('renders the page heading and description', () => {
    renderComponent();
    expect(screen.getByText(faceLoginStrings.faceSignInTitle$())).toBeInTheDocument();
    expect(screen.getByText(faceLoginStrings.faceSignInDescription$())).toBeInTheDocument();
  });

  it('does not render the confirm modal or an error on initial render', () => {
    renderComponent();
    expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();
    expect(screen.queryByText(faceLoginStrings.notRecognized$())).not.toBeInTheDocument();
  });

  it('prevalidates a captured embedding and shows the confirm modal', async () => {
    const login = jest.fn().mockResolvedValue({ data: { full_name: 'Ada Lovelace' } });
    renderComponent({ login });

    await fireEvent.click(screen.getByTestId('emit-embedding'));

    expect(login).toHaveBeenCalledWith(
      { face_embedding: 'ENCODED_EMBEDDING', facility: 'facility_1' },
      true,
      false,
    );
    expect(await screen.findByTestId('confirm-modal')).toBeInTheDocument();
    expect(screen.getByTestId('learner-name')).toHaveTextContent('Ada Lovelace');
  });

  it('creates a session and redirects on confirm', async () => {
    const login = jest
      .fn()
      .mockResolvedValueOnce({ data: { full_name: 'Ada Lovelace' } }) // prevalidate
      .mockResolvedValueOnce({}); // confirm
    renderComponent({ login });

    await fireEvent.click(screen.getByTestId('emit-embedding'));
    await fireEvent.click(await screen.findByTestId('confirm'));

    expect(login).toHaveBeenLastCalledWith(
      { facility: 'facility_1', face_embedding: 'ENCODED_EMBEDDING' },
      false,
      false,
    );
    expect(redirectBrowser).toHaveBeenCalled();
  });

  it('shows the not-recognized error when prevalidation fails', async () => {
    const login = jest.fn().mockResolvedValue({ error: 'NOT_FOUND' });
    renderComponent({ login });

    await fireEvent.click(screen.getByTestId('emit-embedding'));

    expect(await screen.findByText(faceLoginStrings.notRecognized$())).toBeInTheDocument();
    expect(screen.queryByTestId('confirm-modal')).not.toBeInTheDocument();
  });

  // Regression guard: the REAL confirm modal must actually render on a
  // successful prevalidate. The original black-screen bug was a setup() crash
  // in QRSignInConfirmModal that made it mount as nothing — a stubbed modal
  // (used above) hid it. This renders the real modal.
  it('renders the real confirm modal with the recognized name on success', async () => {
    const login = jest.fn().mockResolvedValue({ data: { full_name: 'Ada Lovelace' } });
    renderComponent({ login, realConfirmModal: true });

    await fireEvent.click(screen.getByTestId('emit-embedding'));

    expect(await screen.findByText(qrLoginStrings.isThisYou$())).toBeInTheDocument();
    expect(screen.getByText('Ada Lovelace')).toBeInTheDocument();
  });
});
