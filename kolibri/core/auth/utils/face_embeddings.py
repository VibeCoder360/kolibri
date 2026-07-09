"""
Utilities for face-recognition login.

Face embeddings are computed in the browser (never on the server) and sent to
Kolibri as base64-encoded little-endian float32 vectors. The server's only job
is 1:N matching: find the enrolled user whose stored samples are nearest to
the probe embedding, and accept the match only when it is both close enough
(THRESHOLD) and unambiguous (MARGIN to the runner-up user).

Pure Python on purpose: numpy is not a Kolibri dependency, and a linear scan
over a few hundred users with 512–1024-dimension vectors is well within
budget for a login request.
"""
import base64
import binascii
import math
import struct

from kolibri.utils.conf import OPTIONS

# Bumped whenever the browser-side descriptor model changes incompatibly.
# Stored embeddings with a different version are ignored at match time and
# must be re-enrolled.
CURRENT_EMBEDDING_VERSION = 1

# Guard rails on client-submitted data.
MAX_EMBEDDING_DIMENSIONS = 2048
# Multiple samples across small pose/expression variations reduce false
# rejects; require at least a few so a single frame can't be enrolled.
MIN_SAMPLES_PER_USER = 3
MAX_SAMPLES_PER_USER = 5


def encode_embedding(values):
    """
    Encode a sequence of floats as a base64 string of little-endian float32s.

    :param values: A sequence of floats
    :return: An ASCII-safe base64 string
    """
    packed = struct.pack("<%df" % len(values), *values)
    return base64.b64encode(packed).decode("ascii")


def decode_embedding(encoded):
    """
    Decode a base64 string of little-endian float32s into a list of floats.

    :param encoded: A base64 string as produced by `encode_embedding`
    :return: A list of floats
    :raises ValueError: if the input is not valid base64, is empty, is not a
        whole number of float32s, exceeds MAX_EMBEDDING_DIMENSIONS, or
        contains non-finite values.
    """
    if not isinstance(encoded, str):
        raise ValueError("Embedding must be a base64 string.")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Embedding is not valid base64.")
    if not raw or len(raw) % 4 != 0:
        raise ValueError("Embedding must be a whole number of float32 values.")
    dimensions = len(raw) // 4
    if dimensions > MAX_EMBEDDING_DIMENSIONS:
        raise ValueError("Embedding has too many dimensions.")
    values = list(struct.unpack("<%df" % dimensions, raw))
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Embedding contains non-finite values.")
    return values


def cosine_distance(a, b):
    """
    Cosine distance between two equal-length vectors, in [0, 2].

    Zero-norm vectors cannot be meaningfully compared, so they are treated as
    maximally distant rather than raising.
    """
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 2.0
    return 1.0 - dot / math.sqrt(norm_a * norm_b)


def find_best_face_match(probe, candidates):
    """
    Rank candidates against a probe embedding by their nearest sample.

    :param probe: A list of floats (the probe embedding)
    :param candidates: An iterable of (key, samples) pairs, where samples is a
        list of embeddings (each a list of floats). Samples whose dimensions
        do not match the probe are skipped.
    :return: A (key, best_distance, runner_up_distance) tuple for the nearest
        candidate, where runner_up_distance is the nearest distance of any
        OTHER candidate (infinity when there is only one candidate), or None
        when there are no comparable candidates.
    """
    best_key = None
    best_distance = math.inf
    runner_up_distance = math.inf

    for key, samples in candidates:
        candidate_distance = math.inf
        for sample in samples:
            if len(sample) != len(probe):
                continue
            distance = cosine_distance(probe, sample)
            if distance < candidate_distance:
                candidate_distance = distance
        if math.isinf(candidate_distance):
            continue
        if candidate_distance < best_distance:
            runner_up_distance = best_distance
            best_distance = candidate_distance
            best_key = key
        elif candidate_distance < runner_up_distance:
            runner_up_distance = candidate_distance

    if best_key is None:
        return None
    return (best_key, best_distance, runner_up_distance)


def validate_embedding_samples(samples):
    """
    Validate a client-submitted list of enrollment samples.

    :param samples: The value submitted as a user's enrollment embeddings
    :raises ValueError: if it is not a list of between MIN_SAMPLES_PER_USER and
        MAX_SAMPLES_PER_USER decodable embeddings that all share the same
        dimensions.
    """
    if not isinstance(samples, list):
        raise ValueError("A list of embedding samples is required.")
    if len(samples) < MIN_SAMPLES_PER_USER:
        raise ValueError(
            "At least %d embedding samples are required." % MIN_SAMPLES_PER_USER
        )
    if len(samples) > MAX_SAMPLES_PER_USER:
        raise ValueError(
            "At most %d embedding samples are allowed." % MAX_SAMPLES_PER_USER
        )
    dimensions = None
    for sample in samples:
        decoded = decode_embedding(sample)
        if dimensions is None:
            dimensions = len(decoded)
        elif len(decoded) != dimensions:
            raise ValueError("All embedding samples must have the same dimensions.")


def get_face_login_thresholds():
    """
    :return: A (threshold, margin) tuple. A probe matches a user only when its
        best distance is below `threshold` AND the runner-up user's best
        distance exceeds it by more than `margin` (ambiguity rejection).
    """
    return (
        OPTIONS["Auth"]["FACE_LOGIN_DISTANCE_THRESHOLD"],
        OPTIONS["Auth"]["FACE_LOGIN_DISTANCE_MARGIN"],
    )


__all__ = [
    "CURRENT_EMBEDDING_VERSION",
    "MAX_EMBEDDING_DIMENSIONS",
    "MIN_SAMPLES_PER_USER",
    "MAX_SAMPLES_PER_USER",
    "encode_embedding",
    "decode_embedding",
    "cosine_distance",
    "find_best_face_match",
    "validate_embedding_samples",
    "get_face_login_thresholds",
]
