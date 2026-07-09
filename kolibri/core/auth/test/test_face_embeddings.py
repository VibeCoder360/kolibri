"""
Tests for the pure-Python face embedding utilities. These are bare pytest
function tests as the module under test is not Django code.
"""
import math

import pytest

from kolibri.core.auth.utils.face_embeddings import cosine_distance
from kolibri.core.auth.utils.face_embeddings import decode_embedding
from kolibri.core.auth.utils.face_embeddings import encode_embedding
from kolibri.core.auth.utils.face_embeddings import find_best_face_match
from kolibri.core.auth.utils.face_embeddings import get_face_login_thresholds
from kolibri.core.auth.utils.face_embeddings import MAX_EMBEDDING_DIMENSIONS
from kolibri.core.auth.utils.face_embeddings import validate_embedding_samples


# A fixed vector and its expected base64 of little-endian float32s. This is the
# cross-language wire contract: the JS encodeEmbedding() in
# packages/kolibri-common/utils/faceRecognition.js must produce this exact
# string for the same input (see faceRecognition.spec.js). If either side's
# byte order changes, enrollment silently stores vectors the other side cannot
# match, so both sides pin this golden value.
GOLDEN_VECTOR = [1.0, -2.0, 0.5, 0.0]
GOLDEN_BASE64 = "AACAPwAAAMAAAAA/AAAAAA=="


def one_hot(index, dimensions=8):
    return [1.0 if i == index else 0.0 for i in range(dimensions)]


def test_encode_decode_roundtrip():
    values = [0.5, -1.25, 0.0, 3.75]
    assert decode_embedding(encode_embedding(values)) == values


def test_encode_embedding_matches_golden_wire_format():
    assert encode_embedding(GOLDEN_VECTOR) == GOLDEN_BASE64


def test_decode_golden_base64():
    assert decode_embedding(GOLDEN_BASE64) == GOLDEN_VECTOR


def test_decode_rejects_invalid_base64():
    with pytest.raises(ValueError):
        decode_embedding("not base64!!!")


def test_decode_rejects_empty():
    with pytest.raises(ValueError):
        decode_embedding("")


def test_decode_rejects_partial_float():
    # 6 bytes is not a whole number of float32s
    with pytest.raises(ValueError):
        decode_embedding("AAAAAAAA")


def test_decode_rejects_non_string():
    with pytest.raises(ValueError):
        decode_embedding(12345)


def test_decode_rejects_too_many_dimensions():
    encoded = encode_embedding([0.0] * (MAX_EMBEDDING_DIMENSIONS + 1))
    with pytest.raises(ValueError):
        decode_embedding(encoded)


def test_decode_rejects_non_finite_values():
    encoded = encode_embedding([1.0, float("nan"), 0.0])
    with pytest.raises(ValueError):
        decode_embedding(encoded)


def test_cosine_distance_identical_vectors_is_zero():
    v = [0.3, -0.7, 0.2]
    assert cosine_distance(v, v) == pytest.approx(0.0)


def test_cosine_distance_orthogonal_vectors_is_one():
    assert cosine_distance(one_hot(0), one_hot(1)) == pytest.approx(1.0)


def test_cosine_distance_opposite_vectors_is_two():
    v = [1.0, 2.0]
    assert cosine_distance(v, [-1.0, -2.0]) == pytest.approx(2.0)


def test_cosine_distance_zero_vector_is_max():
    assert cosine_distance([0.0, 0.0], [1.0, 0.0]) == 2.0


def test_find_best_face_match_picks_nearest_candidate():
    probe = one_hot(0)
    candidates = [
        ("far", [one_hot(1)]),
        ("near", [one_hot(0)]),
    ]
    key, best, runner_up = find_best_face_match(probe, candidates)
    assert key == "near"
    assert best == pytest.approx(0.0)
    assert runner_up == pytest.approx(1.0)


def test_find_best_face_match_uses_nearest_sample_per_candidate():
    probe = one_hot(0)
    # The near candidate's nearest sample (an exact match) should win even
    # though its other sample is far away.
    candidates = [
        ("multi", [one_hot(1), one_hot(0)]),
        ("other", [one_hot(2)]),
    ]
    key, best, runner_up = find_best_face_match(probe, candidates)
    assert key == "multi"
    assert best == pytest.approx(0.0)


def test_find_best_face_match_single_candidate_runner_up_is_infinite():
    key, best, runner_up = find_best_face_match(one_hot(0), [("only", [one_hot(0)])])
    assert key == "only"
    assert math.isinf(runner_up)


def test_find_best_face_match_skips_dimension_mismatched_samples():
    probe = one_hot(0, dimensions=8)
    candidates = [
        ("mismatched", [one_hot(0, dimensions=4)]),
        ("valid", [one_hot(1, dimensions=8)]),
    ]
    key, best, runner_up = find_best_face_match(probe, candidates)
    assert key == "valid"


def test_find_best_face_match_returns_none_without_comparable_candidates():
    assert find_best_face_match(one_hot(0), []) is None
    assert (
        find_best_face_match(one_hot(0, dimensions=8), [("bad", [one_hot(0, 4)])])
        is None
    )


def test_get_face_login_thresholds_returns_configured_floats():
    threshold, margin = get_face_login_thresholds()
    assert isinstance(threshold, float)
    assert isinstance(margin, float)
    assert 0 < threshold < 2
    assert 0 <= margin < threshold


def test_validate_embedding_samples_accepts_three_matching():
    validate_embedding_samples([encode_embedding(one_hot(i)) for i in range(3)])


def test_validate_embedding_samples_rejects_too_few():
    with pytest.raises(ValueError):
        validate_embedding_samples([encode_embedding(one_hot(0))])


def test_validate_embedding_samples_rejects_too_many():
    with pytest.raises(ValueError):
        validate_embedding_samples([encode_embedding(one_hot(i % 8)) for i in range(6)])


def test_validate_embedding_samples_rejects_non_list():
    with pytest.raises(ValueError):
        validate_embedding_samples(encode_embedding(one_hot(0)))


def test_validate_embedding_samples_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        validate_embedding_samples(
            [
                encode_embedding(one_hot(0, dimensions=8)),
                encode_embedding(one_hot(1, dimensions=8)),
                encode_embedding(one_hot(0, dimensions=4)),
            ]
        )
