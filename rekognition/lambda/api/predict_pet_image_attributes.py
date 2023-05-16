# Sample Input
# {
#   "bucket": "dv-rekognition-bucket-s3b",
#   "photo": "testing/cat.jpg",
#   "animal": "cat"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import io
import os
import json
import csv
import boto3
import base64
from boto3.dynamodb.conditions import Key


DEFAULT_TOP_N = 3
SEPARATOR = "||"
# separates test name from ids in labels, must match separator in
# scripts/create_animal_manifest.py
attributes_to_send = os.environ["ATTRIBUTES_TO_SEND"]
minimum_confidence = os.environ["MINIMUM_CONFIDENCE"]
rekognition_client = boto3.client("rekognition")
ssm = boto3.client("ssm")
cloudwatch = boto3.client("cloudwatch")
s3 = boto3.client("s3")


def get_breed_data(pf_breed_name):
    """
    retrieve breed attributes from dynamodb table
    """
    dynamo_resource = boto3.resource("dynamodb")
    table = os.environ["ANIMAL_ATTRIBUTES_DDB_TBL"]
    table = dynamo_resource.Table(table)
    response = table.query(KeyConditionExpression=Key("uuid").eq(pf_breed_name))
    return response


def get_breed_prediction(
    animal_type, bucket, prefix, min_confidence=minimum_confidence
):
    """
    gets predictions for an image in s3 using the Rekognition image classification endpoint
    for the animal type.  The endpoint returns classifications for breed, coat, and color.
    It is possible that any of these will have no predictions, in which case the list of
    candidates in the response will be empty.
    """
    try:
        MODEL_REKOGNITION_ENDPOINT = str(
            ssm.get_parameter(
                Name=f"/animal-rekognition/{animal_type}/model/model-arn"
            )["Parameter"]["Value"]
        )
        result = rekognition_client.detect_custom_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": prefix}},
            MinConfidence=min_confidence,
            ProjectVersionArn=MODEL_REKOGNITION_ENDPOINT,
        )
        write_logs = cloudwatch.put_metric_data(
            Namespace="Petfinder/Rekognition/Model/DetectCustomLabels",
            MetricData=[
                {
                    "MetricName": "RekognitionDetectCustomLabelsCalls",
                    "Dimensions": [
                        {"Name": "ModelArn", "Value": MODEL_REKOGNITION_ENDPOINT},
                    ],
                    "Value": 1.0,
                    "Unit": "Count",
                },
            ],
        )
    except Exception as e:
        print(e)
        result = {}
    return result


def split_name_id(label):
    """
    Parses text label and id if one is present
    convention for labels is:
    breed-<BreedName>||<BreedId>
    e.g.
    breed-Tiger||137
    if no id is present, returns an empty string
    """
    tup = label.split(SEPARATOR)
    return tup + [""] * max(0, 2 - len(tup))


def partition_labels(label_list):
    """
    Parses Rekognition labels into separate lists
    """
    labels = {"breed": [], "species": []}
    for label_dict in label_list:
        if label_dict["Name"].startswith("species-"):
            species_name, species_id = split_name_id(label_dict["Name"][8:])
            label_dict["Name"] = species_name
            label_dict["Id"] = species_id
            labels["species"].append(label_dict)
        elif label_dict["Name"].startswith("breed-"):
            breed_name, breed_id = split_name_id(label_dict["Name"][6:])
            label_dict["Name"] = breed_name
            label_dict["Id"] = breed_id
            labels["breed"].append(label_dict)
    return labels


def int_cast(val):
    try:
        return int(float(val))
    except Exception:
        return val


def get_inferred_attributes(
    bucket, image_prefix, animal_type, min_confidence=5, top_n=3
):

    breed_response = get_breed_prediction(
        animal_type, bucket, image_prefix, min_confidence
    )

    try:
        labels = partition_labels(breed_response["CustomLabels"])

    except KeyError as e:
        labels = {"breed": [], "species": []}

    try:
        breed_name = labels["breed"][0]["Name"]
        breed_data = get_breed_data(breed_name)
        all_attrs = breed_data["Items"][0]
        attributes = {
            k: int_cast(v) for k, v in all_attrs.items() if k in attributes_to_send
        }
    except (IndexError, KeyError) as e:
        attributes = {"ERROR": str(e)}

    ret_dict = {
        "breed": labels["breed"][:top_n],
        "species": labels["species"][:top_n],
        "attribute_1": attributes.get("attribute_1", None),
        "attribute_2": attributes.get("attribute_2", None),
        "attribute_3": attributes.get("attribute_3", None),
    }

    return ret_dict


def lambda_handler(event, context):
    animal_type = event["animal_type"]
    path_chunks = event["image_path"].split("/")
    bucket = path_chunks[2]
    prefix = os.path.join(*path_chunks[3:])
    top_n = event.get("top_n", DEFAULT_TOP_N)

    inferred_attributes = get_inferred_attributes(
        bucket=bucket, image_prefix=prefix, animal_type=animal_type, top_n=top_n
    )

    return inferred_attributes
