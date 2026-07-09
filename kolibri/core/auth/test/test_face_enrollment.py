import factory
from django.urls import reverse
from rest_framework import status

from ..models import Facility
from ..models import FacilityUser
from ..models import FacilityUserFaceData
from .helpers import create_superuser
from .helpers import disable_face_login
from .helpers import DUMMY_PASSWORD
from .helpers import enable_face_login
from .helpers import KolibriAPITestCase as APITestCase
from .helpers import provision_device
from kolibri.core.auth.utils.face_embeddings import CURRENT_EMBEDDING_VERSION
from kolibri.core.auth.utils.face_embeddings import encode_embedding
from kolibri.core.auth.utils.face_embeddings import MAX_SAMPLES_PER_USER


class FacilityFactory(factory.DjangoModelFactory):
    class Meta:
        model = Facility

    name = factory.Sequence(lambda n: "Face Enroll Facility #%d" % n)


class FacilityUserFactory(factory.DjangoModelFactory):
    class Meta:
        model = FacilityUser

    facility = factory.SubFactory(FacilityFactory)
    username = factory.Sequence(lambda n: "enrolluser%d" % n)
    password = factory.PostGenerationMethodCall("set_password", DUMMY_PASSWORD)


def one_hot(index, dimensions=8):
    return [1.0 if i == index else 0.0 for i in range(dimensions)]


def sample_embeddings(count=3, dimensions=8):
    return [encode_embedding(one_hot(i, dimensions)) for i in range(count)]


class FaceEnrollmentAPITestCase(APITestCase):
    databases = "__all__"

    @classmethod
    def setUpTestData(cls):
        provision_device()
        cls.facility = FacilityFactory.create()
        cls.other_facility = FacilityFactory.create()
        cls.superuser = create_superuser(cls.facility)
        cls.learner = FacilityUserFactory.create(facility=cls.facility)
        cls.other_learner = FacilityUserFactory.create(facility=cls.facility)
        cls.admin = FacilityUserFactory.create(facility=cls.facility)
        cls.facility.add_admin(cls.admin)
        cls.coach = FacilityUserFactory.create(facility=cls.facility)
        cls.facility.add_coach(cls.coach)

    def setUp(self):
        enable_face_login(self.facility)

    def _enroll_url(self, user):
        return reverse("kolibri:core:facilityuser-enroll-face", kwargs={"pk": user.id})

    def _clear_url(self, user):
        return reverse("kolibri:core:facilityuser-clear-face", kwargs={"pk": user.id})

    def _post_enroll(
        self, target, embeddings=None, consent=True, embedding_version=None
    ):
        data = {
            "embeddings": embeddings if embeddings is not None else sample_embeddings(),
            "consent_acknowledged": consent,
            "embedding_version": (
                embedding_version
                if embedding_version is not None
                else CURRENT_EMBEDDING_VERSION
            ),
        }
        return self.client.post(self._enroll_url(target), data=data, format="json")

    def _login(self, user):
        self.client.login(
            username=user.username,
            password=DUMMY_PASSWORD,
            facility=user.facility,
        )

    def test_admin_can_enroll_learner(self):
        self._login(self.admin)
        response = self._post_enroll(self.learner)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data, {"enrolled": True, "samples": 3})
        face_data = FacilityUserFaceData.objects.get(user=self.learner)
        self.assertEqual(len(face_data.embeddings), 3)
        self.assertEqual(face_data.embedding_version, CURRENT_EMBEDDING_VERSION)
        self.assertTrue(face_data.consent_acknowledged)

    def test_user_can_enroll_self(self):
        self._login(self.learner)
        response = self._post_enroll(self.learner)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(FacilityUserFaceData.objects.filter(user=self.learner).exists())

    def test_superuser_can_enroll_learner(self):
        self._login(self.superuser)
        response = self._post_enroll(self.learner)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_learner_cannot_enroll_other_user(self):
        self._login(self.learner)
        response = self._post_enroll(self.other_learner)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_coach_cannot_enroll_learner(self):
        self._login(self.coach)
        response = self._post_enroll(self.learner)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_enroll(self):
        response = self._post_enroll(self.learner)
        self.assertIn(
            response.status_code,
            (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
        )

    def test_enrollment_requires_consent(self):
        self._login(self.admin)
        response = self._post_enroll(self.learner, consent=False)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            FacilityUserFaceData.objects.filter(user=self.learner).exists()
        )

    def test_enrollment_rejects_empty_embeddings(self):
        self._login(self.admin)
        response = self._post_enroll(self.learner, embeddings=[])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enrollment_rejects_malformed_embeddings(self):
        self._login(self.admin)
        response = self._post_enroll(self.learner, embeddings=["not base64!!!"])
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enrollment_rejects_too_many_samples(self):
        self._login(self.admin)
        response = self._post_enroll(
            self.learner, embeddings=sample_embeddings(MAX_SAMPLES_PER_USER + 1)
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enrollment_rejects_too_few_samples(self):
        self._login(self.admin)
        response = self._post_enroll(self.learner, embeddings=sample_embeddings(2))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enrollment_rejects_mismatched_dimensions(self):
        self._login(self.admin)
        embeddings = [
            encode_embedding(one_hot(0, dimensions=8)),
            encode_embedding(one_hot(1, dimensions=8)),
            encode_embedding(one_hot(0, dimensions=4)),
        ]
        response = self._post_enroll(self.learner, embeddings=embeddings)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_enrollment_rejects_outdated_embedding_version(self):
        self._login(self.admin)
        response = self._post_enroll(self.learner, embedding_version=999)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            FacilityUserFaceData.objects.filter(user=self.learner).exists()
        )

    def test_enrollment_rejected_when_face_login_disabled(self):
        disable_face_login(self.facility)
        self._login(self.admin)
        response = self._post_enroll(self.learner)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            FacilityUserFaceData.objects.filter(user=self.learner).exists()
        )

    def test_re_enrollment_replaces_samples(self):
        self._login(self.admin)
        self._post_enroll(self.learner)
        new_embeddings = [
            encode_embedding(one_hot(5)),
            encode_embedding(one_hot(6)),
            encode_embedding(one_hot(7)),
        ]
        response = self._post_enroll(self.learner, embeddings=new_embeddings)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        face_data = FacilityUserFaceData.objects.get(user=self.learner)
        self.assertEqual(face_data.embeddings, new_embeddings)

    def test_admin_can_clear_face(self):
        self._login(self.admin)
        self._post_enroll(self.learner)
        response = self.client.post(self._clear_url(self.learner), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"enrolled": False})
        self.assertFalse(
            FacilityUserFaceData.objects.filter(user=self.learner).exists()
        )

    def test_user_can_clear_own_face(self):
        self._login(self.admin)
        self._post_enroll(self.learner)
        self.client.logout()
        self._login(self.learner)
        response = self.client.post(self._clear_url(self.learner), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_learner_cannot_clear_other_users_face(self):
        self._login(self.admin)
        self._post_enroll(self.other_learner)
        self.client.logout()
        self._login(self.learner)
        response = self.client.post(self._clear_url(self.other_learner), format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_clear_is_idempotent(self):
        self._login(self.admin)
        response = self.client.post(self._clear_url(self.learner), format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_exposes_face_enrolled_flag(self):
        # The profile page relies on the detail response's computed
        # `face_enrolled` flag to decide between "set up" and "remove".
        self._login(self.learner)
        detail_url = reverse(
            "kolibri:core:facilityuser-detail", kwargs={"pk": self.learner.id}
        )

        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["face_enrolled"])

        self._post_enroll(self.learner)
        response = self.client.get(detail_url)
        self.assertTrue(response.data["face_enrolled"])


class FaceLoginSettingsAPITestCase(APITestCase):
    databases = "__all__"

    @classmethod
    def setUpTestData(cls):
        provision_device()
        cls.facility = FacilityFactory.create()
        cls.superuser = create_superuser(cls.facility)

    def _url(self):
        return reverse(
            "kolibri:core:facilitydataset-save-facility-login-settings",
            kwargs={"pk": self.facility.dataset_id},
        )

    def _login_superuser(self):
        self.client.login(
            username=self.superuser.username,
            password=DUMMY_PASSWORD,
            facility=self.facility,
        )

    def test_enable_face_login(self):
        self._login_superuser()
        response = self.client.patch(
            self._url(), data={"enable_face_login": True}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["dataset"]["enable_face_login"])
        self.facility.dataset.refresh_from_db()
        self.assertTrue(self.facility.dataset.enable_face_login)

    def test_disable_face_login(self):
        enable_face_login(self.facility)
        self._login_superuser()
        response = self.client.patch(
            self._url(), data={"enable_face_login": False}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["dataset"]["enable_face_login"])
        self.facility.dataset.refresh_from_db()
        self.assertFalse(self.facility.dataset.enable_face_login)
