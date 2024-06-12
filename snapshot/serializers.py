from rest_framework import serializers
from snapshot.models import Snapshot

class SnapshotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Snapshot
        fields = ['id', 'title', 'content']

