from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django import forms
from user.models import User
from lot.models import Lot, LotSubscription, Donor


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
                    is_circuit_manager=True
            )
            if slot:
                return

            LotSubscription.objects.create(
                user=self._user,
                lot_id=self.lot_pk,
                is_circuit_manager=True
            )

        if self._type == "shop":
            slot = LotSubscription.objects.filter(
                    user=self._user,
                    lot_id=self.lot_pk,
                    is_shop=True
            )
            if slot:
                return

            LotSubscription.objects.create(
                user=self._user,
                lot_id=self.lot_pk,
                is_shop=True
            )

    def remove(self):
        if not self._user:
            return

        if self._type == "circuit_manager":
            lot_subscription = LotSubscription.objects.filter(
                user=self._user,
                lot_id=self.lot_pk,
                is_circuit_manager=True
            )

        elif self._type == "shop":
            lot_subscription = LotSubscription.objects.filter(
                user=self._user,
                lot_id=self.lot_pk,
                is_circuit_manager=True
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

    def clean(self):
        self._user = self.cleaned_data.get("user")
        return

    def save(self, commit=True):
        if not commit:
            return

        if self.donor:
            self.donor.email = self._user
            self.donor.save()
        else:
            self.donor = Donor.objects.create(
                lot=self.lot,
                email=self._user
            )
        # TODO
        # if self._user:
        #     self.send_email()

    def remove(self):
        if self.donor:
            self.donor.delete()

        return
