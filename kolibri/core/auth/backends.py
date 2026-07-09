"""
Implements custom auth backends as described in the Django docs, for our custom user class -- FacilityUser.
The appropriate classes should be listed in the AUTHENTICATION_BACKENDS. Note that authentication
backends are checked in the order they're listed.
"""
import abc
import logging

from django.contrib.sessions.backends.db import SessionStore as DBStore
from django.core.exceptions import PermissionDenied
from django.db.models import Exists
from django.db.models import OuterRef
from django.utils.functional import cached_property

from kolibri.core.auth.models import Facility
from kolibri.core.auth.models import FacilityUser
from kolibri.core.auth.models import Role
from kolibri.core.auth.models import Session
from kolibri.core.auth.utils.face_embeddings import CURRENT_EMBEDDING_VERSION
from kolibri.core.auth.utils.face_embeddings import decode_embedding
from kolibri.core.auth.utils.face_embeddings import find_best_face_match
from kolibri.core.auth.utils.face_embeddings import get_face_login_thresholds
from kolibri.core.device.utils import is_full_facility_import


FACILITY_CREDENTIAL_KEY = "facility"
logger = logging.getLogger(__name__)


class AuthScope(abc.ABC):
    def get_queryset(self):
        """
        :return: A queryset of FacilityUser objects
        """
        return FacilityUser.objects.select_related("dataset")

    @abc.abstractmethod
    def iter_candidate_users(self):
        """
        Determines candidate users for checking authorization
        :return: An iterator over candidate FacilityUser objects
        """
        pass

    @abc.abstractmethod
    def matches_credentials(self, user):
        """
        Determines whether this user is authorized
        :param user: A FacilityUser object
        :return: A boolean indicating authorization
        """
        pass

    def __str__(self):
        return self.__class__.__name__

    def __repr__(self):
        return str(self)


class UsernameAuthScope(AuthScope, abc.ABC):
    """Auth scope for username based authentication"""

    def __init__(self, username):
        super().__init__()
        self.username = username

    def iter_candidate_users(self):
        """
        First iters over users with exactly matching usernames, then those with an inexact match
        """
        qs = self.get_queryset()
        for user in qs.filter(username=self.username):
            yield user

        for user in qs.filter(username__iexact=self.username):
            yield user


class SuperuserAuthScope(UsernameAuthScope):
    """
    Auth scope for superuser authentication, which does not need to align with a specific facility,
    but requires superuser device permissions
    """

    def __init__(self, username, password):
        super().__init__(username)
        self.password = password

    def get_queryset(self):
        return FacilityUser.objects.filter(devicepermissions__is_superuser=True)

    def matches_credentials(self, user):
        """
        Superuser's password must be verified
        """
        return user.check_password(self.password)


class FacilityAuthScope(AuthScope, abc.ABC):
    """Base facility scope for authentication"""

    def __init__(self, facility_or_id):
        """
        :param facility_or_id: The facility ID string or a Facility object
        """
        self.facility_or_id = facility_or_id

    @cached_property
    def dataset_id(self):
        """
        Resolves a facility string ID or object to its dataset ID.
        See FacilityUserBackend.authenticate on how it accepts either

        :return: The facility dataset ID
        """
        # Resolve dataset_id to leverage the (dataset, picture_password) unique
        # index. facility may be a Facility object or a raw pk/UUID.
        if isinstance(self.facility_or_id, Facility):
            return self.facility_or_id.dataset_id

        try:
            return Facility.objects.values_list("dataset_id", flat=True).get(
                pk=self.facility_or_id
            )
        except Facility.DoesNotExist:
            # if we cannot find the requested facility, we'll just fail fast
            raise PermissionDenied("Invalid credentials")

    @cached_property
    def is_full_facility_import(self):
        return self.dataset_id and not is_full_facility_import(self.dataset_id)

    def get_queryset(self):
        """
        Determines candidate users for checking authorization
        """
        qs = super().get_queryset().filter(dataset_id=self.dataset_id)
        # users who have the most roles could be more active than users who have less, but instead
        # of trying to authenticate them first, through ordering, we just prioritize by date joined
        return qs.annotate(
            has_roles=Exists(Role.objects.filter(user_id=OuterRef("pk"))),
        ).order_by("-has_roles", "date_joined")

    def __str__(self):
        return f"{super().__str__()}<{self.facility_or_id}>"


class BasicUserAuthScope(FacilityAuthScope, UsernameAuthScope):
    """Auth scope for username/password authentication"""

    def __init__(self, facility_or_id, username, password=None):
        super().__init__(facility_or_id)
        UsernameAuthScope.__init__(self, username)
        self.password = password

    def matches_credentials(self, user):
        """
        Either the provided password matches the user, or the user is a learner and the facility
        configuration allows passwordless sign-in.
        """
        if user.check_password(self.password):
            return True

        return (
            user.dataset.learner_can_login_with_no_password
            and not user.has_roles
            and (not user.is_superuser or self.is_full_facility_import)
        )


class PicturePasswordAuthScope(FacilityAuthScope):
    """Auth scope for picture password authentication"""

    def __init__(self, facility_or_id, picture_password=None):
        super().__init__(facility_or_id)
        self.picture_password = picture_password

    def get_queryset(self):
        return super().get_queryset().filter(picture_password=self.picture_password)

    def iter_candidate_users(self):
        """
        We expect only one user with the dataset and picture password filters
        """
        for user in self.get_queryset():
            yield user

    def matches_credentials(self, user):
        """
        Validates that the user is a learner and that the facility configuration allows picture
        password sign-in.
        """
        return (
            user.dataset.picture_password_settings is not None
            and not user.has_roles
            and (not user.is_superuser or self.is_full_facility_import)
        )


class QRTokenAuthScope(FacilityAuthScope):
    """Auth scope for QR code (token) authentication"""

    def __init__(self, facility_or_id, qr_login_token=None):
        super().__init__(facility_or_id)
        self.qr_login_token = qr_login_token

    def get_queryset(self):
        # `qr_login_token` is globally unique, but we scope by dataset for
        # defense-in-depth: a token issued in facility A must not log into
        # facility B even if it somehow leaked across facilities.
        return super().get_queryset().filter(qr_login_token=self.qr_login_token)

    def iter_candidate_users(self):
        """
        We expect exactly one user with this token (globally unique column).
        """
        for user in self.get_queryset():
            yield user

    def matches_credentials(self, user):
        """
        Validates that the user's facility has QR login enabled. Unlike
        picture passwords, QR tokens are not learner-only: coaches, admins,
        and superusers may hold one, but only by explicit opt-in via the ID
        cards API (learners are the only users assigned tokens
        automatically), so no role or superuser check is applied here.
        """
        return user.dataset.enable_qr_login


class FaceAuthScope(FacilityAuthScope):
    """Auth scope for face-recognition (embedding) authentication"""

    def __init__(self, facility_or_id, face_embedding=None):
        super().__init__(facility_or_id)
        self.face_embedding = face_embedding

    def get_queryset(self):
        # Filtering on enable_face_login here short-circuits the (relatively
        # expensive) gallery scan when the facility has face login disabled;
        # matches_credentials re-checks the flag for defense-in-depth,
        # consistent with the other scopes.
        return (
            super()
            .get_queryset()
            .filter(face_data__isnull=False, dataset__enable_face_login=True)
            .select_related("face_data")
        )

    def _decode_user_samples(self, user):
        """
        Decode a user's stored enrollment samples, returning [] for any user
        whose face data is malformed or from an incompatible descriptor model
        version — those users are simply not comparable to the probe.
        """
        face_data = user.face_data
        if face_data.embedding_version != CURRENT_EMBEDDING_VERSION:
            return []
        if not isinstance(face_data.embeddings, list):
            return []
        try:
            return [decode_embedding(sample) for sample in face_data.embeddings]
        except ValueError:
            return []

    def iter_candidate_users(self):
        """
        Face matching is 1:N best-match, not first-match: we rank every
        enrolled user in the facility by their nearest sample distance to the
        probe and yield at most ONE user — the closest — and only when the
        match is both close enough (THRESHOLD) and unambiguous (MARGIN to the
        runner-up user). Yielding a single candidate keeps the generic
        first-match loop in FacilityUserBackend._run correct for this scope.
        """
        try:
            probe = decode_embedding(self.face_embedding)
        except ValueError:
            return

        candidates = []
        for user in self.get_queryset():
            samples = self._decode_user_samples(user)
            if samples:
                candidates.append((user, samples))

        match = find_best_face_match(probe, candidates)
        if match is None:
            return
        user, best_distance, runner_up_distance = match
        threshold, margin = get_face_login_thresholds()
        if best_distance < threshold and runner_up_distance - best_distance > margin:
            yield user

    def matches_credentials(self, user):
        """
        Validates that the user's facility has face login enabled. Like QR
        tokens, face login is not learner-only: any enrolled user may sign in
        with it, and enrollment itself is explicit opt-in.
        """
        return user.dataset.enable_face_login


class FacilityUserBackend:
    """
    A class that implements authentication for FacilityUsers.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticates the user if the credentials correspond to a FacilityUser for the specified Facility.

        :param request: The request is a required positional argument in newer versions of Django
        :param username: a string
        :param password: a string
        :param kwargs: a dict of additional credentials (see `keyword`s)
        :keyword facility: a Facility object or facility pk
        :keyword picture_password: a dot-separated picture sequence string
        :keyword qr_login_token: a QR code login token string
        :keyword face_embedding: a base64-encoded face embedding string
        :return: A FacilityUser instance if successful, or None if authentication failed.
        """
        facility = kwargs.get(FACILITY_CREDENTIAL_KEY, None)
        picture_password = kwargs.get("picture_password", None)
        qr_login_token = kwargs.get("qr_login_token", None)
        face_embedding = kwargs.get("face_embedding", None)

        scopes = []

        # Picture password authentication path.
        # The None check is load-bearing: filter(picture_password=None) would
        # match rows where the column IS NULL, returning an arbitrary learner.
        if picture_password is not None:
            if not facility:
                # we cannot run picture password auth without it
                raise PermissionDenied("Invalid credentials")
            scopes.append(PicturePasswordAuthScope(facility, picture_password))
        elif qr_login_token is not None:
            # QR token authentication path. Same isolation rule as picture
            # password: a failed QR attempt must never fall through to
            # username/password. Facility is required for the dataset scope.
            if not facility:
                raise PermissionDenied("Invalid credentials")
            scopes.append(QRTokenAuthScope(facility, qr_login_token))
        elif face_embedding is not None:
            # Face authentication path. Same isolation rule as the other
            # alternative credentials: a failed face attempt must never fall
            # through to username/password.
            if not facility:
                raise PermissionDenied("Invalid credentials")
            scopes.append(FaceAuthScope(facility, face_embedding))
        else:
            if facility:
                scopes.append(BasicUserAuthScope(facility, username, password))
            scopes.append(SuperuserAuthScope(username, password))

        for auth_scope in scopes:
            user = self._run(auth_scope)
            if user:
                return user

        return None

    def _run(self, auth_scope):
        """
        :param auth_scope: The auth scope to validate against
        :type auth_scope: AuthScope
        :return:
        """
        for user in auth_scope.iter_candidate_users():
            logger.debug(f"Using {auth_scope} to check user {user.id}")
            if auth_scope.matches_credentials(user):
                logger.debug(f"{auth_scope} authorized user {user.id}")
                return user
        return None

    def get_user(self, user_id):
        """
        Gets a user. Auth backends are required to implement this.

        :param user_id: A FacilityUser pk
        :return: A FacilityUser instance if a BaseUser with that pk is found, else None.
        """
        try:
            return FacilityUser.objects.get(pk=user_id)
        except FacilityUser.DoesNotExist:
            return None


class SessionStore(DBStore):
    @classmethod
    def get_model_class(cls):
        return Session

    def create_model_instance(self, data):
        obj = super().create_model_instance(data)
        try:
            user_id = data.get("_auth_user_id")
        except (ValueError, TypeError):
            user_id = None
        obj.user_id = user_id
        return obj

    @classmethod
    def delete_all_sessions(cls, user_ids):
        store = cls()
        sessions = store.get_model_class().objects.filter(user_id__in=user_ids)
        sessions.delete()
