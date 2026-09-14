# PRES-A : légende sous la pastille. Enum AWAY/IN_MEETING = TextChoices seulement (varchar 16).

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0006_auth_r_permission_resource"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="status_message",
            field=models.CharField(blank=True, default="", max_length=140),
        ),
        migrations.AlterField(
            model_name="user",
            name="status",
            field=models.CharField(
                choices=[
                    ("ONLINE", "Online"),
                    ("AWAY", "Away"),
                    ("IN_MEETING", "In Meeting"),
                    ("OFFLINE", "Offline"),
                ],
                db_index=True,
                default="OFFLINE",
                max_length=16,
            ),
        ),
    ]
