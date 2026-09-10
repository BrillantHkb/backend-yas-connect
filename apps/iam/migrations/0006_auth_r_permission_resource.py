from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0005_auth_i_lock_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="permission",
            name="resource",
            field=models.CharField(default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="permission",
            name="code",
            field=models.CharField(db_index=True, max_length=96, unique=True),
        ),
        migrations.AlterUniqueTogether(
            name="permission",
            unique_together={("module", "resource", "action")},
        ),
    ]
