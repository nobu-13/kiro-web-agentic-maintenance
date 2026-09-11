"""Minimal ticket management Lambda handler.

Routes:
    POST /tickets       -> create a ticket
    GET  /tickets/{id}  -> get a single ticket

DynamoDB access is isolated behind ``get_table()`` so it can be mocked in
unit tests. The table name is read from the ``TABLE_NAME`` environment
variable; no credentials or secrets are embedded in this module.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Maximum accepted lengths for user-supplied fields (basic input validation).
MAX_SUBJECT_LENGTH = 200
MAX_MESSAGE_LENGTH = 5000


def get_table() -> Any:
    """Return the DynamoDB table resource.

    The table name is taken from the ``TABLE_NAME`` environment variable.
    This function is the single seam used for DynamoDB access, which keeps
    the handler testable via mocking.
    """
    table_name = os.environ["TABLE_NAME"]
    resource = boto3.resource("dynamodb")
    return resource.Table(table_name)


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    """Build an API Gateway proxy response."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _validate_create_payload(payload: Any) -> tuple[str, str] | None:
    """Validate a POST /tickets payload.

    Returns the ``(subject, message)`` tuple when valid, otherwise ``None``.
    """
    if not isinstance(payload, dict):
        return None

    subject = payload.get("subject")
    message = payload.get("message")

    if not isinstance(subject, str) or not isinstance(message, str):
        return None

    if not subject or not message:
        return None

    if len(subject) > MAX_SUBJECT_LENGTH or len(message) > MAX_MESSAGE_LENGTH:
        return None

    return subject, message


def create_ticket(event: dict[str, Any]) -> dict[str, Any]:
    """Handle POST /tickets."""
    raw_body = event.get("body")
    if raw_body is None:
        return _response(400, {"error": "Request body is required"})

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        return _response(400, {"error": "Request body must be valid JSON"})

    validated = _validate_create_payload(payload)
    if validated is None:
        return _response(
            400,
            {"error": "Fields 'subject' and 'message' are required and must be non-empty strings"},
        )

    subject, message = validated
    item = {
        "id": str(uuid.uuid4()),
        "subject": subject,
        "message": message,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    table = get_table()
    table.put_item(Item=item)
    return _response(201, item)


def get_ticket(event: dict[str, Any]) -> dict[str, Any]:
    """Handle GET /tickets/{id}."""
    path_params = event.get("pathParameters") or {}
    ticket_id = path_params.get("id")

    if not ticket_id:
        return _response(400, {"error": "Ticket id is required"})

    table = get_table()
    result = table.get_item(Key={"id": ticket_id})
    item = result.get("Item")

    if item is None:
        return _response(404, {"error": "Ticket not found"})

    return _response(200, item)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda entry point: route the request by HTTP method and resource."""
    method = event.get("httpMethod")
    resource = event.get("resource")

    try:
        if method == "POST" and resource == "/tickets":
            return create_ticket(event)
        if method == "GET" and resource == "/tickets/{id}":
            return get_ticket(event)
        return _response(404, {"error": "Not found"})
    except ClientError:
        logger.exception("DynamoDB request failed")
        return _response(500, {"error": "Internal server error"})
    except Exception:
        logger.exception("Unexpected error handling request")
        return _response(500, {"error": "Internal server error"})
