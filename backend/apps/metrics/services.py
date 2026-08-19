"""Write-side logic that doesn't fit in a serializer's create/update — see
CLAUDE.md's backend-layering convention. Uses so far: creating or replacing a
`MetricType`'s `MetricTypeChoice` rows is a multi-model write that should
commit atomically with the `MetricType` itself; resolving/persisting a bulk
metric-entry import is a multi-row write shared between the preview and
create endpoints (one parsing/resolution path for both, see the
`import_preview`/`bulk_import` actions in `views.py`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import MetricEntry, MetricType, MetricTypeChoice, ValueType

_TIME_DIRECTIVE_RE = re.compile(r"%[HIMSp]")


def create_metric_type_with_choices(
    *, validated_data: dict, choices_data: list[dict], user
) -> MetricType:
    with transaction.atomic():
        metric_type = MetricType.objects.create(created_by=user, **validated_data)
        _replace_choices(metric_type, choices_data)
    return metric_type


def update_metric_type_choices(*, metric_type: MetricType, choices_data: list[dict]) -> None:
    with transaction.atomic():
        _replace_choices(metric_type, choices_data)


def _replace_choices(metric_type: MetricType, choices_data: list[dict]) -> None:
    metric_type.choices.all().delete()
    MetricTypeChoice.objects.bulk_create(
        [
            MetricTypeChoice(
                metric_type=metric_type,
                code=choice["code"],
                label=choice["label"],
                numeric_value=choice.get("numeric_value"),
                order=choice.get("order", index),
            )
            for index, choice in enumerate(choices_data)
        ]
    )


_BOOLEAN_TRUE_TOKENS = {"true", "1", "yes", "y", "да"}
_BOOLEAN_FALSE_TOKENS = {"false", "0", "no", "n", "нет"}


def _parse_bulk_value(
    metric_type: MetricType, raw_value: str | None, *, decimal_separator: str, date_format: str
) -> Any:
    """Parses one row's raw `{value}` token into the Python value that would
    be stored on `MetricEntry.value`, per the metric type's `value_type`.
    Raises `ValueError` (with a short, stable message) on anything that
    doesn't parse — the caller turns that into an "invalid" row rather than
    failing the whole batch.
    """
    if raw_value is None or not raw_value.strip():
        raise ValueError("missing_value")
    raw_value = raw_value.strip()

    if metric_type.value_type == ValueType.NUMBER:
        normalized = raw_value.replace(" ", "")
        if decimal_separator == "," and "," in normalized:
            # A comma is present and configured as the decimal separator, so
            # any "." is a thousands separator (European formatting, e.g.
            # "1.234,56") — strip it. A row with no comma at all (a plain
            # "70.5") is left untouched rather than treating its "." as a
            # thousands separator, since that would silently mangle a value
            # that's already an unambiguous, correctly formatted number.
            normalized = normalized.replace(".", "").replace(",", ".")
        try:
            return float(normalized)
        except ValueError as exc:
            raise ValueError("invalid_number") from exc

    if metric_type.value_type == ValueType.CHOICE:
        lowered = raw_value.lower()
        for choice in metric_type.choices.all():
            if choice.code.lower() == lowered or choice.label.lower() == lowered:
                return choice.code
        raise ValueError("unknown_choice")

    if metric_type.value_type == ValueType.BOOLEAN:
        lowered = raw_value.lower()
        if lowered in _BOOLEAN_TRUE_TOKENS:
            return True
        if lowered in _BOOLEAN_FALSE_TOKENS:
            return False
        raise ValueError("invalid_boolean")

    if metric_type.value_type == ValueType.DATE:
        try:
            return datetime.strptime(raw_value, date_format).date().isoformat()
        except ValueError as exc:
            raise ValueError("invalid_date") from exc

    return raw_value  # TEXT


def _parse_bulk_date(raw_date: str | None, *, date_format: str) -> datetime | None:
    """Parses one row's raw `{date}` token (maps to `MetricEntry.recorded_at`)
    — `None` when the row has no date token at all (the template didn't
    include `{date}`), distinct from a present-but-unparseable token, which
    raises `ValueError`. The date component is always required; the time
    component is optional — `date_format` may include time directives
    (`%H`/`%I`/`%M`/`%S`/`%p`), in which case the parsed time-of-day is used,
    but when it doesn't, the current time of day is used instead of
    midnight, so a date-only import doesn't silently backdate every entry to
    00:00.
    """
    if raw_date is None or not raw_date.strip():
        return None
    try:
        parsed = datetime.strptime(raw_date.strip(), date_format)
    except ValueError as exc:
        raise ValueError("invalid_date") from exc
    if _TIME_DIRECTIVE_RE.search(date_format):
        return parsed
    return datetime.combine(parsed.date(), timezone.localtime(timezone.now()).time())


@dataclass
class ResolvedImportItem:
    line_number: int
    raw_value: str | None
    raw_date: str | None
    value: Any
    recorded_at: datetime | None
    status: str  # "new" | "duplicate_skip" | "duplicate_overwrite" | "invalid"
    error_code: str | None = None
    existing_entry_id: int | None = None

    def to_dict(self) -> dict:
        return {
            "line_number": self.line_number,
            "raw_value": self.raw_value,
            "raw_date": self.raw_date,
            "value": self.value,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
            "status": self.status,
            "error_code": self.error_code,
        }


def resolve_bulk_import_items(
    *,
    metric_type: MetricType,
    user,
    items: list[dict],
    date_format: str,
    decimal_separator: str,
    duplicate_policy: str,
) -> list[ResolvedImportItem]:
    """Parses and classifies every row of a bulk-import run — the single path
    shared by both the preview endpoint (read-only) and the create endpoint
    (which additionally persists via `execute_bulk_import`), so the two can
    never disagree about what a row's outcome will be.

    A row whose `{date}` token is absent (the chosen template has no date
    field) always resolves to "new" — there's nothing to compare it against
    for duplicate detection, same as every other row sharing "now" as their
    timestamp.
    """
    rows: list[dict] = []
    dates_needed: set[date] = set()
    for line_number, item in enumerate(items, start=1):
        raw_value = item.get("value")
        raw_date = item.get("date")
        error_code = None
        value = None
        parsed_datetime = None
        try:
            value = _parse_bulk_value(
                metric_type, raw_value, decimal_separator=decimal_separator, date_format=date_format
            )
        except ValueError as exc:
            error_code = str(exc)
        try:
            parsed_datetime = _parse_bulk_date(raw_date, date_format=date_format)
        except ValueError as exc:
            error_code = error_code or str(exc)
        rows.append(
            {
                "line_number": line_number,
                "raw_value": raw_value,
                "raw_date": raw_date,
                "value": value,
                "date": parsed_datetime,
                "error_code": error_code,
            }
        )
        if parsed_datetime is not None:
            dates_needed.add(parsed_datetime.date())

    existing_by_date: dict[date, MetricEntry] = {}
    if dates_needed:
        existing_entries = MetricEntry.objects.filter(
            metric_type=metric_type, owner=user, recorded_at__date__in=dates_needed
        )
        for entry in existing_entries:
            existing_by_date.setdefault(timezone.localtime(entry.recorded_at).date(), entry)

    current_tz = timezone.get_current_timezone()
    results: list[ResolvedImportItem] = []
    for row in rows:
        if row["error_code"]:
            results.append(
                ResolvedImportItem(
                    line_number=row["line_number"],
                    raw_value=row["raw_value"],
                    raw_date=row["raw_date"],
                    value=None,
                    recorded_at=None,
                    status="invalid",
                    error_code=row["error_code"],
                )
            )
            continue

        recorded_at = (
            timezone.make_aware(row["date"], current_tz)
            if row["date"] is not None
            else timezone.now()
        )
        existing = existing_by_date.get(row["date"].date()) if row["date"] is not None else None
        if existing is not None:
            status = "duplicate_overwrite" if duplicate_policy == "overwrite" else "duplicate_skip"
            existing_entry_id = existing.id
        else:
            status = "new"
            existing_entry_id = None

        results.append(
            ResolvedImportItem(
                line_number=row["line_number"],
                raw_value=row["raw_value"],
                raw_date=row["raw_date"],
                value=row["value"],
                recorded_at=recorded_at,
                status=status,
                existing_entry_id=existing_entry_id,
            )
        )
    return results


def execute_bulk_import(
    *, metric_type: MetricType, user, resolved_items: list[ResolvedImportItem]
) -> dict:
    """Persists the outcome of `resolve_bulk_import_items` — "new" rows are
    created, "duplicate_overwrite" rows update the existing entry's value in
    place, "duplicate_skip"/"invalid" rows are left untouched. Partial
    success: a bad row never rejects the rest of the batch.
    """
    created_count = 0
    updated_count = 0
    with transaction.atomic():
        for item in resolved_items:
            if item.status == "new":
                MetricEntry.objects.create(
                    metric_type=metric_type,
                    owner=user,
                    value=item.value,
                    recorded_at=item.recorded_at,
                )
                created_count += 1
            elif item.status == "duplicate_overwrite":
                MetricEntry.objects.filter(id=item.existing_entry_id).update(value=item.value)
                updated_count += 1

    return {
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": sum(1 for i in resolved_items if i.status == "duplicate_skip"),
        "invalid_count": sum(1 for i in resolved_items if i.status == "invalid"),
        "items": [item.to_dict() for item in resolved_items],
    }
