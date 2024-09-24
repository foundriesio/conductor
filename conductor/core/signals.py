# Copyright 2021 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import logging
from conductor.core.models import Project
from conductor.core.tasks import create_project_repository, create_project_containers_repository, create_project_meta_repository
from django.db.models.signals import post_save
from django.dispatch import receiver


logger = logging.getLogger()


@receiver(post_save, sender=Project)
def on_project_save(sender, instance, created, **kwargs):
    #if created:
    #    create_project_repository.delay(instance.id)
    create_project_repository.s(instance.id).apply_async(countdown=10)
    create_project_containers_repository.s(instance.id).apply_async(countdown=10)
    create_project_meta_repository.s(instance.id).apply_async(countdown=10)
