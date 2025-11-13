from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from utils.constants import ALGOS
from django.conf import settings


ALGORITHMS = [(x, x) for x in ALGOS.keys()]


class Institution(models.Model):
    name = models.CharField(
        _("Name"),
        max_length=255,
        blank=False,
        null=False,
        unique=True
    )
    logo = models.CharField(_("Logo"), max_length=255, blank=True, null=True)
    location = models.CharField(_("Location"), max_length=255, blank=True, null=True)
    responsable_person = models.CharField(
        _("Responsable"),
        max_length=255,
        blank=True,
        null=True
    )
    supervisor_person = models.CharField(
        _("Supervisor"),
        max_length=255,
        blank=True,
        null=True
    )
    algorithm = models.CharField(max_length=30, choices=ALGORITHMS, default='ereuse24')


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


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    language = models.CharField(
        _("Language"),
        max_length=10,
        choices=settings.LANGUAGES,
        default=settings.LANGUAGE_CODE,
        help_text=_("The user's preferred language for the interface.")
    )

    pinned_lots = models.ManyToManyField(
        "lot.Lot",
        blank=True,
        help_text=_("Lots the user wants to see on their dashboard.")
    )

    pinned_states = models.ManyToManyField(
        "action.StateDefinition",
        blank=True,
        help_text=_("States the user wants to see on their dashboard.")
    )

    def __str__(self):
        return f"Profile for {self.user.email}"
