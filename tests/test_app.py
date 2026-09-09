"""Unit tests for the ticket management Lambda handler.

DynamoDB is mocked with moto; no real AWS calls are made.
"""

from __future__ import annotations

import importlib
import json
import os
from typing import Any, Iterator
from unittest import mock

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

TABLE_NAME = "tickets-test"


@pytest.fixture(autouse=True)
def aws_credentials() -> None:
    """Set fake AWS credentials so mocked calls never hit real AWS."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
    os.environ["TABLE_NAME"] = TABLE_NAME


@pytest.fixture()
def app() -> Any:
    """Import the app module fresh for each test."""
    import app as app_module

    return importlib.reload(app_module)


@pytest.fixture()
def dynamodb_table() -> Iterator[Any]:
    """Create a mocked DynamoDB table for the duration of a test."""
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        resource.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield resource.Table(TABLE_NAME)


def _post_event(body: Any) -> dict[str, Any]:
    return {
        "httpMethod": "POST",
        "resource": "/tickets",
        "body": body if isinstance(body, str) or body is None else json.dumps(body),
    }


def _get_event(ticket_id: str | None) -> dict[str, Any]:
    return {
        "httpMethod": "GET",
        "resource": "/tickets/{id}",
        "pathParameters": {"id": ticket_id} if ticket_id is not None else None,
    }


def test_create_ticket_success(app: Any, dynamodb_table: Any) -> None:
    event = _post_event({"subject": "Login issue", "message": "Cannot log in"})
    response = app.handler(event, None)

    assert response["statusCode"] == 201
    body = json.loads(response["body"])
    assert body["subject"] == "Login issue"
    assert body["message"] == "Cannot log in"
    assert body["id"]
    assert body["created_at"]

    stored = dynamodb_table.get_item(Key={"id": body["id"]})["Item"]
    assert stored["subject"] == "Login issue"


def test_get_ticket_success(app: Any, dynamodb_table: Any) -> None:
    create_response = app.handler(
        _post_event({"subject": "Billing", "message": "Wrong charge"}), None
    )
    ticket_id = json.loads(create_response["body"])["id"]

    response = app.handler(_get_event(ticket_id), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["id"] == ticket_id
    assert body["subject"] == "Billing"


@pytest.mark.parametrize(
    "body",
    [
        None,
        "not-json",
        json.dumps({"subject": "only subject"}),
        json.dumps({"subject": "", "message": ""}),
        json.dumps({"subject": "  ", "message": "hello"}),
        json.dumps({"subject": 123, "message": "hello"}),
        json.dumps(["not", "a", "dict"]),
    ],
)
def test_create_ticket_invalid_input(app: Any, dynamodb_table: Any, body: Any) -> None:
    response = app.handler(_post_event(body), None)

    assert response["statusCode"] == 400
    assert "error" in json.loads(response["body"])


def test_get_ticket_not_found(app: Any, dynamodb_table: Any) -> None:
    response = app.handler(_get_event("does-not-exist"), None)

    assert response["statusCode"] == 404
    assert json.loads(response["body"])["error"] == "Ticket not found"


def test_get_ticket_missing_id(app: Any, dynamodb_table: Any) -> None:
    response = app.handler(_get_event(None), None)

    assert response["statusCode"] == 400


def test_unknown_route_returns_404(app: Any, dynamodb_table: Any) -> None:
    event = {"httpMethod": "DELETE", "resource": "/tickets/{id}"}
    response = app.handler(event, None)

    assert response["statusCode"] == 404


def test_dynamodb_error_returns_500(app: Any) -> None:
    error = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "boom"}},
        "PutItem",
    )
    fake_table = mock.Mock()
    fake_table.put_item.side_effect = error

    with mock.patch.object(app, "get_table", return_value=fake_table):
        response = app.handler(
            _post_event({"subject": "s", "message": "m"}), None
        )

    assert response["statusCode"] == 500
    assert json.loads(response["body"])["error"] == "Internal server error"


def test_dynamodb_get_error_returns_500(app: Any) -> None:
    error = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "boom"}},
        "GetItem",
    )
    fake_table = mock.Mock()
    fake_table.get_item.side_effect = error

    with mock.patch.object(app, "get_table", return_value=fake_table):
        response = app.handler(_get_event("some-id"), None)

    assert response["statusCode"] == 500
    assert json.loads(response["body"])["error"] == "Internal server error"
