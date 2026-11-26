#!/usr/bin/env python3
"""Prepare starter pets and currency in a local demo after Postman onboarding."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import NAMESPACE_URL, uuid4, uuid5

GATEWAY_URL = "http://api-gateway:8080"


def prepare_in_broker():
    import grpc
    from google.protobuf.timestamp_pb2 import Timestamp
    from tamagotchigo.broker.v1 import broker_pb2, broker_pb2_grpc
    from tamagotchigo.tamagotchi.v1 import tamagotchi_pb2 as pets
    from tamagotchigo.usermanagement.v1 import user_management_pb2 as users

    from datetime import datetime, timedelta, timezone

    setup = json.load(sys.stdin)
    values = setup["variables"]
    broker = broker_pb2_grpc.BrokerStub(grpc.insecure_channel("127.0.0.1:9090"))

    def send(service, operation, body, content_type, token=None):
        deadline = Timestamp()
        deadline.FromDatetime(datetime.now(timezone.utc) + timedelta(seconds=8))
        request = broker_pb2.Message(
            message_id=str(uuid4()), service=service, operation=operation,
            headers={"x-correlation-id": "workflow-fixture-" + str(uuid4())},
            content_type=content_type, body=body, deadline=deadline,
        )
        metadata = (("authorization", f"Bearer {token}"),) if token else ()
        return broker.Send(request, metadata=metadata, timeout=10)

    def gateway(player, path, body=None):
        request = Request(
            f"{GATEWAY_URL}/tamagotchi/api/v1{path}",
            data=json.dumps(body).encode() if body else None,
            headers={
                "Authorization": "Bearer " + values[player + "Token"],
                "Content-Type": "application/json",
            },
        )
        with urlopen(request, timeout=10) as response:
            return json.load(response)

    token_reply = send(
        "user-management", "POST /api/v1/oauth2/token",
        urlencode({"grant_type": "client_credentials", "client_id": "battle-service",
                   "client_secret": setup["battleClientSecret"]}).encode(),
        "application/x-www-form-urlencoded",
    )
    if token_reply.status != 200:
        raise RuntimeError(f"Could not authenticate the demo battle client (HTTP {token_reply.status})")
    token = json.loads(token_reply.body)["access_token"]

    def perform(service, method, request):
        reply = send(service, method, request.SerializeToString(), "application/protobuf", token)
        if reply.status:
            raise RuntimeError(f"{method} failed with status {reply.status}")

    def reference(player, kind):
        return str(uuid5(NAMESPACE_URL, f"pad-game-workflow/{values[player+'UserId']}/{kind}"))

    carol = values["carolUserId"]
    for player, pet_name in (("alice", "Sprout"), ("bob", "Pebble")):
        target = values[player + "UserId"]
        roster = gateway(player, f"/users/{target}/tamagotchis")
        if not any(pet["name"] == pet_name and pet["ownershipRole"] == "SECONDARY" for pet in roster):
            if player == "alice":
                pet_id = values["carolPrimaryId"]
            else:
                owned = gateway("carol", f"/users/{carol}/tamagotchis")
                pebble = next((pet for pet in owned if pet["name"] == pet_name), None)
                if pebble is None:
                    pebble = gateway("carol", "/tamagotchis", {
                        "ownerUserId": carol, "packageId": values["packageId"], "name": pet_name,
                        "combatType": "EARTH", "spriteUrl": values["spriteUrl"],
                        "healthStats": {"hunger": 25, "happiness": 55, "energy": 75},
                    })
                pet_id = pebble["tamagotchiId"]
            perform("tamagotchi", "/tamagotchigo.tamagotchi.v1.Tamagotchi/TransferOwnership",
                    pets.TransferOwnershipRequest(
                        tamagotchi_id=pet_id, from_user_id=carol, to_user_id=target,
                        reason=pets.TRANSFER_REASON_BATTLE_REWARD, reference_id=reference(player, "pet"),
                    ))
        perform("user-management", "/tamagotchigo.usermanagement.v1.UserManagement/CreateBalanceTransaction",
                users.CreateBalanceTransactionRequest(
                    user_id=target, currency=users.CURRENCY_GLOBAL, amount=100,
                    reason=users.TRANSACTION_REASON_BATTLE_REWARD, reference_id=reference(player, "coins"),
                ))
        print(f"Prepared {player}'s secondary and starter purse.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("environment", type=Path, help="Private Postman environment exported after onboarding")
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--compose-file", type=Path)
    parser.add_argument("--project-name")
    args = parser.parse_args()

    exported = json.loads(args.environment.read_text())
    variables = {item["key"]: item.get("value") for item in exported["values"]}
    required = ("aliceUserId", "bobUserId", "carolUserId", "aliceToken", "bobToken", "carolToken",
                "carolPrimaryId", "packageId", "spriteUrl")
    missing = [key for key in required if not variables.get(key)]
    if missing:
        parser.error("run onboarding first and export its environment: " + ", ".join(missing))
    env = dict(line.split("=", 1) for line in args.env_file.read_text().splitlines()
               if "=" in line and not line.lstrip().startswith("#"))
    secret = env.get("BATTLE_CLIENT_SECRET")
    if not secret or secret == "change_me":
        parser.error("run scripts/configure_services_auth.py on the demo stack first")

    compose = ["docker", "compose"]
    if args.compose_file:
        compose.extend(("-f", str(args.compose_file)))
    if args.project_name:
        compose.extend(("-p", args.project_name))
    subprocess.run(
        [*compose, "exec", "-T", "broker", "python", "-c", Path(__file__).read_text(), "--inside-broker"],
        input=json.dumps({"variables": {key: variables[key] for key in required}, "battleClientSecret": secret}),
        text=True, check=True,
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["--inside-broker"]:
        prepare_in_broker()
    else:
        main()
