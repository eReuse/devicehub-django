import json
import requests

from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.conf import settings
from django.urls import reverse
from django import forms
from evidence.models import SystemProperty
from device.models import Device
from transfer.models import Transfer


class TransferForm(forms.Form):
    issuer_did = forms.CharField()
    did = forms.CharField(label=_("Organization Did"))
    name = forms.CharField(label=_("Organization Name"))
    reference = forms.URLField(label=_("ID of transfer reference"), required=False)
    api_destination = forms.URLField(required=False)
    token_destination = forms.CharField(required=False)
    type_of_transfer = forms.ChoiceField(
        choices=[("desadv", _("Send")), ("recadv", _("Receibe"))]
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', [])
        self.lot = kwargs.pop('lot')
        self.domain = kwargs.pop("domain")
        self.instance = kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
        if self.instance and (self.instance.signed or self.instance.sended):
            self.fields['issuer_did'].widget.attrs['readonly'] = True
            self.fields['did'].widget.attrs['readonly'] = True
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['reference'].widget.attrs['readonly'] = True
            self.fields['type_of_transfer'].widget.attrs['readonly'] = True
        if self.instance and self.instance.sended:
            self.fields['api_destination'].widget.attrs['readonly'] = True
            self.fields['token_destination'].widget.attrs['readonly'] = True


    def save(self, commit=True):

        if not commit:
            return

        if not self.instance and self.lot.transfer:
            self.instance = self.lot.transfer
            return

        typ_trans = {
            "desadv": Transfer.Type.SENDED,
            "recadv": Transfer.Type.RECEIVED
        }

        if not self.instance:
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
            self.instance.credential_id = self.get_url()
            self.send_sign()
        else:
            if self.instance.sended:
                return

            self.instance.api_destination=self.cleaned_data.get("api_destination")
            self.instance.token_destination=self.cleaned_data.get("token_destination")

            if not self.instance.signed:
                self.instance.issuer_did=self.cleaned_data.get("issuer_did")
                self.instance.organization_did=self.cleaned_data.get("did")
                self.instance.organization_name=self.cleaned_data.get("name")
                self.instance.reference=self.cleaned_data.get("reference")
                self.instance.type=typ_trans[self.cleaned_data.get("type_of_transfer")]
                self.send_sign()

        self.instance.save()
        self.lot.transfer = self.instance
        self.lot.save()
        if self.instance.is_sended:
            for d in  self.lot.devices:
                ev = SystemProperty.objects.filter(value=d.device_id).order_by("-created").first()
                ev.transfer = self.instance
                ev.save()

        return

    def get_data(self):
        issuer_did = self.cleaned_data.get("issuer_did")
        did = self.cleaned_data.get("did")
        institution = issuer_did
        other_part = did
        biz_transaction = self.cleaned_data.get("type_of_transfer")
        source_party = ''
        destination_party = ''
        if biz_transaction == "desadv":
            source_party = institution
            destination_party = other_part
        elif biz_transaction == "recadv":
            source_party = other_part
            destination_party = institution

        if not destination_party or not source_party:
            return

        credential_subject = [{
            "id": self.get_url(),
            "type": ['TransactionEvent', 'Event'],
            "sourceParty": source_party,
            "destinationParty": destination_party,
            "bizTransaction": biz_transaction,
            "epcList": self.get_epc_list()
        }]

        if self.instance.reference:
            credential_subject[0]["unc:externalDocument"] = {
                "unc:uriid": self.instance.reference
            }

        evidences = self.get_evidences()

        return {
            "credentialSubject": credential_subject,
            "evidences": evidences,
            "issuer": {"id": institution, "name": self.user.institution.name},

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
            d_path = reverse("device:device_web", args=[dev.shortid])
            devs.append({
                "type": ["Item"],
                "id": "{}{}".format(self.domain, d_path),
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
        self.instance.str_credential = json.dumps(data)
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
