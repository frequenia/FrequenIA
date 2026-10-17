"""Fila privada de jobs de varredura; configuração pertence ao servidor."""

from dataclasses import dataclass
import json
import os
import threading
import time
from uuid import UUID, uuid4


MESSAGE_KEYS = frozenset({"v", "job_id", "attachment_id", "company_id"})


class AttachmentQueueError(Exception):
    pass


class InvalidScanMessage(AttachmentQueueError):
    pass


@dataclass(frozen=True)
class QueueMessage:
    body: str
    receipt_handle: str
    message_id: str
    receive_count: int = 1


def build_scan_payload(job_id, attachment_id, company_id):
    payload = {
        "v": 1,
        "job_id": str(UUID(str(job_id))),
        "attachment_id": str(UUID(str(attachment_id))),
        "company_id": str(UUID(str(company_id))),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def parse_scan_payload(body):
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or set(payload) != MESSAGE_KEYS:
            raise ValueError
        if payload["v"] != 1:
            raise ValueError
        for key in ("job_id", "attachment_id", "company_id"):
            payload[key] = str(UUID(str(payload[key])))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InvalidScanMessage("Mensagem de varredura inválida.") from exc
    return payload


class InMemoryAttachmentQueue:
    """Emulador determinístico de visibility timeout e DLQ, exclusivo de testes."""

    def __init__(self, visibility_timeout=60, max_receive_count=4, clock=None):
        self.visibility_timeout = int(visibility_timeout)
        self.max_receive_count = int(max_receive_count)
        self._clock = clock or time.monotonic
        self._messages = []
        self.dlq = []
        self._lock = threading.Lock()

    def send(self, body):
        parse_scan_payload(body)
        message_id = str(uuid4())
        with self._lock:
            self._messages.append({
                "body": body,
                "message_id": message_id,
                "receipt": None,
                "visible_at": self._clock(),
                "receives": 0,
            })
        return message_id

    def receive(self, max_messages=1, wait_seconds=0):
        del wait_seconds
        result = []
        now = self._clock()
        with self._lock:
            for item in list(self._messages):
                if len(result) >= max(1, min(int(max_messages), 10)):
                    break
                if item["visible_at"] > now:
                    continue
                item["receives"] += 1
                if item["receives"] > self.max_receive_count:
                    self._messages.remove(item)
                    self.dlq.append(dict(item))
                    continue
                item["receipt"] = str(uuid4())
                item["visible_at"] = now + self.visibility_timeout
                result.append(QueueMessage(
                    item["body"], item["receipt"], item["message_id"], item["receives"]
                ))
        return result

    def delete(self, receipt_handle):
        with self._lock:
            for item in list(self._messages):
                if item["receipt"] == receipt_handle:
                    self._messages.remove(item)
                    return
        raise AttachmentQueueError("Recibo de mensagem inválido.")

    def change_visibility(self, receipt_handle, timeout_seconds):
        timeout = min(max(int(timeout_seconds), 1), self.visibility_timeout * 2)
        with self._lock:
            for item in self._messages:
                if item["receipt"] == receipt_handle:
                    item["visible_at"] = self._clock() + timeout
                    return
        raise AttachmentQueueError("Recibo de mensagem inválido.")

    def healthcheck(self):
        return True
    def stats(self):
        now=self._clock()
        with self._lock:
            return {
                "visible":sum(1 for item in self._messages if item["visible_at"]<=now),
                "inflight":sum(1 for item in self._messages if item["visible_at"]>now),
                "dlq":len(self.dlq),
            }


class SQSAttachmentQueue:
    def __init__(self, queue_url, region=None, endpoint_url=None, client=None):
        self.queue_url = str(queue_url or "").strip()
        if not self.queue_url:
            raise AttachmentQueueError("Fila de varredura não configurada.")
        endpoint=str(endpoint_url or "").strip() or None
        environment=os.getenv("APP_ENV","development").strip().lower()
        if endpoint and not endpoint.startswith("https://") and environment not in {"test","testing"}:
            raise AttachmentQueueError("O endpoint SQS deve usar TLS.")
        if client is None:
            import boto3
            from botocore.config import Config

            config = Config(
                connect_timeout=3,
                read_timeout=25,
                retries={"total_max_attempts": 3, "mode": "standard"},
                user_agent_appid="frequenia-attachment-worker",
            )
            client = boto3.client(
                "sqs",
                region_name=region or None,
                endpoint_url=endpoint,
                config=config,
            )
        self.client = client

    def send(self, body):
        parse_scan_payload(body)
        response = self.client.send_message(QueueUrl=self.queue_url, MessageBody=body)
        message_id = str(response.get("MessageId", ""))
        if not message_id:
            raise AttachmentQueueError("Fila não retornou identificador de mensagem.")
        return message_id

    def receive(self, max_messages=1, wait_seconds=20):
        response = self.client.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=max(1, min(int(max_messages), 10)),
            WaitTimeSeconds=max(0, min(int(wait_seconds), 20)),
            AttributeNames=["ApproximateReceiveCount"],
        )
        return [
            QueueMessage(
                item["Body"],
                item["ReceiptHandle"],
                item["MessageId"],
                int(item.get("Attributes", {}).get("ApproximateReceiveCount", "1")),
            )
            for item in response.get("Messages", [])
        ]

    def delete(self, receipt_handle):
        self.client.delete_message(QueueUrl=self.queue_url, ReceiptHandle=receipt_handle)

    def change_visibility(self, receipt_handle, timeout_seconds):
        self.client.change_message_visibility(
            QueueUrl=self.queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=max(1, min(int(timeout_seconds), 43200)),
        )

    def healthcheck(self):
        try:
            self.client.get_queue_attributes(
                QueueUrl=self.queue_url, AttributeNames=["QueueArn"]
            )
            return True
        except Exception:
            return False
    def stats(self):
        response=self.client.get_queue_attributes(
            QueueUrl=self.queue_url,
            AttributeNames=["ApproximateNumberOfMessages","ApproximateNumberOfMessagesNotVisible"],
        )["Attributes"]
        return {
            "visible":int(response.get("ApproximateNumberOfMessages","0")),
            "inflight":int(response.get("ApproximateNumberOfMessagesNotVisible","0")),
        }


def get_attachment_queue():
    provider = os.getenv("ATTACHMENT_QUEUE_PROVIDER", "").strip().lower()
    environment = os.getenv("APP_ENV", "development").strip().lower()
    if provider in {"memory", "fake"}:
        if environment not in {"test", "testing"}:
            raise AttachmentQueueError("Fila em memória só é permitida em testes.")
        return InMemoryAttachmentQueue(
            os.getenv("ATTACHMENT_QUEUE_VISIBILITY_SECONDS", "60"),
            os.getenv("ATTACHMENT_QUEUE_MAX_RECEIVES", "4"),
        )
    if provider != "sqs":
        raise AttachmentQueueError("Provedor de fila não configurado.")
    return SQSAttachmentQueue(
        os.getenv("ATTACHMENT_QUEUE_URL"),
        os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
        os.getenv("ATTACHMENT_QUEUE_ENDPOINT_URL"),
    )
