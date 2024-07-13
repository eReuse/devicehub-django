


class UploadForm(forms.Form):
    snapshot_file = forms.FileField(label=_("File"))

    def clean(self):
        data = self.cleaned_data
