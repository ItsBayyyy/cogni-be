import ipaddress
import os

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request
from dotenv import load_dotenv

load_dotenv()

def _trusted_proxy_networks():
    networks = []
    for value in os.getenv("TRUSTED_PROXY_IPS", "").split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ipaddress.ip_network(value, strict=False))
        except ValueError:
            continue
    return networks

TRUSTED_PROXY_NETWORKS = _trusted_proxy_networks()

def get_real_ip(request: Request) -> str:
    peer = get_remote_address(request)
    try:
        peer_is_trusted = any(
            ipaddress.ip_address(peer) in network
            for network in TRUSTED_PROXY_NETWORKS
        )
    except ValueError:
        peer_is_trusted = False

    if peer_is_trusted:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            candidate = forwarded.split(",")[0].strip()
            try:
                return str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
    return peer

limiter = Limiter(
    key_func=get_real_ip,
    storage_uri=os.getenv("REDIS_URL") or "memory://",
)
