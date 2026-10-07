"""Deployment identities shared by the additional wallet-owned venue adapters."""
import json
import service as s
from venues import IMPL_SLOT

ROOT=s.ROOT/'config/venue-pins.json'

def pin(venue,block='latest'):
    manifest=json.loads(ROOT.read_text());expected=manifest['venues'][venue];current={}
    if manifest['chainId']!=143 or int(s.rpc('eth_chainId',[]),16)!=143:raise s.Problem('Wrong venue network',503,'venue_contract_changed')
    for label,p in expected.items():
        address=p['address'];code=s.rpc('eth_getCode',[address,block]);implementation='0x'+s.rpc('eth_getStorageAt',[address,IMPL_SLOT,block])[-40:].lower()
        value={'address':address,'codeHash':s.digest(code.lower()),'implementation':implementation,'implementationHash':s.digest(s.rpc('eth_getCode',[implementation,block]).lower()) if implementation!=s.ZERO else None}
        if value!=p:raise s.Problem('Venue deployment changed. Review required.',503,'venue_contract_changed')
        current[label]=value
    return current
