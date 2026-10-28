"""
URL Configuration for the Django Todo Application
"""
from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def api_root(request):
    """API root endpoint."""
    return JsonResponse({
        "message": "Todo Application API",
        "version": "1.0.0",
        "docs": "/api/docs/",
        "health": "/health",
    })


urlpatterns = [
    # Health check (handled by middleware, but include here for completeness)
    path("health/", api_root, name="health"),
    
    # Admin
    path("admin/", admin.site.urls),
    
    # API Root
    path("api/", api_root, name="api-root"),
    
    # Authentication endpoints
    path("api/auth/", include("app.users.urls")),
    
    # Todo endpoints - registered with /api/todos/ route prefix
    path("api/todos/", include("app.todos.urls")),
    
    # OpenAPI Schema
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    
    # Swagger UI
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    
    # ReDoc
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]
