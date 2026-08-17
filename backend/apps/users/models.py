from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model so the app isn't locked into Django's default `auth.User`.

    Kept close to `AbstractUser` for now; this is the seam where multi-user-specific
    fields (timezone, preferred units, etc.) can be added later without a data
    migration across every other app's user FKs.
    """
