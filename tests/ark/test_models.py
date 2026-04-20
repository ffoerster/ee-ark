"""Tests for ark/models.py."""

import pytest

from ark.models import Ark, ArkEvent, Key, Naan, Shoulder


@pytest.fixture
def naan(db):
    return Naan.objects.create(
        naan=99001, name="Test Org", description="desc", url="https://example.com"
    )


@pytest.fixture
def shoulder(db, naan):
    return Shoulder.objects.create(
        shoulder="/s", naan=naan, name="Test", description="desc"
    )


class TestNaan:
    @pytest.mark.django_db
    def test_str(self, naan):
        assert "99001" in str(naan)
        assert "Test Org" in str(naan)


class TestKey:
    @pytest.mark.django_db
    def test_create_for_naan(self, naan):
        key_inst, api_key = Key.create_for_naan(naan.naan)
        assert key_inst.active is True
        assert key_inst.naan == naan
        assert api_key is not None

    @pytest.mark.django_db
    def test_check_password_correct(self, naan):
        key_inst, api_key = Key.create_for_naan(naan.naan)
        assert key_inst.check_password(str(api_key)) is True

    @pytest.mark.django_db
    def test_check_password_wrong(self, naan):
        key_inst, _ = Key.create_for_naan(naan.naan)
        assert key_inst.check_password("wrong-password") is False

    @pytest.mark.django_db
    def test_create_for_nonexistent_naan_raises(self):
        with pytest.raises(ValueError):
            Key.create_for_naan(999999)


class TestShoulder:
    @pytest.mark.django_db
    def test_str(self, shoulder, naan):
        assert str(shoulder) == f"{naan.naan}/s"

    @pytest.mark.django_db
    def test_unique_together(self, naan, shoulder):
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Shoulder.objects.create(
                shoulder="/s", naan=naan, name="Dup", description="dup"
            )


class TestArk:
    @pytest.mark.django_db
    def test_create_generates_valid_ark(self, naan, shoulder):
        ark = Ark.create(naan, shoulder)
        assert ark.ark.startswith(f"{naan.naan}{shoulder.shoulder}")
        assert ark.naan == naan
        assert ark.shoulder == shoulder

    @pytest.mark.django_db
    def test_str(self, naan, shoulder):
        ark = Ark.create(naan, shoulder)
        ark.save()
        assert str(ark).startswith("ark:/")

    @pytest.mark.django_db
    def test_set_fields_updates_permitted(self, naan, shoulder):
        ark = Ark.create(naan, shoulder)
        ark.set_fields({"title": "My Title", "url": "https://example.com/item"})
        assert ark.title == "My Title"
        assert ark.url == "https://example.com/item"

    @pytest.mark.django_db
    def test_set_fields_ignores_non_permitted(self, naan, shoulder):
        ark = Ark.create(naan, shoulder)
        original_ark = ark.ark
        ark.set_fields({"ark": "tampered", "naan": 0})
        assert ark.ark == original_ark

    @pytest.mark.django_db
    def test_set_fields_allows_tombstone_fields(self, naan, shoulder):
        ark = Ark.create(naan, shoulder)
        ark.set_fields(
            {
                "state": "tombstoned",
                "replaced_by": "ark:/12345/replacement",
                "tombstone_reason": "Removed",
            }
        )
        assert ark.state == "tombstoned"
        assert ark.replaced_by == "ark:/12345/replacement"
        assert ark.tombstone_reason == "Removed"


class TestArkEvent:
    @pytest.mark.django_db
    def test_event_str(self, naan, shoulder):
        ark = Ark.create(naan, shoulder)
        ark.save()
        event = ArkEvent.objects.create(
            ark=ark,
            event_type=ArkEvent.EVENT_MINT,
            diff_json={"created": {"url": "https://example.com"}},
        )
        assert "mint" in str(event)
