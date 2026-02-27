#!/usr/bin/env python3

import requests
import logging
from django.db import IntegrityError
from user.models import InstitutionSettings
from evidence.models import CredentialProperty

logger = logging.getLogger(__name__)

class CredentialService:
    def __init__(self, user):
        self.user = user
        self.institution = user.institution
        try:
            self.settings = InstitutionSettings.objects.get(institution=self.institution)
        except InstitutionSettings.DoesNotExist:
            self.settings = None

    def issue_credential(self, credential_type_key, credential_subject,
                         credential_db_key, service_endpoint=None, uuid=None,
                         description=None, did_suffix=None):
        if not self.settings:
            return None, "Institution settings are missing."

        api_token = self.settings.signing_auth_token
        api_base = self.settings.api_base_url
        issuer_did = self.settings.issuer_did

        if not api_token or not api_base:
            return None, "Signing API configuration (Token or URL) is incomplete."

        schema_name = self.settings.schema_config.get(credential_type_key)
        if not schema_name:
            return None, f"No schema configured for type '{credential_type_key}'. Check Institution Settings."

        headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }

        base_payload = {
            "schema_name": schema_name,
        }
        base_payload["issuer_did"] = issuer_did

        try:
            if credential_type_key == 'traceability':
                endpoint = self._get_full_url(api_base, "issue-traceability/")
                payload = {
                    **base_payload,
                    "credentialSubject": credential_subject
                }

            elif credential_type_key == 'facility':
                if not service_endpoint:
                    return None, "Service Endpoint is required for Facility issuance."

                endpoint = self._get_full_url(api_base, "issue-facility/")
                payload = {
                    **base_payload,
                    "create_did": True,
                    "subject_did_suffix": did_suffix,
                    "credentialSubject": credential_subject,
                    "service_endpoint": service_endpoint
                }

            else:
                if not service_endpoint:
                    return None, "Service Endpoint is required for DPP issuance."

                endpoint = self._get_full_url(api_base, "issue-dpp/")
                payload = {
                    **base_payload,
                    "create_did": True,
                    "subject_did_suffix": did_suffix,
                    "credentialSubject": credential_subject,
                    "service_endpoint": service_endpoint
                }

            response = requests.post(
                endpoint, json=payload, headers=headers,
                timeout=30, verify=False
            )
            response.raise_for_status()

            response_data = response.json()
            signed_credential = response_data.get("credential")

            if not signed_credential:
                 if "id" in response_data and "@context" in response_data:
                     signed_credential = response_data
                 else:
                    return None, "API success but response format was invalid (missing 'credential' key)."

            credential_id = signed_credential.get('id')

            cred_prop = CredentialProperty.objects.create(
                uuid=uuid,
                owner=self.institution,
                key=credential_db_key,
                value=credential_id,
                credential=signed_credential,
                user=self.user,
                description=description
            )
            return cred_prop, None

        except requests.exceptions.HTTPError as e:
            return None, self._parse_api_error(e.response)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.error(f"Connection error to {endpoint}")
            return None, "Network error: Could not reach signing service."
        except IntegrityError:
            return None, f"A credential of type '{db_key}' already exists for this item."
        except Exception as e:
            logger.exception("Unexpected error issuing credential")
            return None, f"Unexpected error: {str(e)}"

    def _validate_config(self, type_key):
        """Helper to ensure API configuration is valid before proceeding."""
        if not self.settings:
            return "Institution settings are missing."
        if not self.settings.signing_auth_token or not self.settings.api_base_url:
            return "Signing API configuration (Token or URL) is incomplete."
        if not self.settings.schema_config.get(type_key):
            return f"No schema configured for type '{type_key}'."
        return None

    def _get_full_url(self, base, path):
        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    def _parse_api_error(self, response):
        try:
            data = response.json()
            error_msg = data.get('error')
            details = data.get('details')

            msg = f"API Error: {error_msg}" if error_msg else f"API Error ({response.status_code})"
            if details:
                msg += f" - Validation: {details}" if isinstance(details, list) else f" - {details}"
            return msg
        except:
            return f"API Error ({response.status_code})"
