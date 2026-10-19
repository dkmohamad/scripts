#!/usr/bin/env python3
"""Tests for Speechmatics auth-failure reporting (recorder.stt).

No API call: the SDK's wrapped exception chain is built by hand, mirroring what
``AsyncClient.submit_job`` raises on a 401/403.
"""

import pytest
from speechmatics.batch import (  # pyright: ignore[reportMissingTypeStubs]
    AuthenticationError,
    BatchError,
    JobError,
    TransportError,
)

from recorder.lib import SPEECHMATICS_KEY_FILE
from recorder.stt import (
    _auth_errors_explained,  # pyright: ignore[reportPrivateUsage]
    _auth_failure,  # pyright: ignore[reportPrivateUsage]
)

__all__: list[str] = []


def _sdk_chain(
    auth_message: str, outer: type[Exception] = BatchError
) -> Exception:
    """Build the chain the SDK raises on an auth failure.

    outer ← TransportError("Unexpected error") ←
    TransportError("Error handling response") ← AuthenticationError, where
    outer is BatchError from submit_job and JobError from polling.
    """
    auth = AuthenticationError(auth_message)
    handling = TransportError(f"Error handling response: {auth}")
    handling.__cause__ = auth
    unexpected = TransportError(f"Unexpected error: {handling}")
    unexpected.__cause__ = handling
    error = outer(f"Job failed: {unexpected}")
    error.__cause__ = unexpected
    return error


def test_403_should_point_at_account_credit_and_key_file() -> None:
    """A 403 under the SDK's wrappers names account credit and the key file.

    Build the chain submit_job raises on a 403 and assert the translated
    error names credit and the key file. Regression: a zero-credit account
    surfaced only as the SDK's "check API key permissions", sending the
    debugging after the key instead of the credit.
    """
    failure = _auth_failure(
        _sdk_chain("Access forbidden - check API key permissions")
    )
    assert failure is not None
    assert "403" in str(failure)
    assert "credit" in str(failure)
    assert str(SPEECHMATICS_KEY_FILE) in str(failure)


def test_401_should_point_at_the_key_file_not_credit() -> None:
    """A 401 names the key file and doesn't blame account credit.

    Build the chain for a 401 and assert the message points at the key file
    only, so a bad key isn't misreported as a billing problem.
    """
    failure = _auth_failure(_sdk_chain("Invalid API key - authentication failed"))
    assert failure is not None
    assert "401" in str(failure)
    assert "credit" not in str(failure)
    assert str(SPEECHMATICS_KEY_FILE) in str(failure)


def test_unknown_auth_message_should_still_name_both_causes() -> None:
    """An unrecognised SDK auth message falls back to naming credit and key file.

    Guards against an SDK upgrade rewording its messages: the fallback must
    still steer toward both causes rather than go vague.
    """
    failure = _auth_failure(_sdk_chain("Something new"))
    assert failure is not None
    assert "credit" in str(failure)
    assert str(SPEECHMATICS_KEY_FILE) in str(failure)


def test_bare_auth_error_should_be_translated() -> None:
    """An AuthenticationError raised unwrapped is still translated.

    submit_job lets a bare AuthenticationError through; assert it is handled
    the same as the wrapped form.
    """
    failure = _auth_failure(AuthenticationError("Access forbidden"))
    assert failure is not None
    assert "403" in str(failure)


def test_non_auth_failure_should_not_be_translated() -> None:
    """A submission failure with no auth error in its chain is left alone.

    Assert None for a plain BatchError, so network or job errors re-raise
    unchanged rather than being misreported as a credit/key problem.
    """
    assert _auth_failure(BatchError("HTTP 500")) is None


def test_auth_failure_during_polling_should_be_translated() -> None:
    """A 403 raised while polling (wrapped in JobError) is translated too.

    Raise the polling-shaped chain inside the handler and assert a
    PermissionError chained to the original. Guards a key revoked or credit
    exhausted mid-job, which the SDK wraps in JobError rather than BatchError.
    """
    chain = _sdk_chain("Access forbidden - check API key permissions", JobError)
    with pytest.raises(PermissionError, match="403") as info, _auth_errors_explained():
        raise chain
    assert info.value.__cause__ is chain


def test_non_auth_failure_should_pass_through_handler_unchanged() -> None:
    """The handler re-raises a non-auth failure as the original exception.

    Raise a plain BatchError inside the handler and assert the same object
    propagates, so ordinary job errors keep their own type and message.
    """
    original = BatchError("HTTP 500")
    with pytest.raises(BatchError) as info, _auth_errors_explained():
        raise original
    assert info.value is original
