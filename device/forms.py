from django import forms
from snapshot.models import Annotation


class DeviceForm2(forms.ModelForm):
    class Meta:
        model = Annotation
        fields = ['key', 'value']


class DeviceForm(forms.Form):
    name = forms.CharField()
    value = forms.CharField()


DeviceFormSet = forms.formset_factory(form=DeviceForm, extra=1)

