from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("metrics", "0005_seed_choice_options_data"),
    ]

    operations = [
        migrations.AddField(
            model_name="formuladefinition",
            name="expression",
            field=models.JSONField(
                null=True,
                blank=True,
                help_text="The formula's AST — see apps.metrics.formula_engine.",
            ),
        ),
    ]
