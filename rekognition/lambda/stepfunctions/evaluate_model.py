# Sample Input
# {
#   "version": "0.0.1",
#   "parameters": [
#     {
#       "Name": "VERSION",
#       "Type": "PLAINTEXT",
#       "Value": "0.0.1"
#     },
#     {
#       "Name": "UUID",
#       "Type": "PLAINTEXT",
#       "Value": "9dfb55a8"
#     },
#     {
#       "Name": "ANIMAL",
#       "Type": "PLAINTEXT",
#       "Value": "cat"
#     },
#     {
#       "Name": "PROJECT_ARN",
#       "Type": "PLAINTEXT",
#       "Value": "arn:aws:rekognition:us-east-1:123456789123:project/dv-rekognition-cat-training-0.0.1-9dfb55a8/1649029454598"
#     },
#     {
#       "Name": "ENV_PREFIX",
#       "Type": "PLAINTEXT",
#       "Value": "dv"
#     },
#     {
#       "Name": "MODEL_NAME",
#       "Type": "PLAINTEXT",
#       "Value": "dv-rekognition-cat-training-0-0-1-9dfb55a8"
#     },
#     {
#       "Name": "S3_BUCKET",
#       "Type": "PLAINTEXT",
#       "Value": "dv-rekognition-bucket-s3b"
#     }
#   ]
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, os


def handler(event, context):

    dog_accuracy = float(os.environ.get("dog_accuracy"))
    cat_accuracy = float(os.environ.get("cat_accuracy"))

    animal = ""
    version = ""
    uuid = ""
    version_name = ""
    s3_bucket = ""
    project_arn = ""
    for parameter in event["parameters"]:
        if parameter["Name"] == "ANIMAL":
            animal = parameter["Value"]
        elif parameter["Name"] == "VERSION":
            version = parameter["Value"]
        elif parameter["Name"] == "UUID":
            uuid = parameter["Value"]
        elif parameter["Name"] == "MODEL_NAME":
            version_name = parameter["Value"]
        elif parameter["Name"] == "S3_BUCKET":
            s3_bucket = parameter["Value"]
        elif parameter["Name"] == "PROJECT_ARN":
            project_arn = parameter["Value"]

    ssm = boto3.client("ssm")
    rekognition = boto3.client("rekognition")
    s3 = boto3.client("s3")

    download_file = s3.download_file(
        s3_bucket,
        f"{version}/{animal}/{uuid}/evaluation/classification_metrics.json",
        "/tmp/classification_metrics.json",
    )

    classification_metrics = open("/tmp/classification_metrics.json")
    model_metrics = json.load(classification_metrics)
    accuracy = model_metrics["accuracy"]

    promote = True
    if animal == "dog" and accuracy < dog_accuracy:
        promote = False
    elif animal == "cat" and accuracy < cat_accuracy:
        promote = False

    classification_metrics.close()

    if promote == False:
        return {
            "animal": animal,
            "promote": promote,
            "version_name": version_name,
            "project_arn": project_arn,
            "accuracy": accuracy,
        }
    elif promote == True:
        return {
            "animal": animal,
            "promote": promote,
            "version_name": version_name,
            "project_arn": project_arn,
            "accuracy": accuracy,
        }
