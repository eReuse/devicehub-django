from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django import forms
from user.models import User
from lot.models import Lot


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
        super().__init__(*args, **kwargs)

    def clean(self):
        self._user = self.cleaned_data.get("user")
        self._type = self.cleaned_data.get("type")

        self.user = User.objects.filter(email=self._user).first()
        if self.user and self.user.institution != self.institution:
            txt = _("This user is from another institution")
            raise ValidationError(txt)
        return

    def save(self, commit=True):
        if not commit:
            return

        if not self.user:
            self.user = User.objects.create_user(
                self._user,
                self.institution,
                commit=False
            )
            # TODO
            # self.send_email()

        if self._type == "circuit_manager":
            self.user.is_circuit_manager = True

        if self._type == "shop":
            self.user.is_shop = True

        self.user.save()

    def remove(self):
        if not self.user:
            return

        if self._type == "circuit_manager":
            self.user.is_circuit_manager = False

        if self._type == "shop":
            self.user.is_shop = False

        self.user.save()

        return
