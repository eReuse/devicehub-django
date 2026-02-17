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
    beneficiary = forms.CharField(label=_("Email"))

    def __init__(self, *args, **kwargs):
        self.shop = kwargs.pop("shop")
        self.lot_pk = kwargs.pop("lot_pk")
        self.devices = kwargs.pop("devices", [])
        super().__init__(*args, **kwargs)

    def clean(self):
        self._beneficiary = self.cleaned_data.get("beneficiary")
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
    user = forms.CharField(label=_("Email"))
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
        self.form_user = self.cleaned_data.get("user")
        self._type = self.cleaned_data.get("type")

        self._user = User.objects.filter(email=self.form_user).first()
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
                self.form_user,
                self.institution,
            )
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
    user = forms.CharField()

    def __init__(self, *args, **kwargs):
        self.institution = kwargs.pop("institution")
        self.lot = kwargs.pop("lot")
        self.donor = kwargs.pop("donor", None)
        super().__init__(*args, **kwargs)
        if self.donor:
            self.fields['user'].widget.attrs['readonly'] = True

    def clean(self):
        self.form_user = self.cleaned_data.get("user")
        return

    def save(self, commit=True):
        if not commit:
            return

        if self.donor:
            self.donor.email = self.form_user
            self.donor.save()
        else:
            self.donor = Donor.objects.create(
                lot=self.lot,
                email=self.form_user
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
