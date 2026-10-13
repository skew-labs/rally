"""Finalized graduation dates, separate from token creation and quote refreshes."""
import json
import service as s


def initialize():
    with s.connection() as db:
        db.execute('CREATE TABLE IF NOT EXISTS nad_graduations(address TEXT PRIMARY KEY,version TEXT NOT NULL,block INTEGER NOT NULL,block_hash TEXT NOT NULL,stamp INTEGER NOT NULL,tx TEXT NOT NULL)')


def record(version, item, log, header):
    """Called only for logs inside the finalized index range; verify block identity."""
    import nadfun as n
    if item.get('name') not in {'Graduate', 'CurveGraduate'} or log.get('removed'):
        return False
    token = n.address(item['fields'].get('token'))
    block = int(log['blockNumber'], 16)
    if (str(log.get('address','')).lower() != n.contract(version,'curve').lower()
            or int(header['number'],16) != block
            or header['hash'].lower() != log['blockHash'].lower()):
        raise s.Problem('Graduation block identity mismatch',502,'graduation_identity')
    stamp = int(header['timestamp'],16)
    if not 0 < stamp <= s.now():
        raise s.Problem('Invalid graduation timestamp',502,'graduation_time')
    with s.connection() as db:
        db.execute('INSERT INTO nad_graduations VALUES(?,?,?,?,?,?) ON CONFLICT(address) DO UPDATE SET version=excluded.version,block=excluded.block,block_hash=excluded.block_hash,stamp=excluded.stamp,tx=excluded.tx WHERE excluded.block<=nad_graduations.block',
                   (token,version,block,header['hash'],stamp,log['transactionHash']))
    return True


def replay(limit=16):
    """Backfill timestamps for already indexed events without rescanning the chain."""
    import nadfun as n
    rows=s.rows("SELECT e.* FROM nad_events e LEFT JOIN nad_graduations g ON g.address=lower(json_extract(e.fields,'$.token')) WHERE e.name IN ('Graduate','CurveGraduate') AND g.address IS NULL ORDER BY e.block DESC LIMIT ?",(limit,))
    for e in rows:
        header=s.rpc('eth_getBlockByNumber',[hex(e['block']),False])
        record(e['version'],{'name':e['name'],'fields':json.loads(e['fields'])},
               {'address':n.contract(e['version'],'curve'),'blockNumber':hex(e['block']),'blockHash':e['block_hash'],'transactionHash':e['tx']},header)
    return len(rows)


def fields(row):
    if not row['graduation_stamp']:
        return {}
    return {'graduatedAt':row['graduation_stamp'],'graduatedBlock':row['graduation_block'],
            'graduationTx':row['graduation_tx'],'graduationSource':'nad.fun finalized event'}
