#!/usr/bin/env python3
"""Test owned services through the real gateway/issuer in a disposable stack.

Uses only generated fixture credentials and tmpfs databases. It neither reads
the project's .env/secrets nor starts or stops its normal Compose deployment.
Required: Docker Compose, Go, openssl, and locally built audit images.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = "11111111-1111-4111-8111-111111111111"
CLIENTS = ("guild", "package-registry", "monster-raid", "battle", "map", "tamagotchi", "notification")


def run(command, **kwargs):
    return subprocess.run(command, check=True, text=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-image", required=True)
    parser.add_argument("--guild-image", required=True)
    parser.add_argument("--registry-image", required=True)
    parser.add_argument("--issuer-image", default="sanda2004/user-management-service:2.0.0")
    args = parser.parse_args()
    project = "pad-owned-e2e-" + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix=project + "-") as directory:
        folder = Path(directory)
        key = folder / "jwt-private.pem"
        run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", str(key)], capture_output=True)
        key.chmod(0o644)  # read-only container mount; host parent is mode 0700
        client_file = folder / "service-clients.yaml"
        client_file.write_text((ROOT / "config/service-clients.yaml").read_text())
        gateway_file = folder / "gateway.yaml"
        gateway_file.write_text((ROOT / "config/gateway.yaml").read_text())
        credentials = {name: secrets.token_urlsafe(32) for name in CLIENTS}
        password = secrets.token_urlsafe(32)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            ws_port = reservation.getsockname()[1]

        def database():
            return {"image": "postgres:17-alpine", "environment": {
                "POSTGRES_DB": "audit", "POSTGRES_USER": "audit", "POSTGRES_PASSWORD": password,
            }, "tmpfs": ["/var/lib/postgresql/data"], "healthcheck": {
                "test": ["CMD", "pg_isready", "-U", "audit", "-d", "audit"],
                "interval": "2s", "timeout": "2s", "retries": 30,
            }}

        def health(command):
            return {"test": ["CMD"] + command, "interval": "2s", "timeout": "3s", "retries": 40}

        def owned(image, name, port):
            return {"image": image, "pull_policy": "never", "environment": {
                "PORT": str(port), "DATABASE_URL": f"postgres://audit:{password}@{name}-db:5432/audit?sslmode=disable",
                "GATEWAY_URL": "http://api-gateway:8080", "OAUTH_CLIENT_ID": name + "-service",
                "OAUTH_CLIENT_SECRET": credentials[name], "MOCK_EXTERNAL_SERVICES": "false",
                "REQUEST_TIMEOUT": "4s", "MAX_CONCURRENCY": "64",
            }, "depends_on": {name + "-db": {"condition": "service_healthy"}},
                "healthcheck": health(["wget", "--spider", "--quiet", f"http://127.0.0.1:{port}/healthz"])}

        issuer_env = {
            "USER_MANAGEMENT_DB_HOST": "user-management-db", "USER_MANAGEMENT_DB_PORT": "5432",
            "USER_MANAGEMENT_DB_NAME": "audit", "USER_MANAGEMENT_DB_USER": "audit",
            "USER_MANAGEMENT_DB_PASSWORD": password, "JWT_KEY_ID": "audit-key",
            "JWT_PRIVATE_KEY_PATH": "/run/secrets/jwt-private.pem", "SERVICE_CLIENTS_PATH": "/app/config/service-clients.yaml",
            "USE_MOCK_PACKAGE_REGISTRY": "false", "USE_MOCK_SERVICES": "false",
            "GATEWAY_URL": "http://api-gateway:8080", "REQUEST_TIMEOUT_SECONDS": "4", "MAX_CONCURRENCY": "64",
        }
        issuer_env.update({name.replace("-", "_").upper() + "_CLIENT_SECRET_HASH": hashlib.sha256(secret.encode()).hexdigest()
                           for name, secret in credentials.items()})
        services = {name + "-db": database() for name in ("guild", "package-registry", "user-management")}
        services["guild-api"] = owned(args.guild_image, "guild", 8081)
        services["guild-api"]["environment"].update({"WS_PORT": "8083", "PUBLIC_WS_URL": f"ws://127.0.0.1:{ws_port}"})
        services["guild-api"]["ports"] = [f"127.0.0.1:{ws_port}:8083"]
        services["package-registry-api"] = owned(args.registry_image, "package-registry", 8082)
        services["user-management-api"] = {
            "image": args.issuer_image, "environment": issuer_env,
            "volumes": [f"{key}:/run/secrets/jwt-private.pem:ro", f"{client_file}:/app/config/service-clients.yaml:ro"],
            "depends_on": {"user-management-db": {"condition": "service_healthy"}},
            "healthcheck": health(["curl", "--fail", "--silent", "http://127.0.0.1:8080/_health"]),
        }
        services["api-gateway"] = {
            "image": args.gateway_image, "pull_policy": "never", "ports": ["127.0.0.1::8080"],
            "volumes": [f"{gateway_file}:/app/config/gateway.yaml:ro"],
            "depends_on": {"user-management-api": {"condition": "service_healthy"}},
            "healthcheck": health(["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/readyz',timeout=2)"]),
        }
        compose_file = folder / "compose.json"
        compose_file.write_text(json.dumps({"services": services}))
        compose_file.chmod(0o600)
        compose = ["docker", "compose", "-p", project, "-f", str(compose_file)]
        print(f"Starting isolated test project {project}; existing containers remain untouched.", flush=True)
        try:
            run(compose + ["up", "-d", "--wait", "--wait-timeout", "120"])
            # Bootstrap only this disposable Registry database, so the issuer can
            # register its first user against a real initial package.
            sql = f"INSERT INTO packages(package_id,name,version,description,status) VALUES ('{BOOTSTRAP}','Audit bootstrap','1.0.0','Disposable test fixture','ACTIVE');"
            run(compose + ["exec", "-T", "package-registry-db", "psql", "-U", "audit", "-d", "audit", "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True)
            address = run(compose + ["port", "api-gateway", "8080"], capture_output=True).stdout.strip()
            environment = dict(os.environ, TEST_GATEWAY_URL="http://" + address,
                               TEST_BOOTSTRAP_PACKAGE_ID=BOOTSTRAP,
                               TEST_GUILD_CLIENT_SECRET=credentials["guild"],
                               TEST_REGISTRY_CLIENT_SECRET=credentials["package-registry"],
                               TEST_RAID_CLIENT_SECRET=credentials["monster-raid"])
            environment.pop("TEST_DATABASE_URL", None)
            run(["go", "test", "-count=1", "-v", "-run", "^TestLiveGatewayIssuer$", "./internal/httpapi"],
                cwd=ROOT / "pad-guild-service", env=environment)
            print("PASS: actual gateway + issuer + Guild + Registry, mocks disabled.", flush=True)
        finally:
            run(compose + ["down", "--timeout", "5"])
            print("Removed only the disposable test containers/network; tmpfs fixture data is discarded.", flush=True)


if __name__ == "__main__":
    main()
