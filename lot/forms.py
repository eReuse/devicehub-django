from django import forms
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
