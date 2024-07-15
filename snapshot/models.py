from django.db import models
from utils.constants import STR_SM_SIZE, STR_EXTEND_SIZE
from user.models import User
from device.models import Computer, Component

# Create your models here.


class Snapshot(models.Model):
    class SoftWare(models.TextChoices):
        WORKBENCH= "Workbench"

    class Severity(models.IntegerChoices):
        Info = 0, "Info"
        Notice = 1, "Notice"
        Warning = 2, "Warning"
        Error = 3, "Error"

    created = models.DateTimeField(auto_now_add=True)
    software = models.CharField(max_length=STR_SM_SIZE, choices=SoftWare, default=SoftWare.WORKBENCH)
    uuid = models.UUIDField(unique=True)
    version = models.CharField(max_length=STR_SM_SIZE)
    sid = models.CharField(max_length=STR_SM_SIZE)
    settings_version = models.CharField(max_length=STR_SM_SIZE)
    is_server_erase = models.BooleanField(default=False)
    severity =  models.SmallIntegerField(choices=Severity, default=Severity.Info)
    end_time = models.DateTimeField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    computer = models.ForeignKey(Computer, on_delete=models.CASCADE)
    components = models.ManyToManyField(Component)


class Annotation(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(unique=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    value = models.CharField(max_length=STR_EXTEND_SIZE)
    
