import os
import sys

backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import models

User = models.User
Organization = getattr(models, "Organization", None)
UserOrganizationRole = getattr(models, "UserOrganizationRole", None)
OrganizationInvite = getattr(models, "OrganizationInvite", None)
OrganizationSSOSettings = getattr(models, "OrganizationSSOSettings", None)
Role = getattr(models, "Role", None)
Permission = getattr(models, "Permission", None)

__all__ = [
    "User",
    "Organization",
    "UserOrganizationRole",
    "OrganizationInvite",
    "OrganizationSSOSettings",
    "Role",
    "Permission",
]
