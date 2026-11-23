from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Role, User


@transaction.atomic
def create_user_service(
    *, email, password, first_name="", last_name="", role=None, department=None, vendor=None
):
    """
    Service layer function to create a new user with proper password hashing and atomic transaction.
    """
    clean_email = (email or "").strip().lower()
    if User.objects.filter(email__iexact=clean_email).exists():
        raise ValidationError(f"User with email '{email}' already exists.")

    user = User(
        email=clean_email,
        username=clean_email,
        first_name=first_name,
        last_name=last_name,
        role=role,
        department=department,
        vendor=vendor,
    )
    user.set_password(password)
    user.save()

    from apps.audit.models import AuditLog
    from apps.core.middleware import get_current_user

    AuditLog.objects.create(
        actor=get_current_user(),
        action=AuditLog.ACTION_CREATE,
        target_model="User",
        target_object_id=str(user.id),
        previous_state=None,
        new_state={
            "email": user.email,
            "role": getattr(user.role, "code", None),
            "is_active": user.is_active,
        },
    )
    return user


@transaction.atomic
def update_user_role_service(*, user: User, new_role: Role):
    """
    Updates user assigned role safely within a database transaction.
    """
    old_role_code = getattr(user.role, "code", None)
    user.role = new_role
    user.save(update_fields=["role", "updated_at"] if hasattr(user, "updated_at") else ["role"])

    from apps.audit.models import AuditLog
    from apps.core.middleware import get_current_user

    AuditLog.objects.create(
        actor=get_current_user(),
        action=AuditLog.ACTION_UPDATE,
        target_model="User",
        target_object_id=str(user.id),
        previous_state={"role": old_role_code},
        new_state={"role": getattr(new_role, "code", None)},
    )
    return user
