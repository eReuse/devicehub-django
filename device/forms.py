import re
from django import forms
from django.db.models import Q
from evidence.image_processing import process_photo_upload
from evidence.models import SystemProperty, RootAlias
from utils.device import create_property, create_doc, create_index
from utils.save_snapshots import move_json, save_in_disk
from evidence.forms import BasePhotoMixin, UserAliasForm
from django.utils.translation import gettext_lazy as _


DEVICE_TYPES = [
    ("", _("Select One")),
    ("Desktop", _("Desktop")),
    ("Laptop", _("Laptop")),
    ("Server", _("Server")),
    ("GraphicCard", _("Graphic Card")),
    ("HardDrive", _("Hard Drive")),
    ("SolidStateDrive", _("Solid State Drive")),
    ("Motherboard", _("Motherboard")),
    ("NetworkAdapter", _("Network Adapter")),
    ("Processor", _("Processor")),
    ("RamModule", _("RAM Module")),
    ("SoundCard", _("Sound Card")),
    ("Display", _("Display")),
    ("Battery", _("Battery")),
    ("Camera", _("Camera")),
    ("Switch", _("Switch")),
    ("Router", _("Router")),
    ("RouterWifi", _("Router Wi-Fi")),
]

DEVICE_ATTRIBUTE_SUGGESTIONS = {
    "Desktop": [
        {"name": "model", "label": _("Device Model (e.g. ThinkStation)")},
        {"name": "manufacturer", "label": _("Device Manufacturer (e.g. Lenovo)")},
        {"name": "cpu_model", "label": _("CPU Model (e.g. i5-10400)")},
        {"name": "ram_total", "label": _("Total RAM (e.g. 16GB)")},
        {"name": "storage", "label": _("Storage Drive (e.g. 512GB SSD)")},
        {"name": "gpu_model", "label": _("GPU Model (e.g. RTX 3060)")},
    ],
    "Laptop": [
        {"name": "model", "label": _("Device Model (e.g. ThinkPad)")},
        {"name": "manufacturer", "label": _("Device Manufacturer (e.g. Lenovo)")},
        {"name": "cpu_model", "label": _("CPU Model (e.g. i7-12700H)")},
        {"name": "ram_total", "label": _("Total RAM (e.g. 16GB)")},
        {"name": "storage", "label": _("Storage Drive (e.g. 1TB NVMe)")},
        {"name": "screen_size", "label": _("Screen Size (e.g. 15.6\")")},
        {"name": "battery_health", "label": _("Battery Health (e.g. 85%)")},
    ],
    "Server": [
        {"name": "model", "label": _("Device Model (e.g. PowerEdge R740)")},
        {"name": "manufacturer", "label": _("Device Manufacturer (e.g. Dell)")},
        {"name": "cpu_model", "label": _("CPU Model (e.g. Xeon Silver 4214)")},
        {"name": "ram_total", "label": _("Total RAM (e.g. 128GB ECC)")},
        {"name": "storage", "label": _("Storage Arrays (e.g. 4x 4TB SAS)")},
        {"name": "raid_controller", "label": _("RAID Controller (e.g. PERC H740P)")},
        {"name": "power_supply", "label": _("Power Supply (e.g. Dual 750W)")},
    ],
    "GraphicCard": [
        {"name": "model", "label": _("Card Model (e.g. RTX 3060)")},
        {"name": "manufacturer", "label": _("Card Manufacturer (e.g. Asus)")},
        {"name": "vram_capacity", "label": _("VRAM Capacity (e.g. 8GB)")},
        {"name": "vram_type", "label": _("VRAM Type (e.g. GDDR6)")},
        {"name": "core_clock", "label": _("Core Clock (e.g. 1837 MHz)")},
    ],
    "HardDrive": [
        {"name": "model", "label": _("Model (e.g. WD Blue)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Western Digital)")},
        {"name": "capacity", "label": _("Capacity (e.g. 4TB)")},
        {"name": "interface", "label": _("Interface (e.g. SATA III / SAS)")},
        {"name": "rpm", "label": _("RPM (e.g. 7200 RPM)")},
    ],
    "SolidStateDrive": [
        {"name": "model", "label": _("Model (e.g. 980 PRO)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Samsung)")},
        {"name": "capacity", "label": _("Capacity (e.g. 1TB)")},
        {"name": "interface", "label": _("Interface (e.g. NVMe PCIe 4.0)")},
        {"name": "health_tbw", "label": _("Health / TBW (e.g. 98% / 300TBW)")},
    ],
    "Motherboard": [
        {"name": "model", "label": _("Model (e.g. ROG Strix B550-F)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. ASUS)")},
        {"name": "socket_type", "label": _("Socket Type (e.g. AM4 / LGA1700)")},
        {"name": "chipset", "label": _("Chipset (e.g. B550 / Z690)")},
        {"name": "ram_slots", "label": _("RAM Slots (e.g. 4)")},
    ],
    "NetworkAdapter": [
        {"name": "model", "label": _("Model (e.g. I225-V)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Intel)")},
        {"name": "speed", "label": _("Speed (e.g. 10 Gbps)")},
        {"name": "port_type", "label": _("Port Type (e.g. RJ45 / SFP+)")},
    ],
    "Processor": [
        {"name": "model", "label": _("Model (e.g. Ryzen 5 5600X)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. AMD)")},
        {"name": "cpu_cores", "label": _("Core Count (e.g. 8 Cores / 16 Threads)")},
        {"name": "base_clock", "label": _("Base Clock (e.g. 3.2 GHz)")},
        {"name": "socket_type", "label": _("Socket Type (e.g. AM5)")},
    ],
    "RamModule": [
        {"name": "model", "label": _("Model (e.g. Vengeance LPX)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Corsair)")},
        {"name": "ram_type", "label": _("RAM Type (e.g. DDR4)")},
        {"name": "capacity", "label": _("Capacity (e.g. 16GB)")},
        {"name": "speed_mhz", "label": _("Speed (e.g. 3200 MHz)")},
    ],
    "SoundCard": [
        {"name": "model", "label": _("Model (e.g. Sound Blaster AE-5)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Creative)")},
        {"name": "channels", "label": _("Channels (e.g. 5.1 / 7.1)")},
        {"name": "interface", "label": _("Interface (e.g. PCIe x1)")},
    ],
    "Display": [
        {"name": "model", "label": _("Model (e.g. UltraSharp U2720Q)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Dell)")},
        {"name": "resolution", "label": _("Resolution (e.g. 1920x1080)")},
        {"name": "refresh_rate", "label": _("Refresh Rate (e.g. 144Hz)")},
        {"name": "panel_type", "label": _("Panel Type (e.g. IPS)")},
    ],
    "Battery": [
        {"name": "model", "label": _("Model (e.g. 45N1126)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Sanyo)")},
        {"name": "capacity_wh", "label": _("Capacity in Wh (e.g. 56Wh)")},
        {"name": "cycle_count", "label": _("Cycle Count (e.g. 120)")},
    ],
    "Camera": [
        {"name": "model", "label": _("Model (e.g. C920)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Logitech)")},
        {"name": "megapixels", "label": _("Megapixels (e.g. 12MP)")},
        {"name": "max_resolution", "label": _("Max Resolution (e.g. 4K@60fps)")},
    ],
    "Switch": [
        {"name": "model", "label": _("Model (e.g. Catalyst 2960)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Cisco)")},
        {"name": "ports", "label": _("Port Count (e.g. 24 / 48)")},
        {"name": "link_speed", "label": _("Link Speed (e.g. 10/100/1000)")},
        {"name": "poe_budget", "label": _("PoE Budget (e.g. 370W)")},
        {"name": "management_type", "label": _("Management Type (e.g. Managed / Unmanaged)")},
    ],
    "Router": [
        {"name": "model", "label": _("Model (e.g. EdgeRouter X)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. Ubiquiti)")},
        {"name": "ports", "label": _("Port Count (e.g. 4x LAN, 1x WAN)")},
        {"name": "throughput", "label": _("Throughput (e.g. 1 Gbps)")},
        {"name": "routing_protocols", "label": _("Protocols (e.g. OSPF, BGP)")},
    ],
    "RouterWifi": [
        {"name": "model", "label": _("Model (e.g. Archer AX50)")},
        {"name": "manufacturer", "label": _("Manufacturer (e.g. TP-Link)")},
        {"name": "wifi_standard", "label": _("Wi-Fi Standard (e.g. Wi-Fi 6 / 802.11ax)")},
        {"name": "frequency_bands", "label": _("Bands (e.g. Dual-Band 2.4/5GHz)")},
        {"name": "antennas", "label": _("Antennas (e.g. 4x External)")},
    ],
}

class DeviceMainForm(BasePhotoMixin):
    type = forms.ChoiceField(choices=DEVICE_TYPES)
    amount = forms.IntegerField(initial=1, min_value=1)
    custom_id = forms.CharField(required=False, label=_("Custom ID"))

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_custom_id(self):
        custom_id = self.cleaned_data.get('custom_id')

        if custom_id and self.user:
            _custom_id = f"custom_id:{custom_id}"
            exists = RootAlias.objects.filter(owner=self.user.institution).filter(
                Q(root__iexact=_custom_id) | Q(alias__iexact=_custom_id)
            ).exists()

            if exists:
                raise forms.ValidationError(_("This Custom ID is already in use by another device."))

        return custom_id

    def generate_next_id(self, base_id, offset):
        if offset == 0: return base_id
        match = re.search(r'(\d+)$', base_id)
        if match:
            num_str = match.group(1)
            prefix = base_id[:-len(num_str)]
            new_num = int(num_str) + offset
            return f"{prefix}{str(new_num).zfill(len(num_str))}"
        return f"{base_id}-{offset + 1}"

    def save(self, attribute_formset):
        if not self.user:
            raise ValueError("User is required to save devices.")

        # custom_id is now guaranteed to be safe and duplicate-free
        custom_id = self.cleaned_data.get('custom_id')

        photo_cache = getattr(self, 'photo_data_cache', None)
        photo_doc = process_photo_upload(photo_cache, self.user)

        amount = self.cleaned_data.get('amount') or 1

        # for now, if a photo is uploaded, only create 1 device
        if photo_cache or custom_id:
            amount = 1

        photo_prop = None
        if photo_doc:
            photo_prop = SystemProperty.objects.filter(
                uuid=photo_doc['uuid'], key='photo25'
            ).first()

        created_docs = []
        for i in range(amount):
            device_data = self.cleaned_data.copy()

            device_doc, device_prop = save_device_data(
                main_data=device_data,
                attribute_formset=attribute_formset,
                user=self.user
            )
            created_docs.append(device_doc)

            device_web_id = device_doc.get('WEB_ID', None)

            alias_root_target = None
            if custom_id:
                alias_root_target = custom_id
            elif photo_prop:
                alias_root_target = device_web_id

            if not alias_root_target:
                continue

            if custom_id and device_prop:
                self._create_alias(device_prop, alias_root_target)

            if photo_prop:
                self._create_alias(photo_prop, alias_root_target)

            device_prop = SystemProperty.objects.filter(
                uuid=device_doc['uuid']
            ).first()

        return created_docs

    def _create_alias(self, prop_instance, root_val):
        form = UserAliasForm(
            data={'root': root_val},
            user=self.user,
            uuid=prop_instance.uuid,
            instance=prop_instance
        )
        if form.is_valid():
            form.save()

class DeviceAttributeForm(forms.Form):
    name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Attribute Name', 'class': 'form-control'})
    )
    value = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Value', 'class': 'form-control'})
    )


def save_device_data(main_data, attribute_formset, user, commit=True):
    row = {}
    if main_data.get("type"):
        row["type"] = main_data["type"]
    if main_data.get("name"):
        row["name"] = main_data["name"]

    for form in attribute_formset:
        if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
            name = form.cleaned_data.get("name")
            value = form.cleaned_data.get("value", "")
            if name and value.strip():
                row[name] = value.strip()

    doc = create_doc(row)

    if not commit:
        return doc

    path_name = save_in_disk(doc, user.institution.name, place="placeholder")
    create_index(doc, user)
    prop = create_property(doc, user, commit=commit)
    move_json(path_name, user.institution.name, place="placeholder")

    return doc, prop


DeviceAttributeFormSet = forms.formset_factory(DeviceAttributeForm, extra=1, can_delete=True)
