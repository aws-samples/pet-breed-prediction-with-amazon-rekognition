# Sample Input
# {
#  "status": "SUCCEEDED",
#  "animal": "cat",
#  "env_prefix": "dv",
#  "version": "0.0.1"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, os, uuid


def handler(event, context):

    rekognition = boto3.client("rekognition")

    animal_type = ""
    uuid = ""
    for parameter in event["parameters"]:
        if parameter["Name"] == "ANIMAL":
            animal_type = parameter["Value"]
        elif parameter["Name"] == "UUID":
            uuid = parameter["Value"]

    s3_bucket = os.environ.get("s3_bucket_name")
    version = os.environ.get("version")
    env_prefix = os.environ.get("env_prefix")

    project_name = f"{env_prefix}-rekognition-{animal_type}-training-{version}-{uuid}"

    create_project = rekognition.create_project(ProjectName=project_name)
    project_arn = create_project["ProjectArn"]

    test_manifest = ""
    train_manifest = ""

    test_manifest = f"{version}/{animal_type}/{uuid}/{animal_type}-test.manifest"
    train_manifest = f"{version}/{animal_type}/{uuid}/{animal_type}-train.manifest"

    test_dataset = rekognition.create_dataset(
        DatasetSource={
            "GroundTruthManifest": {
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": test_manifest,
                }
            },
        },
        DatasetType="TEST",
        ProjectArn=project_arn,
    )

    train_dataset = rekognition.create_dataset(
        DatasetSource={
            "GroundTruthManifest": {
                "S3Object": {
                    "Bucket": s3_bucket,
                    "Name": train_manifest,
                }
            },
        },
        DatasetType="TRAIN",
        ProjectArn=project_arn,
    )
    test_dataset_arn = test_dataset["DatasetArn"]
    train_dataset_arn = train_dataset["DatasetArn"]

    # Reset Test ENV
    if os.environ.get("test_env") == "True":
        _lambda = boto3.client("lambda")
        function_name = context.function_name

        environment = _lambda.get_function_configuration(
            FunctionName=function_name,
        )

        old_environment_variables = environment["Environment"]["Variables"]
        new_environment_variables = old_environment_variables
        new_environment_variables["test_env"] = "False"

        remove_env_variables = _lambda.update_function_configuration(
            FunctionName=function_name,
            Environment={"Variables": new_environment_variables},
        )
        print("Successfully removed test env")

    return {
        "test_dataset_arn": test_dataset_arn,
        "train_dataset_arn": train_dataset_arn,
        "animal": animal_type,
        "version": version,
        "uuid": uuid,
        "project_arn": project_arn,
    }
