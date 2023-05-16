# Sample Input
# {
#  "test_dataset_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-cat-rekognition-use1-rkg/dataset/test/1648421378264",
#  "train_dataset_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-cat-rekognition-use1-rkg/dataset/train/1648421378480",
#  "animal": "cat"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0

import json, boto3, os


def handler(event, context):
    print(event)

    ssm = boto3.client("ssm")
    rekognition = boto3.client("rekognition")

    animal_type = event["animal"]
    uuid = event["uuid"]
    test_dataset_arn = event["test_dataset_arn"]
    train_dataset_arn = event["train_dataset_arn"]
    project_arn = event["project_arn"]
    version = os.environ.get("version")

    train_dataset = rekognition.describe_dataset(DatasetArn=train_dataset_arn)
    test_dataset = rekognition.describe_dataset(DatasetArn=test_dataset_arn)

    train_status = train_dataset["DatasetDescription"]["Status"]
    test_status = test_dataset["DatasetDescription"]["Status"]

    if train_status == "CREATE_IN_PROGRESS" or test_status == "CREATE_IN_PROGRESS":
        print(f"Train Status: {train_status} ")
        print(f"Test Status: {test_status} ")
        raise Exception(f"Dataset creation in progress")
    elif test_status == "CREATE_COMPLETE" and train_status == "CREATE_COMPLETE":
        return {
            "test_dataset_arn": test_dataset_arn,
            "train_dataset_arn": train_dataset_arn,
            "animal": animal_type,
            "status": "CREATE_COMPLETE",
            "version": version,
            "uuid": uuid,
            "project_arn": project_arn,
        }
    else:
        print(f"Train Status: {train_status} ")
        print(f"Test Status: {test_status} ")
        raise Exception(f"Dataset creation failed ")
