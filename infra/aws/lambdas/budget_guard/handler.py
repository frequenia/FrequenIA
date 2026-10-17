import json
import os
import time

import boto3
from botocore.config import Config


AWS_CONFIG = Config(
    retries={"total_max_attempts": 3, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=10,
)

TARGET_REGION = os.environ.get("TARGET_REGION", "sa-east-1")
INSTANCE_ID = os.environ.get("INSTANCE_ID", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
ACTION = os.environ.get("ACTION", "STOP").upper()
OPERATOR_ROLE_NAME = os.environ.get("OPERATOR_ROLE_NAME", "")
DENY_POLICY_ARN = os.environ.get("DENY_POLICY_ARN", "")
ALERT_TOPIC_ARN = os.environ.get("ALERT_TOPIC_ARN", "")

ec2 = boto3.client("ec2", region_name=TARGET_REGION, config=AWS_CONFIG)
iam = boto3.client("iam", config=AWS_CONFIG)
sns = boto3.client("sns", region_name=TARGET_REGION, config=AWS_CONFIG)
table = boto3.resource(
    "dynamodb", region_name=TARGET_REGION, config=AWS_CONFIG
).Table(TABLE_NAME)


def month_key(epoch_seconds):
    return time.strftime("%Y-%m", time.gmtime(epoch_seconds))


def lambda_handler(event, context):
    del context
    now_epoch = int(time.time())
    reason = "budget_lock" if ACTION == "LOCK" else "budget_stop"
    table.update_item(
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
    )
    instance = ec2.describe_instances(InstanceIds=[INSTANCE_ID])["Reservations"][0][
        "Instances"
    ][0]
    if instance["State"]["Name"] in {"pending", "running"}:
        ec2.stop_instances(InstanceIds=[INSTANCE_ID])

    if ACTION == "LOCK":
        iam.attach_role_policy(
            RoleName=OPERATOR_ROLE_NAME,
            PolicyArn=DENY_POLICY_ARN,
        )

    source_message = None
    if event.get("Records"):
        source_message = event["Records"][0].get("Sns", {}).get("Message")
    message = {
        "action": ACTION,
        "instance_id": INSTANCE_ID,
        "reason": reason,
        "budget_message": source_message,
    }
    sns.publish(
        TopicArn=ALERT_TOPIC_ARN,
        Subject=f"FrequenIA cost guard: {ACTION}",
        Message=json.dumps(message),
    )
    return message
