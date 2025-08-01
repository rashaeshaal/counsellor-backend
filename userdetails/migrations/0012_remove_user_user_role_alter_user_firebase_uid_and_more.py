# Generated by Django 5.2.4 on 2025-07-22 07:00

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('userdetails', '0011_remove_user_name_counsellor_firebase_uid_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='user_role',
        ),
        migrations.AlterField(
            model_name='user',
            name='firebase_uid',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_role', models.CharField(choices=[('normal', 'Normal User'), ('counsellor', 'Counsellor')], default='normal', max_length=20)),
                ('phone_number', models.CharField(help_text='Phone number with country code', max_length=17, unique=True, validators=[django.core.validators.RegexValidator(message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed.", regex='^\\+?1?\\d{9,15}$')])),
                ('name', models.CharField(blank=True, max_length=100, null=True)),
                ('email', models.EmailField(blank=True, max_length=254, null=True, unique=True)),
                ('age', models.IntegerField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, choices=[('M', 'Male'), ('F', 'Female'), ('O', 'Other')], max_length=1, null=True)),
                ('qualification', models.TextField(blank=True, max_length=500, null=True)),
                ('experience', models.IntegerField(blank=True, null=True)),
                ('google_pay_number', models.CharField(blank=True, max_length=15, null=True)),
                ('account_number', models.CharField(blank=True, max_length=20, null=True)),
                ('ifsc_code', models.CharField(blank=True, max_length=11, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('is_approved', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('profile_photo', models.ImageField(blank=True, null=True, upload_to='profile_photos/')),
                ('firebase_uid', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AlterField(
            model_name='booking',
            name='counsellor',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='userdetails.userprofile'),
        ),
        migrations.AlterField(
            model_name='callrequest',
            name='counsellor',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_requests', to='userdetails.userprofile'),
        ),
        migrations.AlterField(
            model_name='counsellorpayment',
            name='counsellor',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='payment_settings', to='userdetails.userprofile'),
        ),
        migrations.DeleteModel(
            name='Counsellor',
        ),
    ]
