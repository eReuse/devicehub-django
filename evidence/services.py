#!/usr/bin/env python3

import requests
import logging
from django.db import IntegrityError
from evidence.models import CredentialProperty
from user.models import InstitutionSettings

logger = logging.getLogger(__name__)

class CredentialService:
    def __init__(self, user):
        self.user = user
        self.institution = user.institution
        try:
            self.settings = InstitutionSettings.objects.get(institution=self.institution)
        except InstitutionSettings.DoesNotExist:
            self.settings = None

    def issue_credential(self, schema_name, credential_subject, service_endpoint,
                         credential_key, uuid=None, description=None):
        """
        Args:
            schema_name (str): Filename of the schema (e.g. 'passport.json')
            credential_subject (dict): The actual data content.
            service_endpoint (str): Where the credential points to (e.g. evidence URL).
            credential_key (str): The DB key (e.g. 'DigitalProductPassport').
            uuid (UUID, optional): Link to a device. None if linking to Institution.
            description (str, optional): Human readable description.

        Returns:
            tuple: (credential_object, error_message)
            - If success: (CredentialProperty instance, None)
            - If fail: (None, "Error string for the user")
        """
        if not self.settings:
            return None, "Institution settings are missing."

        api_endpoint = getattr(self.settings, "signing_service_domain", "")
        api_key = getattr(self.settings, "signing_auth_token", "")

        if not api_key or not api_endpoint:
            return None, "Signing API configuration is incomplete."

        payload = {
            "schema_name": schema_name,
            "create_did": True,
            "credentialSubject": credential_subject,
            "service_endpoint": service_endpoint
        }

        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(
                api_endpoint, json=payload, headers=headers,
                timeout=15, verify=False, allow_redirects=False
            )
            response.raise_for_status()

            signed_credential = response.json()
            credential_id = signed_credential.get('id')

            if not credential_id:
                return None, "API success but no ID returned."

            # Save to DB
            cred_prop = CredentialProperty.objects.create(
                uuid=uuid,
                owner=self.institution,
                key=credential_key,
                value=credential_id,
                credential=signed_credential,
                user=self.user,
                description=description
            )
            return cred_prop, None

        except requests.exceptions.HTTPError as e:
            return None, self._parse_api_error(e.response)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.error(f"Connection error to {api_endpoint}")
            return None, "Network error: Could not reach signing service."
        except IntegrityError:
            return None, f"A credential of type '{credential_key}' already exists for this item."
        except Exception as e:
            logger.exception("Unexpected error issuing credential")
            return None, f"Unexpected error: {str(e)}"

    def _parse_api_error(self, response):
        """Helper to format API error messages cleanly."""
        try:
            data = response.json()
            msg = f"API Error: {data.get('error', 'Unknown')}"
            if data.get('details'):
                msg += f" - {data.get('details')}"
            return msg
        except:
            return f"API Error ({response.status_code})"
