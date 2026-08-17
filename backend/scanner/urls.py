from django.urls import path

from . import views

urlpatterns = [
    path("scans/", views.ScanListCreateView.as_view(), name="scan-list"),
    path("scans/<int:pk>/", views.ScanDetailView.as_view(), name="scan-detail"),
    path("items/<int:pk>/resolve/", views.resolve_item, name="item-resolve"),
    path("library/", views.LibraryListCreateView.as_view(), name="library-list"),
    path("library/<int:pk>/", views.LibraryDetailView.as_view(), name="library-detail"),
    path("catalog/search/", views.catalog_search, name="catalog-search"),
]
