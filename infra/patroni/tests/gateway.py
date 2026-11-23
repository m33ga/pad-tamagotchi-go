#!/usr/bin/env python3
"""Prove live Guild/Registry processes reconnect after their database primary dies.

Run only against a fresh, fully started, isolated Compose project. Creates one test
account and new probe resources using the public API; credentials stay in memory.
"""
import argparse
import json
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from integration import Probe, wait


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--gateway-url', required=True)
    args = parser.parse_args()
    if not args.project.startswith(('pad-patroni-test-', 'pad-lab5-ha')):
        parser.error('Use a dedicated test project, never an existing deployment.')
    if urllib.parse.urlparse(args.gateway_url).hostname not in {'127.0.0.1', 'localhost'}:
        parser.error('The demonstration gateway must be on localhost.')
    p = Probe(args.project)
    token = None

    # Liveness can turn green before background registration/catalogue refresh.
    def registered():
        pools = p.request('guild-db-1', {'url': 'http://broker:8080/status'})['pools']
        return all(len([i for i in pools.get(service, [])
                        if i['listed'] and i['local'] == 'ACTIVE' and i['reported'] in {'UP', 'DEGRADED'}]) >= 2
                   for service in ('user-management', 'package-registry', 'guild'))
    wait(registered, seconds=90)

    def api(method, path, body=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request(args.gateway_url.rstrip('/') + path,
                                         data=json.dumps(body).encode() if body is not None else None,
                                         method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('Gateway ' + path + ' returned ' + str(error.code)) from None
        except (urllib.error.URLError, TimeoutError) as error:
            raise RuntimeError('Gateway connection not ready: ' + str(error)) from None

    suffix = uuid.uuid4().hex[:12]
    password = secrets.token_urlsafe(24)
    email = 'ha-' + suffix + '@example.test'
    user = api('POST', '/user-management/api/v1/users',
               {'username': 'ha-' + suffix, 'email': email, 'password': password})
    def authenticate():
        nonlocal token
        token = None
        token = api('POST', '/user-management/api/v1/auth/sessions',
                    {'email': email, 'password': password})['accessToken']
    authenticate()

    for cluster, services, path, key, body in (
        ('guild', ['guild-api-1', 'guild-api-2'], '/guild/api/v1/guilds', 'guildId',
         {'name': 'HA-' + suffix, 'description': 'Failover probe', 'requiredPackageId': None}),
        ('package-registry', ['package-registry-api'], '/package-registry/api/v1/packages', 'packageId',
         {'name': 'HA-' + suffix, 'version': '1.0.0', 'description': 'Failover probe', 'developerIds': [user['userId']]}),
    ):
        created = api('POST', path, body)
        resource = path + '/' + created[key]
        assert api('GET', resource)[key] == created[key]
        container_ids = p.compose('ps', '-q', *services).split()
        def restarts():
            return subprocess.check_output(['docker', 'inspect', '--format', '{{.RestartCount}}'] + container_ids, text=True)
        before = restarts()
        members = p.members(cluster + '-db-1')
        leader = next(m['name'] for m in members if m['role'] == 'leader')
        replica = next(m['name'] for m in members if m['role'] == 'replica')
        p.compose('kill', '-s', 'SIGKILL', leader)
        started = time.monotonic()
        try:
            wait(lambda: p.sql(replica, cluster, 'SELECT pg_is_in_recovery()') == [[False]], seconds=45)
            # Test DB recovery with a current session even after a suspended/slow demo.
            authenticate()
            wait(lambda: api('GET', resource).get(key) == created[key], seconds=60)
            body['name'] += '-after'
            assert api('POST', path, body)[key]
            assert p.compose('ps', '-q', *services).split() == container_ids
            assert restarts() == before
            print('PASS ' + cluster + ': gateway reads and writes recover in ' +
                  str(round(time.monotonic() - started, 2)) + ' s; application containers did not restart', flush=True)
        finally:
            p.compose('start', leader)
        wait(lambda: any(m['name'] == leader and m['role'] == 'replica' and m['state'] == 'streaming'
                         for m in p.members(replica)), seconds=120)


if __name__ == '__main__':
    main()
