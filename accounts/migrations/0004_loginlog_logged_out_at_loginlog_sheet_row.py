
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_alter_loginlog_options_alter_person_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginlog',
            name='logged_out_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Sign-out time'),
        ),
        migrations.AddField(
            model_name='loginlog',
            name='sheet_row',
            field=models.PositiveIntegerField(blank=True, null=True, verbose_name='Google Sheets row'),
        ),
    ]
