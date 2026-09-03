# api/v1/routers.py
from django.http import Http404
from ninja.errors import AuthenticationError, HttpError, ValidationError
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


@api.exception_handler(AuthenticationError)
def auth_error_handler(request, exc):
    payload = {
        "error": "Unauthorized",
        "details": "Malformed, invalid or not active token"
    }

    return api.create_response(request, payload, status=401)


@api.exception_handler(Http404)
def not_found_handler(request, exc):
    payload = {
        "error": "Not Found",
        "details": "The requested resource was not found"
    }

    return api.create_response(request, payload, status=404)


@api.exception_handler(ValidationError)
def validation_error_handler(request, exc):
    details = "; ".join(
        "{}: {}".format(".".join(str(loc) for loc in err["loc"]), err["msg"])
        for err in exc.errors
    )
    payload = {
        "error": "Unprocessable Entity",
        "details": details
    }

    return api.create_response(request, payload, status=422)

api.add_router("/lots", lots.router, tags=["Lots"])
api.add_router("/snapshot/", snapshot.router, tags=["Snapshots"])
api.add_router("/devices/", devices.router, tags=["Devices"])
