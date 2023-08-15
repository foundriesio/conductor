import json
from django.db import models


class APICallback(models.Model):
    endpoint = models.CharField(max_length=16)
    content = models.TextField(blank=True, null=True)

    def __str__(self):
        build_id = None
        if self.content:
            build_id = json.loads(self.content).get("build_id")
        return f"{self.endpoint} ({build_id})"
