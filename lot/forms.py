from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django import forms
from user.models import User
from lot.models import (
    Lot,
    LotSubscription,
    Beneficiary,
    Donor,
)


class LotsForm(forms.Form):
    lots = forms.ModelMultipleChoiceField(
        queryset=Lot.objects.filter(archived=False),
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #grouping lots by their lot group for more readability
        self.grouped_lots = {}
        for lot in self.fields['lots'].queryset:
            group_name = lot.type.name if lot.type else "No group"
            if group_name not in self.grouped_lots:
                self.grouped_lots[group_name] = []
            self.grouped_lots[group_name].append(lot)

    def clean(self):
        self._lots = self.cleaned_data.get("lots")
        return self._lots

    def save(self, commit=True):
        if not commit:
            return

        for dev in self.devices:
            for lot in self._lots:
                lot.add(dev.id)
        return

    def remove(self):
        for dev in self.devices:
            for lot in self._lots:
                lot.remove(dev.id)
        return


class BeneficiaryForm(forms.Form):
    email = forms.EmailField(label=_("Email"))
    name = forms.CharField(label=_("Name"))

    def __init__(self, *args, **kwargs):
        self.shop = kwargs.pop("shop")
        self.lot_pk = kwargs.pop("lot_pk")
        self.devices = kwargs.pop("devices", [])
        super().__init__(*args, **kwargs)

    def clean(self):
        self._beneficiary = self.cleaned_data.get("email")
        self._name = self.cleaned_data.get("name")
        self.ben = Beneficiary.objects.filter(
            lot_id=self.lot_pk,
            email=self._beneficiary
        ).first()
        return self._beneficiary

    def save(self, commit=True):
        if not commit:
            return

        if self.ben:
            self.ben.email = self._beneficiary
            self.ben.save()
        else:
            self.ben = Beneficiary.objects.create(
                email=self._beneficiary,
                name=self._name,
                lot_id=self.lot_pk,
                shop=self.shop
            )

            for dev in self.devices:
                self.ben.add(dev.id)
        return

    def remove(self):
        for dev in self.devices:
            self.ben.remove(dev.id)
        return


class LotSubscriptionForm(forms.Form):
    name = forms.CharField(label=_("Name"))
    email = forms.EmailField(label=_("Email"))
    type = forms.ChoiceField(
        choices=[
            ("circuit_manager", _("Circuit Manager")),
            ("shop", _("Shop")),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        self.institution = kwargs.pop("institution")
        self.lot_pk = kwargs.pop("lot_pk")
        super().__init__(*args, **kwargs)

    def clean(self):
        self.form_email = self.cleaned_data.get("email")
        self.form_name = self.cleaned_data.get("name")
        self._type = self.cleaned_data.get("type")

        self._user = User.objects.filter(email=self.form_email).first()
        if self._user and self._user.institution != self.institution:
            txt = _("This user is from another institution")
            raise ValidationError(txt)

        slot = LotSubscription.objects.filter(
                user=self._user,
                lot_id=self.lot_pk,
        )

        if slot:
            txt = _("This user is already subscripted")
            raise ValidationError(txt)

        return

    def save(self, commit=True):
        if not commit:
            return

        if not self._user:
            self._user = User.objects.create_user(
                self.form_email,
                self.institution,
            )
            if self.form_name:
                self._user.first_name = self.form_name
                self._user.save()
            # TODO
            # self.send_email()

        if self._type == "circuit_manager":
            slot = LotSubscription.objects.filter(
                    user=self._user,
                    lot_id=self.lot_pk,
                    type=LotSubscription.Type.CIRCUIT_MANAGER

            )
            if slot:
                return

            LotSubscription.objects.create(
                user=self._user,
                lot_id=self.lot_pk,
                type=LotSubscription.Type.CIRCUIT_MANAGER
            )

        if self._type == "shop":
            slot = LotSubscription.objects.filter(
                    user=self._user,
                    lot_id=self.lot_pk,
                    type=LotSubscription.Type.SHOP
            )
            if slot:
                return

            LotSubscription.objects.create(
                user=self._user,
                lot_id=self.lot_pk,
                type=LotSubscription.Type.SHOP
            )

    def remove(self):
        if not self._user:
            return

        if self._type == "circuit_manager":
            lot_subscription = LotSubscription.objects.filter(
                user=self._user,
                lot_id=self.lot_pk,
                type=LotSubscription.Type.CIRCUIT_MANAGER
            )

        elif self._type == "shop":
            lot_subscription = LotSubscription.objects.filter(
                user=self._user,
                lot_id=self.lot_pk,
                type=LotSubscription.Type.SHOP
            )

        else:
            lot_subscription = None

        if lot_subscription:
            for l in lot_subscription:
                l.delete()

        return


class AddDonorForm(forms.Form):
    name = forms.CharField(label=_("Name"), required=False)
    email = forms.EmailField(label=_("Email"), required=True)
    address = forms.CharField(label=_("Address"), required=False)
    representative = forms.CharField(label=_("Representative"), required=False)
    cm_representative = forms.CharField(label=_("Representative"), required=False)
    cm_established_in = forms.CharField(label=_("Established In"), required=False)
    cm_location = forms.CharField(label=_("Location"), required=False)
    committee = forms.CharField(label=_("Committee"), required=False)
    recipient_entity_name = forms.CharField(label=_("Recipient Entity Name"), required=False)
    collaborated_entity = forms.CharField(label=_("Collaborated Entity"), required=False)
    jurisdiction_city = forms.CharField(label=_("Jurisdiction City"), required=False)
    agreement_place = forms.CharField(label=_("Agreement Place"), required=False)

    def __init__(self, *args, **kwargs):
        self.institution = kwargs.pop("institution")
        self.lot = kwargs.pop("lot")
        self.donor = kwargs.pop("donor", None)
        super().__init__(*args, **kwargs)
        if self.donor:
            self.fields['name'].widget.attrs['readonly'] = True
            self.fields['email'].widget.attrs['readonly'] = True
            self.fields['address'].widget.attrs['readonly'] = True
            self.fields['representative'].widget.attrs['readonly'] = True
            self.fields['cm_representative'].widget.attrs['readonly'] = True
            self.fields['cm_established_in'].widget.attrs['readonly'] = True
            self.fields['cm_location'].widget.attrs['readonly'] = True
            self.fields['committee'].widget.attrs['readonly'] = True
            self.fields['recipient_entity_name'].widget.attrs['readonly'] = True
            self.fields['collaborated_entity'].widget.attrs['readonly'] = True
            self.fields['jurisdiction_city'].widget.attrs['readonly'] = True
            self.fields['agreement_place'].widget.attrs['readonly'] = True

    def clean(self):
        self.form_name = self.cleaned_data.get("name")
        self.form_email = self.cleaned_data.get("email")
        self.form_address = self.cleaned_data.get("address")
        self.form_representative = self.cleaned_data.get("representative")
        self.form_cm_representative = self.cleaned_data.get("cm_representative")
        self.form_cm_established_in = self.cleaned_data.get("cm_established_in")
        self.form_cm_location = self.cleaned_data.get("cm_location")
        self.form_committee = self.cleaned_data.get("committee")
        self.form_recipient_entity_name = self.cleaned_data.get("recipient_entity_name")
        self.form_collaborated_entity = self.cleaned_data.get("collaborated_entity")
        self.form_jurisdiction_city = self.cleaned_data.get("jurisdiction_city")
        self.form_agreement_place = self.cleaned_data.get("agreement_place")
        return

    def save(self, commit=True):
        if not commit:
            return

        if self.donor:
            self.donor.email = self.form_email
            self.donor.save()
        else:
            self.donor = Donor.objects.create(
                lot=self.lot,
                email=self.form_email,
                name=self.form_name,
                address=self.form_address,
                representative=self.form_representative,
                cm_representative=self.form_cm_representative,
                cm_established_in=self.form_cm_established_in,
                cm_location=self.form_cm_location,
                committee=self.form_committee,
                recipient_entity_name=self.form_recipient_entity_name,
                collaborated_entity=self.form_collaborated_entity,
                jurisdiction_city=self.form_jurisdiction_city,
                agreement_place=self.form_agreement_place,
            )

    def remove(self):
        if self.donor:
            self.donor.delete()

        return


class PlaceReturnDeviceForm(forms.Form):
    place = forms.CharField(
        label=_("Place to returned"),
        max_length=500,
        widget=forms.Textarea(attrs={"rows": 3, "cols": 40})
    )


class SelectReturnDeviceForm(forms.Form):
    returned = forms.BooleanField(label="", required=False)
    device_id = forms.CharField(widget=forms.HiddenInput())
    id = forms.IntegerField(widget=forms.HiddenInput())


SelectFormSet = formset_factory(SelectReturnDeviceForm, extra=0)
