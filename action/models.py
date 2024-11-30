from django.db import models, connection
from user.models import User, Institution


class StateDefinition(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    state = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.institution.name} - {self.state}"

class State(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    state = models.CharField(max_length=255)
    snapshot_uuid = models.UUIDField()

    def __str__(self):
        return f"{self.institution.name} - {self.state} - {self.snapshot_uuid}"
