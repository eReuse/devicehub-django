from django.db import models
from django.db.models import Max
from django.core.exceptions import ValidationError
from user.models import User, Institution
from evidence.models import SystemProperty


class State(models.Model):
    date = models.DateTimeField(auto_now_add=True)
    institution = models.ForeignKey(Institution, on_delete=models.SET_NULL, null=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    state = models.CharField(max_length=50)
    snapshot_uuid = models.UUIDField()
    system_property = models.ForeignKey(SystemProperty, on_delete=models.SET_NULL, null=True)

    def clean(self):
        if not StateDefinition.objects.filter(institution=self.institution, state=self.state).exists():
            raise ValidationError(f"The state '{self.state}' is not valid for the institution '{self.institution.name}'.")

    def set_system_property(self):
        if not self.system_property:
            self.system_property = SystemProperty.objects.filter(
                uuid=self.snapshot_uuid,
                owner=self.institution
            ).first()

    def save(self, *args, **kwargs):
        self.clean()
        self.set_system_property()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.institution.name} - {self.state} - {self.snapshot_uuid}"


class StateDefinition(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)

    order = models.PositiveIntegerField(default=0)
    state = models.CharField(max_length=50)

    class Meta:
        ordering = ['order']
        constraints = [
            models.UniqueConstraint(fields=['institution', 'state'], name='unique_institution_state')
        ]

    def save(self, *args, **kwargs):
        if not self.pk:
            # set the order to be last
            max_order = StateDefinition.objects.filter(institution=self.institution).aggregate(Max('order'))['order__max']
            self.order = (max_order or 0) + 1
        super().save(*args, **kwargs)


    def delete(self, *args, **kwargs):
        institution = self.institution
        order = self.order
        super().delete(*args, **kwargs)
        # Adjust the order of other instances
        StateDefinition.objects.filter(institution=institution, order__gt=order).update(order=models.F('order') - 1)


    def __str__(self):
        return f"{self.institution.name} - {self.state}"


class Note(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    description = models.TextField()
    snapshot_uuid = models.UUIDField()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f" Note: {self.description}, by {self.user.username} @ {self.user.institution} - {self.date}, for {self.snapshot_uuid}"


class DeviceLog(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    event = models.CharField(max_length=255)
    snapshot_uuid = models.UUIDField()

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f"{self.event} by {self.user.username} @ {self.institution.name} - {self.date}, for {self.snapshot_uuid}"
