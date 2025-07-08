from marshmallow import Schema, fields


# Schema de entrada
class HelloInputSchema(Schema):
    snapshot = fields.String(required=True)


# Schema de salida
class HelloOutputSchema(Schema):
    snapshot = fields.String()
