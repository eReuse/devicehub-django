#!/usr/bin/env python3
import logging
from django.core.management.base import BaseCommand
from device.models import DeviceType
from user.models import Institution

logger = logging.getLogger('django')


class Command(BaseCommand):
    help = 'Create default ProductTypes for a given institution.'

    def add_arguments(self, parser):
        parser.add_argument('institution_name', type=str, help='The name of the institution')

    def handle(self, *args, **kwargs):
        default_types = [
            "Desktop",
            "Laptop",
            "Server",
            "GraphicCard",
            "HardDrive",
            "SolidStateDrive",
            "Motherboard",
            "NetworkAdapter",
            "Processor",
            "RamModule",
            "SoundCard",
            "Display",
            "Battery",
            "Camera",
        ]

        institution_name = kwargs['institution_name']
        institution = Institution.objects.filter(name=institution_name).first()

        if not institution:
            logger.error("No institution found for: %s. Please create an institution first", institution_name)
            self.stdout.write(self.style.ERROR(f'No institution found: {institution_name}'))
            return

        for type_name in default_types:
            device_type, created = DeviceType.objects.get_or_create(
                institution=institution,
                name=type_name
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Successfully created device type: {type_name}'))
            else:
                self.stdout.write(self.style.WARNING(f'Product type already exists: {type_name}'))
