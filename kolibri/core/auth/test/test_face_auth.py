import factory
import mock
from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from ..backends import FaceAuthScope
from ..models import Facility
from ..models import FacilityUser
from ..models import FacilityUserFaceData
from .helpers import disable_face_login
from .helpers import DUMMY_PASSWORD
from .helpers import enable_face_login
from .helpers import KolibriAPITestCase as APITestCase
from .helpers import provision_device
from kolibri.core import error_constants
from kolibri.core.auth.utils.face_embeddings import encode_embedding
from kolibri.utils.time_utils import local_now


class FacilityFactory(factory.DjangoModelFactory):
    class Meta:
        model = Facility

    name = factory.Sequence(lambda n: "Face Auth Facility #%d" % n)


class FacilityUserFactory(factory.DjangoModelFactory):
    class Meta:
        model = FacilityUser

    facility = factory.SubFactory(FacilityFactory)
    username = factory.Sequence(lambda n: "faceuser%d" % n)
    password = factory.PostGenerationMethodCall("set_password", DUMMY_PASSWORD)


def one_hot(index, dimensions=8):
    return [1.0 if i == index else 0.0 for i in range(dimensions)]


def near_one_hot(index, dimensions=8):
    """A vector close to (but not exactly) the one-hot at `index`."""
    return [0.98 if i == index else 0.03 for i in range(dimensions)]


def enroll_face(user, vectors, embedding_version=1):
    return FacilityUserFaceData.objects.create(
        user=user,
        embeddings=[encode_embedding(v) for v in vectors],
        embedding_version=embedding_version,
    )


class FaceAuthScopeTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.facility = Facility.objects.create(name="Face Scope Facility")
        cls.dataset = cls.facility.dataset
        cls.dataset.enable_face_login = True
        cls.dataset.save()

        cls.learner = FacilityUser.objects.create(
            username="learner", facility=cls.facility
        )
        enroll_face(cls.learner, [one_hot(0)])
        cls.other_learner = FacilityUser.objects.create(
            username="other", facility=cls.facility
        )
        enroll_face(cls.other_learner, [one_hot(1)])

    def setUp(self):
        dataset_id_patcher = mock.patch(
            "kolibri.core.auth.backends.is_full_facility_import"
        )
        self.is_full_facility_import = dataset_id_patcher.start()
        self.is_full_facility_import.return_value = True
        self.addCleanup(dataset_id_patcher.stop)

    def _probe(self, vector):
        return encode_embedding(vector)

    def test_close_probe_yields_only_best_matching_user(self):
        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(0)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [self.learner])

    def test_far_probe_yields_nothing(self):
        auth_scope = FaceAuthScope(self.facility, self._probe(one_hot(7)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def test_ambiguous_probe_yields_nothing(self):
        # Two users enrolled with the same embedding: the margin check must
        # reject the match rather than guessing between them.
        twin = FacilityUser.objects.create(username="twin", facility=self.facility)
        enroll_face(twin, [one_hot(0)])

        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(0)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def test_mismatched_embedding_version_is_ignored(self):
        outdated = FacilityUser.objects.create(
            username="outdated", facility=self.facility
        )
        enroll_face(outdated, [one_hot(2)], embedding_version=999)

        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(2)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def test_malformed_probe_yields_nothing(self):
        auth_scope = FaceAuthScope(self.facility, "not-valid-base64!!!")
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def test_malformed_stored_sample_skips_that_user_only(self):
        corrupted = FacilityUser.objects.create(
            username="corrupted", facility=self.facility
        )
        FacilityUserFaceData.objects.create(
            user=corrupted, embeddings=["garbage!!!"], embedding_version=1
        )

        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(0)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [self.learner])

    def test_disabled_face_login_yields_nothing(self):
        self.dataset.enable_face_login = False
        self.dataset.save()
        self.addCleanup(lambda: enable_face_login(self.facility))

        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(0)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def test_matches_credentials_false_when_face_login_disabled(self):
        self.dataset.enable_face_login = False
        self.dataset.save()
        self.addCleanup(lambda: enable_face_login(self.facility))

        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(0)))
        self.learner.dataset.refresh_from_db()
        self.assertFalse(auth_scope.matches_credentials(self.learner))

    def test_iter_candidate_users_raises_permission_denied_without_facility(self):
        auth_scope = FaceAuthScope(None, self._probe(near_one_hot(0)))
        with self.assertRaises(PermissionDenied):
            list(auth_scope.iter_candidate_users())

    def test_user_enrolled_in_other_facility_is_not_matched(self):
        other_facility = Facility.objects.create(name="Face Other Facility")
        other_facility.dataset.enable_face_login = True
        other_facility.dataset.save()
        outsider = FacilityUser.objects.create(
            username="outsider", facility=other_facility
        )
        enroll_face(outsider, [one_hot(3)])

        auth_scope = FaceAuthScope(self.facility, self._probe(near_one_hot(3)))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def _boundary_facility(self, name):
        facility = Facility.objects.create(name=name)
        facility.dataset.enable_face_login = True
        facility.dataset.save()
        return facility

    def test_margin_rejects_realistic_near_tie(self):
        # Two enrolled users at ~0.30 and ~0.33 cosine distance from the probe:
        # both are inside the 0.4 threshold but the 0.03 gap is under the 0.05
        # margin, so the match must be rejected rather than guessed. Uses
        # non-orthonormal vectors near the decision boundary rather than an
        # exact tie.
        facility = self._boundary_facility("Margin Facility")
        probe = [1.0, 0.0] + [0.0] * 6
        for username, vector in (
            ("near_a", [0.70, 0.714] + [0.0] * 6),  # distance ~0.30
            ("near_b", [0.67, 0.742] + [0.0] * 6),  # distance ~0.33
        ):
            user = FacilityUser.objects.create(username=username, facility=facility)
            FacilityUserFaceData.objects.create(
                user=user, embeddings=[encode_embedding(vector)], embedding_version=1
            )

        auth_scope = FaceAuthScope(facility, encode_embedding(probe))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [])

    def test_margin_allows_clear_winner_near_threshold(self):
        # Winner at ~0.30 distance (inside threshold); runner-up orthogonal
        # (distance 1.0). The gap far exceeds the margin, so the winner is
        # yielded.
        facility = self._boundary_facility("Winner Facility")
        probe = [1.0, 0.0] + [0.0] * 6
        winner = FacilityUser.objects.create(username="winner", facility=facility)
        FacilityUserFaceData.objects.create(
            user=winner,
            embeddings=[encode_embedding([0.70, 0.714] + [0.0] * 6)],
            embedding_version=1,
        )
        far = FacilityUser.objects.create(username="far", facility=facility)
        FacilityUserFaceData.objects.create(
            user=far,
            embeddings=[encode_embedding([0.0, 1.0] + [0.0] * 6)],
            embedding_version=1,
        )

        auth_scope = FaceAuthScope(facility, encode_embedding(probe))
        self.assertEqual(list(auth_scope.iter_candidate_users()), [winner])


class FaceLoginSessionTestCase(APITestCase):
    databases = "__all__"

    @classmethod
    def setUpTestData(cls):
        provision_device()
        cls.facility = FacilityFactory.create()
        cls.other_facility = FacilityFactory.create()
        cls.learner = FacilityUserFactory.create(facility=cls.facility)
        enroll_face(cls.learner, [one_hot(0), one_hot(4)])
        cls.other_learner = FacilityUserFactory.create(facility=cls.facility)
        enroll_face(cls.other_learner, [one_hot(1)])

    def setUp(self):
        enable_face_login(self.facility)
        enable_face_login(self.other_facility)

    def _post_face_login(self, vector, facility=None, extra=None):
        data = {
            "face_embedding": encode_embedding(vector),
            "facility": (facility or self.facility).id,
        }
        if extra:
            data.update(extra)
        return self.client.post(
            reverse("kolibri:core:session-list"), data=data, format="json"
        )

    def test_valid_face_embedding_creates_session(self):
        response = self._post_face_login(near_one_hot(0))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user_id"], self.learner.id)

    def test_probe_near_second_sample_matches(self):
        response = self._post_face_login(near_one_hot(4))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user_id"], self.learner.id)

    def test_unknown_face_returns_not_found(self):
        response = self._post_face_login(one_hot(7))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsInstance(response.data, list)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)
        self.assertEqual(response.data[0]["metadata"]["field"], "face_embedding")

    def test_failed_face_attempt_does_not_fall_through_to_username_password(self):
        response = self._post_face_login(
            one_hot(7),
            extra={
                "username": self.learner.username,
                "password": DUMMY_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIsInstance(response.data, list)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)
        self.assertEqual(response.data[0]["metadata"]["field"], "face_embedding")
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_face_login_disabled_returns_not_found(self):
        disable_face_login(self.facility)
        response = self._post_face_login(near_one_hot(0))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)
        self.assertEqual(response.data[0]["metadata"]["field"], "face_embedding")

    def test_face_wrong_facility_returns_not_found(self):
        response = self._post_face_login(near_one_hot(0), facility=self.other_facility)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)
        self.assertEqual(response.data[0]["metadata"]["field"], "face_embedding")

    def test_deleting_user_cascades_to_face_data(self):
        doomed = FacilityUserFactory.create(facility=self.facility)
        enroll_face(doomed, [one_hot(5)])
        doomed_id = doomed.id
        doomed.delete()
        self.assertFalse(
            FacilityUserFaceData.objects.filter(user_id=doomed_id).exists()
        )

    def test_soft_deleted_user_cannot_face_login_and_data_purged(self):
        self.learner.date_deleted = local_now()
        self.learner.save()
        # Soft delete purges the biometric data immediately.
        self.assertFalse(
            FacilityUserFaceData.objects.filter(user_id=self.learner.id).exists()
        )
        response = self._post_face_login(near_one_hot(0))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)

    def test_stale_embedding_version_returns_not_found(self):
        outdated = FacilityUserFactory.create(facility=self.facility)
        enroll_face(outdated, [one_hot(6)], embedding_version=999)
        response = self._post_face_login(near_one_hot(6))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)


class FaceLoginPrevalidateTestCase(APITestCase):
    databases = "__all__"

    @classmethod
    def setUpTestData(cls):
        provision_device()
        cls.facility = FacilityFactory.create()
        cls.learner = FacilityUserFactory.create(facility=cls.facility)
        enroll_face(cls.learner, [one_hot(0)])

    def setUp(self):
        enable_face_login(self.facility)

    def _url(self):
        return reverse("kolibri:core:session-list") + "?prevalidate=true"

    def _post(self, vector):
        return self.client.post(
            self._url(),
            data={
                "face_embedding": encode_embedding(vector),
                "facility": self.facility.id,
            },
            format="json",
        )

    def test_valid_face_returns_full_name(self):
        response = self._post(near_one_hot(0))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["full_name"], self.learner.full_name)

    def test_valid_face_does_not_create_session(self):
        self._post(near_one_hot(0))
        self.assertFalse(self.client.session.get("_auth_user_id"))

    def test_unknown_face_returns_not_found(self):
        response = self._post(one_hot(7))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data[0]["id"], error_constants.NOT_FOUND)
