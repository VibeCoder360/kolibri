# Generated for face recognition login feature
from django.db import migrations
from django.db import models

import kolibri.core.fields
import kolibri.utils.time_utils


class Migration(migrations.Migration):

    dependencies = [
        ("kolibriauth", "0038_alter_facilitydataset_enable_qr_login"),
    ]

    operations = [
        migrations.AddField(
            model_name="facilitydataset",
            name="enable_face_login",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="FacilityUserFaceData",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("embeddings", kolibri.core.fields.JSONField(default=list)),
                ("embedding_version", models.IntegerField(default=1)),
                ("consent_acknowledged", models.BooleanField(default=False)),
                (
                    "enrolled_at",
                    kolibri.core.fields.DateTimeTzField(
                        default=kolibri.utils.time_utils.local_now
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=models.CASCADE,
                        related_name="face_data",
                        to="kolibriauth.facilityuser",
                    ),
                ),
            ],
        ),
    ]
