import os
import time

import boto3
from botocore.config import Config


AWS_CONFIG = Config(
    retries={"total_max_attempts": 3, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=10,
)

REGION = os.environ.get("TARGET_REGION", "sa-east-1")
INSTANCE_ID = os.environ.get("INSTANCE_ID", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
SESSION_SECONDS = int(os.environ.get("SESSION_SECONDS", "14400"))

ec2 = boto3.client("ec2", region_name=REGION, config=AWS_CONFIG)
table = boto3.resource("dynamodb", region_name=REGION, config=AWS_CONFIG).Table(
    TABLE_NAME
)


def month_key(epoch_seconds):
    return time.strftime("%Y-%m", time.gmtime(epoch_seconds))


def allowed_seconds(instance_type):
    if instance_type.endswith(".medium"):
        return 20 * 60 * 60
    return 40 * 60 * 60


def can_start(control, used_seconds, instance_type):
    if control.get("cost_lock", False):
        return False, control.get("lock_reason", "cost_lock")
    if used_seconds >= allowed_seconds(instance_type):
        return False, "monthly_runtime_limit"
    return True, "allowed"


def _instance():
    response = ec2.describe_instances(InstanceIds=[INSTANCE_ID])
    return response["Reservations"][0]["Instances"][0]


def _control():
    return table.get_item(Key={"pk": "CONTROL"}, ConsistentRead=True).get(
        "Item", {}
    )


def _used_seconds(now_epoch):
    item = table.get_item(
        Key={"pk": f"USAGE#{month_key(now_epoch)}"}, ConsistentRead=True
    ).get("Item", {})
    return int(item.get("used_seconds", 0))


def _status(now_epoch):
    instance = _instance()
    control = _control()
    used_seconds = _used_seconds(now_epoch)
    return {
        "instance_id": INSTANCE_ID,
        "instance_type": instance["InstanceType"],
        "state": instance["State"]["Name"],
        "cost_lock": bool(control.get("cost_lock", False)),
        "lock_reason": control.get("lock_reason"),
        "deadline_epoch": int(control.get("deadline_epoch", 0)),
        "used_seconds": used_seconds,
        "limit_seconds": allowed_seconds(instance["InstanceType"]),
    }


def lambda_handler(event, context):
    del context
    action = (event or {}).get("action", "status").strip().lower()
    if action not in {"start", "renew", "stop", "status"}:
        return {"ok": False, "status": 400, "error": "invalid_action"}

    now_epoch = int(time.time())
    status = _status(now_epoch)
    if action == "status":
        return {"ok": True, **status}

    if action == "stop":
        if status["state"] in {"pending", "running"}:
            ec2.stop_instances(InstanceIds=[INSTANCE_ID])
        table.update_item(
            Key={"pk": "CONTROL"},
            UpdateExpression=(
                "SET deadline_epoch = :expired, session_open = :false, "
                "updated_at = :now"
            ),
            ExpressionAttributeValues={
                ":expired": now_epoch - 1,
                ":false": False,
                ":now": now_epoch,
            },
        )
        return {"ok": True, "action": "stop", "state": status["state"]}

    allowed, reason = can_start(
        _control(), status["used_seconds"], status["instance_type"]
    )
    if not allowed:
        return {"ok": False, "status": 423, "error": reason}

    if action == "renew" and status["state"] != "running":
        return {"ok": False, "status": 409, "error": "instance_not_running"}

    deadline = now_epoch + SESSION_SECONDS
    table.update_item(
        Key={"pk": "CONTROL"},
        UpdateExpression=(
            "SET deadline_epoch = :deadline, session_open = :true, "
            "last_accounted_epoch = :now, updated_at = :now REMOVE lock_reason"
        ),
        ExpressionAttributeValues={
            ":deadline": deadline,
            ":true": True,
            ":now": now_epoch,
        },
    )
    if action == "start" and status["state"] == "stopped":
        ec2.start_instances(InstanceIds=[INSTANCE_ID])
    elif action == "start" and status["state"] not in {"pending", "running"}:
        return {
            "ok": False,
            "status": 409,
            "error": f"instance_{status['state']}",
        }
    return {"ok": True, "action": action, "deadline_epoch": deadline}

