from django.db import models, connection
from user.models import User, Institution
from django.core.exceptions import ValidationError

class State(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    state = models.CharField(max_length=50)
    snapshot_uuid = models.UUIDField()

    def clean(self):
        if not StateDefinition.objects.filter(institution=self.institution, state=self.state).exists():
            raise ValidationError(f"The state '{self.state}' is not valid for the institution '{self.institution.name}'.")
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.institution.name} - {self.state} - {self.snapshot_uuid}"

class StateDefinition(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    order = models.AutoField(primary_key=True)
    state = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['institution', 'state'], name='unique_institution_state')
        ]

    def __str__(self):
        return f"{self.institution.name} - {self.state}"
