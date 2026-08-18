from datetime import datetime, timezone

import pytest
from model_bakery import baker

from apps.metrics.formulas import as_of_value, computed_series, evaluate_formula
from apps.metrics.models import FormulaDefinition, MetricEntry, MetricType, ValueType

pytestmark = pytest.mark.django_db


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def weight_type(db):
    return baker.make(MetricType, name="Weight", value_type=ValueType.NUMBER, unit="kg")


@pytest.fixture
def height_type(db):
    return baker.make(MetricType, name="Height", value_type=ValueType.NUMBER, unit="cm")


@pytest.fixture
def bmi_type(db):
    return baker.make(MetricType, name="BMI", value_type=ValueType.NUMBER, is_computed=True)


@pytest.fixture
def bmi_formula(bmi_type, weight_type, height_type):
    return baker.make(
        FormulaDefinition,
        computed_metric_type=bmi_type,
        formula_key=FormulaDefinition.FormulaKey.BMI,
        input_mapping={"weight_kg": weight_type.id, "height_cm": height_type.id},
    )


class TestAsOfValue:
    def test_returns_none_when_no_entries(self, weight_type, regular_user):
        assert as_of_value(metric_type_id=weight_type.id, user=regular_user, at=dt(2026, 1, 1)) is None

    def test_returns_most_recent_entry_at_or_before_timestamp(self, weight_type, regular_user):
        baker.make(
            MetricEntry, metric_type=weight_type, owner=regular_user, value=70, recorded_at=dt(2026, 1, 1)
        )
        baker.make(
            MetricEntry, metric_type=weight_type, owner=regular_user, value=72, recorded_at=dt(2026, 1, 10)
        )
        assert as_of_value(metric_type_id=weight_type.id, user=regular_user, at=dt(2026, 1, 5)) == 70
        assert as_of_value(metric_type_id=weight_type.id, user=regular_user, at=dt(2026, 1, 10)) == 72
        assert as_of_value(metric_type_id=weight_type.id, user=regular_user, at=dt(2025, 12, 1)) is None

    def test_ignores_other_users_entries(self, weight_type, regular_user, other_user):
        baker.make(
            MetricEntry, metric_type=weight_type, owner=other_user, value=999, recorded_at=dt(2026, 1, 1)
        )
        assert as_of_value(metric_type_id=weight_type.id, user=regular_user, at=dt(2026, 1, 5)) is None


class TestBmiFormula:
    def test_computes_bmi(self, bmi_formula, weight_type, height_type, regular_user):
        baker.make(
            MetricEntry, metric_type=weight_type, owner=regular_user, value=70, recorded_at=dt(2026, 1, 1)
        )
        baker.make(
            MetricEntry, metric_type=height_type, owner=regular_user, value=175, recorded_at=dt(2026, 1, 1)
        )
        value = evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 2))
        assert value == pytest.approx(70 / (1.75**2))

    def test_missing_input_yields_none_not_an_error(self, bmi_formula, weight_type, regular_user):
        baker.make(
            MetricEntry, metric_type=weight_type, owner=regular_user, value=70, recorded_at=dt(2026, 1, 1)
        )
        # height was never logged
        assert evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 2)) is None

    def test_no_data_at_all_yields_none(self, bmi_formula, regular_user):
        assert evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 2)) is None

    def test_as_of_respects_timestamp_before_any_data_logged(
        self, bmi_formula, weight_type, height_type, regular_user
    ):
        baker.make(
            MetricEntry, metric_type=weight_type, owner=regular_user, value=70, recorded_at=dt(2026, 2, 1)
        )
        baker.make(
            MetricEntry, metric_type=height_type, owner=regular_user, value=175, recorded_at=dt(2026, 2, 1)
        )
        assert evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 1)) is None


class TestBodyFatNavyFormula:
    @pytest.fixture
    def navy_formula(self, db, regular_user):
        waist = baker.make(MetricType, name="Waist", value_type=ValueType.NUMBER)
        neck = baker.make(MetricType, name="Neck", value_type=ValueType.NUMBER)
        height = baker.make(MetricType, name="Height2", value_type=ValueType.NUMBER)
        hip = baker.make(MetricType, name="Hip", value_type=ValueType.NUMBER)
        sex = baker.make(MetricType, name="Sex", value_type=ValueType.TEXT)
        computed = baker.make(
            MetricType, name="Body fat %", value_type=ValueType.NUMBER, is_computed=True
        )
        formula = baker.make(
            FormulaDefinition,
            computed_metric_type=computed,
            formula_key=FormulaDefinition.FormulaKey.BODY_FAT_NAVY,
            input_mapping={
                "waist_cm": waist.id,
                "neck_cm": neck.id,
                "height_cm": height.id,
                "hip_cm": hip.id,
                "sex": sex.id,
            },
        )
        return formula, {"waist": waist, "neck": neck, "height": height, "hip": hip, "sex": sex}

    def _log(self, metric_type, owner, value, at):
        baker.make(MetricEntry, metric_type=metric_type, owner=owner, value=value, recorded_at=at)

    def test_male_formula(self, navy_formula, regular_user):
        formula, types = navy_formula
        self._log(types["waist"], regular_user, 85, dt(2026, 1, 1))
        self._log(types["neck"], regular_user, 38, dt(2026, 1, 1))
        self._log(types["height"], regular_user, 180, dt(2026, 1, 1))
        self._log(types["sex"], regular_user, "male", dt(2026, 1, 1))
        value = evaluate_formula(formula, user=regular_user, at=dt(2026, 1, 2))
        assert value is not None
        assert 0 < value < 50

    def test_female_formula_requires_hip(self, navy_formula, regular_user):
        formula, types = navy_formula
        self._log(types["waist"], regular_user, 75, dt(2026, 1, 1))
        self._log(types["neck"], regular_user, 32, dt(2026, 1, 1))
        self._log(types["height"], regular_user, 165, dt(2026, 1, 1))
        self._log(types["sex"], regular_user, "female", dt(2026, 1, 1))
        # hip not logged yet -> omitted, not an error
        assert evaluate_formula(formula, user=regular_user, at=dt(2026, 1, 2)) is None

        self._log(types["hip"], regular_user, 95, dt(2026, 1, 1))
        value = evaluate_formula(formula, user=regular_user, at=dt(2026, 1, 2))
        assert value is not None
        assert 0 < value < 60


class TestTdeeMifflinFormula:
    @pytest.fixture
    def tdee_formula(self, db):
        weight = baker.make(MetricType, name="Weight2", value_type=ValueType.NUMBER)
        height = baker.make(MetricType, name="Height3", value_type=ValueType.NUMBER)
        dob = baker.make(MetricType, name="DOB", value_type=ValueType.DATE)
        sex = baker.make(MetricType, name="Sex2", value_type=ValueType.TEXT)
        activity = baker.make(MetricType, name="Activity", value_type=ValueType.TEXT)
        computed = baker.make(MetricType, name="TDEE", value_type=ValueType.NUMBER, is_computed=True)
        formula = baker.make(
            FormulaDefinition,
            computed_metric_type=computed,
            formula_key=FormulaDefinition.FormulaKey.TDEE_MIFFLIN,
            input_mapping={
                "weight_kg": weight.id,
                "height_cm": height.id,
                "dob": dob.id,
                "sex": sex.id,
                "activity_level": activity.id,
            },
        )
        return formula, {"weight": weight, "height": height, "dob": dob, "sex": sex, "activity": activity}

    def _log(self, metric_type, owner, value, at):
        baker.make(MetricEntry, metric_type=metric_type, owner=owner, value=value, recorded_at=at)

    def test_computes_tdee_for_male(self, tdee_formula, regular_user):
        formula, types = tdee_formula
        self._log(types["weight"], regular_user, 80, dt(2020, 1, 1))
        self._log(types["height"], regular_user, 180, dt(2020, 1, 1))
        self._log(types["dob"], regular_user, "1990-06-15", dt(2020, 1, 1))
        self._log(types["sex"], regular_user, "male", dt(2020, 1, 1))
        self._log(types["activity"], regular_user, "moderate", dt(2020, 1, 1))

        value = evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 20))
        age_at_eval = 36  # born 1990-06-15, evaluated 2026-06-20
        bmr = 10 * 80 + 6.25 * 180 - 5 * age_at_eval + 5
        assert value == pytest.approx(bmr * 1.55)

    def test_age_derived_as_of_evaluation_timestamp_not_today(self, tdee_formula, regular_user):
        formula, types = tdee_formula
        self._log(types["weight"], regular_user, 80, dt(2020, 1, 1))
        self._log(types["height"], regular_user, 180, dt(2020, 1, 1))
        self._log(types["dob"], regular_user, "1990-06-15", dt(2020, 1, 1))
        self._log(types["sex"], regular_user, "male", dt(2020, 1, 1))
        self._log(types["activity"], regular_user, "moderate", dt(2020, 1, 1))

        # Evaluated just before the birthday -> one year younger (higher BMR,
        # since age subtracts from it) than evaluated on/after it.
        before_birthday = evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 14))
        after_birthday = evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 15))
        assert before_birthday > after_birthday

    def test_missing_activity_level_yields_none(self, tdee_formula, regular_user):
        formula, types = tdee_formula
        self._log(types["weight"], regular_user, 80, dt(2020, 1, 1))
        self._log(types["height"], regular_user, 180, dt(2020, 1, 1))
        self._log(types["dob"], regular_user, "1990-06-15", dt(2020, 1, 1))
        self._log(types["sex"], regular_user, "male", dt(2020, 1, 1))
        assert evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 20)) is None


class TestComputedSeries:
    def test_evaluates_at_each_input_timestamp_in_range(
        self, bmi_formula, weight_type, height_type, regular_user
    ):
        self._log(weight_type, regular_user, 70, dt(2026, 1, 1))
        self._log(height_type, regular_user, 175, dt(2026, 1, 1))
        self._log(weight_type, regular_user, 71, dt(2026, 1, 10))

        series = computed_series(
            bmi_formula, user=regular_user, range_start=dt(2026, 1, 1), range_end=dt(2026, 1, 31)
        )
        assert [p.recorded_at for p in series] == [dt(2026, 1, 1), dt(2026, 1, 10)]
        assert series[0].value == pytest.approx(70 / (1.75**2))
        assert series[1].value == pytest.approx(71 / (1.75**2))

    def test_omits_timestamps_where_a_required_input_is_still_missing(
        self, bmi_formula, weight_type, height_type, regular_user
    ):
        # weight logged before height ever exists -> that timestamp has no BMI yet
        self._log(weight_type, regular_user, 70, dt(2026, 1, 1))
        self._log(height_type, regular_user, 175, dt(2026, 1, 5))

        series = computed_series(
            bmi_formula, user=regular_user, range_start=dt(2026, 1, 1), range_end=dt(2026, 1, 31)
        )
        assert [p.recorded_at for p in series] == [dt(2026, 1, 5)]

    def test_empty_range_yields_empty_series(self, bmi_formula, regular_user):
        series = computed_series(
            bmi_formula, user=regular_user, range_start=dt(2026, 1, 1), range_end=dt(2026, 1, 31)
        )
        assert series == []

    @staticmethod
    def _log(metric_type, owner, value, at):
        baker.make(MetricEntry, metric_type=metric_type, owner=owner, value=value, recorded_at=at)
