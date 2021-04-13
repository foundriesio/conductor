from django.shortcuts import render, get_object_or_404
from conductor.core.models import Project

def index(request):
    projects = Project.objects.all()
    context = {"projects": projects}
    return render(request, "conductor/home.html", context)


def project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    context = {"project": project}
    return render(request, "conductor/project.html", context) 
