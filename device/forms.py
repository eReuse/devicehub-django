from django import forms
# from django.utils.translation import gettext_lazy as _
# from django.core.exceptions import ValidationError
# from user.models import User
from device.models import (
    Device,
    PhysicalProperties
)


class DeviceForm(forms.ModelForm):

    class Meta:
        model = Device
        fields = [
            'type',
            "model",
            "manufacturer",
            "serial_number",
            "part_number",
            "brand",
            "generation",
            "version",
            "production_date",
            "variant",
            "family",
        ]


class PhysicalPropsForm(forms.Form):

    class Meta:
        model = PhysicalProperties
        fields = [
            "device",
            "weight",
            "width",
            "height",
            "depth",
            "color",
            "image",
        ]
