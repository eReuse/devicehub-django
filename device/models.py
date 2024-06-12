from django.db import models
from user.models import User
from utils.constants import STR_SM_SIZE, STR_SIZE


# Create your models here.


class Device(models.Model):
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    type = models.CharField(max_length=STR_SM_SIZE)
    model = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    manufacturer = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    serial_number = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    part_number = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    brand = models.TextField(blank=True, null=True)
    generation = models.SmallIntegerField(blank=True, null=True)
    version = models.TextField(blank=True, null=True)
    production_date = models.DateTimeField(blank=True, null=True)
    variant = models.TextField(blank=True, null=True)
    devicehub_id = models.TextField(unique=True, blank=True, null=True)
    dhid_bk = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    phid_bk = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    family = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    hid = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    chid = models.CharField(max_length=STR_SIZE, blank=True, null=True)
    active = models.BooleanField(default=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE)


class PhysicalProperties(models.Model):
    device = models.OneToOneField(Device, models.CASCADE, primary_key=True)
    weight = models.FloatField(blank=True, null=True)
    width = models.FloatField(blank=True, null=True)
    height = models.FloatField(blank=True, null=True)
    depth = models.FloatField(blank=True, null=True)
    color = models.CharField(max_length=20, blank=True, null=True)
    image = models.CharField(max_length=STR_SIZE, blank=True, null=True)


class Computer(models.Model):
    class Types(models.TextChoices):
        DESKTOP = "Desktop"
        LAPTOP = "Laptop"
        SERVER = "Server"

    device = models.OneToOneField(Device, models.CASCADE, primary_key=True)
    chassis = models.TextField(blank=True, null=True)
    system_uuid = models.UUIDField()
    sku = models.TextField(blank=True, null=True)
    type = models.CharField(max_length=STR_SM_SIZE, choices=Types, default=Types.LAPTOP)


class Component(models.Model):
    class Types(models.TextChoices):
        GRAPHICCARD = "GraphicCard"
        DATASTORAGE = "DataStorage"
        MOTHERBOARD = "Motherboard"
        NETWORKADAPTER = "NetworkAdapter"
        PROCESSOR = "Processor"
        RAMMODULE = "RamModule"
        SOUNDCARD = "SoundCard"
        DISPLAY = "Display"
        BATTERY = "Battery"
        CAMERA = "Camera"

    device = models.OneToOneField(Device, models.CASCADE, primary_key=True)
    type = models.CharField(max_length=STR_SM_SIZE, choices=Types)
    computer = models.OneToOneField(Computer, models.CASCADE, null=True)


class GraphicCard(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    memory = models.IntegerField(blank=True, null=True)


class DataStorage(models.Model):
    class Interface(models.TextChoices):
        ATA = 'ATA'
        USB = 'USB'
        PCI = 'PCI'
        NVME = 'NVME'

    class Type(models.TextChoices):
        HARDDRIVE = "HardDrive"
        SOLIDSTATEDRIVE = "SolidStateDrive"

    component = models.OneToOneField(Component, models.CASCADE)
    size = models.IntegerField(blank=True, null=True)
    interface = models.CharField(max_length=STR_SM_SIZE, choices=Interface)
    type = models.CharField(max_length=STR_SM_SIZE, choices=Type)


class Motherboard(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    slots = models.SmallIntegerField(blank=True, null=True)
    usb = models.SmallIntegerField(blank=True, null=True)
    firewire = models.SmallIntegerField(blank=True, null=True)
    serial = models.SmallIntegerField(blank=True, null=True)
    pcmcia = models.SmallIntegerField(blank=True, null=True)
    bios_date = models.DateTimeField()
    ram_slots = models.SmallIntegerField(blank=True, null=True)
    ram_max_size = models.IntegerField(blank=True, null=True)


class NetworkAdapter(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    speed = models.IntegerField(blank=True, null=True)
    wireless = models.BooleanField(default=False)

    def __format__(self, format_spec):
        v = super().__format__(format_spec)
        if 's' in format_spec:
            v += ' – {} Mbps'.format(self.speed)
        return v

    
class Processor(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    speed = models.FloatField(blank=True, null=True)
    cores = models.SmallIntegerField(blank=True, null=True)
    threads = models.SmallIntegerField(blank=True, null=True)
    address = models.SmallIntegerField(blank=True, null=True)


class RamModule(models.Model):
    class Interface(models.TextChoices):
        SDRAM = 'SDRAM'
        DDR = 'DDR SDRAM'
        DDR2 = 'DDR2 SDRAM'
        DDR3 = 'DDR3 SDRAM'
        DDR4 = 'DDR4 SDRAM'
        DDR5 = 'DDR5 SDRAM'
        DDR6 = 'DDR6 SDRAM'
        LPDDR3 = 'LPDDR3'

    class Format(models.TextChoices):
        DIMM = 'DIMM'
        SODIMM = 'SODIMM'

    component = models.OneToOneField(Component, models.CASCADE)
    size = models.IntegerField(blank=True, null=True)
    interface = models.CharField(max_length=STR_SM_SIZE, choices=Interface)
    speed = models.SmallIntegerField(blank=True, null=True)
    interface = models.CharField(max_length=STR_SM_SIZE, choices=Interface)
    format = models.CharField(max_length=STR_SM_SIZE, choices=Format)


class SoundCard(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    

class Display(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    

class Battery(models.Model):
    component = models.OneToOneField(Component, models.CASCADE)
    
