import FacilityUserResource from 'kolibri-common/apiResources/FacilityUserResource';
import { mount, RouterLinkStub, createLocalVue } from '@vue/test-utils';
import { render, screen } from '@testing-library/vue';
import { ref } from 'vue';
import VueRouter from 'vue-router';
import useKResponsiveWindow from 'kolibri-design-system/lib/composables/useKResponsiveWindow';
import useUser, { useUserMock } from 'kolibri/composables/useUser'; // eslint-disable-line
import { UserKinds } from 'kolibri/constants';
import { coreStrings } from 'kolibri/uiText/commonCoreStrings';
import { createTranslator } from 'kolibri/utils/i18n';
import { PicturePasswordIconStyle } from 'kolibri-common/constants/Auth';
import ProfilePage from '../index';
import makeStore from '../../../__tests__/utils/makeStore';
import useOnMyOwnSetup, {
  // eslint-disable-next-line import-x/named
  useOnMyOwnSetupMock,
} from '../../../composables/useOnMyOwnSetup';
import useFacilities, { useFacilitiesMock } from 'kolibri-common/composables/useFacilities'; // eslint-disable-line
import useFacility, { useFacilityMock } from 'kolibri-common/composables/useFacility'; // eslint-disable-line

jest.mock('kolibri-common/apiResources/FacilityUserResource');
jest.mock('../../../composables/useOnMyOwnSetup');
jest.mock('kolibri-design-system/lib/composables/useKResponsiveWindow');
jest.mock('kolibri/composables/useUser');
jest.mock('kolibri/urls');
jest.mock('kolibri-common/composables/useFacilities');
jest.mock('kolibri-common/composables/useFacility');

const { fullNameLabel$ } = coreStrings;
const { changePasswordPrompt$ } = createTranslator(ProfilePage.name, ProfilePage.$trs);

FacilityUserResource.fetchModel = jest.fn().mockResolvedValue({});

const localVue = createLocalVue();
localVue.use(VueRouter);

const router = new VueRouter();
router.getRoute = () => {};

function makeWrapper() {
  const store = makeStore();
  useFacilities.mockImplementation(() =>
    useFacilitiesMock({
      facilityConfig: { learner_can_edit_password: true },
    }),
  );
  return mount(ProfilePage, {
    store,
    localVue,
    router,
    stubs: {
      RouterLink: RouterLinkStub,
      AppBar: {
        name: 'AppBar',
        template: '<div></div>',
      },
    },
  });
}

describe('profilePage component', () => {
  beforeAll(() => {
    useOnMyOwnSetup.mockImplementation(() => useOnMyOwnSetupMock({ onMyOwnSetup: true }));
    useKResponsiveWindow.mockImplementation(() => ({
      windowIsSmall: false,
    }));
    useUser.mockImplementation(() => useUserMock());
  });

  it('smoke test', () => {
    const wrapper = makeWrapper();
    expect(wrapper.exists()).toEqual(true);
  });
});

describe('picture password row', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useOnMyOwnSetup.mockImplementation(() => useOnMyOwnSetupMock({ onMyOwnSetup: false }));
    useKResponsiveWindow.mockImplementation(() => ({ windowIsSmall: false }));
    useFacilities.mockImplementation(() => useFacilitiesMock({ facilities: ref([]) }));
  });

  async function renderProfile({
    userKind = UserKinds.LEARNER,
    picturePasswordSettings = null,
    picturePassword = null,
  } = {}) {
    useUser.mockImplementation(() =>
      useUserMock({
        userKind,
        isLearner: userKind === UserKinds.LEARNER,
        isCoach: userKind === UserKinds.COACH,
        isAdmin: userKind === UserKinds.ADMIN || userKind === UserKinds.SUPERUSER,
        isSuperuser: userKind === UserKinds.SUPERUSER,
      }),
    );
    useFacility.mockImplementation(() =>
      useFacilityMock({
        facilityConfig: ref({
          picture_password_settings: picturePasswordSettings,
          learner_can_edit_password: false,
        }),
      }),
    );
    FacilityUserResource.fetchModel = jest
      .fn()
      .mockResolvedValue({ picture_password: picturePassword });

    const localRouter = new VueRouter();
    localRouter.getRoute = () => '/';

    return render(ProfilePage, {
      store: makeStore(),
      routes: localRouter,
    });
  }

  it('fetches the facility and its config on mount', async () => {
    // Without this fetch the page-level facilityConfig is empty, which silently
    // disables every facility-config-driven row on the Profile (#14545 fallout).
    await renderProfile({ userKind: UserKinds.LEARNER });

    const { fetchFacilities, updateFacilityConfig } = useFacilityMock();
    expect(fetchFacilities).toHaveBeenCalled();
    expect(updateFacilityConfig).toHaveBeenCalled();
  });

  it("hides figcaption labels when the facility's show_icon_text is false", async () => {
    await renderProfile({
      userKind: UserKinds.LEARNER,
      picturePasswordSettings: {
        icon_style: PicturePasswordIconStyle.COLORFUL,
        show_icon_text: false,
      },
      picturePassword: '3.7.12',
    });

    const display = await screen.findByTestId('picture-password-display');
    const icons = screen.queryAllByTestId(/^picture-password-icon-/);
    expect(icons).toHaveLength(3);
    const captions = [...display.querySelectorAll('figcaption')];
    expect(captions).toHaveLength(3);
    expect(captions.every(el => el.classList.contains('visuallyhidden'))).toBe(true);
  });

  it('renders the empty-value placeholder when the learner has no picture_password', async () => {
    await renderProfile({
      userKind: UserKinds.LEARNER,
      picturePasswordSettings: {
        icon_style: PicturePasswordIconStyle.COLORFUL,
        show_icon_text: false,
      },
      picturePassword: null,
    });

    expect(await screen.findByTestId('picture-password-empty')).toBeInTheDocument();
    expect(screen.queryByTestId('picture-password-display')).not.toBeInTheDocument();
  });

  it('omits the picture password row when picture_password_settings is null', async () => {
    await renderProfile({
      userKind: UserKinds.LEARNER,
      picturePasswordSettings: null,
      picturePassword: null,
    });

    // Wait for the page to actually render before negative-asserting.
    await screen.findByText(fullNameLabel$());

    expect(screen.queryByTestId('picture-password-display')).not.toBeInTheDocument();
    expect(screen.queryByTestId('picture-password-empty')).not.toBeInTheDocument();
  });

  it('omits the picture password row for a coach in a picture-login facility', async () => {
    await renderProfile({
      userKind: UserKinds.COACH,
      picturePasswordSettings: {
        icon_style: PicturePasswordIconStyle.COLORFUL,
        show_icon_text: false,
      },
      picturePassword: null,
    });

    await screen.findByText(fullNameLabel$());

    expect(screen.queryByTestId('picture-password-display')).not.toBeInTheDocument();
    expect(screen.queryByTestId('picture-password-empty')).not.toBeInTheDocument();
  });

  it("shows figcaption labels when the facility's show_icon_text is true", async () => {
    await renderProfile({
      userKind: UserKinds.LEARNER,
      picturePasswordSettings: {
        icon_style: PicturePasswordIconStyle.COLORFUL,
        show_icon_text: true,
      },
      picturePassword: '3.7.12',
    });

    const display = await screen.findByTestId('picture-password-display');
    const captions = [...display.querySelectorAll('figcaption')];
    expect(captions).toHaveLength(3);
    expect(captions.every(el => !el.classList.contains('visuallyhidden'))).toBe(true);
  });

  it.each([UserKinds.COACH, UserKinds.ADMIN, UserKinds.SUPERUSER])(
    'shows the Change password button for a %s when learner_can_edit_password is false',
    async userKind => {
      await renderProfile({ userKind });

      await screen.findByText(fullNameLabel$());
      expect(screen.getByText(changePasswordPrompt$())).toBeVisible();
    },
  );
});

describe('QR login row', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    useOnMyOwnSetup.mockImplementation(() => useOnMyOwnSetupMock({ onMyOwnSetup: false }));
    useKResponsiveWindow.mockImplementation(() => ({ windowIsSmall: false }));
    useFacilities.mockImplementation(() => useFacilitiesMock({ facilities: ref([]) }));
  });

  async function renderProfile({
    userKind = UserKinds.LEARNER,
    enableQrLogin = true,
    qrLoginToken = null,
  } = {}) {
    useUser.mockImplementation(() =>
      useUserMock({
        userKind,
        currentUserId: 'user-1',
        isLearner: userKind === UserKinds.LEARNER,
        isCoach: userKind === UserKinds.COACH,
        isAdmin: userKind === UserKinds.ADMIN || userKind === UserKinds.SUPERUSER,
        isSuperuser: userKind === UserKinds.SUPERUSER,
      }),
    );
    useFacility.mockImplementation(() =>
      useFacilityMock({
        facilityConfig: ref({
          enable_qr_login: enableQrLogin,
          learner_can_edit_password: false,
        }),
      }),
    );
    FacilityUserResource.fetchModel = jest
      .fn()
      .mockResolvedValue({ id: 'user-1', qr_login_token: qrLoginToken });
    FacilityUserResource.assignQrToken = jest
      .fn()
      .mockResolvedValue({ data: { qr_login_token: 'x'.repeat(43) } });

    const localRouter = new VueRouter();
    localRouter.getRoute = () => '/';

    return render(ProfilePage, {
      store: makeStore(),
      routes: localRouter,
    });
  }

  it.each([UserKinds.LEARNER, UserKinds.COACH, UserKinds.ADMIN, UserKinds.SUPERUSER])(
    'shows a Generate QR code action for a %s without a token',
    async userKind => {
      await renderProfile({ userKind });

      expect(await screen.findByTestId('generate-qr-token')).toBeVisible();
      expect(screen.queryByTestId('qr-login-token-display')).not.toBeInTheDocument();
    },
  );

  it('generates and displays a token when the action is clicked', async () => {
    await renderProfile({ userKind: UserKinds.COACH });

    const button = await screen.findByTestId('generate-qr-token');
    button.click();

    expect(await screen.findByTestId('qr-login-token-display')).toBeInTheDocument();
    expect(FacilityUserResource.assignQrToken).toHaveBeenCalledWith('user-1');
    expect(screen.queryByTestId('generate-qr-token')).not.toBeInTheDocument();
  });

  it('displays the existing token without a generate action', async () => {
    await renderProfile({ userKind: UserKinds.ADMIN, qrLoginToken: 'a'.repeat(43) });

    expect(await screen.findByTestId('qr-login-token-display')).toBeInTheDocument();
    expect(screen.queryByTestId('generate-qr-token')).not.toBeInTheDocument();
  });

  it('omits the QR row when QR login is disabled for the facility', async () => {
    await renderProfile({ userKind: UserKinds.LEARNER, enableQrLogin: false });

    await screen.findByText(fullNameLabel$());
    expect(screen.queryByTestId('qr-login-token-display')).not.toBeInTheDocument();
    expect(screen.queryByTestId('generate-qr-token')).not.toBeInTheDocument();
  });
});
