from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.forms import formset_factory
from django import forms
from user.models import User
from device.models import Device
from lot.models import (
    Lot,
    LotSubscription,
    DeviceBeneficiary,
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

        self.remove_donor()
        return

    def remove(self):
        for dev in self.devices:
            for lot in self._lots:
                lot.remove(dev.id)

        self.remove_donor()
        return

    def remove_donor(self):
        Donor.objects.filter(lot__in=self._lots).delete()


class BeneficiaryForm(forms.Form):
    beneficiary = forms.CharField()

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
    user = forms.CharField()
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


class SelectDeviceForm(forms.Form):
    checked = forms.BooleanField(label="", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))
    device_id = forms.CharField(widget=forms.HiddenInput())
    id = forms.IntegerField(widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        self.devicebeneficiary = kwargs.pop('device', None)
        lot = kwargs.pop('lot', None)
        self.device = Device(id=self.devicebeneficiary.device_id, lot=lot)
        super().__init__(*args, **kwargs)


class BaseSelectDeviceFormSet(forms.BaseFormSet):
    def __init__(self, *args, **kwargs):
        self.devices = kwargs.pop('devices', [])
        self.lot = kwargs.pop('lot', None)
        super().__init__(*args, **kwargs)

    def _construct_form(self, i, **kwargs):
        kwargs['device'] = self.devices[i]
        kwargs['lot'] = self.lot
        return super()._construct_form(i, **kwargs)

    def get_selected_devices_pks(self):
        selected_pks = []
        if self.is_valid():
            for form in self.forms:
                if form.cleaned_data.get('checked'):
                    selected_pks.append(form.device.pk)
        return selected_pks


class BulkUpdateStatusForm(forms.Form):
    status = forms.ChoiceField(
        choices=DeviceBeneficiary.Status,
        required=True,
        label="Seleccionar nuevo estado para los equipos marcados",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    email = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = self.fields['status'].choices
        self.fields['status'].choices = choices[1:]


SelectFormSet = formset_factory(SelectReturnDeviceForm, extra=0)
SelectDeviceFormSet = forms.formset_factory(
    SelectDeviceForm,
    formset=BaseSelectDeviceFormSet,
    extra=0
)
