import json
import requests

from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse
from django import forms
from device.models import Device
from transfer.models import Transfer


class TransferForm(forms.Form):
    issuer_did = forms.CharField()
    did = forms.CharField(label=_("Organization Did"))
    name = forms.CharField(label=_("Organization Name"))
    website = forms.URLField(label=_("Organization WebSite"))
    reference = forms.URLField(label=_("ID of transfer reference"), required=False)
    api_destination = forms.URLField(required=False)
    token_destination = forms.CharField(required=False)
    type_of_transfer = forms.ChoiceField(
        choices=[("cbv:BTT-desad", _("Send")), ("cbv:BTT-recadv", _("Receibe"))]
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', [])
        self.lot = kwargs.pop('lot')
        self.domain = kwargs.pop("domain")

        super().__init__(*args, **kwargs)

    def save(self, commit=True):

        if commit:
            if self.lot.transfer:
                return

            typ_trans = {
                "cbv:BTT-desad": Transfer.Type.SENDED,
                "cbv:BTT-recadv": Transfer.Type.RECEIVED
            }
            self.instance = Transfer.objects.create(
                issuer_did=self.cleaned_data.get("issuer_did"),
                organization_did=self.cleaned_data.get("did"),
                organization_name=self.cleaned_data.get("name"),
                reference=self.cleaned_data.get("reference"),
                api_destination=self.cleaned_data.get("api_destination"),
                token_destination=self.cleaned_data.get("token_destination"),
                owner=self.user.institution,
                type=typ_trans[self.cleaned_data.get("type_of_transfer")]
            )
            self.send_sign()
            if not self.instance.credential:
                self.instance.delete()
                self.instance = None
                return

            self.instance.save()
            self.lot.transfer = self.instance
            self.lot.save()

        return

    def get_data(self):
        issuer_did = self.cleaned_data.get("issuer_did")
        did = self.cleaned_data.get("did")
        name = self.cleaned_data.get("name")
        website = self.cleaned_data.get("website")
        institution = {
            "id": issuer_did,
            "name": self.user.institution.name,
            "organisationWebsite": self.domain
        }
        other_part = {
            "id": did,
            "name": name,
            "organisationWebsite": website
        }
        biz_transaction = self.cleaned_data.get("type_of_transfer")
        source_party = {}
        destination_party = {}
        if biz_transaction == "cbv:BTT-desad":
            source_party = institution
            destination_party = other_part
        elif biz_transaction == "cbv:BTT-recadv":
            source_party = other_part
            destination_party = institution

        if not destination_party or not source_party:
            return

        credential_subject = {
            "sourceParty": source_party,
            "destinationParty": destination_party,
            "bizTransaction": biz_transaction,
            "epcList": self.get_epc_list()
        }

        evidences = self.get_evidences()

        return {
            "credentialSubject": credential_subject,
            "evidences": evidences,
            "issuer": institution,
            "id": self.get_url()
        }

    def get_url(self):
        path = reverse("transfer:id", args=[self.instance.id])
        return "{}{}".format(self.domain, path)

    def get_epc_list(self):
        devs = []
        for d in self.lot.devices:
            dev = Device(id=d.device_id)
            name = "{} {} {}".format(dev.type, dev.manufacturer, dev.model)
            devs.append({
                "type": ["Item"],
                "id": dev.shortid,
                "name": name
            })
        return devs

    def get_evidences(self):
        evs = {}
        for d in self.lot.devices:
            dev = Device(id=d.device_id)
            dev.get_last_evidence()
            evs[dev.shortid] = dev.last_evidence.doc
        return evs

    def send_sign(self):
        data = self.get_data()
        self.instance.str_credential = data
        url = settings.IDHUB_API_SIGN
        token = settings.IDHUB_TOKEN
        header = {"Authorization": f"Bearer {token}"}
        verify = not settings.DEBUG
        try:
            res = requests.post(url, json=data, headers=header, verify=verify)

            if 199 < res.status_code < 300:
                cred = json.loads(res.text)
                if cred.get("data"):
                    self.instance.str_credential = cred["data"]
        except Exception:
            pass

        return
