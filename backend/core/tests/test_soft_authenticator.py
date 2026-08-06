"""Программный аутентификатор: библиотека должна принимать его ответы."""

from __future__ import annotations

import pytest
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.exceptions import InvalidAuthenticationResponse

from repibot_core.testing.webauthn import SoftAuthenticator

RP_ID = "example.org"
ORIGIN = "https://example.org"


def test_registration_response_is_accepted() -> None:
    device = SoftAuthenticator(rp_id=RP_ID, origin=ORIGIN)
    options = generate_registration_options(rp_id=RP_ID, rp_name="Re:Pibot", user_name="user")

    verified = verify_registration_response(
        credential=device.register(options.challenge),
        expected_challenge=options.challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )

    assert verified.credential_id == device.credential_id


def test_authentication_response_is_accepted() -> None:
    device = SoftAuthenticator(rp_id=RP_ID, origin=ORIGIN)
    registration = verify_registration_response(
        credential=device.register(
            generate_registration_options(
                rp_id=RP_ID, rp_name="Re:Pibot", user_name="user", challenge=b"registration"
            ).challenge
        ),
        expected_challenge=b"registration",
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )
    options = generate_authentication_options(rp_id=RP_ID)

    verified = verify_authentication_response(
        credential=device.authenticate(options.challenge, user_handle=b"1"),
        expected_challenge=options.challenge,
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        credential_public_key=registration.credential_public_key,
        credential_current_sign_count=registration.sign_count,
    )

    assert verified.new_sign_count == 1


def test_stale_sign_count_is_rejected() -> None:
    """Счётчик меньше сохранённого — признак клона ключа."""
    device = SoftAuthenticator(rp_id=RP_ID, origin=ORIGIN)
    registration = verify_registration_response(
        credential=device.register(b"registration"),
        expected_challenge=b"registration",
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
    )

    with pytest.raises(InvalidAuthenticationResponse):
        verify_authentication_response(
            credential=device.authenticate(b"login", user_handle=b"1"),
            expected_challenge=b"login",
            expected_rp_id=RP_ID,
            expected_origin=ORIGIN,
            credential_public_key=registration.credential_public_key,
            credential_current_sign_count=99,
        )
