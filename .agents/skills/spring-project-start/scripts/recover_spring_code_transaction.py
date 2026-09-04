#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from apply_approved_spring_code import recover_transaction
def main()->int:
    parser=argparse.ArgumentParser(); parser.add_argument("--target",required=True,type=Path); parser.add_argument("--transaction-id",required=True); args=parser.parse_args()
    try: result=recover_transaction(args.target,args.transaction_id)
    except (OSError,ValueError) as error: print(f"SPRING_CODE_RECOVERY_VALID: no\nERROR: {error}",file=sys.stderr); return 1
    json.dump(result,sys.stdout,ensure_ascii=False,indent=2); print(); print("SPRING_CODE_RECOVERY_VALID: yes",file=sys.stderr); return 0
if __name__=="__main__": sys.exit(main())
