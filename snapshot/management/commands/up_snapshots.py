
import os
import json

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from snapshot.parse import Build


User = get_user_model()


class Command(BaseCommand):
    help = "Insert Snapshots"
    snapshots = []
    files = []
    devices = []

    def add_arguments(self, parser):
        parser.add_argument('path', type=str, help='Path to snapshots')
        parser.add_argument('email', type=str, help='Email of user')


    def handle(self, *args, **kwargs):
        path = kwargs['path']
        email = kwargs['email']
        self.user = User.objects.get(email=email)

        if os.path.isfile(path):
            self.open(path)

        elif os.path.isdir(path):
            self.read_directory(path)

        self.parsing()
            
    def read_directory(self, directory):
        for filename in os.listdir(directory):
            filepath = os.path.join(directory, filename)
            if os.path.isfile(filepath):
                self.open(filepath)

    def open(self, filepath):
        with open(filepath, 'r') as file:
            content = json.loads(file.read())        
            self.snapshots.append(content)
        
    def parsing(self):
        for s in self.snapshots:
            self.devices.append(Build(s, self.user))
