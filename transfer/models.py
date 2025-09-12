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
    organization_did = models.CharField(max_length=STR_SIZE)
    organization_name = models.CharField(max_length=STR_SIZE)
    str_credential = models.CharField(max_length=5000)
    reference = models.CharField(max_length=STR_SIZE, null=True)
    api_destination = models.CharField(max_length=5000, null=True)
    token_destination = models.CharField(max_length=5000, null=True)
    type = models.SmallIntegerField(choices=Type.choices, default=Type.SENDED)
    sended = models.BooleanField(default=False)
    credential_id = models.CharField(max_length=STR_SIZE)

    def send_transfer(self):
        if not all([self.credential, self.api_destination, self.token_destination]):
            return ""

        data = self.str_credential
        header = {"Authorization": "Bearer {}".format(self.token_destination)}
        verify = not settings.DEBUG
        res = requests.post(self.api_destination, data=data, headers=header, verify=verify)

        assert 200 <= res.status_code < 300, "Bad connection with {}".format(self.api_destination)
        self.sended = True
        self.save()

    def get_items(self):
        try:
            items = self.credential["credentialSubject"][0]['epcList']
            for i in items:
                i["transfer"] = self.id
            return items
        except Exception:
            return []

    def get_evidences(self):
        try:
            return self.credential["evidences"]
        except Exception:
            return []

    def get_credential_id(self):
        self.credential_id = self.credential["id"]
        return self.credential_id

    @property
    def get_credential_id_last(self):
        return self.credential_id.split("/")[-1]

    @property
    def signed(self):
        return True if self.credential.get("proof") else False

    @property
    def credential(self):
        if not self.str_credential:
            return {}

        if hasattr(self, "_credential"):
            return self._credential

        self._credential = json.loads(self.str_credential)
        return self._credential

    @property
    def number_items(self):
        try:
            return len(self.credential["credentialSubject"][0]['epcList'])
        except Exception:
            return 0

    @property
    def is_transfer(self):
        return True

    @property
    def is_sended(self):
        return self.type == self.Type.SENDED

    @property
    def lot(self):
        return self.lot_set.first().name

    @property
    def get_id_lot(self):
        return self.lot_set.first().id

    @property
    def is_foreing_transfer(self):
        try:
            dtype = self.credential.get("credentialSubject")[0].get("bizTransaction")
            typ_trans = {
                "desadv": self.Type.SENDED,
                "recadv": self.Type.RECEIVED
            }

            return typ_trans.get(dtype) != self.Type(self.type)
        except Exception:
            return False
