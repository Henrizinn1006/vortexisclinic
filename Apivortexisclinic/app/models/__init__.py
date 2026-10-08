"""Modelos do banco. Importar este pacote registra tudo no metadata."""
from app.models.agenda import AppointmentSeries, ScheduleBlock  # noqa: F401
from app.models.appointment import Appointment  # noqa: F401
from app.models.billing import BillingEvent, Plan, Subscription  # noqa: F401
from app.models.client import Client, ClientProfessional  # noqa: F401
from app.models.clinical import (ClinicalAccessLog, ClinicalNote,  # noqa: F401
                                 ClinicalNoteVersion)
from app.models.payment import Payment  # noqa: F401
from app.models.invitation import Invitation  # noqa: F401
from app.models.document import Document  # noqa: F401
from app.models.email import EmailMessage, EmailVerification  # noqa: F401
from app.models.lgpd import (Consent, DataRequest, DataRequestItem,  # noqa: F401
                             RetentionPolicy)
from app.models.membership import Membership, MembershipPermission  # noqa: F401
from app.models.profession import Profession  # noqa: F401
from app.models.professional import Professional  # noqa: F401
from app.models.rbac import Permission, Role, RolePermission  # noqa: F401
from app.models.security import AuthSession, PasswordResetToken, SecurityEvent  # noqa: F401
from app.models.tenant import Tenant, TenantSettings  # noqa: F401
from app.models.user import User  # noqa: F401

__all__ = [
    "User",
    "Client",
    "ClientProfessional",
    "Appointment",
    "AppointmentSeries",
    "ScheduleBlock",
    "ClinicalNote",
    "ClinicalNoteVersion",
    "ClinicalAccessLog",
    "Payment",
    "Tenant",
    "TenantSettings",
    "Plan",
    "Subscription",
    "Document",
    "EmailMessage",
    "EmailVerification",
    "Consent",
    "DataRequest",
    "DataRequestItem",
    "RetentionPolicy",
    "Invitation",
    "Membership",
    "MembershipPermission",
    "Professional",
    "Profession",
    "Role",
    "Permission",
    "RolePermission",
    "AuthSession",
    "PasswordResetToken",
    "SecurityEvent",
]
