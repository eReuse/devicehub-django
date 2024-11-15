from django.db import models
from user.models import User, Institution
from utils.constants import STR_EXTEND_SIZE
# Create your models here.


class Proof(models.Model):
    timestamp = models.IntegerField()
    uuid = models.UUIDField()
    signature = models.CharField(max_length=STR_EXTEND_SIZE)
    normalizeDoc = models.TextField()
    type = models.CharField(max_length=STR_EXTEND_SIZE)
    action = models.CharField(max_length=STR_EXTEND_SIZE)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)


class Dpp(models.Model):
    timestamp = models.IntegerField()
    key = models.CharField(max_length=STR_EXTEND_SIZE)
    uuid = models.UUIDField()
    signature = models.CharField(max_length=STR_EXTEND_SIZE)
    normalizeDoc = models.TextField()
    type = models.CharField(max_length=STR_EXTEND_SIZE)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True)

    
