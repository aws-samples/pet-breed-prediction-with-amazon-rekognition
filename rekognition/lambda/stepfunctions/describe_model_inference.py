# Sample Input
# {
#  "version_name": "dv-rekognition-cat-training-0-0-1-9dfb55a8"
#  "animal": "cat"
#  "uuid": "9dfb55a8"
#  "project_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-rekognition-cat-training-0.0.1-9dfb55a8/1649029454598"
# }
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0

import json, boto3


def handler(event, context):

    version_name = event["version_name"]
    animal_type = event["animal"]
    project_arn = event["project_arn"]
    uuid = event["uuid"]

    ssm = boto3.client("ssm")
    rekognition = boto3.client("rekognition")

    response = rekognition.describe_project_versions(
        ProjectArn=project_arn, VersionNames=[version_name]
    )

    model_status = ""

    versions = response["ProjectVersionDescriptions"]
    for version in versions:
        if version_name in version["ProjectVersionArn"]:
            model_status = version["Status"]

    if model_status == "RUNNING":
        return {
            "animal": animal_type,
            "version_name": version_name,
            "status": "RUNNING",
            "uuid": uuid,
            "project_arn": project_arn,
        }
    else:
        print(f"Model Status: {model_status} ")
        raise Exception(f"Model not Running")
