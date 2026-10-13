"""Deterministic local market data for isolated tests; never imported in production."""
import os
assert os.environ.get('RALLY_TESTING') == '1'
import service as s
import market_universe as universe
import nadfun


def address(n):
    return '0x'+format(n, '040x')


def asset(n, **values):
    return dict(id=address(n), address=address(n), chainId=143, name='QA Token '+str(n),
                symbol='QA'+str(n), decimals=18, logoURI='/assets/MON.png', **values)


def dex(n, **values):
    item=asset(n)
    price=dict(price=1, volume=1000*n, liquidity=1000*n, change=n, fetchedAt=s.now())
    price.update(values)
    with universe.db() as db:
        db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',
                   (item['id'],s.dump(item),s.dump(price),s.now()))
    return {**item, **price}


def launch(n, **values):
    item=asset(n, nadfun=True, version='v2', phase='curve', graduated=False, block=100,
               price=.01, marketCap=100000, holders=100, progressBps=5000, referenceAt=s.now(),
               created=s.now()-n, locked=False, tradeSupported=True, quoteAsset=s.USDC)
    item.update(values)
    s.write('INSERT OR REPLACE INTO nad_tokens VALUES(?,?,?,?)', (item['id'],'v2',s.dump(item),s.now()))
    return item


def install():
    nadfun.initialize()
    for n in range(1,86):
        dex(n)
    launch(100)
    launch(101,phase='dex',graduated=True)
    launch(102,created=s.now()-1,holders=400,progressBps=9000)
    dex(101,volume=400000,liquidity=200000)
