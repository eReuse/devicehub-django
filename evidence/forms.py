


class UploadForm(forms.Form):
    evidence_file = forms.FileField(label=_("File"))

    def clean(self):
        data = self.cleaned_data
