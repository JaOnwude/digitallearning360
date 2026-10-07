from fastapi import Request


def client_ip(request: Request) -> str:
    """The caller's IP, as forwarded by the web proxy / hosting platform."""
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "?")
