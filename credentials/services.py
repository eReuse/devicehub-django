import requests
import logging
from django.db import IntegrityError
from django.core.cache import cache

from user.models import InstitutionDPPSettings
from evidence.models import CredentialProperty, SystemProperty

from .registry import PayloadBuilderRegistry

#imported so the builders register onto the register class
from . import untp_0_7_0

logger = logging.getLogger(__name__)

class CredentialService:
    def __init__(self, user):
        self.user = user
        self.institution = user.institution
        try:
            self.settings = InstitutionDPPSettings.objects.get(institution=self.institution)
        except InstitutionDPPSettings.DoesNotExist:
            self.settings = None

    def fetch_schemas(self) -> dict:
        """Fetches active UNTP schemas from idhub and caches them for 10 minutes."""
        if not self.settings or not self.settings.api_base_url or not self.settings.signing_auth_token:
            logger.warning("Cannot fetch schemas: API base URL or auth token is missing.")
            return {}

        cached_schemas = cache.get('idhub_schemas')
        if cached_schemas:
            return cached_schemas

        endpoint = self._get_full_url(self.settings.api_base_url, "schemas/untp/active/")

        try:
            res = requests.get(endpoint, headers=self._get_auth_headers(), timeout=10, verify=False)
            res.raise_for_status()

            schemas = res.json()

            cache.set('idhub_schemas', schemas, timeout=600)
            return schemas

        except requests.exceptions.HTTPError as e:
            logger.error(f"Failed to fetch schemas. API Error: {e.response.text}")
            return {}
        except Exception as e:
            logger.exception("Unexpected error fetching schemas from IdHub")
            return {}

    def ensure_device_did(self, device, service_endpoint: str = None) -> str | None:
        """Ensures a device has a DID. Creates one if missing, updates endpoint if provided."""
        if not self.settings:
            return "Institution settings are missing."

        target_suffix = getattr(device, 'shortid', str(device.id))

        if not device.did:
            did_str, did_doc, err = self._create_object_did(target_suffix, service_endpoint)
            if err:
                return err

            sysprop_instance = SystemProperty.objects.filter(uuid=device.last_evidence.uuid).first()
            CredentialProperty.objects.create(
                sysprop=sysprop_instance,
                key=CredentialProperty.CredentialType.DIDDOC,
                owner=self.institution,
                value=did_str,
                credential=did_doc,
                user=self.user,
                description=f"DID Document for {device.id}"
            )
            return None

        if service_endpoint:
            return self._update_object_did(device.did, service_endpoint)

        return None

    def _create_object_did(self, suffix: str, service_endpoint: str):
        endpoint = self._get_full_url(self.settings.api_base_url, "object-did/create/")
        payload = {"suffix_did_id": str(suffix)}
        if service_endpoint:
            payload["service_endpoint"] = service_endpoint

        try:
            res = requests.post(endpoint, json=payload, headers=self._get_auth_headers(), timeout=30, verify=False)
            res.raise_for_status()
            data = res.json()
            return data.get("did"), data.get("did_document"), None
        except requests.exceptions.HTTPError as e:
            return None, None, self._parse_api_error(e.response)
        except Exception as e:
            logger.exception("Unexpected error creating DID")
            return None, None, f"Unexpected error: {str(e)}"

    def _update_object_did(self, did_str: str, service_endpoint: str) -> str | None:
        endpoint = self._get_full_url(self.settings.api_base_url, "object-did/update/")
        payload = {"did": did_str, "service_endpoint": service_endpoint}

        try:
            res = requests.post(endpoint, json=payload, headers=self._get_auth_headers(), timeout=30, verify=False)
            res.raise_for_status()
            return None
        except requests.exceptions.HTTPError as e:
            return self._parse_api_error(e.response)
        except Exception as e:
            logger.exception("Unexpected error updating DID endpoint")
            return f"Unexpected error: {str(e)}"

    def issue_credential(self, workflow_type: str, build_kwargs: dict, description: str = None):
        """
        Dynamically builds and issues a credential based on the active schema configuration.
        workflow_type: 'dpp', 'traceability', or 'facility'
        build_kwargs: The data injected into the PayloadBuilder
        """
        error_msg = self._validate_config(workflow_type)
        if error_msg:
            return None, error_msg

        # 1. Map the workflow string to the direct model attribute
        target_version = self.settings.active_dpp_standard

        try:
            builder = PayloadBuilderRegistry.get_builder(workflow_key=workflow_type, version=target_version)


        except ValueError as e:
            return None, str(e)

        schema_field_map = {
            'dpp': 'dpp_schema',
            'traceability': 'dte_schema',
            'facility': 'dfr_schema'
        }
        target_schema_filename = getattr(self.settings, schema_field_map[workflow_type], None)

        if not target_schema_filename:
            return None, f"No schema mapped for workflow: {workflow_type}"

        try:
            credential_subject = builder.build(**build_kwargs)
        except Exception as e:
            logger.exception(f"Failed to build payload for {workflow_type}")
            return None, f"Payload builder failed: {str(e)}"

        sysprop_instance = None

        if workflow_type == 'traceability':
            path = "issue-traceability/"
            db_key = CredentialProperty.CredentialType.DTE
            device = build_kwargs.get('device')
            if device and getattr(device, 'last_evidence', None):
                sysprop_instance = SystemProperty.objects.filter(uuid=device.last_evidence.uuid).first()

        elif workflow_type == 'dpp':
            path = "issue-dpp/"
            db_key = CredentialProperty.CredentialType.DPP
            device = build_kwargs.get('device')
            if device and getattr(device, 'last_evidence', None):
                sysprop_instance = SystemProperty.objects.filter(uuid=device.last_evidence.uuid).first()

        elif workflow_type == 'facility':
            path = "issue-facility/"
            db_key = CredentialProperty.CredentialType.DFR

        # 6. Construct the final API payload wrapper
        endpoint = self._get_full_url(self.settings.api_base_url, path)
        payload = {
            "schema_name": target_schema_filename,
            "issuer_did": self.settings.issuer_did,
            "credentialSubject": credential_subject
        }

        # 7. Execute network request & save to database
        return self._execute_issuance(endpoint, payload, db_key, description, sysprop_instance)


    def _validate_config(self, type_key: str) -> str | None:
        if not self.settings:
            return "Institution settings are missing."
        if not self.settings.signing_auth_token or not self.settings.api_base_url:
            return "Signing API configuration is incomplete."

        # Map to the new direct model fields for validation
        schema_field_map = {
            'dpp': 'dpp_schema',
            'traceability': 'dte_schema',
            'facility': 'dfr_schema'
        }

        attr_name = schema_field_map.get(type_key)
        if not attr_name or not getattr(self.settings, attr_name, None):
            return f"No schema configured for type '{type_key}'."

        return None


    def _execute_issuance(self, endpoint: str, payload: dict, db_key: str, description: str, sysprop_instance):
        try:
            res = requests.post(endpoint, json=payload, headers=self._get_auth_headers(), timeout=30, verify=False)
            res.raise_for_status()
            response_data = res.json()

            signed_credential = response_data.get("credential")
            if not signed_credential:
                 if "id" in response_data and "@context" in response_data:
                     signed_credential = response_data
                 else:
                    return None, "API success but response format was invalid."

            cred_prop = CredentialProperty.objects.create(
                sysprop=sysprop_instance,
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

    def _get_full_url(self, base: str, path: str) -> str:
        return f"{base.rstrip('/')}/{path.lstrip('/')}"

    def _parse_api_error(self, response) -> str:
        try:
            data = response.json()
            error_msg = data.get('error', '')
            details = data.get('details', '')

            msg = f"[{response.status_code}] API Error"
            if error_msg:
                msg += f": {error_msg}"
            if details:
                msg += f" - Validation: {details}" if isinstance(details, list) else f" - {details}"
            return msg
        except Exception:
            return f"[{response.status_code}] API Error"
