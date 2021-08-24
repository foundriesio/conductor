from django.shortcuts import render, get_object_or_404
from conductor.core.models import Project
from conductor.version import __version__ as app_version

def index(request):
    projects = Project.objects.all()
    context = {"projects": projects, "version": app_version}
    return render(request, "conductor/home.html", context)


def project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    context = {"project": project, "version": app_version}
    return render(request, "conductor/project.html", context)
