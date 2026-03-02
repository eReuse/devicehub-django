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

    def ensure_device_did(self, device, service_endpoint=None):
        if not self.settings:
            return "Institution settings are missing."
        target_suffix = getattr(device, 'shortid', str(device.id))

        if not device.did:
            did_str, did_doc, err = self._create_object_did(target_suffix, service_endpoint)
            if err: return err

            CredentialProperty.objects.create(
                uuid=device.last_evidence.uuid,
                key="DID_DOCUMENT",
                owner= self.institution,
                value= did_str,
                credential= did_doc,
                user= self.user,
                description= f"DID Document for {device.id}"
            )
        else:
            if service_endpoint:
                err = self._update_object_did(device.did, service_endpoint)
                if err: return err

        return None

    def _create_object_did(self, suffix, service_endpoint):
        headers = self._get_auth_headers()
        endpoint = self._get_full_url(self.settings.api_base_url, "object-did/create/")
        payload = {"suffix_did_id": str(suffix)}
        if service_endpoint: payload["service_endpoint"] = service_endpoint

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=30, verify=False)
            res.raise_for_status()
            data = res.json()
            return data.get("did"), data.get("did_document"), None
        except requests.exceptions.HTTPError as e:
            return None, None, self._parse_api_error(e.response)
        except Exception as e:
            logger.exception("Unexpected error creating DID")
            return None, None, f"Unexpected error: {str(e)}"

    def _update_object_did(self, did_str, service_endpoint):
        headers = self._get_auth_headers()
        endpoint = self._get_full_url(self.settings.api_base_url, "object-did/update/")
        payload = {"did": did_str, "service_endpoint": service_endpoint}

        try:
            res = requests.post(endpoint, json=payload, headers=headers, timeout=30, verify=False)
            res.raise_for_status()
            return None
        except requests.exceptions.HTTPError as e:
            return self._parse_api_error(e.response)
        except Exception as e:
            logger.exception("Unexpected error updating DID endpoint")
            return f"Unexpected error: {str(e)}"

    # -------------------------------------------------------------------------
    def issue_device_credential(self, credential_type_key, credential_subject,
                                credential_db_key, device, description=None, uuid=None):

        error_msg = self._validate_config(credential_type_key)
        if error_msg: return None, error_msg

        if not device or not device.did:
            return None, "Device DID is missing. Call `ensure_device_did` before issuing credentials."

        if isinstance(credential_subject, dict) and not credential_subject.get('id'):
            credential_subject['id'] = device.did

        path = "issue-traceability/" if credential_type_key == 'traceability' else "issue-dpp/"
        endpoint = self._get_full_url(self.settings.api_base_url, path)

        payload = {
            "schema_name": self.settings.schema_config.get(credential_type_key),
            "issuer_did": self.settings.issuer_did,
            "credentialSubject": credential_subject
        }

        return self._execute_issuance(endpoint, payload, credential_db_key, description, uuid)

    def issue_facility_credential(self, credential_subject, credential_db_key, description=None, uuid=None):
        error_msg = self._validate_config('facility')
        if error_msg: return None, error_msg

        endpoint = self._get_full_url(self.settings.api_base_url, "issue-facility/")
        payload = {
            "schema_name": self.settings.schema_config.get('facility'),
            "issuer_did": self.settings.issuer_did,
            "credentialSubject": credential_subject
        }

        return self._execute_issuance(endpoint, payload, credential_db_key, description, uuid)

    # -------------------------------------------------------------------------
    def _execute_issuance(self, endpoint, payload, db_key, description, uuid):
        headers = self._get_auth_headers()
        try:
            response = requests.post(endpoint, json=payload, headers=headers, timeout=30, verify=False)
            response.raise_for_status()

            response_data = response.json()
            signed_credential = response_data.get("credential")

            if not signed_credential:
                 if "id" in response_data and "@context" in response_data:
                     signed_credential = response_data
                 else:
                    return None, "API success but response format was invalid."

            cred_prop = CredentialProperty.objects.create(
                uuid=uuid,
                owner=self.institution,
                key=db_key,
                value=signed_credential.get('id'),
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

    def _get_auth_headers(self):
        return {
            'Authorization': f'Bearer {self.settings.signing_auth_token}',
            'Content-Type': 'application/json'
        }

    def _validate_config(self, type_key):
        if not self.settings:
            return "Institution settings are missing."
        if not self.settings.signing_auth_token or not self.settings.api_base_url:
            return "Signing API configuration is incomplete."
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

            msg = f"[{response.status_code}] API Error: {error_msg}" if error_msg else f"[{response.status_code}] API Error"

            if details:
                msg += f" - Validation: {details}" if isinstance(details, list) else f" - {details}"
            return msg
        except:
            return f"[{response.status_code}] API Error"
