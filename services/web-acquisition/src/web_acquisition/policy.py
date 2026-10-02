"""Scope and network authorization are separate from robots compliance."""

from __future__ import annotations

import asyncio
import fnmatch
import ipaddress
import socket
from collections.abc import Sequence
from urllib.parse import urlsplit

from .models import AcquisitionError, CrawlPolicy
from .urls import normalize, origin


class PolicyEngine:
    def __init__(self, policy: CrawlPolicy, seeds: Sequence[str]):
        self.policy = policy
        self.seed_origins = {origin(seed) for seed in seeds}
        self.seed_hosts = {urlsplit(seed).hostname for seed in seeds}
        self.hosts = {normalize(f"https://{host}").split("/")[2] for host in policy.allowed_hosts}
        self.domains = {
            normalize(f"https://{host}").split("/")[2] for host in policy.allowed_domains
        }
        if (
            any(len(p) > 256 for p in (*policy.denied_path_globs, *policy.allowed_path_prefixes))
            or len(policy.denied_path_globs) > 32
        ):
            raise AcquisitionError("invalid_path_policy")

    def normalized(self, url: str, base: str | None = None) -> str:
        return normalize(
            url,
            base,
            query_mode=self.policy.query_mode,
            collapse_slashes=self.policy.collapse_slashes,
            max_length=self.policy.max_url_length,
        )

    def check(self, url: str, *, robots: bool = False) -> None:
        parts = urlsplit(url)
        if parts.scheme not in self.policy.allowed_schemes:
            raise AcquisitionError("unsupported_scheme")
        host = parts.hostname
        if self.policy.same_origin and origin(url) not in self.seed_origins:
            raise AcquisitionError("outside_scope")
        if self.hosts or self.domains:
            domain_match = any(
                host == domain
                or (
                    self.policy.include_subdomains
                    and host is not None
                    and host.endswith("." + domain)
                )
                for domain in self.domains
            )
            if host not in self.hosts and not domain_match:
                raise AcquisitionError("outside_scope")
        elif host not in self.seed_hosts:
            raise AcquisitionError("outside_scope")
        if not robots:
            if self.policy.allowed_path_prefixes and not any(
                parts.path.startswith(prefix) for prefix in self.policy.allowed_path_prefixes
            ):
                raise AcquisitionError("outside_scope")
            if any(
                fnmatch.fnmatchcase(parts.path, pattern)
                for pattern in self.policy.denied_path_globs
            ):
                raise AcquisitionError("policy_denied")


class Resolver:
    async def resolve(self, host: str, port: int) -> list[str]:
        addresses = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
        return sorted({str(record[4][0]) for record in addresses})


class EgressPolicy:
    """No allow-private escape hatch. Connections use these literal addresses."""

    def validate_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or parts.port not in (None, 80, 443):
            raise AcquisitionError("egress_port_or_scheme")
        if parts.hostname is None:
            raise AcquisitionError("invalid_host")
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            return
        self.validate_resolved_addresses([str(address)])

    def validate_resolved_addresses(self, addresses: Sequence[str]) -> None:
        if not addresses:
            raise AcquisitionError("dns_empty")
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise AcquisitionError("dns_invalid") from exc
            if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
                address = address.ipv4_mapped
            if (
                not address.is_global
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
                or address.is_loopback
                or address.is_link_local
            ):
                raise AcquisitionError("ssrf_blocked")
            # Block translation/tunnel ranges that can encode other targets.
            if isinstance(address, ipaddress.IPv6Address) and (
                address.sixtofour
                or address.teredo
                or address in ipaddress.ip_network("64:ff9b::/96")
                or address in ipaddress.ip_network("64:ff9b:1::/48")
            ):
                raise AcquisitionError("ssrf_blocked")
