import accounts.models
import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='LoginThrottle',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=60, unique=True)),
                ('failed_count', models.PositiveSmallIntegerField(default=0)),
                ('locked_until', models.DateTimeField(blank=True, null=True)),
                ('updated_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
        ),
        migrations.CreateModel(
            name='Person',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('first_name', models.CharField(max_length=50, verbose_name='ชื่อ')),
                ('last_name', models.CharField(max_length=50, verbose_name='นามสกุล')),
                ('nickname', models.CharField(max_length=30, verbose_name='ชื่อเล่น')),
                ('member_code', models.CharField(default=accounts.models.generate_member_code, max_length=12, unique=True, verbose_name='รหัสสมาชิก')),
                ('pin_hash', models.CharField(max_length=128, verbose_name='PIN (แฮช)')),
                ('face_photo', models.ImageField(upload_to=accounts.models.face_photo_path, verbose_name='รูปหน้า')),
                ('face_descriptor', models.JSONField(verbose_name='face descriptor (128 ค่า)')),
                ('consent_pdpa', models.BooleanField(default=False, verbose_name='ยินยอมเก็บภาพใบหน้า')),
                ('consent_at', models.DateTimeField(blank=True, null=True, verbose_name='เวลาที่ให้ความยินยอม')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='วันที่สมัคร')),
            ],
            options={
                'verbose_name': 'สมาชิก',
                'verbose_name_plural': 'สมาชิก',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='LoginLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('attempted_name', models.CharField(blank=True, max_length=50, verbose_name='ชื่อที่พิมพ์')),
                ('created_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='เวลา')),
                ('success', models.BooleanField(verbose_name='สำเร็จ')),
                ('fail_reason', models.CharField(blank=True, max_length=20, verbose_name='เหตุผล (ภายใน)')),
                ('sheet_status', models.CharField(choices=[('not_needed', 'ไม่ต้องส่ง'), ('pending', 'รอส่ง'), ('sending', 'กำลังส่ง'), ('sent', 'ส่งแล้ว'), ('failed', 'ส่งไม่สำเร็จ (จะลองใหม่)')], default='not_needed', max_length=12, verbose_name='สถานะส่งชีต')),
                ('sheet_attempts', models.PositiveSmallIntegerField(default=0, verbose_name='จำนวนครั้งที่ลองส่ง')),
                ('sheet_last_try', models.DateTimeField(blank=True, null=True, verbose_name='ลองส่งล่าสุด')),
                ('sheet_error', models.CharField(blank=True, max_length=200, verbose_name='ข้อผิดพลาดล่าสุดของชีต')),
                ('person', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='logs', to='accounts.person')),
            ],
            options={
                'verbose_name': 'ประวัติการล็อกอิน',
                'verbose_name_plural': 'ประวัติการล็อกอิน',
                'ordering': ['-created_at'],
            },
        ),
    ]
