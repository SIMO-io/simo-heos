# Generated by Django 4.2.10 on 2025-01-03 15:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('simo_heos', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='hplayer',
            name='pid',
            field=models.IntegerField(db_index=True),
        ),
        migrations.AlterUniqueTogether(
            name='hplayer',
            unique_together={('device', 'pid')},
        ),
    ]