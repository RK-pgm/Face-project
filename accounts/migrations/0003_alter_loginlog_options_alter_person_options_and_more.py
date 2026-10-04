import accounts.models
import django.utils.timezone
from django.db import migrations, models
class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_loginlog_amount_loginlog_payment_method_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='loginlog',
            options={'ordering': ['-created_at'], 'verbose_name': 'Sign-in history', 'verbose_name_plural': 'Sign-in history'},
        ),
        migrations.AlterModelOptions(
            name='person',
            options={'ordering': ['-created_at'], 'verbose_name': 'Member', 'verbose_name_plural': 'Member'},
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True, verbose_name='Amount (baht)'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='attempted_name',
            field=models.CharField(blank=True, max_length=50, verbose_name='Entered name'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='created_at',
            field=models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='Time'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='fail_reason',
            field=models.CharField(blank=True, max_length=20, verbose_name='Internal reason'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('cash', 'Cash'), ('transfer', 'Bank transfer')], max_length=10, verbose_name='Payment method'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='recorded_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Recorded at'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='recorded_by',
            field=models.CharField(blank=True, max_length=150, verbose_name='Recorded by'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='sheet_attempts',
            field=models.PositiveSmallIntegerField(default=0, verbose_name='Attempt count'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='sheet_error',
            field=models.CharField(blank=True, max_length=200, verbose_name='Latest sheet error'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='sheet_last_try',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Last attempt'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='sheet_status',
            field=models.CharField(choices=[('not_needed', 'Not required'), ('pending', 'Pending'), ('sending', 'Sending'), ('sent', 'Sent'), ('failed', 'Failed (will retry)')], default='not_needed', max_length=12, verbose_name='Sheet status'),
        ),
        migrations.AlterField(
            model_name='loginlog',
            name='success',
            field=models.BooleanField(verbose_name='Successful'),
        ),
        migrations.AlterField(
            model_name='person',
            name='consent_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Consent time'),
        ),
        migrations.AlterField(
            model_name='person',
            name='consent_pdpa',
            field=models.BooleanField(default=False, verbose_name='Consent to face data storage'),
        ),
        migrations.AlterField(
            model_name='person',
            name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name='Registration date'),
        ),
        migrations.AlterField(
            model_name='person',
            name='face_descriptor',
            field=models.JSONField(verbose_name='Face descriptor (128 values)'),
        ),
        migrations.AlterField(
            model_name='person',
            name='face_photo',
            field=models.ImageField(upload_to=accounts.models.face_photo_path, verbose_name='Face photo'),
        ),
        migrations.AlterField(
            model_name='person',
            name='first_name',
            field=models.CharField(max_length=50, verbose_name='First name'),
        ),
        migrations.AlterField(
            model_name='person',
            name='last_name',
            field=models.CharField(max_length=50, verbose_name='Last name'),
        ),
        migrations.AlterField(
            model_name='person',
            name='member_code',
            field=models.CharField(default=accounts.models.generate_member_code, max_length=12, unique=True, verbose_name='Member ID'),
        ),
        migrations.AlterField(
            model_name='person',
            name='nickname',
            field=models.CharField(max_length=30, verbose_name='Nickname'),
        ),
        migrations.AlterField(
            model_name='person',
            name='pin_hash',
            field=models.CharField(max_length=128, verbose_name='PIN hash'),
        ),
    ]
