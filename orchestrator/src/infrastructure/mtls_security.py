"""
mTLS (Mutual TLS) security implementation for internal service communication.
Provides certificate management and secure service-to-service authentication.
"""
import ssl
import os
import time
import hashlib
import secrets
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
import httpx
import asyncio
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import datetime

from shared.src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CertificateInfo:
    """Certificate information for mTLS."""
    service_name: str
    cert_path: str
    key_path: str
    ca_cert_path: str
    expires_at: datetime.datetime
    fingerprint: str


@dataclass
class mTLSConfig:
    """Configuration for mTLS security."""
    enabled: bool = True
    cert_dir: str = "/app/certs"
    ca_cert_path: str = "/app/certs/ca.crt"
    service_cert_path: str = "/app/certs/service.crt"
    service_key_path: str = "/app/certs/service.key"

    # Certificate settings
    cert_validity_days: int = 365
    key_size: int = 2048
    auto_renew_days_before_expiry: int = 30

    # Service identity
    service_name: str = "famagpt-orchestrator"
    organization: str = "FamaGPT"
    country: str = "BR"

    # Allowed services (for certificate validation)
    allowed_services: List[str] = None

    def __post_init__(self):
        if self.allowed_services is None:
            self.allowed_services = [
                "famagpt-orchestrator",
                "famagpt-webhooks",
                "famagpt-transcription",
                "famagpt-web-search",
                "famagpt-memory",
                "famagpt-rag",
                "famagpt-database",
                "famagpt-specialist"
            ]


class CertificateManager:
    """Manages SSL certificates for mTLS."""

    def __init__(self, config: mTLSConfig):
        self.config = config
        self.cert_info: Optional[CertificateInfo] = None

    def generate_ca_certificate(self) -> tuple[bytes, bytes]:
        """Generate a Certificate Authority certificate and key."""
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.config.key_size
        )

        # Create certificate
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, self.config.country),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.config.organization),
            x509.NameAttribute(NameOID.COMMON_NAME, f"{self.config.organization} CA"),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            issuer
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=self.config.cert_validity_days * 2)  # CA lasts longer
        ).add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=True,
                crl_sign=True,
                digital_signature=False,
                key_encipherment=False,
                key_agreement=False,
                data_encipherment=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True,
        ).sign(private_key, hashes.SHA256())

        # Serialize certificate and key
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        return cert_pem, key_pem

    def generate_service_certificate(self, ca_cert_pem: bytes, ca_key_pem: bytes) -> tuple[bytes, bytes]:
        """Generate a service certificate signed by the CA."""
        # Load CA certificate and key
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem)
        ca_key = serialization.load_pem_private_key(ca_key_pem, password=None)

        # Generate service private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=self.config.key_size
        )

        # Create service certificate
        subject = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, self.config.country),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, self.config.organization),
            x509.NameAttribute(NameOID.COMMON_NAME, self.config.service_name),
        ])

        cert = x509.CertificateBuilder().subject_name(
            subject
        ).issuer_name(
            ca_cert.subject
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.datetime.utcnow()
        ).not_valid_after(
            datetime.datetime.utcnow() + datetime.timedelta(days=self.config.cert_validity_days)
        ).add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(self.config.service_name),
                x509.DNSName(f"{self.config.service_name}.default.svc.cluster.local"),
                x509.DNSName("localhost"),
                x509.IPAddress("127.0.0.1"),
            ]),
            critical=False,
        ).add_extension(
            x509.KeyUsage(
                key_cert_sign=False,
                crl_sign=False,
                digital_signature=True,
                key_encipherment=True,
                key_agreement=False,
                data_encipherment=False,
                content_commitment=False,
                encipher_only=False,
                decipher_only=False
            ),
            critical=True,
        ).add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=True,
        ).sign(ca_key, hashes.SHA256())

        # Serialize certificate and key
        cert_pem = cert.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        )

        return cert_pem, key_pem

    def setup_certificates(self) -> bool:
        """Set up certificates for mTLS."""
        try:
            # Ensure certificate directory exists
            cert_dir = Path(self.config.cert_dir)
            cert_dir.mkdir(parents=True, exist_ok=True)

            ca_cert_path = Path(self.config.ca_cert_path)
            service_cert_path = Path(self.config.service_cert_path)
            service_key_path = Path(self.config.service_key_path)

            # Check if CA certificate exists
            if not ca_cert_path.exists():
                logger.info("Generating CA certificate")
                ca_cert_pem, ca_key_pem = self.generate_ca_certificate()

                # Save CA certificate
                ca_cert_path.write_bytes(ca_cert_pem)

                # Save CA key (in production, this should be stored securely)
                ca_key_path = cert_dir / "ca.key"
                ca_key_path.write_bytes(ca_key_pem)
                os.chmod(ca_key_path, 0o600)  # Restrict permissions

            else:
                # Load existing CA certificate and key
                ca_cert_pem = ca_cert_path.read_bytes()
                ca_key_path = cert_dir / "ca.key"
                ca_key_pem = ca_key_path.read_bytes()

            # Check if service certificate exists or needs renewal
            needs_new_cert = True
            if service_cert_path.exists():
                try:
                    cert_pem = service_cert_path.read_bytes()
                    cert = x509.load_pem_x509_certificate(cert_pem)

                    # Check if certificate is still valid
                    now = datetime.datetime.utcnow()
                    renewal_threshold = now + datetime.timedelta(days=self.config.auto_renew_days_before_expiry)

                    if cert.not_valid_after > renewal_threshold:
                        needs_new_cert = False
                        logger.info("Existing service certificate is still valid")

                except Exception as e:
                    logger.warning("Failed to validate existing certificate", error=str(e))

            if needs_new_cert:
                logger.info("Generating new service certificate")
                service_cert_pem, service_key_pem = self.generate_service_certificate(
                    ca_cert_pem, ca_key_pem
                )

                # Save service certificate and key
                service_cert_path.write_bytes(service_cert_pem)
                service_key_path.write_bytes(service_key_pem)
                os.chmod(service_key_path, 0o600)  # Restrict permissions

            # Load certificate info
            cert_pem = service_cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem)

            # Calculate fingerprint
            fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()

            self.cert_info = CertificateInfo(
                service_name=self.config.service_name,
                cert_path=str(service_cert_path),
                key_path=str(service_key_path),
                ca_cert_path=str(ca_cert_path),
                expires_at=cert.not_valid_after,
                fingerprint=fingerprint
            )

            logger.info("mTLS certificates ready",
                       service_name=self.config.service_name,
                       expires_at=cert.not_valid_after.isoformat(),
                       fingerprint=fingerprint[:16])

            return True

        except Exception as e:
            logger.error("Failed to setup certificates", error=str(e))
            return False

    def get_ssl_context(self, is_server: bool = True) -> ssl.SSLContext:
        """Get SSL context for mTLS."""
        if not self.cert_info:
            raise ValueError("Certificates not set up")

        # Create SSL context
        if is_server:
            context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            # Load server certificate and key
            context.load_cert_chain(self.cert_info.cert_path, self.cert_info.key_path)
        else:
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
            # Load client certificate and key
            context.load_cert_chain(self.cert_info.cert_path, self.cert_info.key_path)

        # Load CA certificate for verification
        context.load_verify_locations(self.cert_info.ca_cert_path)

        # Require certificate verification
        context.verify_mode = ssl.CERT_REQUIRED
        context.check_hostname = False  # We'll verify service names manually

        return context

    def verify_peer_certificate(self, peer_cert_der: bytes) -> bool:
        """Verify peer certificate."""
        try:
            # Load peer certificate
            peer_cert = x509.load_der_x509_certificate(peer_cert_der)

            # Check if service is allowed
            common_name = None
            for attribute in peer_cert.subject:
                if attribute.oid == NameOID.COMMON_NAME:
                    common_name = attribute.value
                    break

            if common_name not in self.config.allowed_services:
                logger.warning("Peer service not in allowed list", peer_service=common_name)
                return False

            # Check certificate validity
            now = datetime.datetime.utcnow()
            if peer_cert.not_valid_before > now or peer_cert.not_valid_after < now:
                logger.warning("Peer certificate not valid", peer_service=common_name)
                return False

            logger.debug("Peer certificate verified", peer_service=common_name)
            return True

        except Exception as e:
            logger.error("Failed to verify peer certificate", error=str(e))
            return False


class mTLSClient:
    """HTTP client with mTLS support."""

    def __init__(self, cert_manager: CertificateManager):
        self.cert_manager = cert_manager
        self.client: Optional[httpx.AsyncClient] = None

    async def create_client(self) -> httpx.AsyncClient:
        """Create HTTP client with mTLS."""
        if not self.cert_manager.cert_info:
            raise ValueError("Certificates not configured")

        # Get SSL context for client
        ssl_context = self.cert_manager.get_ssl_context(is_server=False)

        # Create HTTPX client with mTLS
        self.client = httpx.AsyncClient(
            verify=ssl_context,
            cert=(
                self.cert_manager.cert_info.cert_path,
                self.cert_manager.cert_info.key_path
            ),
            timeout=30.0
        )

        return self.client

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Make GET request with mTLS."""
        if not self.client:
            await self.create_client()
        return await self.client.get(url, **kwargs)

    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Make POST request with mTLS."""
        if not self.client:
            await self.create_client()
        return await self.client.post(url, **kwargs)

    async def close(self):
        """Close the client."""
        if self.client:
            await self.client.aclose()


class mTLSMiddleware:
    """FastAPI middleware for mTLS server verification."""

    def __init__(self, cert_manager: CertificateManager):
        self.cert_manager = cert_manager

    async def __call__(self, request, call_next):
        """Process request with mTLS verification."""
        # Check if mTLS is enabled
        if not self.cert_manager.config.enabled:
            return await call_next(request)

        # Skip mTLS for health checks and public endpoints
        if request.url.path in ["/health", "/metrics"]:
            return await call_next(request)

        # Verify client certificate (would be populated by reverse proxy)
        client_cert_header = request.headers.get("x-client-cert")
        if client_cert_header:
            try:
                # Decode certificate from header (base64 encoded DER)
                import base64
                cert_der = base64.b64decode(client_cert_header)

                if not self.cert_manager.verify_peer_certificate(cert_der):
                    from fastapi import HTTPException
                    raise HTTPException(status_code=403, detail="Invalid client certificate")

            except Exception as e:
                logger.error("Certificate verification failed", error=str(e))
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="Certificate verification failed")

        # Add certificate info to request state
        request.state.mtls_verified = True
        request.state.cert_info = self.cert_manager.cert_info

        return await call_next(request)


# Global mTLS components
_cert_manager: Optional[CertificateManager] = None
_mtls_client: Optional[mTLSClient] = None


def initialize_mtls(config: Optional[mTLSConfig] = None) -> tuple[CertificateManager, mTLSClient]:
    """Initialize global mTLS components."""
    global _cert_manager, _mtls_client

    if config is None:
        config = mTLSConfig()

    _cert_manager = CertificateManager(config)

    if config.enabled:
        success = _cert_manager.setup_certificates()
        if not success:
            logger.error("Failed to setup mTLS certificates")
            config.enabled = False

    _mtls_client = mTLSClient(_cert_manager)

    logger.info("mTLS initialized",
               enabled=config.enabled,
               service_name=config.service_name)

    return _cert_manager, _mtls_client


def get_mtls_client() -> Optional[mTLSClient]:
    """Get the global mTLS client."""
    return _mtls_client


def get_cert_manager() -> Optional[CertificateManager]:
    """Get the global certificate manager."""
    return _cert_manager


# Convenience decorator for mTLS-protected endpoints
def require_mtls(func):
    """Decorator to require mTLS for endpoint."""
    async def wrapper(request, *args, **kwargs):
        if not hasattr(request.state, 'mtls_verified') or not request.state.mtls_verified:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="mTLS required")
        return await func(request, *args, **kwargs)
    return wrapper