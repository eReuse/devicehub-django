#!/usr/bin/env python3
import uuid
import datetime
import re
from datetime import date
from openlocationcode import openlocationcode as olc
from .registry import PayloadBuilderRegistry

class BaseUNTPBuilder:
    def get_context(self):
        return [
            "https://www.w3.org/2018/credentials/v1",
            "https://vocabulary.uncefact.org/untp/0.7.0/context/"
        ]

@PayloadBuilderRegistry.register(workflow_key="facility", version="untp-0.7.0")
class UNTP070DFRBuilder(BaseUNTPBuilder):
    def build(self, institution, request_data=None, **kwargs):
        request_data = request_data or {}

        # location (should we keep this geolocalization here=)
        location_info = {}
        try:
            raw_lat = request_data.get('latitude')
            raw_lon = request_data.get('longitude')

            if raw_lat and raw_lon:
                lat = float(raw_lat)
                lon = float(raw_lon)

                plus_code = olc.encode(lat, lon, 11)
                plus_code_url = f"https://plus.codes/{plus_code}"

                location_info = {
                    "plusCode": plus_code_url,
                    "geoLocation": {
                        "latitude": lat,
                        "longitude": lon
                    }
                }
        except (ValueError, TypeError):
            pass

        address_data = {
            "streetAddress": getattr(institution, 'street_address', None),
            "postalCode": getattr(institution, 'postal_code', None),
            "addressLocality": getattr(institution, 'location', None),
            "addressRegion": getattr(institution, 'region', None),
            "addressCountry": {
                "countryCode": getattr(institution, 'country', "XX") or "XX"
            }
        }
        # clean empty strings
        address_data = {k: v for k, v in address_data.items() if v}

        # process category dict
        isic_names = {
            '9511': "Repair of computers and peripheral equipment",
            '3830': "Materials recovery and recycling",
            '3313': "Repair of electronic and optical equipment",
            '4649': "Wholesale of other household goods",
            '0000': "General Operations"
        }
        process_code = getattr(institution, 'process_category_code', '0000')
        process_name = isic_names.get(str(process_code), "General Operations")

        process_category = [{
            "code": str(process_code),
            "name": process_name,
            "schemeId": "https://unstats.un.org/unsd/classifications/Econ/ISIC/",
            "schemeName": "UN ISIC Rev.4"
        }]

        facility_uri = getattr(institution, 'facility_id_uri', None) or f"urn:uuid:{uuid.uuid4()}"
        related_party = [{
            "role": "operator",
            "party": {
                "type": ["Party"],
                "id": facility_uri,
                "name": institution.name,
                "registeredId": getattr(institution, 'registered_id', None) or str(institution.id)
            }
        }]

        credential_subject = {
            "type": ["Facility"],
            "id": facility_uri,
            "name": institution.name,
            "countryOfOperation": {
                "countryCode": getattr(institution, 'country', "XX") or "XX"
            },
            "address": address_data,
            "relatedParty": related_party,
            "processCategory": process_category,
            "locationInformation": location_info
        }

        if getattr(institution, 'facility_description', None):
            credential_subject["description"] = institution.facility_description
        if getattr(institution, 'logo', None):
            credential_subject["logo"] = institution.logo

        # add any uploaded claim
        #TODO: do math verification of these claims
        performance_claims = []
        claims_qs = institution.claims.all() if hasattr(institution, 'claims') else []

        for claim in claims_qs:
            claim_id = f"urn:uuid:{uuid.uuid4()}"

            if hasattr(claim, 'assessment_date') and claim.assessment_date:
                claim_date_str = claim.assessment_date.strftime("%Y-%m-%d")
            else:
                claim_date_str = date.today().strftime("%Y-%m-%d")

            conformance_status = "Conformant" if getattr(claim, 'conformance', True) else "Non-Conformant"

            claim_data = {
                "type": ["Claim"],
                "id": claim_id,
                "name": getattr(claim, 'admin_name', None) or "Facility Conformity Claim",
                "description": getattr(claim, 'description', ""),
                "claimDate": claim_date_str,
                "conformityTopic": [{
                    "type": ["ConformityTopic"],
                    "id": f"http://vocabulary.uncefact.org/ConformityTopic#{getattr(claim, 'topic_code', 'unknown')}",
                    "name": getattr(claim, 'topic_code', 'Unknown Topic')
                }],
                "referenceCriteria": [{
                    "type": ["Criterion"],
                    "id": getattr(claim, 'admin_url', None) or "urn:uuid:unknown-criterion",
                    "name": getattr(claim, 'admin_name', None) or "Standard Criterion"
                }],
                "claimedPerformance": [{
                    "score": {
                        "code": conformance_status
                    }
                }]
            }

            if hasattr(claim, 'evidence_url') and claim.evidence_url:
                claim_data["evidence"] = [{
                    "linkURL": claim.evidence_url,
                    "linkName": getattr(claim, 'evidence_name', "Evidence Document") or "Evidence Document"
                }]

            performance_claims.append(claim_data)

        if performance_claims:
            credential_subject["performanceClaim"] = performance_claims

        return credential_subject


@PayloadBuilderRegistry.register(workflow_key="traceability", version="untp-0.7.0")
class UNTP070DTEBuilder(BaseUNTPBuilder):
    def build(self, event_type, device, institution, facility_info=None, previous_state=None, new_state=None, comment=None, **kwargs):
        """Constructs a UNTP 0.7.0 compliant Traceability Lifecycle Event payload."""

        device_uri = device.did or f"urn:uuid:{device.id}"
        inst_facility_uri = getattr(institution, 'facility_id_uri', None)
        fallback_facility_uri = f"urn:uuid:{institution.id}"

        biz_location_id = facility_info["id"] if facility_info else (inst_facility_uri or fallback_facility_uri)
        facility_name = facility_info["name"] if facility_info else institution.name

        now = datetime.datetime.now(datetime.timezone.utc).astimezone().replace(microsecond=0)

        event = {
            "type": [event_type, "LifecycleEvent"],
            "id": f"urn:uuid:{uuid.uuid4()}",
            "name": f"State Change to {new_state}" if new_state else f"{event_type} Generated",
            "description": f"Device state was updated from {previous_state} to {new_state} following an inspection or action." if new_state else f"{event_type} recorded.",
            "eventDate": now.isoformat(),

            "activityType": {
                "code": "inspecting",
                "name": "Inspecting",
                "schemeId": "urn:epcglobal:cbv:bizstep",
                "schemeName": "GS1 CBV"
            },

            "modifiedProduct": [{
                "product": {
                    "type": ["Product"],
                    "id": device_uri,
                    "name": getattr(device, 'model', "Unknown Device") or "Unknown Device",
                    "idGranularity": "item"
                },
                "disposition": "active"
            }],

            "modifiedAtFacility": {
                "type": ["Facility"],
                "id": biz_location_id,
                "name": facility_name
            },

            "relatedParty": [{
                "role": "operator",
                "party": {
                    "type": ["Party"],
                    "id": biz_location_id,
                    "name": institution.name
                }
            }]
        }

        # add custom states
        if new_state:
            event["ereuse:deviceState"] = new_state
        if previous_state:
            event["ereuse:previousState"] = previous_state

        event["ereuse:lastUpdate"] = now.isoformat()

        if comment:
            event["ereuse:operatorComment"] = comment

        return [event]


@PayloadBuilderRegistry.register(workflow_key="dpp", version="untp-0.7.0")
class UNTP070DPPBuilder(BaseUNTPBuilder):
    def build(self, device, institution, post_data=None, facility_info=None, traceability_info=None, **kwargs):
        post_data = post_data or {}
        components = device.components_export() or {}
        country_code = getattr(institution, 'country', None) or "XX"

        def parse_ram_to_mb(ram_string):
            if not isinstance(ram_string, str): return 0
            match = re.match(r'(\d+\.?\d*)\s*(GiB|MiB|GB|MB)', ram_string, re.IGNORECASE)
            if not match: return 0
            value, unit = float(match.groups()[0]), match.groups()[1].lower()
            if 'gib' in unit: return int(value * 1024)
            if 'gb' in unit: return int(value * 1000)
            if 'mib' in unit or 'mb' in unit: return int(value)
            return 0

        characteristics = {
            "chassis": components.get('type') or "Laptop",
            "manufacturer": components.get('manufacturer') or "Unknown",
            "model": components.get('model') or "Unknown",
            "cpu_model": components.get('cpu_model'),
            "cpu_cores": str(components.get('cpu_cores')) if components.get('cpu_cores') else None,
            "ram_total": parse_ram_to_mb(components.get('ram_total')),
            "ram_type": components.get('ram_type') or "Other",
            "ram_slots": components.get('ram_slots'),
            "slots_used": components.get('slots_used'),
            "drive": components.get('drive') or "Other",
            "gpu_model": components.get('gpu_model'),
            "serial": components.get('serial', "NA")
        }
        # clean nulls
        characteristics = {k: v for k, v in characteristics.items() if v is not None and v != ''}

        subject = {
            "type": ["Product"],
            "id": device.did if device.did else f"ereuse:{device.id}",
            "name": f"Device {device.shortid}",
            "description": "A personal refurbished computing device.",
            "idGranularity": "item",
            "idScheme": {
                "type": ["IdentifierScheme"],
                "id": "https://www.w3.org/ns/did/v1",
                "name": "Decentralized Identifiers"
            },
            "productCategory": [{
                "code": "452",
                "name": "Computing machinery and parts",
                "schemeId": "https://unstats.un.org/unsd/classifications/Econ/cpc/",
                "schemeName": "UN Central Product Classification (CPC)"
            }],
            "countryOfProduction": {"countryCode": country_code},
            "characteristics": characteristics,
            "traceabilityInformation": traceability_info or []
        }

        if facility_info:
            subject["producedAtFacility"] = {
                "type": ["Facility"],
                "id": facility_info["id"],
                "name": facility_info["name"]
            }
            if facility_info.get("registeredId"):
                subject["producedAtFacility"]["registeredId"] = str(facility_info["registeredId"])
        else:
            subject["producedAtFacility"] = {
                "type": ["Facility"],
                "id": getattr(institution, 'facility_id_uri', f"urn:uuid:{institution.id}"),
                "name": institution.name
            }

        serial = components.get('serial')
        if serial and str(serial).upper() != "NA":
            subject["itemNumber"] = str(serial)

        repair_guide = post_data.get('repair_guide', '').strip()
        if repair_guide:
            subject["relatedDocument"] = [{"linkURL": repair_guide, "linkName": "Device Repair Guide"}]
            subject["circularityScorecard"] = {
                "type": ["CircularityPerformance"],
                "repairInformation": {
                    "type": ["Link"],
                    "linkURL": repair_guide,
                    "linkName": "Device Repair Guide"
                }
            }

        raw_grade = post_data.get('cosmetic_grade', '').strip()
        if raw_grade:
            subject["characteristics"]["itemCondition"] = raw_grade

        operator_notes = post_data.get('operator_notes', '').strip()
        if operator_notes:
            subject["characteristics"]["operatorNotes"] = operator_notes

        warranty_months = post_data.get('warranty_months', '').strip()
        warranty_url = post_data.get('warranty_url', '').strip()
        if warranty_months or warranty_url:
            warranty_obj = {}
            if warranty_months and warranty_months.isdigit():
                warranty_obj["durationMonths"] = int(warranty_months)
            if warranty_url:
                warranty_obj["termsOfService"] = warranty_url
            subject["characteristics"]["warrantyPromise"] = warranty_obj

        return subject
