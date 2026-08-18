# Data migration: converts every existing FormulaDefinition's formula_key +
# input_mapping into the new AST `expression`, using the same builder
# functions the seed command now uses for fresh installs. Accepted tradeoff:
# this migration imports live app code (apps.metrics.formula_engine.builtins)
# rather than duplicating the AST-construction logic inline — same pattern
# this project's seed_metrics.py already uses, and these builder functions
# are stable/self-contained enough for the risk to be low.

from django.db import migrations

from apps.metrics.formula_engine import builtins

_BUILDERS = {
    "bmi": lambda m: builtins.build_bmi(weight_kg_id=m["weight_kg"], height_cm_id=m["height_cm"]),
    "body_fat_navy": lambda m: builtins.build_body_fat_navy(
        waist_cm_id=m["waist_cm"],
        neck_cm_id=m["neck_cm"],
        height_cm_id=m["height_cm"],
        hip_cm_id=m["hip_cm"],
        sex_id=m["sex"],
    ),
    "tdee_mifflin": lambda m: builtins.build_tdee_mifflin(
        weight_kg_id=m["weight_kg"],
        height_cm_id=m["height_cm"],
        dob_id=m["dob"],
        sex_id=m["sex"],
        activity_level_id=m["activity_level"],
    ),
}


def migrate_forward(apps, schema_editor):
    FormulaDefinition = apps.get_model("metrics", "FormulaDefinition")
    for formula_definition in FormulaDefinition.objects.all():
        builder = _BUILDERS.get(formula_definition.formula_key)
        if builder is None:
            continue
        formula_definition.expression = builder(formula_definition.input_mapping)
        formula_definition.save(update_fields=["expression"])


def migrate_backward(apps, schema_editor):
    FormulaDefinition = apps.get_model("metrics", "FormulaDefinition")
    FormulaDefinition.objects.update(expression=None)


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0006_formula_expression_field"),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
