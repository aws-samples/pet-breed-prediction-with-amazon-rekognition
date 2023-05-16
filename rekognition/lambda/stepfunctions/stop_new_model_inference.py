# Sample Input
# {
#  "animal": "cat"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, uuid


def handler(event, context):
    rekognition = boto3.client("rekognition")

    animal_type = event["animal"]
    version_name = event["version_name"]
    project_arn = event["project_arn"]
    version_name = event["version_name"]

    project_versions = rekognition.describe_project_versions(
        ProjectArn=project_arn, VersionNames=[version_name]
    )

    version_arn = ""
    status = ""
    versions = project_versions["ProjectVersionDescriptions"]
    for version in versions:
        if version_name in version["ProjectVersionArn"]:
            version_arn = version["ProjectVersionArn"]
            status = version["Status"]

    if status == "STOPPED":
        ssm = boto3.client("ssm")
        topic_arn = ssm.get_parameter(Name="/animal-rekognition/sns/arn")["Parameter"][
            "Value"
        ]

        sns = boto3.client("sns")
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Model not promoted and in 'Stopped' state: {version_name}",
            Subject=f"Model not promoted for: {animal_type}",
        )
        return {"status": "SUCCESS"}
    elif status == "RUNNING":
        stop_model = rekognition.stop_project_version(ProjectVersionArn=version_arn)
        print("Stop Model Executed")
        raise Exception(f"Waiting for Model to Stop: {version_arn}")
    elif status == "STOPPING":
        raise Exception(f"Waiting for Model to Stop: {version_arn}")
    else:
        print(f"New Model Status: {status}")
        raise Exception(f"Model in unkown state {version_arn}")
