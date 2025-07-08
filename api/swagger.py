from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from api.schemas import HelloInputSchema, HelloOutputSchema

spec = APISpec(
    title="DeviceHub",
    version="1.0.0",
    openapi_version="3.0.2",
    plugins=[MarshmallowPlugin()],
    components={
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT"  # opcional, si usas JWT
            }
        }
    }
)


spec.options["security"] = [{"BearerAuth": []}]


spec.path(
    path="/hello",
    operations={
        "post": {
            "summary": "Recibe un snapshot",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": HelloInputSchema,
                    }
                },
            },
            "responses": {
                "200": {
                    "description": "Snapshot recibido",
                    "content": {
                        "application/json": {
                            "schema": HelloOutputSchema,
                        }
                    },
                },
            },
        }
    },
)
