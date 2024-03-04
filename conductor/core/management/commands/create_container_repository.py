# Copyright 2023 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import logging
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from conductor.core.models import Project
from conductor.core.tasks import create_project_containers_repository

class Command(BaseCommand):
    help = "Clone container repository for project"

    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.add_argument("--project", help="Name of the project")

    def handle(self, *args, **options):
        self.logger = logging.getLogger("core")
        self.logger.setLevel(logging.DEBUG)
        self.logger.setLevel(logging.DEBUG)
        if options["verbosity"] == 0:
            self.logger.setLevel(logging.ERROR)
        elif options["verbosity"] == 1:
            self.logger.setLevel(logging.WARN)
        elif options["verbosity"] == 2:
            self.logger.setLevel(logging.INFO)

        project_name = options["project"]
        self.logger.info(f"Cloning containers repository for {project_name}")
        self.logger.debug("Debug enabled")
        try:
            project = Project.objects.get(name=project_name)
        except Project.DoesNotExist:
            logger.error(f"Project {project_name} does not exist")
            return
        create_project_containers_repository(project.id)
