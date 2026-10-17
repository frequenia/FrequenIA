import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
AWS_ROOT = ROOT / "infra" / "aws"


@unittest.skipUnless(
    AWS_ROOT.is_dir() and (ROOT / ".gitignore").is_file(),
    "infraestrutura AWS e metadados do repositorio nao fazem parte da imagem runtime",
)
class AwsPilotInfrastructureTests(unittest.TestCase):
    def test_arm_image_preloads_biometric_models(self):
        dockerfile = (ROOT / "Dockerfile.arm64").read_text(encoding="utf-8")
        self.assertIn("TARGETARCH", dockerfile)
        self.assertIn('test "$TARGETARCH" = "arm64"', dockerfile)
        self.assertIn("model_name='Fasnet'", dockerfile)
        self.assertIn("model_name='ArcFace'", dockerfile)
        self.assertIn("--workers 1 --threads 1", dockerfile)

    def test_runtime_uses_two_gb_floor_and_no_paid_network_appliances(self):
        template = (AWS_ROOT / "runtime.template.yaml").read_text(encoding="utf-8")
        self.assertIn("Default: t4g.small", template)
        self.assertNotIn("t4g.micro", template)
        self.assertNotIn("AWS::EC2::NatGateway", template)
        self.assertNotIn("AWS::EC2::EIP", template)
        self.assertNotIn("AWS::ElasticLoadBalancing", template)
        self.assertIn("VolumeSize: 30", template)
        self.assertIn("CPUCredits: standard", template)
        self.assertIn("rate(5 minutes)", template)

    def test_runtime_uses_supported_os_imdsv2_and_stops_after_bootstrap(self):
        template = (AWS_ROOT / "runtime.template.yaml").read_text(encoding="utf-8")
        self.assertIn("al2023-ami-kernel-default-arm64", template)
        self.assertIn("al2023-ami-kernel-default-x86_64", template)
        self.assertNotIn("amzn2-ami", template)
        self.assertIn("HttpTokens: required", template)
        self.assertIn("HttpPutResponseHopLimit: 2", template)
        self.assertIn("trap '/sbin/shutdown -h now || true' EXIT", template)
        self.assertIn("dnf install -y docker jq gzip", template)
        self.assertIn("clamav/clamav:1.5.4-debian13-slim", template)
        self.assertIn("frequenia-clamav-db", template)

    def test_budget_has_stop_and_lock_thresholds(self):
        template = (AWS_ROOT / "billing.template.yaml").read_text(encoding="utf-8")
        self.assertIn("Default: 5", template)
        self.assertIn("Threshold: 80", template)
        self.assertIn("Threshold: 100", template)
        self.assertIn("NotificationType: FORECASTED", template)
        self.assertIn("ACTION: STOP", template)
        self.assertIn("ACTION: LOCK", template)

    def test_lambda_functions_fit_fresh_account_concurrency_quota(self):
        runtime = (AWS_ROOT / "runtime.template.yaml").read_text(encoding="utf-8")
        billing = (AWS_ROOT / "billing.template.yaml").read_text(encoding="utf-8")
        self.assertNotIn("ReservedConcurrentExecutions", runtime)
        self.assertNotIn("ReservedConcurrentExecutions", billing)

    def test_apk_public_access_is_scoped_to_apk_prefix(self):
        template = (AWS_ROOT / "bootstrap.yaml").read_text(encoding="utf-8")
        self.assertIn("PublicReadOnlyForApk", template)
        self.assertIn("${ArtifactBucket.Arn}/apk/*", template)
        self.assertNotIn("Principal: '*'\n              Action: s3:*\n              Resource: !Sub '${ArtifactBucket.Arn}/*'", template)

    def test_private_attachments_are_separate_encrypted_and_not_versioned(self):
        template = (AWS_ROOT / "attachments.template.yaml").read_text(encoding="utf-8")
        self.assertIn("BlockPublicAcls: true", template)
        self.assertIn("RestrictPublicBuckets: true", template)
        self.assertIn("aws:SecureTransport: false", template)
        self.assertIn("s3:x-amz-server-side-encryption: AES256", template)
        self.assertIn("${AttachmentBucket.Arn}/${Environment}/*", template)
        self.assertNotIn("VersioningConfiguration", template)

    def test_deploy_injects_private_storage_and_clamav_configuration(self):
        script = (AWS_ROOT / "scripts" / "deploy.ps1").read_text(encoding="utf-8")
        self.assertIn("frequenia-pilot-attachments", script)
        self.assertIn("ATTACHMENT_STORAGE_PROVIDER'] = 's3'", script)
        self.assertIn("ATTACHMENT_SCANNER_PROVIDER'] = 'clamav'", script)
        self.assertIn("CLAMAV_HOST'] = 'frequenia-clamav'", script)
        self.assertIn("AttachmentBucketName=$attachmentBucket", script)
        self.assertIn("AttachmentScanQueueUrl=$attachmentQueueUrl", script)
        self.assertIn("AttachmentPublisherPolicyArn=$attachmentPublisherPolicyArn", script)
        self.assertIn("AttachmentWorkerPolicyArn=$attachmentWorkerPolicyArn", script)
        self.assertIn("ATTACHMENT_QUEUE_PROVIDER'] = 'sqs'", script)
        self.assertIn("DynamicDnsSubdomain=$DuckDnsSubdomain", script)
        self.assertNotIn("        DuckDnsSubdomain=$DuckDnsSubdomain", script)
        self.assertIn("s3api head-object", script)
        self.assertIn("Get-FileHash -Algorithm SHA256", script)
        self.assertIn("--metadata \"sha256=$localArchiveSha256\"", script)
        self.assertNotIn("$containerArchive.Length", script)

    def test_runtime_supervises_async_attachment_processes_and_uses_readiness(self):
        template = (AWS_ROOT / "runtime.template.yaml").read_text(encoding="utf-8")
        self.assertIn("frequenia-dispatcher --restart unless-stopped", template)
        self.assertIn("frequenia-worker --restart unless-stopped", template)
        self.assertIn("dispatch_attachment_scan_jobs.py --continuous", template)
        self.assertIn("run_attachment_scan_worker.py", template)
        self.assertIn("ATTACHMENT_QUEUE_PROVIDER=sqs", template)
        self.assertIn("/ready", template)
        self.assertIn("AttachmentPublisherPolicyArn", template)
        self.assertIn("AttachmentWorkerPolicyArn", template)

    def test_secret_files_are_not_tracked(self):
        gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".env.*", gitignore)
        self.assertIn(".secrets/", gitignore)
        self.assertIn("infra/aws/dist/", gitignore)


if __name__ == "__main__":
    unittest.main()
