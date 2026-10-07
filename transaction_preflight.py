"""Read-only gas and native-balance checks before a human wallet prompt."""
import service as s

def funded(transaction,padding=120):
    tx=dict(transaction)
    if tx.get('chainId','0x8f')!='0x8f':raise s.Problem('Monad mainnet is required',409,'wrong_network')
    tx['chainId']='0x8f'
    value=int(tx.get('value','0x0'),16)
    balance=int(s.rpc('eth_getBalance',[tx['from'],'latest']),16)
    if balance<=value:raise s.Problem('Add MON to cover the transaction and network fee',409,'insufficient_gas')
    gas=(int(s.rpc('eth_estimateGas',[{k:v for k,v in tx.items() if k not in {'chainId','gas'}}]),16)*padding+99)//100
    price=int(s.rpc('eth_gasPrice',[]),16)
    if gas<=0 or price<=0:raise s.Problem('Network fee unavailable. Try again shortly.',503,'fee_unavailable')
    if balance<value+gas*price:raise s.Problem('Add MON to cover the transaction and network fee',409,'insufficient_gas')
    return {**tx,'gas':hex(gas)}
