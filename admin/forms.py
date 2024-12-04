from django import forms


class OrderingStateForm(forms.Form):
    ordering = forms.CharField()
