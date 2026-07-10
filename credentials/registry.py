#!/usr/bin/env python3

class PayloadBuilderRegistry:
    _builders = {}

    @classmethod
    def register(cls, workflow_key: str, version: str):
        def wrapper(builder_class):
            if version not in cls._builders:
                cls._builders[version] = {}
            cls._builders[version][workflow_key] = builder_class
            return builder_class
        return wrapper

    @classmethod
    def get_builder(cls, workflow_key: str, version: str):
        version_builders = cls._builders.get(version, {})
        builder_class = version_builders.get(workflow_key)
        if not builder_class:
            raise ValueError(f"No payload builder registered for workflow '{workflow_key}' on DPP version '{version}'.")
        return builder_class()
