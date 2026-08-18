from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0007_migrate_formula_expressions_data"),
    ]

    operations = [
        migrations.RemoveField(model_name="formuladefinition", name="formula_key"),
        migrations.RemoveField(model_name="formuladefinition", name="input_mapping"),
        migrations.AlterField(
            model_name="formuladefinition",
            name="expression",
            field=models.JSONField(help_text="The formula's AST — see apps.metrics.formula_engine."),
        ),
    ]
