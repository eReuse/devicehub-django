import json
import requests
import logging

from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from utils.constants import STR_SIZE


from user.models import Institution


logger = logging.getLogger(__name__)


class Transfer(models.Model):
    class Type(models.IntegerChoices):
        SENDED = 0, _("Sended")
        RECEIVED = 1, _("Received")

    created = models.DateTimeField(default=timezone.now)
    issuer_did = models.CharField(max_length=STR_SIZE)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    destination_did = models.CharField(max_length=STR_SIZE)
    destination_name = models.CharField(max_length=STR_SIZE)
    credential = models.CharField(max_length=5000)
    api_destination = models.CharField(max_length=5000)
    token_destination = models.CharField(max_length=5000)
    type = models.SmallIntegerField(choices=Type.choices, default=Type.SENDED)

    def send_transfer(self):
        if not all([self.credential, self.api_destination, self.token_destination]):
            return ""

        data = {"data": self.credential}
        header = {"Authorization": "Bearer {}".format(self.token_destination)}
        verify = not settings.DEBUG
        res = requests.post(self.api_destination, json=data, headers=header, verify=verify)

        if 200 < res.status < 300:
            self.credential = res.text

    def get_items(self):
        try:
            cred = json.loads(self.credential)
            items = json.loads(cred['data'])["credentialSubject"]['epcList']
            for i in items:
                i["transfer"] = self.id
            return items
        except Exception:
            return []

    def get_evidences(self):
        try:
            cred = json.loads(self.credential)
            return json.loads(cred['data'])["evidences"]
        except Exception:
            return []

    @property
    def number_items(self):
        try:
            cred = json.loads(self.credential)
            return len(json.loads(cred['data'])["credentialSubject"]['epcList'])
        except Exception:
            return 0

    @property
    def is_transfer(self):
        return True

    @property
    def lot(self):
        return self.lot_set.first().name

    @property
    def get_id_lot(self):
        return self.lot_set.first().id
