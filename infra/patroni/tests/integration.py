#!/usr/bin/env python3
"""Exercise real replication/failover only in an explicitly named test project.

Start the selected clusters first. No existing database volumes are deleted. This test
kills and restarts their primary and writes only infra_probe/analytics.infra_probe.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
CLUSTERS = ('broker', 'user-management', 'battle', 'monster-raid', 'guild', 'package-registry', 'tamagotchi', 'notification')
PROGRAM = '''
import os,sys,json,urllib.request
import psycopg2
p=json.load(sys.stdin)
if 'url' in p:
    with urllib.request.urlopen(p['url'],timeout=3) as r:
        b=r.read().decode(); print(json.dumps(json.loads(b) if p.get('json',True) else b))
else:
    role=p.get('role','application')
    u,pw=(os.environ['POSTGRES_USER'],os.environ['POSTGRES_PASSWORD']) if role=='application' else (role,os.environ[{'analytics_reader':'ANALYTICS_READER_PASSWORD','monitoring':'POSTGRES_EXPORTER_PASSWORD'}[role]])
    c=psycopg2.connect(host=p['host'],port=p.get('port',5432),dbname=os.environ['POSTGRES_DB'],user=u,password=pw,connect_timeout=2)
    c.autocommit=True
    try:
        with c.cursor() as q:
            q.execute(p['sql'],p.get('params'))
            print(json.dumps(q.fetchall() if q.description else [],default=str))
    finally: c.close()
'''


class Probe:
    def __init__(self, project):
        self.command = ['docker', 'compose', '-p', project]

    def compose(self, *args, data=None):
        result = subprocess.run(self.command + list(args), cwd=ROOT, input=data,
                                text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise RuntimeError(result.stderr[-1500:])
        return result.stdout

    def request(self, node, body):
        return json.loads(self.compose('exec', '-T', node, 'python', '-c', PROGRAM, data=json.dumps(body)))

    def sql(self, node, cluster, statement, params=None, port=5432, role='application'):
        return self.request(node, dict(host=cluster+'-db', sql=statement, params=params, port=port, role=role))

    def members(self, node):
        return self.request(node, {'url':'http://127.0.0.1:8008/cluster'})['members']


def wait(check, seconds=60):
    end = time.monotonic() + seconds
    last = None
    while time.monotonic() < end:
        try:
            result = check()
            if result:
                return result
        except (RuntimeError, KeyError, IndexError, ValueError) as error:
            last = error
        time.sleep(1)
    raise AssertionError('Timed out waiting for cluster state: ' + str(last))


def metric_value(metrics, name):
    match = re.search(r'^' + re.escape(name) + r'(?:\{[^\n]*\})? ([0-9.eE+-]+)$', metrics, re.MULTILINE)
    if not match:
        raise AssertionError('Missing metric: ' + name)
    return float(match.group(1))


def test_cluster(p, cluster):
    print('\nTesting ' + cluster, flush=True)
    first = cluster + '-db-1'
    members = p.members(first)
    leader = next(m['name'] for m in members if m['role'] == 'leader')
    replica = next(m['name'] for m in members if m['role'] == 'replica' and m['state'] == 'streaming')
    initial_timeline = next(m['timeline'] for m in members if m['name'] == leader)
    assert p.sql(replica, cluster, 'SELECT pg_is_in_recovery()') == [[False]]
    assert p.sql(replica, cluster, 'SELECT pg_is_in_recovery()', port=5433) == [[True]]
    print('PASS one leader, one streaming replica; :5432 writes, :5433 replica', flush=True)
    p.sql(replica, cluster, 'CREATE SCHEMA IF NOT EXISTS infra_probe; CREATE TABLE IF NOT EXISTS infra_probe.rows (id text PRIMARY KEY)')
    marker = str(uuid.uuid4())
    p.sql(replica, cluster, 'INSERT INTO infra_probe.rows VALUES (%s)', [marker])
    p.sql(replica, cluster, 'CREATE SCHEMA IF NOT EXISTS analytics; CREATE OR REPLACE VIEW analytics.infra_probe AS SELECT id FROM infra_probe.rows; GRANT USAGE ON SCHEMA analytics TO analytics_reader; GRANT SELECT ON analytics.infra_probe TO analytics_reader')
    wait(lambda: p.sql(replica, cluster, 'SELECT count(*) FROM analytics.infra_probe WHERE id=%s', [marker], port=5433, role='analytics_reader') == [[1]])
    assert p.sql(replica, cluster, 'SHOW transaction_read_only', role='analytics_reader') == [['on']]
    try:
        p.sql(replica, cluster, 'INSERT INTO infra_probe.rows VALUES (%s)', ['forbidden'], role='analytics_reader')
    except RuntimeError:
        pass
    else:
        raise AssertionError('analytics_reader could write application data')
    print('PASS analytics_reader can read the granted view and cannot write', flush=True)
    prepared = cluster in {'user-management', 'package-registry'}
    expected = '64' if prepared else '0'
    assert p.sql(replica, cluster, 'SHOW max_prepared_transactions') == [[expected]]
    gid = 'infra-' + str(uuid.uuid4())
    if prepared:
        p.sql(replica, cluster, 'BEGIN; INSERT INTO infra_probe.rows VALUES (%s); PREPARE TRANSACTION %s', [gid, gid])
    # Asynchronous replication can lose an unreceived commit. For this survival test,
    # explicitly wait until the standby has replayed the tested WAL before crashing.
    lsn = p.sql(replica, cluster, 'SELECT pg_current_wal_lsn()')[0][0]
    wait(lambda: p.request(replica, dict(host='127.0.0.1', sql='SELECT pg_last_wal_replay_lsn() >= %s::pg_lsn', params=[lsn])) == [[True]])
    p.compose('kill', '-s', 'SIGKILL', leader)
    started = time.monotonic()
    try:
        wait(lambda: p.sql(replica, cluster, 'SELECT pg_is_in_recovery()') == [[False]], seconds=45)
        elapsed = round(time.monotonic() - started, 2)
        assert p.sql(replica, cluster, 'SELECT count(*) FROM infra_probe.rows WHERE id=%s', [marker]) == [[1]]
        assert p.sql(replica, cluster, 'SELECT pg_is_in_recovery()', port=5433, role='analytics_reader') == [[False]]
        assert p.sql(replica, cluster, 'SHOW transaction_read_only', port=5433, role='analytics_reader') == [['on']]
        print('PASS crash failover through unchanged proxy in ' + str(elapsed) + ' s; read fallback works', flush=True)
        if prepared:
            assert p.sql(replica, cluster, 'SELECT count(*) FROM pg_prepared_xacts WHERE gid=%s', [gid]) == [[1]]
            metrics = p.request(replica, {'url':'http://'+cluster+'-db-exporter:9187/metrics', 'json':False})
            assert metric_value(metrics, 'pad_postgres_prepared_transactions_count') == 1
            assert metric_value(metrics, 'pad_postgres_prepared_transactions_oldest_age_seconds') > 0
            p.sql(replica, cluster, 'COMMIT PREPARED %s', [gid])
            assert p.sql(replica, cluster, 'SELECT count(*) FROM infra_probe.rows WHERE id=%s', [gid]) == [[1]]
            abort = 'infra-' + str(uuid.uuid4())
            p.sql(replica, cluster, 'BEGIN; INSERT INTO infra_probe.rows VALUES (%s); PREPARE TRANSACTION %s', [abort, abort])
            p.sql(replica, cluster, 'ROLLBACK PREPARED %s', [abort])
            assert p.sql(replica, cluster, 'SELECT count(*) FROM infra_probe.rows WHERE id=%s', [abort]) == [[0]]
            def prepared_resolved():
                metrics = p.request(replica, {'url':'http://'+cluster+'-db-exporter:9187/metrics', 'json':False})
                return (metric_value(metrics, 'pad_postgres_prepared_transactions_count') == 0
                        and metric_value(metrics, 'pad_postgres_prepared_transactions_oldest_age_seconds') == 0)
            wait(prepared_resolved)
            print('PASS replicated prepared transaction commits after failover; abort leaves no row', flush=True)
        else:
            metrics = p.request(replica, {'url':'http://'+cluster+'-db-exporter:9187/metrics', 'json':False})
            assert 'pad_postgres_prepared_transactions_count' in metrics
    finally:
        p.compose('start', leader)
    def rejoined():
        members = p.members(replica)
        return next((m for m in members if m['name'] == leader and m['role'] == 'replica' and m['state'] == 'streaming'), None)
    member = wait(rejoined, seconds=120)
    assert member['timeline'] > initial_timeline
    assert p.sql(replica, cluster, 'SELECT pg_is_in_recovery()', port=5433) == [[True]]
    p.sql(replica, cluster, 'INSERT INTO infra_probe.rows VALUES (%s)', [str(uuid.uuid4())])
    print('PASS former leader rejoined as streaming replica on timeline ' + str(member['timeline']), flush=True)
    return {'cluster':cluster, 'oldLeader':leader, 'newLeader':replica, 'failoverSeconds':elapsed, 'preparedTransactions':prepared}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True)
    parser.add_argument('--cluster', action='append', choices=CLUSTERS)
    args = parser.parse_args()
    if not args.project.startswith(('pad-patroni-test-', 'pad-lab5-ha')):
        parser.error('Use a dedicated pad-patroni-test-* or pad-lab5-ha* project, never an existing deployment.')
    p = Probe(args.project)
    results = [test_cluster(p, cluster) for cluster in (args.cluster or CLUSTERS)]
    print('\nPASS all requested replication scenarios\n' + json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
