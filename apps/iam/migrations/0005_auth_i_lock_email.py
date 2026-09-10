# AUTH-I : locked_at + purpose/expires_at/revoked_at sur email_verifications.

from datetime import timedelta

from django.db import migrations, models


def backfill_email_verifications(apps, schema_editor):
    """Lignes D04 : REGISTER, expires_at = created_at + 48 h."""
    EmailVerification = apps.get_model("iam", "EmailVerification")
    ttl = timedelta(hours=48)
    rows = EmailVerification.objects.filter(expires_at__isnull=True)
    for row in rows.iterator():
        row.purpose = "REGISTER"
        row.expires_at = row.created_at + ttl
        row.save(update_fields=["purpose", "expires_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("iam", "0004_auth_g_reset_channel_totp"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="locked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="emailverification",
            name="purpose",
            field=models.CharField(
                choices=[("REGISTER", "Register"), ("EMAIL_CHANGE", "Email change")],
                default="REGISTER",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="emailverification",
            name="expires_at",
            field=models.DateTimeField(null=True),
        ),
        migrations.AddField(
            model_name="emailverification",
            name="revoked_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(backfill_email_verifications, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="emailverification",
            name="expires_at",
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name="emailverification",
            name="token_hash",
            field=models.TextField(unique=True),
        ),
    ]
