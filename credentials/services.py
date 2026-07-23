import logging
import requests
from django.urls import reverse
from django.conf import settings
from collections import defaultdict
from django.core.cache import cache
from django.db import IntegrityError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

from user.models import InstitutionDPPSettings
from evidence.models import CredentialProperty, SystemProperty
from .registry import PayloadBuilderRegistry

from . import untp_0_7_0
# imported so the builders register onto the register class

logger = logging.getLogger(__name__)

class CredentialService:
    def __init__(self, user=None, institution=None):
        self.user = user

        if user and getattr(user, 'institution', None):
            self.institution = user.institution
        elif institution:
            self.institution = institution
            logger.warning("CredentialService has been created with only the institution (no user provided).")
        else:
            raise ValueError("CredentialService requires either a user with an institution or an explicit institution parameter.")

    @cached_property
    def settings(self):
        """Lazy-loads settings."""
        try:
            return InstitutionDPPSettings.objects.get(institution=self.institution)
        except InstitutionDPPSettings.DoesNotExist:
            logger.warning(f"InstitutionDPPSettings not found for institution {self.institution.id}.")
            return None

    @property
    def _verify_ssl(self):
        return not settings.DEBUG

    def fetch_schemas(self) -> dict:
        """Fetches active UNTP schemas from idhub and caches them for 10 minutes."""
        if not self.settings or not self.settings.api_base_url or not self.settings.signing_auth_token:
            logger.warning(f"Cannot fetch schemas for institution {self.institution.id}: API config is missing.")
            return {}

        cache_key = f"idhub_schemas_inst_{self.institution.id}"
        cached_schemas = cache.get(cache_key)
        if cached_schemas:
            logger.debug(f"Returning cached schemas for institution {self.institution.id}.")
            return cached_schemas

        endpoint = self.get_full_url("schemas/untp/active/")
        logger.info(f"Fetching fresh schemas from IDHub for institution {self.institution.id} at {endpoint}")

        try:
            res = requests.get(
                endpoint,
                headers=self._get_auth_headers(),
                timeout=10,
                verify=self._verify_ssl
            )
            res.raise_for_status()

            schemas = res.json()
            cache.set(cache_key, schemas, timeout=600)
            logger.info(f"Successfully fetched and cached {len(schemas)} schemas for institution {self.institution.id}.")
            return schemas

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTPError fetching schemas for institution {self.institution.id}. API Error: {e.response.text}")
            return {}
        except Exception as e:
            logger.exception(f"Unexpected error fetching schemas for institution {self.institution.id}")
            return {}

    def ensure_device_did(self, device, service_endpoint: str = None) -> str | None:
        """Ensures a device has a DID. Creates one if missing, updates endpoint if provided."""
        if not self.settings:
            logger.warning(f"Cannot ensure DID for device {device.id}: Institution settings missing.")
            return "Institution settings are missing."

        target_suffix = getattr(device, 'shortid', str(device.id))

        if not device.did:
            logger.info(f"Device {device.id} has no DID. Attempting to create one with suffix '{target_suffix}'.")
            did_str, did_doc, err = self._create_object_did(target_suffix, service_endpoint)

            if err:
                logger.error(f"Failed to create DID for device {device.id}: {err}")
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
            logger.info(f"Successfully created and stored DID ({did_str}) for device {device.id}.")
            return None

        if service_endpoint:
            logger.info(f"Updating service endpoint for DID {device.did} (Device {device.id}).")
            err = self._update_object_did(device.did, service_endpoint)
            if err:
                logger.error(f"Failed to update service endpoint for device {device.id}: {err}")
                return err
            logger.info(f"Successfully updated service endpoint for DID {device.did}.")

        return None

    def _create_object_did(self, suffix: str, service_endpoint: str):
        endpoint = self.get_full_url("object-did/create/")
        payload = {"suffix_did_id": str(suffix)}
        if service_endpoint:
            payload["service_endpoint"] = service_endpoint

        try:
            res = requests.post(endpoint, json=payload, headers=self._get_auth_headers(), timeout=30, verify=self._verify_ssl)
            res.raise_for_status()
            data = res.json()
            return data.get("did"), data.get("did_document"), None
        except requests.exceptions.HTTPError as e:
            err_msg = self._parse_api_error(e.response)
            logger.error(f"API Error creating object DID (suffix: {suffix}): {err_msg}")
            return None, None, err_msg
        except Exception as e:
            logger.exception(f"Unexpected error creating object DID (suffix: {suffix})")
            return None, None, f"Unexpected error: {str(e)}"

    def _update_object_did(self, did_str: str, service_endpoint: str) -> str | None:
        endpoint = self.get_full_url("object-did/update/")
        payload = {"did": did_str, "service_endpoint": service_endpoint}

        try:
            res = requests.post(endpoint, json=payload, headers=self._get_auth_headers(), timeout=30, verify=self._verify_ssl)
            res.raise_for_status()
            return None
        except requests.exceptions.HTTPError as e:
            err_msg = self._parse_api_error(e.response)
            logger.error(f"API Error updating object DID ({did_str}): {err_msg}")
            return err_msg
        except Exception as e:
            logger.exception(f"Unexpected error updating object DID ({did_str})")
            return f"Unexpected error: {str(e)}"

    def issue_credential(self, workflow_type: str, build_kwargs: dict, description: str = None):
        """
        Dynamically builds and issues a credential based on the active schema configuration.
        workflow_type: 'dpp', 'traceability', or 'facility'
        """
        logger.info(f"Initiating '{workflow_type}' credential issuance for institution {self.institution.id}.")

        error_msg = self._validate_config(workflow_type)
        if error_msg:
            logger.warning(f"Validation failed for '{workflow_type}' credential issuance: {error_msg}")
            return None, error_msg

        target_version = self.settings.active_dpp_standard

        try:
            builder = PayloadBuilderRegistry.get_builder(workflow_key=workflow_type, version=target_version)
        except ValueError as e:
            logger.error(f"Payload builder error for workflow '{workflow_type}': {str(e)}")
            return None, str(e)

        schema_field_map = {
            'dpp': 'dpp_schema',
            'traceability': 'dte_schema',
            'facility': 'dfr_schema'
        }
        target_schema_filename = getattr(self.settings, schema_field_map[workflow_type], None)

        try:
            credential_subject = builder.build(**build_kwargs)
            logger.debug(f"Successfully built payload for '{workflow_type}' using schema '{target_schema_filename}'.")
        except Exception as e:
            logger.exception(f"Failed to build payload subject for {workflow_type}")
            return None, f"Payload builder failed: {str(e)}"

        sysprop_instance = None
        device = build_kwargs.get('device')
        if device and getattr(device, 'last_evidence', None):
            sysprop_instance = SystemProperty.objects.filter(uuid=device.last_evidence.uuid).first()
            if not sysprop_instance:
                logger.warning(f"Could not find SystemProperty matching device evidence UUID: {device.last_evidence.uuid}")

        workflow_configs = {
            'traceability': ("issue-traceability/", CredentialProperty.CredentialType.DTE),
            'dpp': ("issue-dpp/", CredentialProperty.CredentialType.DPP),
            'facility': ("issue-facility/", CredentialProperty.CredentialType.DFR),
        }

        path, db_key = workflow_configs[workflow_type]

        endpoint = self.get_full_url(path)
        payload = {
            "schema_name": target_schema_filename,
            "issuer_did": self.settings.issuer_did,
            "credentialSubject": credential_subject
        }

        return self._execute_issuance(endpoint, payload, db_key, description, sysprop_instance)

    def _validate_config(self, type_key: str) -> str | None:
        if not self.settings:
            return "Institution settings are missing."
        if not self.settings.signing_auth_token or not self.settings.api_base_url:
            return "Signing API configuration is incomplete."

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
        logger.info(f"Sending issuance request to API endpoint: {endpoint}")

        try:
            res = requests.post(endpoint, json=payload, headers=self._get_auth_headers(), timeout=30, verify=self._verify_ssl)
            res.raise_for_status()
            response_data = res.json()

            signed_credential = response_data.get("credential")
            if not signed_credential:
                 if "id" in response_data and "@context" in response_data:
                     signed_credential = response_data
                 else:
                    logger.error(f"API issued success response but payload format is invalid. Endpoint: {endpoint}")
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

            logger.info(f"Successfully issued '{db_key}' credential. Stored with CredentialProperty ID: {cred_prop.pk}.")
            return cred_prop, None

        except requests.exceptions.HTTPError as e:
            err_msg = self._parse_api_error(e.response)
            logger.error(f"API HTTPError during '{db_key}' issuance: {err_msg}")
            return None, err_msg
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.error(f"Network error (Timeout/Connection) while trying to reach signing service at {endpoint}.")
            return None, "Network error: Could not reach signing service."
        except IntegrityError:
            logger.warning(f"IntegrityError: A credential of type '{db_key}' already exists for this item.")
            return None, f"A credential of type '{db_key}' already exists for this item."
        except Exception as e:
            logger.exception(f"Unexpected error executing issuance for '{db_key}'")
            return None, f"Unexpected error: {str(e)}"

    def _get_auth_headers(self):
        return {
            'Authorization': f'Bearer {self.settings.signing_auth_token}',
            'Content-Type': 'application/json'
        }

    def get_full_url(self, append_path=""):
        if not self.settings or not self.settings.api_base_url:
            logger.error("Attempted to construct URL but api_base_url is missing or not configured in settings.")
            return ""

        base = str(self.settings.api_base_url).strip()
        if not base:
            logger.error("Attempted to construct URL but api_base_url is empty.")
            return ""

        if not append_path:
            return base.rstrip('/')

        append_path = str(append_path).strip()

        if append_path.startswith(('?', '#', '&')):
            return f"{base.rstrip('/')}{append_path}"

        return f"{base.rstrip('/')}/{append_path.lstrip('/')}"

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


    def get_facility_info(self, request):
        """Extracts facility info from the device owner's latest facility credential."""

        institution = self.institution
        if not institution or not getattr(institution, 'latest_facility_credential', None):
            logger.debug(f"No facility credential found for institution ID {institution.id if institution else 'None'}.")
            return None

        facility_cred_prop = institution.latest_facility_credential
        subject = facility_cred_prop.credential.get('credentialSubject', {})
        facility_data = subject.get('facility', subject)
        operated_by = facility_data.get('operatedByParty', {})

        fac_url = request.build_absolute_uri(
            reverse('evidence:credential_detail', kwargs={'uuid': facility_cred_prop.uuid})
        )

        return {
            "type": ["Facility"],
            "id": fac_url,
            "name": facility_data.get("name", str(_("Unknown Facility"))),
            "registeredId": operated_by.get("registeredId", ""),
            "idScheme": {
                "type": ["IdentifierScheme"],
                "id": "https://www.pangea.org/dummy/id-scheme",
                "name": "Dummy Legal Entity Identifier"
            }
        }

    def get_traceability_info(self, device, request):
        """Extracts and formats traceability events (DTE) for a given device into UNTP performance metrics."""

        events = CredentialProperty.objects.filter(
            sysprop__uuid__in=device.uuids, key=CredentialProperty.CredentialType.DTE
        ).order_by('created')

        if not events.exists():
            logger.debug(f"No DTE traceability events found for device {device.id}.")
            return []

        grouped = defaultdict(list)
        for prop in events:
            subject = prop.credential.get('credentialSubject', [])
            if isinstance(subject, dict):
                subject = [subject]

            for event in subject:
                raw_process = event.get('activityType', 'Unknown').get('name','Unknown')

                process_name = raw_process.split(':')[-1].capitalize() if ':' in raw_process else raw_process
                cred_url = request.build_absolute_uri(
                    reverse('evidence:credential_detail', kwargs={'uuid': prop.uuid})
                )

                grouped[process_name].append({
                    "type": ["SecureLink", "Link"],
                    "linkURL": cred_url,
                    "linkName": "Traceability Event - {process_name}".format(process_name=process_name)
                })

        logger.info(f"Extracted {len(events)} traceability events for device {device.id} grouped into {len(grouped)} processes.")

        return [
            {
                "type": ["TraceabilityPerformance"],
                "valueChainProcess": process,
                "verifiedRatio": 1.0,
                "traceabilityEvent": links
            }
            for process, links in grouped.items()
        ]
