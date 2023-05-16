# Sample Input
# {
#   "test_dataset_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-dog-rekognition-use1-rkg/dataset/test/1648474994113",
#   "train_dataset_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-dog-rekognition-use1-rkg/dataset/train/1648474994277",
#   "animal": "dog",
#   "status": "CREATE_COMPLETE",
#   "version": "0.0.1"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, os, uuid


def handler(event, context):

    rekognition = boto3.client("rekognition")
    ssm = boto3.client("ssm")

    animal_type = event["animal"]
    uuid = event["uuid"]
    project_arn = event["project_arn"]
    s3_bucket = os.environ.get("s3_bucket_name")
    env_prefix = os.environ.get("env_prefix")
    version = os.environ.get("version")
    version_name = version.replace(".", "-")

    version_name = (
        f"{env_prefix}-rekognition-{animal_type}-training-{version_name}-{uuid}"
    )

    response = rekognition.create_project_version(
        ProjectArn=project_arn,
        VersionName=version_name,
        OutputConfig={
            "S3Bucket": s3_bucket,
            "S3KeyPrefix": f"{version}/{animal_type}/{uuid}/output",
        },
    )

    return {
        "version_name": version_name,
        "animal": animal_type,
        "project_arn": project_arn,
        "uuid": uuid,
    }
