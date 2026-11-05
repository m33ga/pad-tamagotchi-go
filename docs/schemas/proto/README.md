# gRPC contracts

The single source of truth for every gRPC interface in Tamagotchi Go. The rules for using them
(the broker interface, headers, deadlines, errors, circuit breakers, events) are in the
[Message Broker](../../../README.md#message-broker) section of the CPR README.

| File | Package | Served by | Called by |
|---|---|---|---|
| [`tamagotchigo/broker/v1/broker.proto`](tamagotchigo/broker/v1/broker.proto) | `tamagotchigo.broker.v1` | message broker (`Broker.Send`, `Broker.Publish`) | the gateway and every service |
| [`tamagotchigo/events/v1/events.proto`](tamagotchigo/events/v1/events.proto) | `tamagotchigo.events.v1` | every subscribing service (`EventConsumer.Deliver`) | the broker |
| [`tamagotchigo/usermanagement/v1/user_management.proto`](tamagotchigo/usermanagement/v1/user_management.proto) | `tamagotchigo.usermanagement.v1` | User Management | Map, Guild, Battle |
| [`tamagotchigo/packageregistry/v1/package_registry.proto`](tamagotchigo/packageregistry/v1/package_registry.proto) | `tamagotchigo.packageregistry.v1` | Package Registry | User Management, Guild, Tamagotchi, Battle, Monster Raid |
| [`tamagotchigo/guild/v1/guild.proto`](tamagotchigo/guild/v1/guild.proto) | `tamagotchigo.guild.v1` | Guild | Monster Raid |
| [`tamagotchigo/tamagotchi/v1/tamagotchi.proto`](tamagotchigo/tamagotchi/v1/tamagotchi.proto) | `tamagotchigo.tamagotchi.v1` | Tamagotchi | Battle, Monster Raid |

## Using them in a service

1. Copy the files you need, with their directory structure, into your repository (for example
   under `proto/`). A service that calls others needs `broker/v1` and the protos of the services it
   calls; a service that serves gRPC needs its own; a subscriber needs `events/v1` and
   `broker/v1`.
2. Generate code in your build. Go: set the import path with `buf` managed mode
   (`go_package_prefix`) or `protoc --go_opt=M<file>=<import path>`; the protos carry no
   `go_package` because the import path belongs to the consuming repository. C#: `Grpc.Tools` with
   `<Protobuf Include=... GrpcServices="Server|Client" />`; `csharp_namespace` is set.
3. **Never edit a copy.** A change is made here first, in a PR the owners of the affected services
   review; every repository then copies the new version. CI in each repository may compare its
   copies with this folder.

## Conventions

| REST | Protobuf |
|---|---|
| camelCase field `userId` | snake_case field `user_id` (the JSON mapping turns it back into `userId`) |
| UUID string | `string` |
| UTC ISO 8601 timestamp | `google.protobuf.Timestamp` |
| enum string `FRIEND` | enum value `RELATIONSHIP_FRIEND`; the `_UNSPECIFIED` zero value is never sent |
| optional or nullable field, optional query parameter | `optional` |
| free-form JSON object (`healthStats`, `specialProperties`) | `google.protobuf.Struct` |
| integer amount (currency, XP, HP) | `int64` |
| page `{items, nextCursor}` | `repeated items` and `optional string next_cursor` |
| `ErrorResponse` with `code` | gRPC status plus `google.rpc.ErrorInfo` with `reason` = the code |

- Every RPC mirrors one REST operation, named in its comment: same fields, same authorization by
  the caller's verified service name, same error codes.
- Read operations carry `option idempotency_level = NO_SIDE_EFFECTS`: the broker may retry them on
  another instance. Commands are retried only with an `idempotency-key` header.
- Service names are the canonical service names in PascalCase, without a `Service` suffix, so a
  method path reads `/tamagotchigo.usermanagement.v1.UserManagement/GetUser`.
- Request and response messages are named `<Rpc>Request` and `<Rpc>Response`. The broker API is
  the deliberate exception: `Send`, `Publish` and `Deliver` share one `Message` envelope.

## Checking

CI runs `buf lint`, `buf format` and `buf build` on every change to this folder
([`proto.yml`](../../../.github/workflows/proto.yml)). The same checks locally:

```
docker run --rm -v "$PWD/docs/schemas/proto:/workspace" -w /workspace bufbuild/buf:1.50.0 lint
docker run --rm -v "$PWD/docs/schemas/proto:/workspace" -w /workspace bufbuild/buf:1.50.0 format -d --exit-code
docker run --rm -v "$PWD/docs/schemas/proto:/workspace" -w /workspace bufbuild/buf:1.50.0 build
```

From Git Bash on Windows, prefix the commands with `MSYS_NO_PATHCONV=1`.
