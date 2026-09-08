from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="NumberSequence",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("scope", models.CharField(max_length=50, verbose_name="النطاق")),
                (
                    "period",
                    models.CharField(
                        blank=True, default="", max_length=20, verbose_name="الفترة"
                    ),
                ),
                (
                    "last_value",
                    models.PositiveBigIntegerField(default=0, verbose_name="آخر قيمة"),
                ),
            ],
            options={
                "verbose_name": "تسلسل ترقيم",
                "verbose_name_plural": "تسلسلات الترقيم",
            },
        ),
        migrations.AddConstraint(
            model_name="numbersequence",
            constraint=models.UniqueConstraint(
                fields=("scope", "period"), name="numbersequence_scope_period_uniq"
            ),
        ),
    ]
