from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from conductor.core.models import Project
from conductor.core.tasks import schedule_lmp_pr_tests
from conductor.version import __version__ as app_version

@login_required
def index(request):
    projects = Project.objects.all()
    context = {"projects": projects, "version": app_version}
    return render(request, "conductor/home.html", context)


@login_required
def project(request, project_id):
    project = get_object_or_404(Project, pk=project_id)
    api_builds = project.get_api_builds()
    context = {"project": project, "version": app_version, "api_builds": api_builds}
    return render(request, "conductor/project.html", context)


@login_required
def start_project_qa(request, project_id, ci_id):
    project = get_object_or_404(Project, pk=project_id)
    build_details = project.ci_build_details(ci_id)
    schedule_lmp_pr_tests.delay(build_details)
    return redirect("project-details", project_id=project.id)
