from django import forms
from lot.models import Lot

class LotsForm(forms.Form):
    lots = forms.ModelMultipleChoiceField(
        queryset=Lot.objects.all(),
        widget=forms.CheckboxSelectMultiple,
    )

    def clean(self):
        # import pdb; pdb.set_trace()
        self._lots = self.cleaned_data.get("lots")
        return self._lots
    
    def save(self, commit=True):
        if not commit:
            return
        for dev in self.devices:
            for lot in self._lots:
                lot.devices.add(dev.id)
        return

    def remove(self):
        for dev in self.devices:
            for lot in self._lots:
                lot.devices.remove(dev.id)
        return
