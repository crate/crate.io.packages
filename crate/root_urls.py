from django.conf.urls import patterns, include, url

urlpatterns = patterns("",
    url(r"^packages/", include('crate.web.urls'),
)
