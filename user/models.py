from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from utils.constants import ALGOS


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
    def create_user(self, email, password=None):
        """
        Creates and saves a User with the given email, date of
        birth and password.
        """
        if not email:
            raise ValueError("Users must have an email address")

        user = self.model(
            email=self.normalize_email(email)
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, institution, password=None):
        """
        Creates and saves a superuser with the given email and password.
        """
        user = self.create_user(
            email,
            password=password,
        )

        user.institutions.create(
            institution=institution,
            is_active=True,
            is_admin=True
        )


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

        user.institutions.create(
            institution=institution,
            is_active=True,
            is_circuit_manager=True
        )


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
        user.institutions.create(
            institution=institution,
            is_active=True,
            is_shop=True
        )

        return user


class User(AbstractBaseUser):
    email = models.EmailField(
        _('Email address'),
        max_length=255,
        unique=True,
    )

    first_name = models.CharField(_("First name"), max_length=255, blank=True, null=True)
    last_name = models.CharField(_("Last name"), max_length=255, blank=True, null=True)
    accept_gdpr = models.BooleanField(default=False)

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

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin

    @property
    def username(self):
        "Is the email of the user"
        return self.email


class UserInstitution(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="institutions")
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="users")
    is_active = models.BooleanField(_("is active"), default=True)
    is_admin = models.BooleanField(_("is admin"), default=False)
    is_circuit_manager = models.BooleanField(_("is circuit manager"), default=False)
    is_shop = models.BooleanField(_("is shop"), default=False)

    class Meta:
        unique_together = ('user', 'institution')
