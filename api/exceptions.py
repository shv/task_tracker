from rest_framework import status
from rest_framework.exceptions import APIException


class EndpointNotImplemented(APIException):
    status_code = status.HTTP_501_NOT_IMPLEMENTED
    default_detail = "This endpoint is not implemented yet."
    default_code = "not_implemented"
