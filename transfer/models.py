import requests
import logging

from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from utils.constants import STR_SIZE

from user.models import Institution


logger = logging.getLogger(__name__)


class Transfer(models.Model):
    issuer_did = models.CharField(max_length=STR_SIZE)
    owner = models.ForeignKey(Institution, on_delete=models.CASCADE)
    destination_did = models.CharField(max_length=STR_SIZE)
    destination_name = models.CharField(max_length=STR_SIZE)
    credential = models.CharField(max_length=5000)
    api_destination = models.CharField(max_length=5000)
    token_destination = models.CharField(max_length=5000)

    def send_transfer(self):
        if not all([self.credential, self.api_destination, self.token_destination]):
            return ""

        data = {"data": self.credential}
        header = {"Authorization": "Bearer {}".format(self.token_destination)}
        verify = not settings.DEBUG
        res = requests.post(self.api_destination, json=data, headers=header, verify=verify)

        if 200 < res.status < 300:
            self.credential = res.text
