<template>

  <NotificationsRoot>
    <AppBarPage
      :title="coreString('profileLabel')"
      :loading="pageLoading"
    >
      <KPageContainer>
        <KGrid>
          <KGridItem
            :layout8="{ span: 4 }"
            :layout12="{ span: 6 }"
          >
            <h1>{{ coreString('profileLabel') }}</h1>
          </KGridItem>
          <KGridItem
            v-if="!isLearnerOnlyImport"
            :layout8="{ span: 4, alignment: 'right' }"
            :layout12="{ span: 6, alignment: 'right' }"
          >
            <h1>
              <KRouterLink
                :text="coreString('editAction')"
                appearance="raised-button"
                :primary="true"
                :to="profileEditRoute"
              />
            </h1>
          </KGridItem>
        </KGrid>

        <table>
          <tr>
            <th>{{ $tr('points') }}</th>
            <td class="points-cell">
              <KIcon
                icon="pointsActive"
                :color="$themeTokens.primary"
              />
              <span :style="{ color: $themeTokens.correct }">
                {{ $formatNumber(totalPoints) }}
              </span>
            </td>
          </tr>

          <tr>
            <th>{{ coreString('userTypeLabel') }}</th>

            <td>
              <UserTypeDisplay
                :distinguishCoachTypes="false"
                :userType="userKind"
              />
            </td>
          </tr>

          <tr v-if="facilityName">
            <th>{{ coreString('facilityLabel') }}</th>
            <td>{{ facilityName }}</td>
          </tr>

          <tr v-if="userHasPermissions">
            <th style="vertical-align: top">
              {{ coreString('devicePermissionsLabel') }}
            </th>
            <td>
              <KLabeledIcon>
                <template #icon>
                  <PermissionsIcon
                    :permissionType="permissionType"
                    class="permissions-icon"
                  />
                </template>
                {{ permissionTypeText }}
              </KLabeledIcon>
              <p>{{ $tr('youCan') }}</p>
              <ul class="permissions-list">
                <li v-if="isSuperuser">
                  {{ $tr('manageDevicePermissions') }}
                </li>
                <li
                  v-for="(value, key) in userPermissions"
                  :key="key"
                >
                  {{ getPermissionString(key) }}
                </li>
              </ul>
            </td>
          </tr>

          <tr>
            <th>{{ coreString('fullNameLabel') }}</th>
            <td>{{ currentUser.full_name }}</td>
          </tr>

          <tr>
            <th>{{ coreString('usernameLabel') }}</th>
            <td>{{ currentUser.username }}</td>
          </tr>

          <tr>
            <th>{{ coreString('genderLabel') }}</th>
            <td>
              <GenderDisplayText :gender="currentUser.gender" />
            </td>
          </tr>

          <tr>
            <th>{{ coreString('birthYearLabel') }}</th>
            <td>
              <BirthYearDisplayText :birthYear="currentUser.birth_year" />
            </td>
          </tr>

          <tr v-if="showPicturePasswordRow">
            <th>{{ coreString('passwordLabel') }}</th>
            <td>
              <UserPicturePassword
                v-if="currentUser.picture_password"
                data-testid="picture-password-display"
                :picturePassword="currentUser.picture_password"
              />
              <KEmptyPlaceholder
                v-else
                data-testid="picture-password-empty"
              />
            </td>
          </tr>

          <tr v-if="showQrLoginRow">
            <th>{{ myQRCode$() }}</th>
            <td>
              <UserQRCode
                v-if="qrLoginToken"
                data-testid="qr-login-token-display"
                :token="qrLoginToken"
                :size="120"
              />
              <template v-else>
                <KEmptyPlaceholder data-testid="qr-login-token-empty" />
                <div>
                  <KButton
                    appearance="basic-link"
                    data-testid="generate-qr-token"
                    :text="generateQrCode$()"
                    :disabled="assigningQrToken"
                    @click="handleGenerateQrToken"
                  />
                </div>
              </template>
            </td>
          </tr>

          <tr v-if="showFaceLoginRow">
            <th>{{ faceSignInTitle$() }}</th>
            <td>
              <KButton
                appearance="basic-link"
                data-testid="face-enroll-button"
                :text="faceEnrolled ? removeFaceSignIn$() : setUpFaceSignIn$()"
                @click="showFaceModal = true"
              />
            </td>
          </tr>

          <tr v-if="!isLearnerOnlyImport && canEditPassword">
            <th>{{ coreString('passwordLabel') }}</th>
            <td>
              <KButton
                appearance="basic-link"
                :text="$tr('changePasswordPrompt')"
                class="change-password"
                @click="showPasswordModal = true"
              />
            </td>
          </tr>
        </table>

        <KGrid
          v-if="onMyOwnSetup"
          :style="{
            marginTop: '34px',
            paddingTop: '10px',
            borderTop: `1px solid ${$themeTokens.fineLine}`,
          }"
        >
          <KGridItem
            :layout8="{ span: 4 }"
            :layout12="{ span: 6 }"
          >
            <h2>{{ coreString('changeLearningFacility') }}</h2>
          </KGridItem>
          <KGridItem
            :layout8="{ span: 4, alignment: 'right' }"
            :layout12="{ span: 6, alignment: 'right' }"
          >
            <h2>
              <KRouterLink
                :text="$tr('changeAction')"
                appearance="raised-button"
                :primary="false"
                :to="$router.getRoute('CHANGE_FACILITY')"
              />
            </h2>
          </KGridItem>
          <KGridItem>
            <span>{{ $tr('changeLearningFacilityDescription') }}</span>
            <span><KButton
              appearance="basic-link"
              :text="$tr('learnMore')"
              class="learn"
              @click="showLearnModal = true"
            /></span>
          </KGridItem>
        </KGrid>

        <ChangeUserPasswordModal
          v-if="!isLearnerOnlyImport && showPasswordModal"
          @cancel="showPasswordModal = false"
        />

        <FaceEnrollment
          v-if="showFaceModal"
          :userId="currentUser.id"
          :alreadyEnrolled="faceEnrolled"
          @success="handleFaceEnrollmentSuccess"
          @cancel="showFaceModal = false"
        />

        <KModal
          v-if="showLearnModal"
          :title="coreString('changeLearningFacility')"
          size="medium"
          :cancelText="coreString('closeAction')"
          @cancel="showLearnModal = false"
        >
          <p>{{ $tr('learnModalLine1') }}</p>
          <p>{{ $tr('learnModalLine2') }}</p>
        </KModal>
      </KPageContainer>
    </AppBarPage>
  </NotificationsRoot>

</template>


<script>

  import NotificationsRoot from 'kolibri/components/pages/NotificationsRoot';
  import AppBarPage from 'kolibri/components/pages/AppBarPage';
  import { computed, ref } from 'vue';
  import find from 'lodash/find';
  import pickBy from 'lodash/pickBy';
  import commonCoreStrings from 'kolibri/uiText/commonCoreStrings';
  import PermissionsIcon from 'kolibri-common/components/labels/PermissionsIcon';
  import UserPicturePassword from 'kolibri-common/components/UserPicturePassword';
  import UserQRCode from 'kolibri-common/components/UserQRCode';
  import UserTypeDisplay from 'kolibri-common/components/UserTypeDisplay';
  import { PermissionTypes, UserKinds } from 'kolibri/constants';
  import useUser from 'kolibri/composables/useUser';
  import GenderDisplayText from 'kolibri-common/components/userAccounts/GenderDisplayText';
  import BirthYearDisplayText from 'kolibri-common/components/userAccounts/BirthYearDisplayText';
  import useTotalProgress from 'kolibri/composables/useTotalProgress';
  import useFacilities from 'kolibri-common/composables/useFacilities';
  import useFacility from 'kolibri-common/composables/useFacility';
  import useSnackbar from 'kolibri/composables/useSnackbar';
  import FacilityUserResource from 'kolibri-common/apiResources/FacilityUserResource';
  import { qrLoginStrings } from 'kolibri-common/strings/qrLoginStrings';
  import { faceLoginStrings } from 'kolibri-common/strings/faceLoginStrings';
  import cameraSupported from 'kolibri-common/utils/cameraSupported';
  import FaceEnrollment from 'kolibri-common/components/FaceEnrollment';
  import { pageLoading } from 'kolibri-common/composables/usePageLoading';
  import { RoutesMap } from '../../constants';
  import useCurrentUser from '../../composables/useCurrentUser';
  import useOnMyOwnSetup from '../../composables/useOnMyOwnSetup';
  import ChangeUserPasswordModal from './ChangeUserPasswordModal';

  export default {
    name: 'ProfilePage',
    metaInfo() {
      return {
        title: this.$tr('documentTitle'),
      };
    },
    components: {
      AppBarPage,
      BirthYearDisplayText,
      ChangeUserPasswordModal,
      FaceEnrollment,
      NotificationsRoot,
      GenderDisplayText,
      PermissionsIcon,
      UserPicturePassword,
      UserQRCode,
      UserTypeDisplay,
    },
    mixins: [commonCoreStrings],
    setup() {
      const showPasswordModal = ref(false);
      const showLearnModal = ref(false);
      const showFaceModal = ref(false);
      const { currentUser } = useCurrentUser();
      const {
        isLearnerOnlyImport,
        userKind,
        userPermissions: _userPermissions,
        isCoach,
        isAdmin,
        isSuperuser,
        userHasPermissions,
        userFacilityId,
      } = useUser();
      const { onMyOwnSetup } = useOnMyOwnSetup();
      const { fetchPoints, totalPoints } = useTotalProgress();
      const { facilities } = useFacilities();
      const { facilityConfig, fetchFacilities, updateFacilityConfig } = useFacility();
      const userPermissions = computed(() => pickBy(_userPermissions.value));
      const { createSnackbar } = useSnackbar();
      const { myQRCode$, generateQrCode$, qrTokenOperationFailed$ } = qrLoginStrings;
      const { faceSignInTitle$, setUpFaceSignIn$, removeFaceSignIn$ } = faceLoginStrings;

      // Face-login enrollment state. Initialised from the API's computed
      // `face_enrolled` flag and overridden locally after enroll/remove so the
      // row updates without a full refetch.
      const faceEnrolledOverride = ref(null);
      const faceEnrolled = computed(() => {
        if (faceEnrolledOverride.value !== null) {
          return faceEnrolledOverride.value;
        }
        return Boolean(currentUser.value?.face_enrolled);
      });
      const showFaceLoginRow = computed(() => {
        return Boolean(facilityConfig.value?.enable_face_login) && cameraSupported();
      });

      function handleFaceEnrollmentSuccess() {
        // We only know it's now enrolled if we were setting up; a remove flips
        // it off.
        faceEnrolledOverride.value = !faceEnrolled.value;
        showFaceModal.value = false;
      }

      // Any user (including coaches, admins, and super admins) can generate a
      // QR login token for themselves. Learners usually already have one
      // assigned automatically.
      const assigningQrToken = ref(false);
      const generatedQrToken = ref(null);
      const qrLoginToken = computed(
        () => currentUser.value?.qr_login_token || generatedQrToken.value,
      );

      async function handleGenerateQrToken() {
        assigningQrToken.value = true;
        try {
          const { data } = await FacilityUserResource.assignQrToken(currentUser.value.id);
          generatedQrToken.value = data.qr_login_token;
        } catch (err) {
          createSnackbar(qrTokenOperationFailed$());
        } finally {
          assigningQrToken.value = false;
        }
      }

      return {
        assigningQrToken,
        qrLoginToken,
        handleGenerateQrToken,
        generateQrCode$,
        pageLoading,
        currentUser,
        onMyOwnSetup,
        isLearnerOnlyImport,
        userKind,
        userPermissions,
        isCoach,
        isAdmin,
        isSuperuser,
        userHasPermissions,
        userFacilityId,
        showLearnModal,
        showPasswordModal,
        showFaceModal,
        faceEnrolled,
        showFaceLoginRow,
        handleFaceEnrollmentSuccess,
        fetchPoints,
        totalPoints,
        facilityConfig,
        facilities,
        fetchFacilities,
        updateFacilityConfig,
        myQRCode$,
        faceSignInTitle$,
        setUpFaceSignIn$,
        removeFaceSignIn$,
      };
    },
    computed: {
      profileEditRoute() {
        return this.$router.getRoute(RoutesMap.PROFILE_EDIT);
      },
      facilityName() {
        const match = find(this.facilities, {
          id: this.userFacilityId,
        });
        return match ? match.name : '';
      },
      permissionType() {
        if (this.isSuperuser) {
          return PermissionTypes.SUPERUSER;
        } else if (this.userHasPermissions) {
          return PermissionTypes.LIMITED_PERMISSIONS;
        }
        return null;
      },
      permissionTypeText() {
        if (this.isSuperuser) {
          return this.$tr('isSuperuser');
        } else if (this.userHasPermissions) {
          return this.$tr('limitedPermissions');
        }
        return '';
      },
      showPicturePasswordRow() {
        if (this.facilityConfig?.picture_password_settings == null) {
          return false;
        }
        if (this.isSuperuser && this.isLearnerOnlyImport) {
          return true;
        }
        return this.userKind === UserKinds.LEARNER;
      },
      showQrLoginRow() {
        // Unlike picture passwords, QR login is available to every user kind:
        // coaches, admins, and super admins can generate a code for themselves.
        return Boolean(this.facilityConfig?.enable_qr_login);
      },
      canEditPassword() {
        const learner_can_edit =
          this.facilityConfig.learner_can_edit_password &&
          !this.facilityConfig.learner_can_login_with_no_password;
        return this.isSuperuser || this.isAdmin || this.isCoach || learner_can_edit;
      },
    },
    async created() {
      this.fetchPoints();
      // Load the facility list and selected-facility config so facilityConfig is
      // populated for everything on this page that depends on it (#14545).
      await this.fetchFacilities();
      await this.updateFacilityConfig();
    },
    methods: {
      getPermissionString(permission) {
        if (permission === 'can_manage_content') {
          return this.$tr('manageContent');
        }
        return permission;
      },
    },
    $trs: {
      changeAction: {
        message: 'Change',
        context: 'Button which allows the user to change to a different facility.',
      },
      changeLearningFacilityDescription: {
        message: 'Move your account and progress data to another learning facility.',
        context: 'Explanation of what change a learning facility means',
      },
      learnMore: {
        message: 'Learn more',
        context:
          'Link to open a modal window explaining what changing to another learning facility represents.',
      },
      isSuperuser: {
        message: 'Super admin permissions ',
        context:
          'A super admin is an account type that can manage the device. Super admin accounts also have permission to do everything that admins, coaches, and learners can do.',
      },
      manageContent: {
        message: 'Manage channels and resources',
        context: 'A type of device permission.',
      },
      manageDevicePermissions: {
        message: 'Manage device permissions',
        context: 'A type of device permission.',
      },
      points: {
        message: 'Points',
        context:
          'Points are an abstract reward given to learners as they make progress through resources.',
      },
      limitedPermissions: {
        message: 'Limited permissions',
        context:
          'A type of device permission that indicates that the user has permissions to manage content, but not other users or facility settings.',
      },
      youCan: {
        message: 'You can:',
        context: 'Descriptive text on user profile page. Indicates the permissions a user has.',
      },
      changePasswordPrompt: {
        message: 'Change password',
        context:
          'Users have the option to change their password if, for example, they have forgotten it.\n\nThis is the text that appears on the change password prompt.',
      },
      documentTitle: {
        message: 'User Profile',
        context: 'Title of the user profile page.',
      },
      learnModalLine1: {
        message:
          'Learning facility represents the location where you are using Kolibri, such as a school, training center, or a home.',
        context:
          'First line of text in the modal explaining what changing to another learning facility means.',
      },
      learnModalLine2: {
        message:
          'Moving your account to another learning facility means administrators of that facility will be able to access your data.',
        context:
          'Second line of text in the modal explaining what changing to another learning facility means.',
      },
    },
  };

</script>


<style lang="scss" scoped>

  .points-icon,
  .points-num {
    display: inline-block;
  }

  th {
    text-align: left;
  }

  th,
  td {
    height: 2em;
    padding-top: 24px;
    padding-right: 24px;
  }

  .points-icon {
    width: 24px;
    height: 24px;
    margin-right: 4px;
  }

  .points-num {
    margin-left: 16px;
    font-size: 3em;
    font-weight: bold;
  }

  section {
    margin-bottom: 36px;
  }

  .permissions-list {
    padding-left: 37px;
  }

  .permissions-icon {
    padding-right: 8px;
  }

  .submit {
    margin-left: 0;
  }

  .change-password {
    margin-top: 8px;
  }

  .learn {
    margin-left: 8px;
  }

  .points-cell {
    vertical-align: middle;
  }

</style>
