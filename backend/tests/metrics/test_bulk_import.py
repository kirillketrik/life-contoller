
import pytest
from django.utils import timezone
from model_bakery import baker
from rest_framework import status

from apps.metrics.models import MetricEntry, MetricImportSettings, ValueType

pytestmark = pytest.mark.django_db


def _preview_url(metric_type) -> str:
    return f"/api/metric-types/{metric_type.id}/import/preview/"


def _import_url(metric_type) -> str:
    return f"/api/metric-types/{metric_type.id}/import/"


def _settings_url(metric_type) -> str:
    return f"/api/metric-types/{metric_type.id}/import-settings/"


def _base_payload(items, **overrides):
    payload = {
        "items": items,
        "date_format": "%d.%m.%Y",
        "decimal_separator": ".",
        "duplicate_policy": "skip",
    }
    payload.update(overrides)
    return payload


def _jan_1_recorded_at():
    return timezone.datetime(2026, 1, 1, 12, 0, tzinfo=timezone.get_current_timezone())


@pytest.fixture
def sex_metric_type(db):
    metric_type = baker.make("metrics.MetricType", value_type=ValueType.CHOICE, name="Пол")
    baker.make("metrics.MetricTypeChoice", metric_type=metric_type, code="male", label="Мужской")
    baker.make("metrics.MetricTypeChoice", metric_type=metric_type, code="female", label="Женский")
    return metric_type


class TestBulkImportPreview:
    def test_anonymous_cannot_preview(self, api_client, number_metric_type):
        response = api_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "1", "date": "01.01.2026"}]),
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_preview_does_not_persist(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}]),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert not MetricEntry.objects.exists()
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["value"] == 70.5

    def test_preview_rejects_computed_metric_type(self, authenticated_client):
        computed = baker.make("metrics.MetricType", value_type=ValueType.NUMBER, is_computed=True)
        response = authenticated_client.post(
            _preview_url(computed),
            _base_payload([{"value": "1", "date": "01.01.2026"}]),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_preview_rejects_singleton_metric_type(self, authenticated_client):
        singleton = baker.make("metrics.MetricType", value_type=ValueType.NUMBER, is_singleton=True)
        response = authenticated_client.post(
            _preview_url(singleton),
            _base_payload([{"value": "1", "date": "01.01.2026"}]),
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_preview_unknown_metric_type_404s(self, authenticated_client):
        response = authenticated_client.post(
            "/api/metric-types/999999/import/preview/",
            _base_payload([{"value": "1", "date": "01.01.2026"}]),
            format="json",
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_number_value_respects_comma_decimal_separator(
        self, authenticated_client, number_metric_type
    ):
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70,5", "date": "01.01.2026"}], decimal_separator=","),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["value"] == 70.5

    def test_dot_decimal_value_is_untouched_under_comma_policy(
        self, authenticated_client, number_metric_type
    ):
        """A row with no comma at all (already an unambiguous "70.5") must
        not have its "." stripped as a thousands separator just because the
        run's decimal_separator is set to comma — only a value that actually
        mixes both symbols (European "1.234,56" style) should."""
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}], decimal_separator=","),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["value"] == 70.5

    def test_european_thousands_separator_is_stripped_under_comma_policy(
        self, authenticated_client, number_metric_type
    ):
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "1.234,5", "date": "01.01.2026"}], decimal_separator=","),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["value"] == 1234.5

    def test_invalid_number_is_flagged_invalid(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "not-a-number", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "invalid"
        assert item["error_code"] == "invalid_number"

    def test_missing_value_is_flagged_invalid(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "invalid"
        assert item["error_code"] == "missing_value"

    def test_choice_value_matches_code_case_insensitively(
        self, authenticated_client, sex_metric_type
    ):
        response = authenticated_client.post(
            _preview_url(sex_metric_type),
            _base_payload([{"value": "MALE", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["value"] == "male"

    def test_choice_value_matches_label_case_insensitively(
        self, authenticated_client, sex_metric_type
    ):
        response = authenticated_client.post(
            _preview_url(sex_metric_type),
            _base_payload([{"value": "женский", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["value"] == "female"

    def test_unknown_choice_value_is_flagged_invalid(self, authenticated_client, sex_metric_type):
        response = authenticated_client.post(
            _preview_url(sex_metric_type),
            _base_payload([{"value": "other", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "invalid"
        assert item["error_code"] == "unknown_choice"

    def test_row_matching_existing_entry_date_is_duplicate(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=50,
            recorded_at=_jan_1_recorded_at(),
        )
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "duplicate_skip"

    def test_duplicate_overwrite_policy_flags_row_accordingly(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=50,
            recorded_at=_jan_1_recorded_at(),
        )
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}], duplicate_policy="overwrite"),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "duplicate_overwrite"

    def test_duplicate_detection_is_scoped_per_user(
        self, authenticated_client, number_metric_type, other_user
    ):
        baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=other_user,
            value=50,
            recorded_at=_jan_1_recorded_at(),
        )
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"

    def test_row_without_date_token_is_always_new(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            _preview_url(number_metric_type),
            _base_payload([{"value": "70.5"}]),
            format="json",
        )
        [item] = response.data["items"]
        assert item["status"] == "new"
        assert item["recorded_at"] is not None


class TestBulkImportCreate:
    def test_anonymous_cannot_import(self, api_client, number_metric_type):
        response = api_client.post(
            _import_url(number_metric_type),
            _base_payload([{"value": "1", "date": "01.01.2026"}]),
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_valid_rows_are_created_owned_by_requesting_user(
        self, authenticated_client, number_metric_type, regular_user
    ):
        response = authenticated_client.post(
            _import_url(number_metric_type),
            _base_payload(
                [
                    {"value": "70.5", "date": "01.01.2026"},
                    {"value": "71.0", "date": "02.01.2026"},
                ]
            ),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        assert response.data["created_count"] == 2
        entries = MetricEntry.objects.filter(metric_type=number_metric_type, owner=regular_user)
        assert entries.count() == 2

    def test_invalid_rows_do_not_block_valid_rows(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            _import_url(number_metric_type),
            _base_payload(
                [
                    {"value": "not-a-number", "date": "01.01.2026"},
                    {"value": "71.0", "date": "02.01.2026"},
                ]
            ),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["created_count"] == 1
        assert response.data["invalid_count"] == 1
        assert MetricEntry.objects.count() == 1

    def test_duplicate_skip_policy_leaves_existing_entry_untouched(
        self, authenticated_client, number_metric_type, regular_user
    ):
        existing = baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=50,
            recorded_at=_jan_1_recorded_at(),
        )
        response = authenticated_client.post(
            _import_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}], duplicate_policy="skip"),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["skipped_count"] == 1
        existing.refresh_from_db()
        assert existing.value == 50

    def test_duplicate_overwrite_policy_updates_existing_entry(
        self, authenticated_client, number_metric_type, regular_user
    ):
        existing = baker.make(
            MetricEntry,
            metric_type=number_metric_type,
            owner=regular_user,
            value=50,
            recorded_at=_jan_1_recorded_at(),
        )
        response = authenticated_client.post(
            _import_url(number_metric_type),
            _base_payload([{"value": "70.5", "date": "01.01.2026"}], duplicate_policy="overwrite"),
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["updated_count"] == 1
        existing.refresh_from_db()
        assert existing.value == 70.5
        remaining = MetricEntry.objects.filter(metric_type=number_metric_type, owner=regular_user)
        assert remaining.count() == 1

    def test_import_rejects_empty_items(self, authenticated_client, number_metric_type):
        response = authenticated_client.post(
            _import_url(number_metric_type), _base_payload([]), format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestMetricImportSettings:
    def test_get_returns_null_when_unset(self, authenticated_client, number_metric_type):
        response = authenticated_client.get(_settings_url(number_metric_type))
        assert response.status_code == status.HTTP_200_OK
        assert response.data is None

    def test_put_creates_settings(self, authenticated_client, number_metric_type, regular_user):
        response = authenticated_client.put(
            _settings_url(number_metric_type),
            {
                "template": "{date}{sep}{value}",
                "separator": ";",
                "date_format": "%d.%m.%Y",
                "decimal_separator": ".",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        settings_obj = MetricImportSettings.objects.get(
            user=regular_user, metric_type=number_metric_type
        )
        assert settings_obj.separator == ";"

    def test_put_updates_existing_settings(
        self, authenticated_client, number_metric_type, regular_user
    ):
        baker.make(
            MetricImportSettings,
            user=regular_user,
            metric_type=number_metric_type,
            template="{value}",
            separator=" ",
            date_format="%Y-%m-%d",
            decimal_separator=".",
        )
        response = authenticated_client.put(
            _settings_url(number_metric_type),
            {
                "template": "{date}{sep}{value}",
                "separator": ",",
                "date_format": "%d.%m.%Y",
                "decimal_separator": ",",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK
        remaining = MetricImportSettings.objects.filter(
            user=regular_user, metric_type=number_metric_type
        )
        assert remaining.count() == 1
        settings_obj = remaining.get()
        assert settings_obj.separator == ","
        assert settings_obj.decimal_separator == ","

    def test_put_accepts_a_space_only_separator(
        self, authenticated_client, number_metric_type, regular_user
    ):
        """A space is a common, meaningful separator value — must not be
        rejected as blank (regression: DRF's CharField trims whitespace by
        default, which reduces " " to "" unless trim_whitespace=False)."""
        response = authenticated_client.put(
            _settings_url(number_metric_type),
            {
                "template": "{date}{sep}{value}",
                "separator": " ",
                "date_format": "%d.%m.%Y",
                "decimal_separator": ".",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK, response.data
        settings_obj = MetricImportSettings.objects.get(
            user=regular_user, metric_type=number_metric_type
        )
        assert settings_obj.separator == " "

    def test_settings_are_scoped_per_user(
        self, authenticated_client, number_metric_type, other_user
    ):
        baker.make(
            MetricImportSettings,
            user=other_user,
            metric_type=number_metric_type,
            template="{value}",
            separator=" ",
            date_format="%Y-%m-%d",
            decimal_separator=".",
        )
        response = authenticated_client.get(_settings_url(number_metric_type))
        assert response.status_code == status.HTTP_200_OK
        assert response.data is None

    def test_anonymous_cannot_read_settings(self, api_client, number_metric_type):
        response = api_client.get(_settings_url(number_metric_type))
        assert response.status_code == status.HTTP_403_FORBIDDEN
