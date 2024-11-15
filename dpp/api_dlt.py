from ereuseapi.methods import API


def connect_api():

    if not session.get('token_dlt'):
        return

    token_dlt = session.get('token_dlt')
    api_dlt = app.config.get('API_DLT')

    return API(api_dlt, token_dlt, "ethereum")

def register_dlt():
    api = self.connect_api()
    if not api:
        return

    snapshot = [x for x in self.actions if x.t == 'Snapshot']
    if not snapshot:
        return
    snapshot = snapshot[0]
    from ereuse_devicehub.modules.dpp.models import ALGORITHM
    from ereuse_devicehub.resources.enums import StatusCode
    cny_a = 1
    while cny_a:
        api = self.connect_api()
        result = api.register_device(
            self.chid,
            ALGORITHM,
            snapshot.phid_dpp,
            app.config.get('ID_FEDERATED')
        )
        try:
            assert result['Status'] == StatusCode.Success.value
            assert result['Data']['data']['timestamp']
            cny_a = 0
        except Exception:
            if result.get("Data") != "Device already exists":
                logger.error("API return: %s", result)
                time.sleep(10)
            else:
                cny_a = 0


    register_proof(result)

    if app.config.get('ID_FEDERATED'):
        cny = 1
        while cny:
            try:
                api.add_service(
                    self.chid,
                    'DeviceHub',
                    app.config.get('ID_FEDERATED'),
                    'Inventory service',
                    'Inv',
                )
                cny = 0
            except Exception:
                time.sleep(10)

def register_proof(self, result):
    from ereuse_devicehub.modules.dpp.models import PROOF_ENUM, Proof
    from ereuse_devicehub.resources.enums import StatusCode

    if result['Status'] == StatusCode.Success.value:
        timestamp = result.get('Data', {}).get('data', {}).get('timestamp')

        if not timestamp:
            return

        snapshot = [x for x in self.actions if x.t == 'Snapshot']
        if not snapshot:
            return
        snapshot = snapshot[0]

        d = {
            "type": PROOF_ENUM['Register'],
            "device": self,
            "action": snapshot,
            "timestamp": timestamp,
            "issuer_id": g.user.id,
            "documentId": snapshot.id,
            "documentSignature": snapshot.phid_dpp,
            "normalizeDoc": snapshot.json_hw,
        }
        proof = Proof(**d)
        db.session.add(proof)

    if not hasattr(self, 'components'):
        return

    for c in self.components:
        if isinstance(c, DataStorage):
            c.register_dlt()
