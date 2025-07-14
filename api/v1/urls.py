# api/v1/routers.py
from ninja import NinjaAPI
from . import lots, snapshot, devices
from api.auth import GlobalAuth

api = NinjaAPI(auth= GlobalAuth() ,version='1.0.0')
api.add_router("/lots", lots.router, tags=["Lots"])
api.add_router("/snapshot/", snapshot.router, tags=["Devices"])
api.add_router("/devices/", devices.router, tags=["Devices"])
