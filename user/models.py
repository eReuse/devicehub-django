from django.db import models
from django.db.models import ProtectedError
from django.core.validators import URLValidator, RegexValidator, MinValueValidator, MaxValueValidator
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from utils.constants import ALGOS


ALGORITHMS = [(x, x) for x in ALGOS.keys()]

class QRContentType(models.TextChoices):
    NONE = 'NONE', _("No QR on label")
    DEVICE_ID = 'INTERNAL', _("Internal Device ID")
    DEVICE_INVENTORY = 'INVENTORY', _("Device inventory URL")
    PUBLIC_VIEW = 'PUBLIC', _("Public Device View")
    DPP_URL = 'DPP', _("DPP URL (DPP or Inventory)")
    DID = 'DID', _("DID (Fallback to Short ID)")

class LabelVersion(models.TextChoices):
    V1 = 'V1', _("Version 1 (Classic)")
    V2 = 'V2', _("Version 2 (Modern Customizable)")

class LabelOrientation(models.TextChoices):
    HORIZONTAL = 'HORIZONTAL', _("Horizontal (Landscape)")
    VERTICAL = 'VERTICAL', _("Vertical (Portrait)")

def default_printed_properties():
    return ["ID"]

class Institution(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=255,
        unique=True,
        help_text=_("Official registered name of the organization.")
    )
    logo = models.CharField(
        _("Logo URL"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("A public URL pointing to the organization's logo image.")
    )

    responsable_person = models.CharField(
        _("Responsible Person"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("The primary person responsible for the operations at this facility.")
    )
    supervisor_person = models.CharField(
        _("Supervisor"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("The person supervising this facility or organization.")
    )

    facility_id_uri = models.URLField(
        _("Facility ID (URI)"),
        max_length=500,
        blank=True,
        null=True,
        validators=[URLValidator(schemes=['http', 'https', 'did'])],
        help_text=_("Globally unique URI for this facility (e.g., did:web:example.com).")
    )
    facility_description = models.TextField(
        _("Facility Description"),
        blank=True,
        null=True,
        help_text=_("A detailed description of the facility's main activities and scope.")
    )
    country = models.CharField(
        _("Country of Operation"),
        max_length=2,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^[A-Z]{2}$', _("Must be a 2-letter uppercase ISO code (e.g. AU, DE)"))],
        help_text=_("ISO 3166-1 alpha-2 code (e.g., AU, US, DE).")
    )

    street_address = models.CharField(
        _("Street Address"),
        max_length=255,
        blank=True,
        null=True,
        help_text=_("The physical street address of the facility.")
    )
    postal_code = models.CharField(
        _("Postal Code"),
        max_length=20,
        blank=True,
        null=True,
        help_text=_("The postal or ZIP code.")
    )
    location = models.CharField(
        _("City/Locality"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("The city, town, or locality name.")
    )
    region = models.CharField(
        _("State/Region"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("The state, province, or geographic region.")
    )

    algorithm = models.CharField(
        _("Algorithm"),
        max_length=30,
        default='ereuse24',
        choices=ALGORITHMS,
        help_text=_("The default algorithm used for device aggregation."),
    )

    @property
    def latest_facility_credential(self):
        return self.credentialproperty_set.filter(
            uuid__isnull=True,
            key='DigitalFacilityRecord'
        ).order_by('-created').first()

    def __str__(self):
        return self.name


class InstitutionSettings(models.Model):
    institution = models.OneToOneField(
        Institution,
        on_delete=models.CASCADE,
        verbose_name=_("Institution"),
        help_text=_("The institution these settings belong to."),
        related_name='settings'
    )

    # --- QR Settings ---
    qr_content_type = models.CharField(
        _("QR Code Content"),
        max_length=20,
        choices=QRContentType.choices,
        default=QRContentType.DEVICE_ID,
        help_text=_("Determines what data is embedded inside the QR code.")
    )
    qr_printed_properties = models.JSONField(
        _("Properties to Print"),
        default=default_printed_properties,
        blank=True,
        help_text=_("List of device properties (e.g., 'ram', 'cpu', 'storage') to print alongside the QR code.")
    )
    qr_include_logo = models.BooleanField(
        _("Print Institution Logo"),
        default=True,
        help_text=_("Check to include the institution's logo (if exists) on printed QR labels.")
    )
    qr_label_header = models.CharField(
        _("Label Header Text"),
        max_length=100,
        default="Property of ...",
        blank=True,
        help_text=_("Text printed at the top of the label.")
    )
    qr_label_version = models.CharField(
        _("Label Version"),
        max_length=2,
        choices=LabelVersion.choices,
        default=LabelVersion.V1,
        help_text=_("Select the visual template for the labels.")
    )
    qr_label_orientation = models.CharField(
        _("Label Orientation"),
        max_length=15,
        choices=LabelOrientation.choices,
        default=LabelOrientation.HORIZONTAL,
        help_text=_("Only applies to Version 2.")
    )
    qr_label_columns = models.PositiveIntegerField(
        _("Labels per row"),
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(10)],
        help_text=_("Set to 0 for adaptive.")
    )
    qr_width_mm = models.PositiveIntegerField(
        _("Label Width (mm)"),
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(200)],
        help_text=_("Set to 0 for adaptive.")
    )
    qr_height_mm = models.PositiveIntegerField(
        _("Label Height (mm)"),
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(200)],
        help_text=_("Set to 0 for adaptive.")
    )
    qr_font_size = models.PositiveIntegerField(
        _("Font Size (pt)"),
        default=4,
        validators=[MinValueValidator(4), MaxValueValidator(24)],
        help_text=_("Base text size for properties. Header is scaled slightly larger.")
    )

    # --- IDHub  Settings ---
    api_base_url = models.URLField(
        _("Signing Service Base URL"),
        max_length=1024,
        blank=True,
        null=True,
        help_text=_("The root URL of the IdHub instance (e.g., https://idhub.example.com/api/v1/)")
    )

    signing_auth_token = models.CharField(
        _("Signing API Token"),
        max_length=1024,
        blank=True,
        null=True,
        help_text=_("Bearer token for the signing service.")
    )

    issuer_did = models.CharField(
        _("Issuer DID"),
        max_length=255,
        blank=True, null=True,
        validators=[RegexValidator(r'^did:[a-z0-9]+:.+', _("Invalid DID format"))],
        help_text=_("The DID used by this client on the signing service.")
    )

    # {
    #    "dpp": "product_passport_v1.json",
    #    "traceability": "traceability_event_v0.6.json",
    #    "facility": "facility_record_v2.json"
    # }
    schema_config = models.JSONField(
        _("Schema Mapping"),
        default=dict,
        blank=True,
        help_text=_("Map 'credential_type' (keys) to 'schema_filename' (values).")
    )

    def get_service_url(self, endpoint: str) -> str:
        base = self.api_base_url.rstrip('/')
        path = endpoint.lstrip('/')
        return f"{base}/{path}/"

    def get_schema_for_type(self, type_key: str) -> str:
        return self.schema_config.get(type_key, 'default_schema.json')

    def __str__(self):
        return f"Config: {self.institution.name} ({self.api_base_url})"


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


    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

    @property
    def username(self):
        "Is the email of the user"
        return self.email
