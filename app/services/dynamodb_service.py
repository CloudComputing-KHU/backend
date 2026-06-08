import os
from decimal import Decimal

import boto3
from dotenv import load_dotenv

load_dotenv()


def _convert_decimals(obj):
    if isinstance(obj, dict):
        return {k: _convert_decimals(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_convert_decimals(v) for v in obj]
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    return obj


def _strip_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def _build_update_expr(updates: dict) -> tuple[str, dict, dict]:
    parts, names, values = [], {}, {}
    for i, (key, value) in enumerate(updates.items()):
        ph_name = f"#k{i}"
        ph_val = f":v{i}"
        names[ph_name] = key
        values[ph_val] = value
        parts.append(f"{ph_name} = {ph_val}")
    return "SET " + ", ".join(parts), names, values


class DynamoDBService:
    def __init__(self):
        self._resource = None

    def _get_resource(self):
        if self._resource is None:
            self._resource = boto3.resource(
                "dynamodb",
                region_name=os.getenv("DYNAMODB_REGION", os.getenv("AWS_REGION", "ap-northeast-2")),
            )
        return self._resource

    def is_configured(self) -> bool:
        return bool(os.getenv("AWS_REGION") or os.getenv("DYNAMODB_REGION"))

    def table(self, name: str):
        return self._get_resource().Table(name)


dynamodb_service = DynamoDBService()
