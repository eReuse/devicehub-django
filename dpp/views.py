import json
import logging
import hashlib

from django.views.generic.edit import View
from django.http import JsonResponse

from dpp.api_dlt import ALGORITHM
from evidence.models import Evidence
from evidence.parse import Build
from dpp.models import Proof


class ProofView(View):

    def get(self, request, *args, **kwargs):
        timestamp = kwargs.get("proof_id")
        proof = Proof.objects.filter(timestamp=timestamp).first()
        if not proof:
            return JsonResponse({}, status=404)

        ev = Evidence(proof.uuid)
        if not ev.doc:
            return JsonResponse({}, status=404)

        dev = Build(ev.doc, None, check=True)
        doc = dev.build.get_doc()

        data = {
            "algorithm": ALGORITHM,
            "document": json.dumps(doc)
        }

        d = {
            '@context': ['https://ereuse.org/proof0.json'],
            'data': data,
        }
        response = JsonResponse(d, status=200)
        response["Access-Control-Allow-Origin"] = "*"
        return response
