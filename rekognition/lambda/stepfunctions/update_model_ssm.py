# Sample Input
# {
#   "animal": "cat",
#   "promote": true,
#   "version_name": "dv-rekognition-cat-training-0-0-1-9dfb55a8",
#   "project_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-rekognition-cat-training-0.0.1-9dfb55a8/1649029454598"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, os, boto3


def handler(event, context):
    animal_type = event["animal"]
    version_name = event["version_name"]
    project_arn = event["project_arn"]

    ssm = boto3.client("ssm")
    rekognition = boto3.client("rekognition")

    previous_model = ""
    previous_project = ""

    # Get existing model if it exists, so that we can pass these values to stop_model_inference
    try:
        previous_model = ssm.get_parameter(
            Name=f"/animal-rekognition/{animal_type}/model/version-name"
        )["Parameter"]["Value"]

        previous_project = ssm.get_parameter(
            Name=f"/animal-rekognition/{animal_type}/model/project-arn"
        )["Parameter"]["Value"]

    except Exception as e:
        print(f"No version name or project for {animal_type}")

    previous_model_running = False
    previous_model_arn = ""
    # Check to see if previous model is running
    try:
        response = rekognition.describe_project_versions(
            ProjectArn=previous_project, VersionNames=[previous_model]
        )

        model_status = ""

        versions = response["ProjectVersionDescriptions"]
        for version in versions:
            if previous_model in version["ProjectVersionArn"]:
                model_status = version["Status"]
                previous_model_arn = version["ProjectVersionArn"]
        # Check if previous model is running
        print(f"previous model status: {model_status}")
        if model_status == "RUNNING" and previous_model != version_name:
            previous_model_running = True

    except Exception as e:
        print(f"Model {previous_model} not running or does not exist")

    if previous_model_running == False:
        ssm = boto3.client("ssm")
        topic_arn = ssm.get_parameter(Name="/animal-rekognition/sns/arn")["Parameter"][
            "Value"
        ]

        sns = boto3.client("sns")
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Model Deployed: {version_name}",
            Subject=f"Model Deployed for: {animal_type}",
        )

    # Update SSM with New Model Version Name
    put_version_name = ssm.put_parameter(
        Name=f"/animal-rekognition/{animal_type}/model/version-name",
        Value=version_name,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    put_project_arn = ssm.put_parameter(
        Name=f"/animal-rekognition/{animal_type}/model/project-arn",
        Value=project_arn,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    # Get model arn
    get_model_arn = rekognition.describe_project_versions(
        ProjectArn=project_arn, VersionNames=[version_name]
    )
    model_arn = ""
    versions = get_model_arn["ProjectVersionDescriptions"]
    for version in versions:
        if version_name in version["ProjectVersionArn"]:
            model_arn = version["ProjectVersionArn"]

    put_model_arn = ssm.put_parameter(
        Name=f"/animal-rekognition/{animal_type}/model/model-arn",
        Value=model_arn,
        Type="String",
        Overwrite=True,
        DataType="text",
    )

    return {
        "animal": animal_type,
        "version_name": version_name,
        "project_arn": project_arn,
        "model_arn": model_arn,
        "previous_model_running": previous_model_running,
        "previous_model_arn": previous_model_arn,
        "previous_project_arn": previous_project,
    }
