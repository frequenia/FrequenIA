import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def _stub_boto3():
    module = types.ModuleType("boto3")
    module.client = lambda *args, **kwargs: object()

    class Resource:
        def Table(self, name):
            return object()

    module.resource = lambda *args, **kwargs: Resource()
    sys.modules.setdefault("boto3", module)

    conditions = types.ModuleType("boto3.dynamodb.conditions")

    class Attr:
        def __init__(self, name):
            self.name = name

        def not_exists(self):
            return (self.name, "not_exists")

    conditions.Attr = Attr
    sys.modules.setdefault("boto3.dynamodb", types.ModuleType("boto3.dynamodb"))
    sys.modules.setdefault("boto3.dynamodb.conditions", conditions)

    config_module = types.ModuleType("botocore.config")
    config_module.Config = lambda **kwargs: kwargs
    sys.modules.setdefault("botocore", types.ModuleType("botocore"))
    sys.modules.setdefault("botocore.config", config_module)


def _load(name, relative_path):
    _stub_boto3()
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RuntimeGuardPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guard = _load("runtime_guard", "lambdas/runtime_guard/handler.py")
        cls.control = _load("session_control", "lambdas/session_control/handler.py")

    def test_small_instance_receives_forty_hours(self):
        self.assertEqual(self.guard.allowed_seconds("t4g.small"), 40 * 60 * 60)

    def test_medium_instance_receives_twenty_hours(self):
        self.assertEqual(self.guard.allowed_seconds("t4g.medium"), 20 * 60 * 60)

    def test_cost_lock_always_stops(self):
        action, reason = self.guard.evaluate_control(
            {"cost_lock": True, "deadline_epoch": 999999}, 0, 100, "t4g.small"
        )
        self.assertEqual((action, reason), ("stop", "cost_lock"))

    def test_expired_session_stops(self):
        action, reason = self.guard.evaluate_control(
            {"cost_lock": False, "deadline_epoch": 99}, 0, 100, "t4g.small"
        )
        self.assertEqual((action, reason), ("stop", "session_expired"))

    def test_monthly_limit_locks(self):
        action, reason = self.guard.evaluate_control(
            {"cost_lock": False, "deadline_epoch": 200},
            40 * 60 * 60,
            100,
            "t4g.small",
        )
        self.assertEqual((action, reason), ("lock", "monthly_runtime_limit"))

    def test_control_refuses_locked_start(self):
        allowed, reason = self.control.can_start(
            {"cost_lock": True, "lock_reason": "budget_lock"}, 0, "t4g.small"
        )
        self.assertFalse(allowed)
        self.assertEqual(reason, "budget_lock")

    def test_control_allows_start_below_limit(self):
        allowed, reason = self.control.can_start({}, 60, "t4g.small")
        self.assertTrue(allowed)
        self.assertEqual(reason, "allowed")


if __name__ == "__main__":
    unittest.main()
