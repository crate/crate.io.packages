from django.conf.urls import patterns, url

from crate.web.packages.views import ReleaseDetail
from crate.web.search.views import Search

urlpatterns = patterns("",
    url(r"^(?P<package>[^/]+)/(?:(?P<version>[^/]+)/)?$", ReleaseDetail.as_view(), name="old_package_detail"),
)
