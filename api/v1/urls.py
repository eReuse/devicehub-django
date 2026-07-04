# api/v1/routers.py
from ninja.errors import HttpError
from ninja import NinjaAPI
from . import lots, snapshot, devices
from api.auth import GlobalAuth

api = NinjaAPI(auth= GlobalAuth() ,version='1.0.0', urls_namespace='api_v1')

@api.exception_handler(HttpError)
def custom_http_error_handler(request, exc):
    """
    Catches all HttpErrors and formats them
    to match the MessageOut schema.
    """
    titles = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        500: "Internal Server Error"
    }

    error_title = titles.get(exc.status_code, "Request Failed")

    payload = {
        "error": error_title,
        "details": str(exc.message)
    }

    return api.create_response(request, payload, status=exc.status_code)

api.add_router("/lots", lots.router, tags=["Lots"])
api.add_router("/snapshot/", snapshot.router, tags=["Snapshots"])
api.add_router("/devices/", devices.router, tags=["Devices"])
