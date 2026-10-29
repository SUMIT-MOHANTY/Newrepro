"""
Schema exports for the Django Todo Application
"""
from app.users.schemas import (
    UserBaseSerializer,
    UserCreateSerializer,
    UserResponseSerializer,
    UserUpdateSerializer,
    PasswordChangeSerializer,
    TokenSerializer,
    LoginSerializer,
    RefreshTokenSerializer,
    LogoutSerializer,
)
from app.schemas.admin import (
    SystemStatsSerializer,
    UserActivitySerializer,
    TodoAnalyticsSerializer,
    UserActivitySummary,
    PriorityDistributionItem,
    StatusDistributionItem,
    CategoryDistributionItem,
    RecentActivityItem,
    SystemHealthStatus,
    AdminStatsResponse,
    AdminStatsFilter,
)

__all__ = [
    # User schemas
    "UserBaseSerializer",
    "UserCreateSerializer",
    "UserResponseSerializer",
    "UserUpdateSerializer",
    "PasswordChangeSerializer",
    "TokenSerializer",
    "LoginSerializer",
    "RefreshTokenSerializer",
    "LogoutSerializer",
    # Admin schemas
    "SystemStatsSerializer",
    "UserActivitySerializer",
    "TodoAnalyticsSerializer",
    "UserActivitySummary",
    "PriorityDistributionItem",
    "StatusDistributionItem",
    "CategoryDistributionItem",
    "RecentActivityItem",
    "SystemHealthStatus",
    "AdminStatsResponse",
    "AdminStatsFilter",
]
