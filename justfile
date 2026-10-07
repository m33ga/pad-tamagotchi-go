set shell := ["sh", "-eu", "-c"]

# Generate a high-entropy service credential and the hash stored by User Management.
# The plaintext is printed once; copy each value only to the indicated local .env.
gen-client-secret service:
    #!/usr/bin/env sh
    set -eu
    variable_name="$(printf '%s' '{{service}}' | tr '[:lower:]-' '[:upper:]_')"
    variable_name="${variable_name%_SERVICE}"
    secret="$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')"
    secret_hash="$(printf '%s' "$secret" | openssl dgst -sha256 -r | awk '{print $1}')"
    printf '%s_CLIENT_SECRET=%s\n' "$variable_name" "$secret"
    printf '%s_CLIENT_SECRET_HASH=%s\n' "$variable_name" "$secret_hash"
