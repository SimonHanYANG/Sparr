"""Password policy: length + uppercase + lowercase + special character."""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

MIN_LENGTH = 8
MAX_LENGTH = 64


class SparrPasswordValidator:
    """Require length bounds, upper & lower case letters, and at least one
    special (non-alphanumeric) character."""

    def validate(self, password, user=None):
        errors = []
        if len(password) < MIN_LENGTH:
            errors.append(_("密码长度至少 %(min)d 位。") % {"min": MIN_LENGTH})
        if len(password) > MAX_LENGTH:
            errors.append(_("密码长度不能超过 %(max)d 位。") % {"max": MAX_LENGTH})
        if not re.search(r"[a-z]", password):
            errors.append(_("密码需包含小写字母。"))
        if not re.search(r"[A-Z]", password):
            errors.append(_("密码需包含大写字母。"))
        if not re.search(r"[^A-Za-z0-9]", password):
            errors.append(_("密码需包含特殊字符（非字母数字）。"))
        if errors:
            raise ValidationError(errors)

    def get_help_text(self):
        return _(
            "密码需 8–64 位，且同时包含大写字母、小写字母和特殊字符。"
        )
