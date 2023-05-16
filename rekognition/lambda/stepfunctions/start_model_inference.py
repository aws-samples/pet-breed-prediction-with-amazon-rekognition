# Sample Input
# {
#   "animal": "dog",
#   "version_name": "dv-rekognition-cat-training-0-0-1-9a4bb15e"
#   "project_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-rekognition-cat-training-0.0.1-9a4bb15e/1649029454598"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, os


def handler(event, context):

    animal_type = event["animal"]
    version_name = event["version_name"]
    project_arn = event["project_arn"]
    uuid = event["uuid"]

    min_inference_units = int(os.environ.get("inference_units"))

    ssm = boto3.client("ssm")
    rekognition = boto3.client("rekognition")

    project_versions = rekognition.describe_project_versions(
        ProjectArn=project_arn, VersionNames=[version_name]
    )

    version_arn = ""

    versions = project_versions["ProjectVersionDescriptions"]
    for version in versions:
        if version_name in version["ProjectVersionArn"]:
            version_arn = version["ProjectVersionArn"]

    start_project = rekognition.start_project_version(
        ProjectVersionArn=version_arn,
        MinInferenceUnits=min_inference_units,
    )

    return {
        "animal": animal_type,
        "version_name": version_name,
        "version_arn": version_arn,
        "project_arn": project_arn,
        "uuid": uuid,
    }
