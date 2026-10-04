from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='loginlog',
            name='amount',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=9, null=True, verbose_name='ยอดเงิน (บาท)'),
        ),
        migrations.AddField(
            model_name='loginlog',
            name='payment_method',
            field=models.CharField(blank=True, choices=[('cash', 'เงินสด'), ('transfer', 'เงินโอน')], max_length=10, verbose_name='วิธีชำระเงิน'),
        ),
        migrations.AddField(
            model_name='loginlog',
            name='recorded_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='เวลาที่บันทึกยอด'),
        ),
        migrations.AddField(
            model_name='loginlog',
            name='recorded_by',
            field=models.CharField(blank=True, max_length=150, verbose_name='ผู้บันทึกยอด'),
        ),
    ]
