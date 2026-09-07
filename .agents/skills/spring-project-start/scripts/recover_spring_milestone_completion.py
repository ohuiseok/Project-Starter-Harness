#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from complete_spring_milestone import recover

def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--target",required=True,type=Path); parser.add_argument("--transaction-id",required=True); args=parser.parse_args()
    try: result=recover(args.target.resolve(strict=True),args.transaction_id)
    except (OSError,ValueError,KeyError,TypeError) as error: print(f"SPRING_MILESTONE_RECOVERY_VALID: no\nERROR: {error}",file=sys.stderr); return 1
    print(json.dumps({"transactionId":result["transactionId"],"state":result["state"]},ensure_ascii=False)); print("SPRING_MILESTONE_RECOVERY_VALID: yes",file=sys.stderr); return 0
if __name__=="__main__": sys.exit(main())
