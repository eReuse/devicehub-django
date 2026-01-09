from django.db import models
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from utils.constants import ALGOS


ALGORITHMS = [(x, x) for x in ALGOS.keys()]


class Institution(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=255,
        unique=True,
        help_text=_("Official registered name of the organization.")
    )
    logo = models.CharField(_("Logo URL"), max_length=255, blank=True, null=True)

    responsable_person = models.CharField(_("Responsable Person"), max_length=255, blank=True, null=True)
    supervisor_person = models.CharField(_("Supervisor"), max_length=255, blank=True, null=True)

    facility_id_uri = models.URLField(
        _("Facility ID (URI)"),
        max_length=500,
        blank=True,
        null=True,
        help_text=_("Globally unique URI for this facility (e.g. https://...)")
    )
    facility_description = models.TextField(
        _("Facility Description"),
        blank=True,
        null=True
    )
    country = models.CharField(
        _("Country of Operation"),
        max_length=2,
        blank=True,
        null=True,
        help_text=_("ISO 3166-1 alpha-2 code (e.g., AU, US, DE).")
    )

    street_address = models.CharField(_("Street Address"), max_length=255, blank=True, null=True)
    postal_code = models.CharField(_("Postal Code"), max_length=20, blank=True, null=True)
    locality = models.CharField(_("City/Locality"), max_length=100, blank=True, null=True)
    region = models.CharField(_("State/Region"), max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name

class InstitutionSettings(models.Model):
    institution = models.OneToOneField(
        Institution,
        on_delete=models.CASCADE,
        related_name='settings',
        verbose_name=_("Institution")
    )

    algorithm = models.CharField(
        _("Algorithm"),
        max_length=30,
        default='ereuse24',
        help_text=_("The default algorithm used for device aggregation."),
        choices=ALGORITHMS,
    )

    issuer_did = models.CharField(
        _("Issuer DID"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("The W3C DID (e.g., did:web:example.com) that is used on the idhub service.")
    )
    signing_service_domain = models.URLField(
        _("Signing Service URL"),
        blank=True,
        null=True,
        help_text=_("Idhub endpoint where the credential will be signed.")
    )
    signing_auth_token = models.CharField(
        _("Signing API Token"),
        max_length=1024,
        blank=True,
        null=True,
        help_text=_("Bearer token for the signing service.")
    )

    device_dpp_schema = models.CharField(
        _("Device schema name"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Filename of the dpp credential schema found on your idhub provider.")
    )

    untp_drf_schema = models.CharField(
        _("UNTP's Digital Facility Record schema name"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("Filename of the drf schema found on your idhub provider.")
    )

    def __str__(self):
        return f"Settings for {self.institution.name}"

    class Meta:
        verbose_name = _("Institution Settings")
        verbose_name_plural = _("Institution Settings")


class UserManager(BaseUserManager):
    def create_user(self, email, institution, password=None, commit=True):
        """
        Creates and saves a User with the given email, date of
        birth and password.
        """
        if not email:
            raise ValueError("Users must have an email address")

        user = self.model(
            email=self.normalize_email(email),
            institution=institution
        )

        user.set_password(password)
        if commit:
            user.save(using=self._db)
        return user

    def create_superuser(self, email, institution, password=None):
        """
        Creates and saves a superuser with the given email and password.
        """
        user = self.create_user(
            email,
            institution,
            password=password,
            commit=False
        )

        user.is_admin = True
        user.save(using=self._db)
        return user

    def create_circuit_manager(self, email, institution, password=None):
        """
        Creates and saves a circuit manager with the given email and password.
        """
        user = self.create_user(
            email,
            institution=institution,
            password=password,
        )
        user.is_circuit_manager = True
        user.save(using=self._db)
        return user

    def create_shop(self, email, institution, password=None):
        """
        Creates and saves a shop with the given email and password.
        """
        user = self.create_user(
            email,
            institution=institution,
            password=password,
        )
        user.is_shop = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    email = models.EmailField(
        _('Email address'),
        max_length=255,
        unique=True,
    )
    is_active = models.BooleanField(_("is active"), default=True)
    is_admin = models.BooleanField(_("is admin"), default=False)
    is_circuit_manager = models.BooleanField(_("is circuitmanager"), default=False)
    is_shop = models.BooleanField(_("is shop"), default=False)
    first_name = models.CharField(_("First name"), max_length=255, blank=True, null=True)
    last_name = models.CharField(_("Last name"), max_length=255, blank=True, null=True)
    accept_gdpr = models.BooleanField(default=False)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="users")

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ['institution']

    def delete(self, **kwargs):
        if self.pk == 1:
            raise ProtectedError(
                f"User #{self.pk} is a protected user and cannot be deleted",
                self
            )
        super().delete(**kwargs)

    def save(self, *args, **kwargs):
        if self.pk == 1:
            self.is_admin = True
            self.is_active = True
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    def get_full_name(self):
        if self.first_name:
            return f"{self.first_name}{self.last_name}"
        else: return _("None")

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

    @property
    def username(self):
        "Is the email of the user"
        return self.email
