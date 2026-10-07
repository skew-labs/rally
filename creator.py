"""Read-only creator earnings from finalized Rally payment records.

Amounts use the allocation captured by each invoice, never today's policy.
Pool/vault observations are separate from period-filtered payment receipts.
"""
import json
from eth_abi import decode
from eth_abi.exceptions import DecodingError
from eth_utils import keccak
import service as s
import settlement
import community_tokens as ct

PERIODS={'24h':86400,'7d':7*86400,'30d':30*86400,'all':None}
BUYBACK_TOPIC='0x'+keccak(text='BuybackExecuted(uint256,uint256,uint256,uint256)').hex()

def overview(who,period='all'):
    user=s.require(who,human=True)
    if period not in PERIODS:raise s.Problem('Choose 24h, 7d, 30d or all')
    now=s.now();start=now-PERIODS[period] if PERIODS[period] else 0
    token=ct.public(user)
    totals={'grossRaw':0,'creatorRaw':0,'reservedRaw':0,'payments':0}
    payments=[];buybacks=[];seen=set()
    # One snapshot prevents the totals and the visible receipts disagreeing.
    with s.connection() as db:
        rows=db.execute("""SELECT i.id,i.feed,f.name feedName,i.amount_raw,i.recipient,
            i.tx,i.settled,i.community_terms,i.receipt
            FROM invoices i JOIN feeds f ON f.id=i.feed
            WHERE f.owner=? AND i.state='paid' AND i.settled>=? AND i.settled<=?
            ORDER BY i.settled DESC,i.id DESC""",(user,start,now))
        for item in rows:
            row=dict(item);terms=settlement.terms(row);gross=int(row['amount_raw'])
            reserved=gross*terms['buybackBps']//10000 if terms else 0
            totals['grossRaw']+=gross;totals['creatorRaw']+=gross-reserved
            totals['reservedRaw']+=reserved;totals['payments']+=1
            if len(payments)<50:
                payments.append({'id':row['id'],'feed':row['feed'],'feedName':row['feedName'],
                    'grossRaw':str(gross),'creatorRaw':str(gross-reserved),'reservedRaw':str(reserved),
                    'tx':row['tx'],'recordedAt':row['settled'],'state':'finalized',
                    'creatorRecipient':terms['creator'] if terms else row['recipient'],
                    'buybackBps':terms['buybackBps'] if terms else 0})
            # Only exact vault events from receipts already finalized by settlement.
            # This is payment-linked activity, not a claim to index all keeper calls.
            receipt=json.loads(row['receipt'] or '{}')
            for log in receipt.get('logs',[]):
                ident=(row['tx'],log.get('logIndex'))
                if not terms or ident in seen or log.get('removed') or log.get('address','').lower()!=terms['vault'] or log.get('topics')!=[BUYBACK_TOPIC]:continue
                try:
                    quote,bought,burned,treasury=decode(['uint256']*4,bytes.fromhex(log['data'][2:]))
                    if burned+treasury!=bought:continue
                except (ValueError,KeyError,OverflowError,DecodingError):continue
                seen.add(ident)
                if len(buybacks)<50:buybacks.append({'id':row['tx']+':'+str(log.get('logIndex')),
                    'tx':row['tx'],'quoteRaw':str(quote),'boughtRaw':str(bought),'burnedRaw':str(burned),
                    'treasuryRaw':str(treasury),'recordedAt':row['settled'],'state':'finalized','token':terms['communityToken'],'burnMethod':terms.get('burnMethod','supply_burn')})
    return {'period':period,'from':start or None,'fetchedAt':now,
        'totals':{k:str(v) if k.endswith('Raw') else v for k,v in totals.items()},
        'payments':payments,'buybacks':buybacks,'hasMorePayments':totals['payments']>len(payments),
        'token':token,'coverage':'Finalized Rally feed payments. Periods use receipt recording time. Buyback activity includes payment-linked events only.'}
