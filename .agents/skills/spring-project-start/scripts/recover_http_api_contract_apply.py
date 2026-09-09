#!/usr/bin/env python3
"""Recover an interrupted create-only HTTP API contract transaction."""
from __future__ import annotations
import argparse,sys
from pathlib import Path
from apply_approved_http_api_contract import recover
from prepare_http_api_contract_handoff import argument_path
def main()->int:
 p=argparse.ArgumentParser(); p.add_argument("--transaction",required=True,type=Path); p.add_argument("--target",required=True,type=Path); a=p.parse_args()
 try:
  root=a.target.resolve(strict=True); recover(root,argument_path(root,a.transaction,"transaction"))
 except (OSError,ValueError,KeyError,TypeError) as e: print(f"HTTP_API_CONTRACT_RECOVERED: no\nERROR: {e}"); return 1
 print("HTTP_API_CONTRACT_RECOVERED: yes"); return 0
if __name__=="__main__":sys.exit(main())
