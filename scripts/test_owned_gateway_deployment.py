"""Check Guild/Registry Compose wiring without loading private env files."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OwnedGatewayDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            ["docker", "compose", "--env-file", ".env.example", "config",
             "--no-env-resolution", "--format", "json"],
            cwd=ROOT, check=True, capture_output=True, text=True,
        )
        cls.services = json.loads(result.stdout)["services"]

    def test_rest_and_databases_have_no_host_ports(self):
        for name in ("package-registry-api", "guild-db", "package-registry-db"):
            self.assertFalse(self.services[name].get("ports"), name)
        guild = self.services["guild-api"]
        self.assertEqual(len(guild["ports"]), 1)
        self.assertEqual(guild["ports"][0]["target"], int(guild["environment"]["WS_PORT"]))
        self.assertNotEqual(guild["environment"]["PORT"], guild["environment"]["WS_PORT"])

    def test_gateway_can_reach_both_services(self):
        gateway_networks = set(self.services["api-gateway"]["networks"])
        for name in ("guild-api", "package-registry-api"):
            self.assertTrue(gateway_networks & set(self.services[name]["networks"]), name)

    def test_private_credentials_are_scoped_to_their_service(self):
        for name, client in (("guild-api", "guild-service"),
                             ("package-registry-api", "package-registry-service")):
            service = self.services[name]
            paths = [entry["path"] if isinstance(entry, dict) else entry
                     for entry in service["env_file"]]
            self.assertEqual([Path(path).name for path in paths], [client + ".env"])
            self.assertNotIn("CLIENT_SECRET", service["environment"])
            self.assertNotIn("OAUTH_CLIENT_SECRET", service["environment"])

    def test_deadlines_leave_gateway_time_to_forward_service_error(self):
        for name in ("guild-api", "package-registry-api"):
            self.assertEqual(self.services[name]["environment"]["REQUEST_TIMEOUT"], "4s")


if __name__ == "__main__":
    unittest.main()
