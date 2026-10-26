from __future__ import annotations

from ..vendor_interface import VendorError
from .rules import Kind

_CODES: dict[int, Kind] = {
    100: Kind.TEMPORARY,
    200: Kind.BAD_REQUEST,
    201: Kind.BAD_REQUEST,
    202: Kind.BAD_REQUEST,
    203: Kind.BAD_REQUEST,
    204: Kind.BAD_REQUEST,
    205: Kind.BAD_REQUEST,
    206: Kind.BAD_REQUEST,
    300: Kind.PERMANENT,
    401: Kind.PERMANENT,
    402: Kind.CONNECTION_LOST,
}


def classify(error: BaseException) -> Kind:
    if isinstance(error, VendorError):
        return _CODES.get(error.code, Kind.PERMANENT)
    if isinstance(error, TimeoutError):
        return Kind.TEMPORARY
    if isinstance(error, ConnectionError):
        return Kind.CONNECTION_LOST
    return Kind.PERMANENT
