#!/usr/bin/env python3
"""Normalize and compare an approved PostgreSQL physical model with catalogs."""

from __future__ import annotations

import hashlib
import json
import re


TYPE_MAP = {"UUID": "uuid", "TEXT": "text", "BOOLEAN": "boolean", "DATE": "date", "TIME": "time without time zone", "TIMESTAMP WITH TIME ZONE": "timestamp with time zone", "TIMESTAMP WITHOUT TIME ZONE": "timestamp without time zone", "INTEGER": "integer", "BIGINT": "bigint", "SMALLINT": "smallint", "BYTEA": "bytea", "JSONB": "jsonb"}
ACTION = {"a": "NO_ACTION", "r": "RESTRICT", "c": "CASCADE", "n": "SET_NULL", "d": "SET_DEFAULT"}


def sql_type(value: str) -> str:
    if value.startswith("VARCHAR("): return f"character varying({value[8:-1]})"
    if value.startswith("NUMERIC("): return f"numeric({value[8:-1]})"
    return TYPE_MAP[value]


def expression(value: str | None) -> str | None:
    if value is None: return None
    value = re.sub(r"::[a-zA-Z0-9_ ]+(?:\([0-9, ]+\))?", "", value.lower())
    value = re.sub(r"\s", "", value)
    while value.startswith("(") and value.endswith(")"):
        depth = 0; wraps = True
        for index, character in enumerate(value):
            depth += 1 if character == "(" else -1 if character == ")" else 0
            if depth == 0 and index != len(value) - 1: wraps = False; break
        if not wraps: break
        value = value[1:-1]
    return value


def expected(physical: dict) -> dict:
    tables = {}
    by_id = {table["tableId"]: table for table in physical["tables"]}
    for table in physical["tables"]:
        columns = {column["columnId"]: column for column in table["columns"]}
        unique = sorted([[column["name"]] for column in table["columns"] if column["unique"]])
        foreign_keys = {}
        for item in table["foreignKeys"]:
            target = by_id[item["referencedTableId"]]; target_columns = {column["columnId"]: column for column in target["columns"]}
            foreign_keys[item["name"]] = {"columns": [columns[column]["name"] for column in item["columnIds"]], "referencedTable": target["name"], "referencedColumns": [target_columns[column]["name"] for column in item["referencedColumnIds"]], "onDelete": item["onDelete"], "onUpdate": item["onUpdate"]}
        tables[table["name"]] = {
            "columns": {column["name"]: {"type": sql_type(column["sqlType"]), "nullable": column["nullable"], "default": expression(column["defaultExpression"])} for column in table["columns"]},
            "primaryKey": {"name": table["primaryKey"]["name"], "columns": [columns[item]["name"] for item in table["primaryKey"]["columnIds"]]},
            "uniqueColumns": unique,
            "foreignKeys": foreign_keys,
            "checks": {item["name"]: expression(item["expression"]) for item in table["checkConstraints"]},
            "indexes": {item["name"]: {"columns": [columns[column]["name"] for column in item["columnIds"]], "unique": item["unique"]} for item in table["indexes"]},
        }
    return {"schema": physical["database"]["schemaName"], "tables": tables}


def catalog_query(schema: str) -> str:
    return f"""WITH rel AS (SELECT c.oid,c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='{schema}' AND c.relkind IN ('r','p') AND c.relname<>'flyway_schema_history') SELECT json_build_object('tables',(SELECT COALESCE(json_agg(json_build_object('name',relname) ORDER BY relname),'[]'::json) FROM rel),'columns',(SELECT COALESCE(json_agg(json_build_object('table',r.relname,'name',a.attname,'type',format_type(a.atttypid,a.atttypmod),'nullable',NOT a.attnotnull,'default',pg_get_expr(d.adbin,d.adrelid)) ORDER BY r.relname,a.attnum),'[]'::json) FROM rel r JOIN pg_attribute a ON a.attrelid=r.oid AND a.attnum>0 AND NOT a.attisdropped LEFT JOIN pg_attrdef d ON d.adrelid=r.oid AND d.adnum=a.attnum),'constraints',(SELECT COALESCE(json_agg(json_build_object('table',r.relname,'name',con.conname,'type',con.contype,'columns',(SELECT json_agg(a.attname ORDER BY u.ord) FROM unnest(con.conkey) WITH ORDINALITY u(attnum,ord) JOIN pg_attribute a ON a.attrelid=con.conrelid AND a.attnum=u.attnum),'referencedTable',rr.relname,'referencedColumns',(SELECT json_agg(a.attname ORDER BY u.ord) FROM unnest(con.confkey) WITH ORDINALITY u(attnum,ord) JOIN pg_attribute a ON a.attrelid=con.confrelid AND a.attnum=u.attnum),'onDelete',con.confdeltype,'onUpdate',con.confupdtype,'definition',pg_get_constraintdef(con.oid,true)) ORDER BY r.relname,con.conname),'[]'::json) FROM pg_constraint con JOIN rel r ON r.oid=con.conrelid LEFT JOIN pg_class rr ON rr.oid=con.confrelid WHERE con.contype IN ('p','u','f','c')),'indexes',(SELECT COALESCE(json_agg(json_build_object('table',r.relname,'name',ci.relname,'unique',i.indisunique,'columns',(SELECT json_agg(pg_get_indexdef(i.indexrelid,k,true) ORDER BY k) FROM generate_series(1,i.indnkeyatts) k)) ORDER BY r.relname,ci.relname),'[]'::json) FROM pg_index i JOIN rel r ON r.oid=i.indrelid JOIN pg_class ci ON ci.oid=i.indexrelid WHERE NOT i.indisprimary AND NOT EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid=i.indexrelid)))::text;"""


def actual(document: dict, schema: str) -> dict:
    tables = {item["name"]: {"columns": {}, "primaryKey": None, "uniqueColumns": [], "foreignKeys": {}, "checks": {}, "indexes": {}} for item in document.get("tables", [])}
    for item in document.get("columns", []): tables[item["table"]]["columns"][item["name"]] = {"type": item["type"], "nullable": item["nullable"], "default": expression(item["default"])}
    for item in document.get("constraints", []):
        table = tables[item["table"]]
        if item["type"] == "p": table["primaryKey"] = {"name": item["name"], "columns": item["columns"]}
        elif item["type"] == "u": table["uniqueColumns"].append(item["columns"])
        elif item["type"] == "f": table["foreignKeys"][item["name"]] = {"columns": item["columns"], "referencedTable": item["referencedTable"], "referencedColumns": item["referencedColumns"], "onDelete": ACTION[item["onDelete"]], "onUpdate": ACTION[item["onUpdate"]]}
        elif item["type"] == "c": table["checks"][item["name"]] = expression(re.sub(r"^CHECK\s*", "", item["definition"], flags=re.I))
    for table in tables.values(): table["uniqueColumns"].sort()
    for item in document.get("indexes", []): tables[item["table"]]["indexes"][item["name"]] = {"columns": item["columns"], "unique": item["unique"]}
    return {"schema": schema, "tables": tables}


def fingerprint(document: dict) -> str: return hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def differences(expected_schema: dict, actual_schema: dict) -> list[dict]:
    result = []
    def walk(path: str, wanted, observed):
        if isinstance(wanted, dict) and isinstance(observed, dict):
            for key in sorted(set(wanted) | set(observed)): walk(f"{path}.{key}" if path else key, wanted.get(key, "<MISSING>"), observed.get(key, "<MISSING>"))
        elif wanted != observed: result.append({"path": path, "expected": wanted, "actual": observed})
    walk("", expected_schema, actual_schema)
    return result
