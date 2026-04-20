"""Tests for ark/views.py, comprising the main endpoints for arklet."""

import uuid
from dataclasses import asdict, dataclass
from itertools import chain, count
from unittest.mock import patch

import pytest

from ark.models import Ark, Key, Naan, Shoulder
from ark.utils import parse_ark


@dataclass
class MintArkArgs:
    """Django test client named arguments to test mint_ark.

    Example use: client.post(**asdict(mint_ark_args))
    """

    path: str
    data: dict
    content_type: str
    HTTP_AUTHORIZATION: str  # pylint: disable=invalid-name


@pytest.fixture
def naan(db):
    """Create the initial NAAN used for most tests."""
    return Naan.objects.create(
        naan=1, name="Archive", description="A NAAN", url="https://example.com"
    )


@pytest.fixture
def shoulder(db, naan):
    """Create an initial shoulder used for most tests."""
    return Shoulder.objects.create(
        shoulder="/t2", naan=naan, name="Test", description="A Shoulder"
    )


@pytest.fixture
def auth(db, naan):
    """Create an access key for the initial naan."""
    key = Key.objects.create(naan=naan, active=True)
    return f"Bearer {key.key}"


@pytest.fixture
def ark(db, naan, shoulder):
    """Create an ARK for tests."""
    return Ark.objects.create(
        ark=f"{naan.naan}{shoulder.shoulder}12346",
        naan=naan,
        shoulder=shoulder,
        assigned_name="12346",
    )


@pytest.fixture
def mint_ark_args(naan, shoulder, auth) -> MintArkArgs:
    """Create the happy path arguments for mint_ark in Django test client."""
    return MintArkArgs(
        path="/mint",
        data={
            "naan": naan.naan,
            "shoulder": shoulder.shoulder,
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=auth,
    )


class TestMintArk:
    """Test the arklet mint_ark endpoint.

    mint_ark is responsible for the creation of new ARKs.
    """

    @staticmethod
    def _validate_success(test_args, res) -> None:
        """mint_ark returns a 200 and a json payload with a valid ARK on success."""
        minted_ark = res.json()["ark"]
        _, minted_naan, minted_assigned_name = parse_ark(minted_ark)
        expected_naan = test_args.data["naan"]
        expected_assigned_name = test_args.data["shoulder"].lstrip("/")
        assert res.status_code == 200
        assert minted_naan == expected_naan
        assert minted_assigned_name.startswith(expected_assigned_name)

    @pytest.mark.django_db
    def test_happy_path(self, client, mint_ark_args) -> None:
        """mint_ark succeeds on the happy path."""
        res = client.post(**asdict(mint_ark_args))
        self._validate_success(mint_ark_args, res)

    @pytest.mark.django_db
    def test_post_only(self, client, mint_ark_args) -> None:
        """mint_ark only accepts POST requests."""
        # When using client.put instead of client.post
        res = client.put(**asdict(mint_ark_args))
        # Then we get a 405
        assert res.status_code == 405

    def test_only_accepts_json(self, client, mint_ark_args) -> None:
        """mint_ark only accepts JSON payloads."""
        args = asdict(mint_ark_args)
        # When a request is sent form encoded instead of application/json
        del args["content_type"]
        res = client.post(**args)
        # Then we get a 400 Bad Request
        assert res.status_code == 400

    def test_invalid_form_is_bad_request(self, client, mint_ark_args) -> None:
        """mint_ark doesn't crash when sent JSON with the wrong structure."""
        mint_ark_args.data = {"a": "b"}
        res = client.post(**asdict(mint_ark_args))
        assert res.status_code == 400

    def test_http_authorization_header_required(self, client, mint_ark_args) -> None:
        """mint_ark requires an HTTP_AUTHORIZATION header."""
        # When we send a request with no HTTP_AUTHORIZATION header
        args = asdict(mint_ark_args)
        del args["HTTP_AUTHORIZATION"]
        res = client.post(**args)
        # Then we get a 403 Forbidden
        assert res.status_code == 403

    def test_verify_key_has_naan(self, client, mint_ark_args) -> None:
        """mint_ark requires present auth header to link to a NAAN."""
        # When we create an auth header value with a random UUID4
        mint_ark_args.HTTP_AUTHORIZATION = f"Bearer {uuid.uuid4()}"
        res = client.post(**asdict(mint_ark_args))
        # Then there will be no NAAN in the database with a key with that UUID4 value.
        assert res.status_code == 403

    def test_verify_key_is_valid(self, client, mint_ark_args) -> None:
        """mint_ark requires an uuid4 as the key."""
        # When the authorization header value isn't a UUID4
        mint_ark_args.HTTP_AUTHORIZATION = "Bearer not-a-uuid4"
        res = client.post(**asdict(mint_ark_args))
        # Then we get a 400 Bad Request
        assert res.status_code == 400

    def test_authorized_naan_matches_post_naan(self, client, mint_ark_args) -> None:
        """mint_ark NAAN in auth header matches NAAN in POST body."""
        # When the POST body naan field doesn't match the auth header NAAN
        mint_ark_args.data["naan"] += 1
        res = client.post(**asdict(mint_ark_args))
        # Then we get a 403 Forbidden
        assert res.status_code == 403

    @pytest.mark.django_db(transaction=True)
    @patch("ark.views.generate_noid")
    def test_fails_after_too_many_collisions(
        self, mock_noid_gen, caplog, client, mint_ark_args, ark
    ) -> None:
        """mint_ark returns an error after too many collisions.

        We need to set `pytest.mark.django_db(transaction=True)` because this test
        deliberately causes IntegrityErrors. When transaction=False all tests occur
        within a transaction. That prevents the test from using transaction features
        within the test. `transaction=True` is equivalent to Django
        TransactionTestCase. `transaction=False` is equivalent to Django TestCase.

        We patch ark.views.generate_noid (even though generate_noid is originally
        defined in ark.utils) because it is imported directly into ark.views.
        """
        # pylint: disable=too-many-arguments
        # When mint_ark keeps creating NOIDs that collide with an existing ARK
        existing_noid = ark.assigned_name[:-1]
        mock_noid_gen.return_value = existing_noid
        res = client.post(**asdict(mint_ark_args))
        # Then we log the error
        msg = "Gave up creating ark after"
        assert any(record for record in caplog.records if record.msg.startswith(msg))
        # Then we get a 500 Internal Server Error
        assert res.status_code == 500

    @pytest.mark.django_db(transaction=True)
    @patch("ark.views.generate_noid")
    def test_succeeds_on_single_collision(
        self, mock_noid_gen, caplog, client, mint_ark_args, ark
    ) -> None:
        """mint_ark succeeds with collisions, but fewer than the max collisions.

        mint_ark will also log a warning when collisions occur.

        See notes for test_fails_after_too_many_collisions.
        """
        # pylint: disable=too-many-arguments

        # mock generate_noid to return a conflicting NOID on first call
        # and non-conflicting NOIDs on subsequent calls
        existing_noid = ark.assigned_name[:-1]
        non_colliding_noid_gen = (str(i) for i in count(100_000_000))
        return_values = chain([existing_noid], non_colliding_noid_gen)
        mock_noid_gen.side_effect = lambda noid_length: next(return_values)

        # When mint_ark generates a single collision
        res = client.post(**asdict(mint_ark_args))
        # Then arklet logs a warning about the collision, but otherwise succeeds
        msg = "Ark created after %d collision(s)"
        assert any(record for record in caplog.records if record.msg == msg)
        self._validate_success(mint_ark_args, res)


class TestUpdateArk:
    @pytest.mark.django_db
    def test_happy_path(self, client, ark, auth) -> None:
        res = client.put(
            "/update",
            data={"ark": f"ark:/{ark.ark}", "title": "Updated Title"},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 200
        assert res.json()["title"] == "Updated Title"

    @pytest.mark.django_db
    def test_put_only(self, client, ark, auth) -> None:
        res = client.post(
            "/update",
            data={"ark": f"ark:/{ark.ark}"},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 405

    @pytest.mark.django_db
    def test_missing_auth(self, client, ark) -> None:
        res = client.put(
            "/update",
            data={"ark": f"ark:/{ark.ark}"},
            content_type="application/json",
        )
        assert res.status_code == 403

    @pytest.mark.django_db
    def test_ark_not_found(self, client, auth) -> None:
        res = client.put(
            "/update",
            data={"ark": "ark:/1/nonexistent99"},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code in (403, 404)

    def test_invalid_json_is_bad_request(self, client, auth) -> None:
        res = client.put(
            "/update",
            data="not-json",
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 400


class TestResolveArk:
    @pytest.mark.django_db
    def test_resolves_to_url(self, client, naan, shoulder) -> None:
        ark_obj = Ark.objects.create(
            ark=f"{naan.naan}{shoulder.shoulder}redirect1",
            naan=naan,
            shoulder=shoulder,
            assigned_name="redirect1",
            url="https://example.com/target",
        )
        res = client.get(f"/ark:/{ark_obj.ark}")
        assert res.status_code == 302
        assert "example.com/target" in res["Location"]

    @pytest.mark.django_db
    def test_info_inflection(self, client, naan, shoulder) -> None:
        ark_obj = Ark.objects.create(
            ark=f"{naan.naan}{shoulder.shoulder}infotest",
            naan=naan,
            shoulder=shoulder,
            assigned_name="infotest",
        )
        res = client.get(f"/ark:/{ark_obj.ark}?info")
        assert res.status_code == 200
        assert b"html" in res.content.lower()

    @pytest.mark.django_db
    def test_json_inflection(self, client, naan, shoulder) -> None:
        ark_obj = Ark.objects.create(
            ark=f"{naan.naan}{shoulder.shoulder}jsontest",
            naan=naan,
            shoulder=shoulder,
            assigned_name="jsontest",
        )
        res = client.get(f"/ark:/{ark_obj.ark}?json")
        assert res.status_code == 200
        data = res.json()
        assert "ark" in data

    @pytest.mark.django_db
    def test_naan_url_fallback(self, client, naan) -> None:
        res = client.get(f"/ark:/{naan.naan}/unknownark999")
        assert res.status_code == 302
        assert "example.com" in res["Location"]

    @pytest.mark.django_db
    def test_n2t_fallback(self, client) -> None:
        res = client.get("/ark:/999999999/unknownark")
        assert res.status_code == 302
        assert "n2t.net" in res["Location"]

    @pytest.mark.django_db
    def test_suffix_passthrough(self, client, naan, shoulder) -> None:
        ark_obj = Ark.objects.create(
            ark=f"{naan.naan}{shoulder.shoulder}suffixtest",
            naan=naan,
            shoulder=shoulder,
            assigned_name="suffixtest",
            url="https://example.com/item",
        )
        res = client.get(f"/ark:/{ark_obj.ark}/page/2")
        assert res.status_code == 302
        assert "/page/2" in res["Location"]


class TestBatchMintArks:
    @pytest.mark.django_db
    def test_happy_path(self, client, naan, shoulder, auth) -> None:
        res = client.post(
            "/bulk_mint",
            data={"naan": naan.naan, "data": [{"shoulder": shoulder.shoulder}]},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 200
        body = res.json()
        assert body["num_received"] == 1
        assert len(body["arks_created"]) == 1

    @pytest.mark.django_db
    def test_exceeds_max_rows(self, client, naan, shoulder, auth) -> None:
        records = [{"shoulder": shoulder.shoulder}] * 101
        res = client.post(
            "/bulk_mint",
            data={"naan": naan.naan, "data": records},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 400

    @pytest.mark.django_db
    def test_missing_shoulder_field(self, client, naan, auth) -> None:
        res = client.post(
            "/bulk_mint",
            data={"naan": naan.naan, "data": [{"url": "https://example.com"}]},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 400

    @pytest.mark.django_db
    def test_missing_auth(self, client, naan, shoulder) -> None:
        res = client.post(
            "/bulk_mint",
            data={"naan": naan.naan, "data": [{"shoulder": shoulder.shoulder}]},
            content_type="application/json",
        )
        assert res.status_code == 403


class TestBatchUpdateArks:
    @pytest.mark.django_db
    def test_happy_path(self, client, naan, shoulder, ark, auth) -> None:
        res = client.post(
            "/bulk_update",
            data={"data": [{"ark": f"ark:/{ark.ark}", "title": "Bulk Updated"}]},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 200
        assert res.json()["num_received"] == 1

    @pytest.mark.django_db
    def test_exceeds_max_rows(self, client, naan, shoulder, auth) -> None:
        records = [
            {"ark": f"ark:/{naan.naan}{shoulder.shoulder}fake{i}"} for i in range(101)
        ]
        res = client.post(
            "/bulk_update",
            data={"data": records},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 400

    @pytest.mark.django_db
    def test_missing_ark_field(self, client, auth) -> None:
        res = client.post(
            "/bulk_update",
            data={"data": [{"title": "No ark field"}]},
            content_type="application/json",
            HTTP_AUTHORIZATION=auth,
        )
        assert res.status_code == 400


class TestBatchQueryArks:
    @pytest.mark.django_db
    def test_happy_path(self, client, ark) -> None:
        res = client.post(
            "/bulk_query",
            data=[{"ark": f"ark:/{ark.ark}"}],
            content_type="application/json",
        )
        assert res.status_code == 200
        results = res.json()
        assert isinstance(results, list)
        assert any(r["ark"] == ark.ark for r in results)

    @pytest.mark.django_db
    def test_exceeds_max_rows(self, client) -> None:
        records = [{"ark": f"ark:/1/fake{i}"} for i in range(101)]
        res = client.post(
            "/bulk_query",
            data=records,
            content_type="application/json",
        )
        assert res.status_code == 400
