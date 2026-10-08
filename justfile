# Generate a secret and its issuer hash; copy both into the private local .env.
gen-client-secret client:
    python3 scripts/generate_client_secret.py {{client}}

# Prepare the local signing key and all seven clients, preserving existing values.
configure:
    python3 scripts/configure_services_auth.py
