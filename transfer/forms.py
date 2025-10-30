import requests

from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse
from django import forms
from device.models import Device
from lot.models import Lot
from transfer.models import Transfer


class TransferForm(forms.Form):
    issuer_did = forms.CharField()
    did = forms.CharField()
    name = forms.CharField()
    website = forms.URLField()
    api_destination = forms.URLField(required=False)
    token_destination = forms.CharField(required=False)
    type_of_transfer = forms.ChoiceField(
        choices=[("cbv:BTT-desad", _("Send")), ("cbv:BTT-recadv", _("Receibe"))]
    )
    selected_ids = forms.MultipleChoiceField(
        choices=[],
        widget=forms.MultipleHiddenInput,
        required=False,
    )

    def __init__(self, *args, **kwargs):
        choices = kwargs.get("initial").get('selected_ids', [])
        if not choices:
            choices = kwargs.get("data", {}).getlist("selected_ids")
        self.user = kwargs.pop('user', [])
        self.website = kwargs.pop('website', "")

        super().__init__(*args, **kwargs)
        self.fields['selected_ids'].choices = [(x, x) for x in choices]


    def clean(self):
        selected_ids = self.cleaned_data.get("selected_ids")
        self.lots = Lot.objects.filter(
            id__in=selected_ids,
            owner=self.user.institution
        )

        return self.cleaned_data

    def save(self, commit=True):

        if commit:
            self.instance = Transfer.objects.create(
                issuer_did=self.cleaned_data.get("issuer_did"),
                destination_did=self.cleaned_data.get("did"),
                destination_name=self.cleaned_data.get("name"),
                api_destination=self.cleaned_data.get("api_destination"),
                token_destination=self.cleaned_data.get("token_destination")
            )
            self.send_sign()
            if not self.instance.credential:
                self.instance.delete()
                self.instance = None
                return

            self.instance.save()

            c = 0
            for lot in self.lots:
                if lot.transfer:
                    continue
                c = 1
                lot.transfer = self.instance
                lot.save()

            if not c:
                self.instance.delete()
        return

    def get_data(self):
        issuer_did = self.cleaned_data.get("issuer_did")
        did = self.cleaned_data.get("did")
        name = self.cleaned_data.get("name")
        website = self.cleaned_data.get("website")
        institution = {
            "id": issuer_did,
            "name": self.user.institution.name,
            "organisationWebsite": self.website
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
        return "https://localhost"
        path = reverse("lot:credential_transfer", args=[self.instance.id])
        domain = self.website
        return f"https://{domain}/{path}"

    def get_epc_list(self):
        devs = []
        for lot in self.lots:
            for d in lot.devices:
                dev = Device(id=d.device_id)
                name = "{} {} {}".format(dev.type, dev.manufacturer, dev.model)
                devs.append({
                    "type": ["Item"],
                    "id": dev.shortid,
                    "name": name
                })
        return devs

    def get_evidences(self):
        evs = []
        for lot in self.lots:
            for d in lot.devices:
                dev = Device(id=d.device_id)
                dev.get_last_evidence()
                evs.append(dev.last_evidence.doc)
        return evs

    def send_sign(self):
        data = self.get_data()
        url = settings.IDHUB_API_SIGN
        token = settings.IDHUB_TOKEN
        header = {"Authorization": f"Bearer {token}"}
        verify = not settings.DEBUG
        res = requests.post(url, json=data, headers=header, verify=verify)

        if 199 < res.status_code < 300:
            self.instance.credential = res.text

        return
