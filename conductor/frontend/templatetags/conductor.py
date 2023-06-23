from django import template
from allauth.socialaccount.models import SocialApp
from allauth.socialaccount import providers


register = template.Library()


@register.simple_tag(takes_context=True)
def provider_login(context, provider_name):    
    request = context.get('request')
    provider = providers.registry.by_id(provider_name)
    return provider.get_login_url(request)

@register.inclusion_tag("account/_logininclude.html", takes_context=True)
def socialaccount_providers(context):
    provider_list = []
    configured_backends = SocialApp.objects.all()
    for backend in SocialApp.objects.all():
        provider = providers.registry.by_id(backend.provider)
        provider_list.append(provider)
    return {"providers": provider_list}
