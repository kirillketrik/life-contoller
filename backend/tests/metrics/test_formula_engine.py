from datetime import UTC, datetime

import pytest
from model_bakery import baker

from apps.metrics.formula_engine import (
    builtins,
    computed_series,
    evaluate_formula,
    validate_expression,
)
from apps.metrics.formula_engine.interpreter import evaluate_node
from apps.metrics.formula_engine.nodes import parse_node
from apps.metrics.formula_engine.resolvers import AsOfResolver
from apps.metrics.models import FormulaDefinition, MetricEntry, MetricType, ValueType

pytestmark = pytest.mark.django_db


def dt(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


def log(metric_type, owner, value, at):
    baker.make(MetricEntry, metric_type=metric_type, owner=owner, value=value, recorded_at=at)


def make_choice(metric_type, code, label, numeric_value=None):
    baker.make(
        "metrics.MetricTypeChoice",
        metric_type=metric_type,
        code=code,
        label=label,
        numeric_value=numeric_value,
    )


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
        expression=builtins.build_bmi(weight_kg_id=weight_type.id, height_cm_id=height_type.id),
    )


def c(value) -> dict:
    return {"type": "constant", "value": value}


def binop(op, left, right) -> dict:
    return {"type": "binary_op", "op": op, "left": left, "right": right}


def unary(op, operand) -> dict:
    return {"type": "unary_op", "op": op, "operand": operand}


def fn(name, *args) -> dict:
    return {"type": "function", "name": name, "args": list(args)}


def compare(op, left, right) -> dict:
    return {"type": "comparison", "op": op, "left": left, "right": right}


class TestInterpreterOps:
    """Direct node-level tests, independent of any stored FormulaDefinition."""

    def _resolver(self):
        return AsOfResolver(user=None, at=dt(2026, 1, 1))

    def test_arithmetic_ops(self):
        expr = binop("+", c(2), binop("*", c(3), c(4)))
        assert evaluate_node(parse_node(expr), self._resolver()) == 14

    def test_exponent(self):
        expr = binop("^", c(2), c(10))
        assert evaluate_node(parse_node(expr), self._resolver()) == 1024

    def test_division_by_zero_yields_none(self):
        expr = binop("/", c(5), c(0))
        assert evaluate_node(parse_node(expr), self._resolver()) is None

    def test_sqrt_abs_neg(self):
        resolver = self._resolver()
        assert evaluate_node(parse_node(unary("sqrt", c(16))), resolver) == 4
        assert evaluate_node(parse_node(unary("abs", c(-3))), resolver) == 3
        assert evaluate_node(parse_node(unary("neg", c(3))), resolver) == -3

    def test_sqrt_of_negative_yields_none(self):
        expr = unary("sqrt", c(-1))
        assert evaluate_node(parse_node(expr), self._resolver()) is None

    def test_min_max_round(self):
        resolver = self._resolver()
        args = [c(v) for v in (3, 1, 2)]
        assert evaluate_node(parse_node(fn("min", *args)), resolver) == 1
        assert evaluate_node(parse_node(fn("max", *args)), resolver) == 3
        assert evaluate_node(parse_node(fn("round", c(3.456), c(1))), resolver) == 3.5

    def test_comparisons(self):
        resolver = self._resolver()
        cases = [
            ("==", True),
            ("!=", False),
            ("<", False),
            (">", False),
            ("<=", True),
            (">=", True),
        ]
        for op, expected in cases:
            expr = compare(op, c(5), c(5))
            assert evaluate_node(parse_node(expr), resolver) is expected

    def test_conditional(self):
        expr = {
            "type": "conditional",
            "condition": compare(">", c(5), c(1)),
            "then": c("big"),
            "else": c("small"),
        }
        assert evaluate_node(parse_node(expr), self._resolver()) == "big"

    def test_conditional_with_unresolved_condition_yields_none(self):
        expr = {
            "type": "conditional",
            "condition": {"type": "metric", "metric_type_id": 999999},
            "then": c(1),
            "else": c(2),
        }
        assert evaluate_node(parse_node(expr), self._resolver()) is None


class TestChoiceMetricResolution:
    def test_choice_without_numeric_value_resolves_to_code(self, regular_user):
        sex = baker.make(MetricType, name="Sex", value_type=ValueType.CHOICE)
        make_choice(sex, "male", "Мужской")
        log(sex, regular_user, "male", dt(2026, 1, 1))
        resolver = AsOfResolver(user=regular_user, at=dt(2026, 1, 2))
        assert resolver.resolve(sex.id) == "male"

    def test_choice_with_numeric_value_resolves_to_number(self, regular_user):
        activity = baker.make(MetricType, name="Activity", value_type=ValueType.CHOICE)
        make_choice(activity, "moderate", "Умеренная активность", numeric_value=1.55)
        log(activity, regular_user, "moderate", dt(2026, 1, 1))
        resolver = AsOfResolver(user=regular_user, at=dt(2026, 1, 2))
        assert resolver.resolve(activity.id) == 1.55


class TestBmiFormula:
    def test_computes_bmi(self, bmi_formula, weight_type, height_type, regular_user):
        log(weight_type, regular_user, 70, dt(2026, 1, 1))
        log(height_type, regular_user, 175, dt(2026, 1, 1))
        value = evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 2))
        assert value == pytest.approx(70 / (1.75**2))

    def test_missing_input_yields_none_not_an_error(self, bmi_formula, weight_type, regular_user):
        log(weight_type, regular_user, 70, dt(2026, 1, 1))
        assert evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 2)) is None

    def test_no_data_at_all_yields_none(self, bmi_formula, regular_user):
        assert evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 2)) is None

    def test_as_of_respects_timestamp_before_any_data_logged(
        self, bmi_formula, weight_type, height_type, regular_user
    ):
        log(weight_type, regular_user, 70, dt(2026, 2, 1))
        log(height_type, regular_user, 175, dt(2026, 2, 1))
        assert evaluate_formula(bmi_formula, user=regular_user, at=dt(2026, 1, 1)) is None


class TestBodyFatNavyFormula:
    @pytest.fixture
    def navy_formula(self, db):
        waist = baker.make(MetricType, name="Waist", value_type=ValueType.NUMBER)
        neck = baker.make(MetricType, name="Neck", value_type=ValueType.NUMBER)
        height = baker.make(MetricType, name="Height2", value_type=ValueType.NUMBER)
        hip = baker.make(MetricType, name="Hip", value_type=ValueType.NUMBER)
        sex = baker.make(MetricType, name="Sex", value_type=ValueType.CHOICE)
        make_choice(sex, "male", "Мужской")
        make_choice(sex, "female", "Женский")
        computed = baker.make(
            MetricType, name="Body fat %", value_type=ValueType.NUMBER, is_computed=True
        )
        formula = baker.make(
            FormulaDefinition,
            computed_metric_type=computed,
            expression=builtins.build_body_fat_navy(
                waist_cm_id=waist.id,
                neck_cm_id=neck.id,
                height_cm_id=height.id,
                hip_cm_id=hip.id,
                sex_id=sex.id,
            ),
        )
        return formula, {"waist": waist, "neck": neck, "height": height, "hip": hip, "sex": sex}

    def test_male_formula(self, navy_formula, regular_user):
        formula, types = navy_formula
        log(types["waist"], regular_user, 85, dt(2026, 1, 1))
        log(types["neck"], regular_user, 38, dt(2026, 1, 1))
        log(types["height"], regular_user, 180, dt(2026, 1, 1))
        log(types["sex"], regular_user, "male", dt(2026, 1, 1))
        value = evaluate_formula(formula, user=regular_user, at=dt(2026, 1, 2))
        assert value is not None
        assert 0 < value < 50

    def test_female_formula_requires_hip(self, navy_formula, regular_user):
        formula, types = navy_formula
        log(types["waist"], regular_user, 75, dt(2026, 1, 1))
        log(types["neck"], regular_user, 32, dt(2026, 1, 1))
        log(types["height"], regular_user, 165, dt(2026, 1, 1))
        log(types["sex"], regular_user, "female", dt(2026, 1, 1))
        assert evaluate_formula(formula, user=regular_user, at=dt(2026, 1, 2)) is None

        log(types["hip"], regular_user, 95, dt(2026, 1, 1))
        value = evaluate_formula(formula, user=regular_user, at=dt(2026, 1, 2))
        assert value is not None
        assert 0 < value < 60


class TestTdeeMifflinFormula:
    @pytest.fixture
    def tdee_formula(self, db):
        weight = baker.make(MetricType, name="Weight2", value_type=ValueType.NUMBER)
        height = baker.make(MetricType, name="Height3", value_type=ValueType.NUMBER)
        dob = baker.make(MetricType, name="DOB", value_type=ValueType.DATE)
        sex = baker.make(MetricType, name="Sex2", value_type=ValueType.CHOICE)
        make_choice(sex, "male", "Мужской")
        make_choice(sex, "female", "Женский")
        activity = baker.make(MetricType, name="Activity", value_type=ValueType.CHOICE)
        make_choice(activity, "moderate", "Умеренная активность", numeric_value=1.55)
        computed = baker.make(
            MetricType, name="TDEE", value_type=ValueType.NUMBER, is_computed=True
        )
        formula = baker.make(
            FormulaDefinition,
            computed_metric_type=computed,
            expression=builtins.build_tdee_mifflin(
                weight_kg_id=weight.id,
                height_cm_id=height.id,
                dob_id=dob.id,
                sex_id=sex.id,
                activity_level_id=activity.id,
            ),
        )
        types = {"weight": weight, "height": height, "dob": dob, "sex": sex, "activity": activity}
        return formula, types

    def test_computes_tdee_for_male(self, tdee_formula, regular_user):
        formula, types = tdee_formula
        log(types["weight"], regular_user, 80, dt(2020, 1, 1))
        log(types["height"], regular_user, 180, dt(2020, 1, 1))
        log(types["dob"], regular_user, "1990-06-15", dt(2020, 1, 1))
        log(types["sex"], regular_user, "male", dt(2020, 1, 1))
        log(types["activity"], regular_user, "moderate", dt(2020, 1, 1))

        value = evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 20))
        age_at_eval = 36
        bmr = 10 * 80 + 6.25 * 180 - 5 * age_at_eval + 5
        assert value == pytest.approx(bmr * 1.55)

    def test_age_derived_as_of_evaluation_timestamp_not_today(self, tdee_formula, regular_user):
        formula, types = tdee_formula
        log(types["weight"], regular_user, 80, dt(2020, 1, 1))
        log(types["height"], regular_user, 180, dt(2020, 1, 1))
        log(types["dob"], regular_user, "1990-06-15", dt(2020, 1, 1))
        log(types["sex"], regular_user, "male", dt(2020, 1, 1))
        log(types["activity"], regular_user, "moderate", dt(2020, 1, 1))

        before_birthday = evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 14))
        after_birthday = evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 15))
        assert before_birthday > after_birthday

    def test_missing_activity_level_yields_none(self, tdee_formula, regular_user):
        formula, types = tdee_formula
        log(types["weight"], regular_user, 80, dt(2020, 1, 1))
        log(types["height"], regular_user, 180, dt(2020, 1, 1))
        log(types["dob"], regular_user, "1990-06-15", dt(2020, 1, 1))
        log(types["sex"], regular_user, "male", dt(2020, 1, 1))
        assert evaluate_formula(formula, user=regular_user, at=dt(2026, 6, 20)) is None


class TestComputedSeries:
    def test_evaluates_at_each_input_timestamp_in_range(
        self, bmi_formula, weight_type, height_type, regular_user
    ):
        log(weight_type, regular_user, 70, dt(2026, 1, 1))
        log(height_type, regular_user, 175, dt(2026, 1, 1))
        log(weight_type, regular_user, 71, dt(2026, 1, 10))

        series = computed_series(
            bmi_formula, user=regular_user, range_start=dt(2026, 1, 1), range_end=dt(2026, 1, 31)
        )
        assert [p.recorded_at for p in series] == [dt(2026, 1, 1), dt(2026, 1, 10)]
        assert series[0].value == pytest.approx(70 / (1.75**2))
        assert series[1].value == pytest.approx(71 / (1.75**2))

    def test_omits_timestamps_where_a_required_input_is_still_missing(
        self, bmi_formula, weight_type, height_type, regular_user
    ):
        log(weight_type, regular_user, 70, dt(2026, 1, 1))
        log(height_type, regular_user, 175, dt(2026, 1, 5))

        series = computed_series(
            bmi_formula, user=regular_user, range_start=dt(2026, 1, 1), range_end=dt(2026, 1, 31)
        )
        assert [p.recorded_at for p in series] == [dt(2026, 1, 5)]

    def test_empty_range_yields_empty_series(self, bmi_formula, regular_user):
        series = computed_series(
            bmi_formula, user=regular_user, range_start=dt(2026, 1, 1), range_end=dt(2026, 1, 31)
        )
        assert series == []


class TestValidateExpression:
    def test_valid_expression_has_no_errors(self, weight_type, height_type):
        expr = builtins.build_bmi(weight_kg_id=weight_type.id, height_cm_id=height_type.id)
        assert validate_expression(expr, computed_metric_type_id=None) == []

    def test_malformed_structure_reports_invalid_structure(self):
        errors = validate_expression({"type": "not_a_real_type"}, computed_metric_type_id=None)
        assert [e.code for e in errors] == ["invalid_structure"]

    def test_missing_metric_type_id_is_reported(self):
        expr = {"type": "metric", "metric_type_id": 999999}
        errors = validate_expression(expr, computed_metric_type_id=None)
        assert [e.code for e in errors] == ["missing_metric_type"]

    def test_literal_division_by_zero_is_reported(self, weight_type):
        expr = {
            "type": "binary_op",
            "op": "/",
            "left": {"type": "metric", "metric_type_id": weight_type.id},
            "right": {"type": "constant", "value": 0},
        }
        errors = validate_expression(expr, computed_metric_type_id=None)
        assert [e.code for e in errors] == ["division_by_zero"]

    def test_direct_self_reference_is_a_circular_reference(self, bmi_type):
        expr = {"type": "metric", "metric_type_id": bmi_type.id}
        errors = validate_expression(expr, computed_metric_type_id=bmi_type.id)
        assert [e.code for e in errors] == ["circular_reference"]

    def test_transitive_self_reference_is_a_circular_reference(self, db):
        a = baker.make(MetricType, name="A", value_type=ValueType.NUMBER, is_computed=True)
        b = baker.make(MetricType, name="B", value_type=ValueType.NUMBER, is_computed=True)
        # b's formula depends on a
        baker.make(
            FormulaDefinition,
            computed_metric_type=b,
            expression={"type": "metric", "metric_type_id": a.id},
        )
        # proposed formula for a depends on b -> a -> b cycle
        proposed_expression_for_a = {"type": "metric", "metric_type_id": b.id}
        errors = validate_expression(proposed_expression_for_a, computed_metric_type_id=a.id)
        assert [e.code for e in errors] == ["circular_reference"]

    def test_non_circular_nested_computed_metric_is_allowed(
        self, bmi_type, weight_type, height_type
    ):
        baker.make(
            FormulaDefinition,
            computed_metric_type=bmi_type,
            expression=builtins.build_bmi(weight_kg_id=weight_type.id, height_cm_id=height_type.id),
        )
        other = baker.make(MetricType, name="Other", value_type=ValueType.NUMBER, is_computed=True)
        expr = {
            "type": "binary_op",
            "op": "+",
            "left": {"type": "metric", "metric_type_id": bmi_type.id},
            "right": {"type": "constant", "value": 1},
        }
        assert validate_expression(expr, computed_metric_type_id=other.id) == []
