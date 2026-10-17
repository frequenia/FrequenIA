import json
import os
import time
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr
from botocore.config import Config


AWS_CONFIG = Config(
    retries={"total_max_attempts": 3, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=10,
)

REGION = os.environ.get("TARGET_REGION", "sa-east-1")
INSTANCE_ID = os.environ.get("INSTANCE_ID", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
ALERT_TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")
SESSION_SECONDS = int(os.environ.get("SESSION_SECONDS", "14400"))

ec2 = boto3.client("ec2", region_name=REGION, config=AWS_CONFIG)
sns = boto3.client("sns", region_name=REGION, config=AWS_CONFIG)
table = boto3.resource("dynamodb", region_name=REGION, config=AWS_CONFIG).Table(
    TABLE_NAME
)


def month_key(epoch_seconds):
    return time.strftime("%Y-%m", time.gmtime(epoch_seconds))


def allowed_seconds(instance_type):
    if instance_type.endswith(".medium"):
        return 20 * 60 * 60
    return 40 * 60 * 60


def evaluate_control(control, used_seconds, now_epoch, instance_type):
    if control.get("cost_lock", False):
        return "stop", "cost_lock"
    deadline = int(control.get("deadline_epoch", 0))
    if deadline <= now_epoch:
        return "stop", "session_expired"
    if used_seconds >= allowed_seconds(instance_type):
        return "lock", "monthly_runtime_limit"
    return "continue", "within_limits"


def _instance():
    response = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    return response["Reservations"][0]["Instances"][0]


def _notify(subject, message):
    sns.publish(TopicArn=ALERT_TOPIC_ARN, Subject=subject[:100], Message=message)


def _stop():
    ec2.stop_instances(InstanceIds=[INSTANCE_ID])


def _bootstrap_control(now_epoch):
    control = {
        "pk": "CONTROL",
        "cost_lock": False,
        "session_open": True,
        "deadline_epoch": now_epoch + SESSION_SECONDS,
        "last_accounted_epoch": now_epoch,
        "updated_at": now_epoch,
    }
    try:
        table.put_item(
            Item=control,
            ConditionExpression=Attr("pk").not_exists(),
        )
        return control
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return table.get_item(Key={"pk": "CONTROL"}, ConsistentRead=True)["Item"]


def _usage(now_epoch, control):
    last_accounted = int(control.get("last_accounted_epoch", now_epoch))
    elapsed = max(0, now_epoch - last_accounted)
    table.update_item(
        Key={"pk": "CONTROL"},
        UpdateExpression="SET last_accounted_epoch = :now, updated_at = :now",
        ExpressionAttributeValues={":now": now_epoch},
    )
    if elapsed:
        response = table.update_item(
            Key={"pk": f"USAGE#{month_key(now_epoch)}"},
            UpdateExpression="ADD used_seconds :elapsed SET updated_at = :now",
            ExpressionAttributeValues={
                ":elapsed": Decimal(elapsed),
                ":now": now_epoch,
            },
            ReturnValues="ALL_NEW",
        )
        return int(response["Attributes"].get("used_seconds", 0))
    item = table.get_item(
        Key={"pk": f"USAGE#{month_key(now_epoch)}"}, ConsistentRead=True
    ).get("Item", {})
    return int(item.get("used_seconds", 0))


def _lock(reason, now_epoch):
    previous = table.update_item(
        Key={"pk": "CONTROL"},
        UpdateExpression=(
            "SET cost_lock = :true, lock_reason = :reason, locked_month = :month, "
            "session_open = :false, updated_at = :now"
        ),
        ExpressionAttributeValues={
            ":true": True,
            ":reason": reason,
            ":month": month_key(now_epoch),
            ":now": now_epoch,
        },
        ReturnValues="ALL_OLD",
    ).get("Attributes", {})
    return not previous.get("cost_lock", False)


def lambda_handler(event, context):
    del event, context
    now_epoch = int(time.time())
    instance = _instance()
    state = instance["State"]["Name"]
    if state != "running":
        return {"state": state, "action": "none"}

    control = table.get_item(Key={"pk": "CONTROL"}, ConsistentRead=True).get("Item")
    if control is None:
        control = _bootstrap_control(now_epoch)

    used_seconds = _usage(now_epoch, control)
    action, reason = evaluate_control(
        control, used_seconds, now_epoch, instance["InstanceType"]
    )
    if action == "continue":
        return {
            "state": state,
            "action": action,
            "used_seconds": used_seconds,
            "limit_seconds": allowed_seconds(instance["InstanceType"]),
        }

    newly_locked = False
    if action == "lock":
        newly_locked = _lock(reason, now_epoch)
    _stop()
    if action == "lock" and newly_locked:
        _notify(
            "FrequenIA bloqueado por limite mensal",
            json.dumps(
                {
                    "instance_id": INSTANCE_ID,
                    "reason": reason,
                    "used_seconds": used_seconds,
                }
            ),
        )
    elif reason == "session_expired":
        _notify(
            "Sessao de teste FrequenIA encerrada",
            f"A instancia {INSTANCE_ID} foi parada ao atingir quatro horas.",
        )
    return {"state": state, "action": action, "reason": reason}
