"""
DynamoDB 테이블 생성 스크립트
실행: uv run python scripts/create_dynamodb_tables.py
"""

import os
import sys
import boto3
import time
from dotenv import load_dotenv

load_dotenv()

REGION = os.getenv("DYNAMODB_REGION", os.getenv("AWS_REGION", "us-east-1"))

client = boto3.client("dynamodb", region_name=REGION)

TABLES = [
    {
        "TableName": "user_profiles",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "email-index",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    {
        "TableName": "family_invites",
        "KeySchema": [
            {"AttributeName": "child_user_id", "KeyType": "HASH"},
            {"AttributeName": "created_at", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "child_user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
            {"AttributeName": "invite_code", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "invite-code-index",
                "KeySchema": [
                    {"AttributeName": "invite_code", "KeyType": "HASH"},
                    {"AttributeName": "status", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    {
        "TableName": "family_links",
        "KeySchema": [
            {"AttributeName": "link_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "link_id", "AttributeType": "S"},
            {"AttributeName": "parent_user_id", "AttributeType": "S"},
            {"AttributeName": "child_user_id", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "parent-index",
                "KeySchema": [
                    {"AttributeName": "parent_user_id", "KeyType": "HASH"},
                    {"AttributeName": "status", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "child-index",
                "KeySchema": [
                    {"AttributeName": "child_user_id", "KeyType": "HASH"},
                    {"AttributeName": "status", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    {
        "TableName": "photos",
        "KeySchema": [
            {"AttributeName": "photo_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "photo_id", "AttributeType": "S"},
            {"AttributeName": "sender_user_id", "AttributeType": "S"},
            {"AttributeName": "receiver_user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
            {"AttributeName": "status", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "sender-index",
                "KeySchema": [
                    {"AttributeName": "sender_user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "receiver-index",
                "KeySchema": [
                    {"AttributeName": "receiver_user_id", "KeyType": "HASH"},
                    {"AttributeName": "status", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    {
        "TableName": "photo_reactions",
        "KeySchema": [
            {"AttributeName": "photo_id", "KeyType": "HASH"},
            {"AttributeName": "reaction_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "photo_id", "AttributeType": "S"},
            {"AttributeName": "reaction_id", "AttributeType": "S"},
        ],
    },
    {
        "TableName": "answers",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "answer_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "answer_id", "AttributeType": "S"},
            {"AttributeName": "type_date", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "answer-type-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "type_date", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    {
        "TableName": "dementia_assessments",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "analysis_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "analysis_id", "AttributeType": "S"},
        ],
    },
    {
        "TableName": "device_tokens",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
    },
    {
        "TableName": "notifications",
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "notification_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "notification_id", "AttributeType": "S"},
        ],
    },
]


def create_tables():
    print(f"리전: {REGION}\n")

    existing = client.list_tables()["TableNames"]
    created = []

    for table_def in TABLES:
        name = table_def["TableName"]
        if name in existing:
            print(f"[SKIP] {name} - 이미 존재")
            continue

        params = {
            "TableName": name,
            "KeySchema": table_def["KeySchema"],
            "AttributeDefinitions": table_def["AttributeDefinitions"],
            "BillingMode": "PAY_PER_REQUEST",
            "DeletionProtectionEnabled": True,
        }
        if "GlobalSecondaryIndexes" in table_def:
            params["GlobalSecondaryIndexes"] = table_def["GlobalSecondaryIndexes"]

        client.create_table(**params)
        print(f"[생성] {name}")
        created.append(name)

    if not created:
        print("\n모든 테이블이 이미 존재합니다.")
        return

    print(f"\n{len(created)}개 테이블 생성 중. 활성화 대기...")
    for name in created:
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=name, WaiterConfig={"Delay": 3, "MaxAttempts": 30})
        print(f"[활성] {name}")

    print("\n모든 테이블 준비 완료. 서버를 시작하세요: uv run poe serve")


if __name__ == "__main__":
    create_tables()
