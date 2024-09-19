from django.db import models
from user.models import User

# Create your models here.


class Token(models.Model):
    token = models.UUIDField()
    owner = models.ForeignKey(User, on_delete=models.CASCADE)
