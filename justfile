# Generate a secret and its issuer hash; copy both into the private local .env.
gen-client-secret client:
    python3 scripts/generate_client_secret.py {{client}}

# Prepare the local signing key and all seven clients, preserving existing values.
configure:
    python3 scripts/configure_services_auth.py

# Validate deployment isolation and collection authentication without Docker startup.
check:
    python3 -m unittest discover -s tests -p 'test_*.py'

# Pull and exercise the published stack in a temporary, isolated Compose project.
integration:
    python3 tests/deployment_smoke.py
