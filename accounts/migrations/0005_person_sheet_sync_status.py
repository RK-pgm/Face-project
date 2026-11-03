from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_loginlog_logged_out_at_loginlog_sheet_row"),
    ]

    operations = [
        migrations.AddField(
            model_name="person",
            name="sheet_synced_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Google Sheets sync time"),
        ),
        migrations.AddField(
            model_name="person",
            name="sheet_error",
            field=models.CharField(blank=True, max_length=200, verbose_name="Latest Google Sheets error"),
        ),
    ]
