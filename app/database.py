import os
from decimal import Decimal
from typing import Any, Dict, List, Optional
import asyncio

import boto3
from boto3.dynamodb.conditions import Attr, Key
from dotenv import load_dotenv

load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "ap-south-1")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")

_dynamodb_resource = None
_dynamodb_client = None

TABLE_NAMES = {
    "users": os.getenv("DYNAMODB_USERS_TABLE", "users"),
    "collections": os.getenv("DYNAMODB_COLLECTIONS_TABLE", "collections"),
    "scrape_jobs": os.getenv("DYNAMODB_SCRAPE_JOBS_TABLE", "scrape_jobs"),
    "chunk_question": os.getenv("DYNAMODB_CHUNK_QUESTION_TABLE", "chunk_question"),
    "learning_node_summaries": os.getenv("DYNAMODB_LEARNING_NODE_SUMMARIES_TABLE", "learning_node_summaries"),
    "quiz_sessions": os.getenv("DYNAMODB_QUIZ_SESSIONS_TABLE", "quiz_sessions"),
}


def _session_kwargs() -> Dict[str, str]:
    kwargs: Dict[str, str] = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY
    if AWS_SESSION_TOKEN:
        kwargs["aws_session_token"] = AWS_SESSION_TOKEN
    return kwargs


def get_dynamodb_resource():
    global _dynamodb_resource
    if _dynamodb_resource is None:
        _dynamodb_resource = boto3.resource("dynamodb", **_session_kwargs())
    return _dynamodb_resource


def get_dynamodb_client():
    global _dynamodb_client
    if _dynamodb_client is None:
        _dynamodb_client = boto3.client("dynamodb", **_session_kwargs())
    return _dynamodb_client


async def connect_to_dynamodb():
    await asyncio.to_thread(get_dynamodb_client().list_tables, Limit=1)
    print("Connected to DynamoDB")


async def close_dynamodb_connection():
    print("DynamoDB connection closed")


def get_table(name: str):
    table_name = TABLE_NAMES.get(name, name)
    return get_dynamodb_resource().Table(table_name)


def serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialize_value(v) for v in value]
    return value


def serialize_item(item: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if item is None:
        return None
    serialized = serialize_value(item)
    if isinstance(serialized, dict):
        if "PK" in serialized and "id" not in serialized:
            serialized["id"] = serialized["PK"]
    return serialized


def serialize_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [serialize_item(item) for item in items]


def scan_table(
    table_name: str,
    filter_expression=None,
    limit: Optional[int] = None,
    index_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    table = get_table(table_name)
    scan_kwargs: Dict[str, Any] = {}
    if filter_expression is not None:
        scan_kwargs["FilterExpression"] = filter_expression
    if index_name:
        scan_kwargs["IndexName"] = index_name

    items: List[Dict[str, Any]] = []
    while True:
        response = table.scan(**scan_kwargs)
        items.extend(response.get("Items", []))
        if limit is not None and len(items) >= limit:
            return serialize_items(items[:limit])
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key
    return serialize_items(items)


def query_table(
    table_name: str,
    key_expression,
    index_name: Optional[str] = None,
    limit: Optional[int] = None,
    scan_forward: bool = True,
) -> List[Dict[str, Any]]:
    table = get_table(table_name)
    query_kwargs: Dict[str, Any] = {
        "KeyConditionExpression": key_expression,
        "ScanIndexForward": scan_forward,
    }
    if index_name:
        query_kwargs["IndexName"] = index_name
    if limit is not None:
        query_kwargs["Limit"] = limit

    items: List[Dict[str, Any]] = []
    while True:
        response = table.query(**query_kwargs)
        items.extend(response.get("Items", []))
        if limit is not None and len(items) >= limit:
            return serialize_items(items[:limit])
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        query_kwargs["ExclusiveStartKey"] = last_key
    return serialize_items(items)


def get_by_id(table_name: str, item_id: str) -> Optional[Dict[str, Any]]:
    table = get_table(table_name)
    response = table.get_item(Key={"PK": item_id})
    return serialize_item(response.get("Item"))


def put_item(table_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
    table = get_table(table_name)
    table.put_item(Item=item)
    return item


def delete_item(table_name: str, key: Dict[str, Any]) -> bool:
    table = get_table(table_name)
    response = table.delete_item(Key=key, ReturnValues="ALL_OLD")
    return "Attributes" in response


def update_item(table_name: str, key: Dict[str, Any], updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not updates:
        table = get_table(table_name)
        response = table.get_item(Key=key)
        return serialize_item(response.get("Item"))

    table = get_table(table_name)
    names: Dict[str, str] = {}
    values: Dict[str, Any] = {}
    expressions = []

    for index, (field, value) in enumerate(updates.items(), start=1):
        name_key = f"#f{index}"
        value_key = f":v{index}"
        names[name_key] = field
        values[value_key] = value
        expressions.append(f"{name_key} = {value_key}")

    response = table.update_item(
        Key=key,
        UpdateExpression="SET " + ", ".join(expressions),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return serialize_item(response.get("Attributes"))


def append_to_list(table_name: str, key: Dict[str, Any], field: str, value: Any, extra_updates: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    table = get_table(table_name)
    expression_names = {"#field": field}
    expression_values: Dict[str, Any] = {":empty": [], ":value": [value]}
    set_parts = ["#field = list_append(if_not_exists(#field, :empty), :value)"]

    if extra_updates:
        for index, (name, item_value) in enumerate(extra_updates.items(), start=1):
            name_key = f"#u{index}"
            value_key = f":u{index}"
            expression_names[name_key] = name
            expression_values[value_key] = item_value
            set_parts.append(f"{name_key} = {value_key}")

    response = table.update_item(
        Key=key,
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=expression_names,
        ExpressionAttributeValues=expression_values,
        ReturnValues="ALL_NEW",
    )
    return serialize_item(response.get("Attributes"))


def get_scan_attr(name: str):
    return Attr(name)


def get_query_key(name: str):
    return Key(name)
