"""Remote operator entry point. Read-only providers; no wallet operations."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import service as s,wallet_research as w
p=argparse.ArgumentParser();p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);args=p.parse_args()
if args.input:
    if args.input.stat().st_size>8_000_000:raise SystemExit('Research input exceeds the bound')
    cohort=json.loads(args.input.read_text());candidates=w.cycles(cohort);verified=[]
    final=int(s.rpc('eth_getBlockByNumber',['finalized',False])['number'],16)
    for candidate in candidates[:20]:
        try:
            row=w.verify(candidate,final);verified.append(row)
            print('Verified',row['wallet'],row['symbol'],row['pnlMON'],'MON',flush=True)
        except Exception as e:
            print('Excluded',candidate['wallet'],getattr(e,'code',type(e).__name__),flush=True)
    value=w.build(cohort,verified,s.now());w.save(value)
    if args.output:args.output.write_text(s.dump(value))
    print('Collected',len(value['wallets']),'wallets from',len(cohort),'markets',flush=True)
else:
    print(json.dumps(w.collect()))
