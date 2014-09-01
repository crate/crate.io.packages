from django.conf.urls import patterns, url

from crate.web.packages.simple.views import PackageIndex, PackageDetail

handler404 = "crate.web.packages.simple.views.not_found"

urlpatterns = patterns("",
    url(r"^$", PackageIndex.as_view(restricted=True), name="simple_package_index"),
    url(r"^(?P<slug>[^/]+)/(?:(?P<version>[^/]+)/)?$", PackageDetail.as_view(restricted=True), name="simple_package_detail"),
)
