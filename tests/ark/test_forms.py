"""Tests for ark/forms.py."""

import pytest

from ark.forms import MintArkForm, UpdateArkForm, validate_shoulder


class TestValidateShoulder:
    def test_valid_shoulder(self):
        validate_shoulder("/t")  # no exception

    def test_invalid_shoulder_raises(self):
        from django.core.exceptions import ValidationError
        with pytest.raises(ValidationError):
            validate_shoulder("t")


class TestMintArkForm:
    def test_valid_minimal(self):
        form = MintArkForm({"naan": 12345, "shoulder": "/t"})
        assert form.is_valid(), form.errors

    def test_valid_with_optional_fields(self):
        form = MintArkForm({
            "naan": 12345,
            "shoulder": "/t",
            "url": "https://example.com",
            "title": "A Title",
            "type": "Text",
        })
        assert form.is_valid(), form.errors

    def test_missing_naan_invalid(self):
        form = MintArkForm({"shoulder": "/t"})
        assert not form.is_valid()
        assert "naan" in form.errors

    def test_missing_shoulder_invalid(self):
        form = MintArkForm({"naan": 12345})
        assert not form.is_valid()
        assert "shoulder" in form.errors

    def test_invalid_shoulder_no_slash(self):
        form = MintArkForm({"naan": 12345, "shoulder": "t"})
        assert not form.is_valid()
        assert "shoulder" in form.errors

    def test_invalid_url(self):
        form = MintArkForm({"naan": 12345, "shoulder": "/t", "url": "not-a-url"})
        assert not form.is_valid()
        assert "url" in form.errors

    def test_non_integer_naan(self):
        form = MintArkForm({"naan": "abc", "shoulder": "/t"})
        assert not form.is_valid()
        assert "naan" in form.errors


class TestUpdateArkForm:
    def test_valid_minimal(self):
        form = UpdateArkForm({"ark": "ark:/12345/abc123"})
        assert form.is_valid(), form.errors

    def test_valid_with_url(self):
        form = UpdateArkForm({"ark": "ark:/12345/abc123", "url": "https://example.com"})
        assert form.is_valid(), form.errors

    def test_missing_ark_invalid(self):
        form = UpdateArkForm({"url": "https://example.com"})
        assert not form.is_valid()
        assert "ark" in form.errors

    def test_invalid_ark_format(self):
        form = UpdateArkForm({"ark": "not-an-ark"})
        assert not form.is_valid()
        assert "ark" in form.errors

    def test_clean_removes_missing_optional_fields(self):
        form = UpdateArkForm({"ark": "ark:/12345/abc123"})
        assert form.is_valid()
        assert "url" not in form.cleaned_data

    def test_clean_keeps_provided_optional_fields(self):
        form = UpdateArkForm({"ark": "ark:/12345/abc123", "title": "New Title"})
        assert form.is_valid()
        assert form.cleaned_data["title"] == "New Title"
