// Structural/script regression checks; no HTTP requests or real credentials.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");
const root = path.resolve(__dirname, "..");
const flatten = items => items.flatMap(item => item.item ? flatten(item.item) : [item]);
const collections = Object.fromEntries(["guild", "package-registry"].map(name => [
  name, JSON.parse(fs.readFileSync(path.join(root, "collections", name + "-service.postman_collection.json")))
]));

for (const [name, collection] of Object.entries(collections)) {
  test(name + ": variables and trusted identity", () => {
    const keys = collection.variable.map(variable => variable.key);
    assert.equal(new Set(keys).size, keys.length);
    assert(keys.includes("gatewayUrl"));
    for (const variable of collection.variable) {
      if (/Password|Secret|Token|Ticket/.test(variable.key)) assert.equal(variable.value, "");
    }
    for (const item of flatten(collection.item)) {
      assert.equal(typeof item.request.url, "string", item.name);
      assert(item.request.url.startsWith("{{"), item.name);
      for (const header of item.request.header || []) {
        assert(!/^x-(caller-kind|user-id|service-name|user-role|scopes)$/i.test(header.key), item.name);
      }
      assert(["bearer", "noauth"].includes(item.request.auth.type), item.name);
    }
  });

  test(name + ": scripts run twice in a shared context and capture IDs", () => {
    const variables = new Map();
    const subject = "11111111-1111-4111-8111-111111111111";
    const token = "fixture." + Buffer.from(JSON.stringify({ sub: subject })).toString("base64url") + ".fixture";
    const body = { accessToken: token, access_token: token, guildId: subject,
      invitationId: subject, packageId: subject, raidConfigurationId: subject,
      scheduleId: subject, ticket: "a".repeat(43), url: "ws://localhost/fixture" };
    const pm = {
      test: (_name, fn) => fn(),
      expect: value => ({ to: { match: regex => assert(regex.test(value)) } }),
      response: { code: 200, json: () => body, to: { have: {
        status: code => assert.equal(pm.response.code, code)
      } } },
      collectionVariables: { set: (key, value) => variables.set(key, value) },
      variables: { set: (key, value) => variables.set(key, value) }
    };
    const context = vm.createContext({ pm, atob });
    for (let iteration = 0; iteration < 2; iteration++) {
      for (const item of flatten(collection.item)) {
        for (const event of item.event || []) {
          const source = event.script.exec.join("\n");
          pm.response.code = Number(source.match(/\.status\((\d+)\)/)?.[1] || 200);
          new vm.Script(source, { filename: item.name }).runInContext(context, { timeout: 1000 });
        }
      }
    }
    for (const key of name === "guild" ? ["ownerUserId", "inviteeUserId", "guildId", "invitationId"]
      : ["adminUserId", "developerUserId", "moderatorUserId", "registeredUserId", "packageId", "raidConfigurationId", "scheduleId"]) {
      assert.equal(variables.get(key), subject, key);
    }
    if (name === "guild") assert.equal(variables.get("chatTicket"), body.ticket);
    else for (const client of ["guild", "tamagotchi", "battle", "monsterRaid"]) {
      assert.equal(variables.get(client + "ServiceToken"), token, client);
    }
  });
}

test("Registry requests use operation-specific identities", () => {
  const requests = new Map(flatten(collections["package-registry"].item).map(item => [item.name, item.request]));
  const expected = {
    "Get package registration": "guildServiceToken",
    "Get stat definitions": "tamagotchiServiceToken",
    "Get battle boosts": "battleServiceToken",
    "Get battle boost by key": "battleServiceToken",
    "List raid schedules": "monsterRaidServiceToken",
    "Get raid schedule": "monsterRaidServiceToken",
    "Register user for package": "registeredAccessToken",
    "List user's packages through User Management": "registeredAccessToken"
  };
  for (const [name, token] of Object.entries(expected)) {
    assert.equal(requests.get(name).auth.bearer[0].value, "{{" + token + "}}", name);
  }
  assert.equal(requests.get("Register user for package").method, "PUT");
  for (const name of ["Register user for package", "List user's packages through User Management"]) {
    assert(requests.get(name).url.startsWith("{{gatewayUrl}}/user-management/"), name);
  }
});
