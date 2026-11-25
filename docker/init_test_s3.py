import json
import os
from time import monotonic, sleep

from minio import Minio
from minio.error import S3Error
from urllib3 import PoolManager
from urllib3.exceptions import HTTPError


def main():
    bucket = os.environ["S3_BUCKET_NAME"]
    client = Minio(
        os.environ["S3_ENDPOINT"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        secure=False,
        region="us-east-1",
        http_client=PoolManager(timeout=3, retries=False),
    )
    deadline = monotonic() + 90
    while True:
        try:
            if client.bucket_exists(bucket):
                break
        except S3Error as exc:
            if exc.code not in {"InternalError", "ServiceUnavailable", "SlowDown"}:
                raise
        except HTTPError:
            if monotonic() >= deadline:
                raise
        if monotonic() >= deadline:
            raise TimeoutError(f"S3 bucket {bucket!r} is not ready")
        sleep(2)

    policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": "*",
            "Action": "s3:GetObject",
            "Resource": f"arn:aws:s3:::{bucket}/*",
        }],
    }
    client.set_bucket_policy(bucket, json.dumps(policy))
    print(f"S3 bucket {bucket!r} is ready")


if __name__ == "__main__":
    main()
