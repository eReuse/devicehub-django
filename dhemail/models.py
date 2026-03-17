from django.db import models


class InstitutionTemplate(models.Model):
    institution = models.ForeignKey(
        'user.Institution',
        on_delete=models.CASCADE,
        related_name='custom_templates',
    )
    template_name = models.CharField(max_length=255)
    content = models.TextField()

    class Meta:
        unique_together = ('institution', 'template_name')


class LotTemplate(models.Model):
    lot = models.ForeignKey(
        'lot.Lot',
        on_delete=models.CASCADE,
        related_name='custom_templates',
    )
    template_name = models.CharField(max_length=255)
    content = models.TextField()

    class Meta:
        unique_together = ('lot', 'template_name')
