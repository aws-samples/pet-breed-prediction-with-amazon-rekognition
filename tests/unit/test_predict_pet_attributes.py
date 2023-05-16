## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
from lib2to3.pgen2.token import GREATER
import sys
import json
import os
import unittest
import boto3
import mock
from mock import patch
from moto import mock_s3, mock_dynamodb, mock_rekognition


script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, "../../rekognition/utils/"))
from constants import *

config = get_config()
atrributes_to_send = config["attributesToSend"]
attributes_comma_delim = ",".join(atrributes_to_send)
# Set env vars used by the lambda
os.environ["ATTRIBUTES_TO_SEND"] = attributes_comma_delim
os.environ["MINIMUM_CONFIDENCE"] = f"{config['minConfidence']}"


# necessary because the lambda function resources are not a python module and lambda is a keyword
script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, "../../rekognition/lambda/api"))
from predict_pet_image_attributes import lambda_handler, partition_labels


S3_BUCKET_NAME = "s3-bucket"
DEFAULT_REGION = "us-east-1"

S3_TEST_FILE_KEY = "cat.jpg"
S3_TEST_FILE_CONTENT = os.path.join(script_dir, "../data/cat.jpg")
SAMPLE_REKOGNITION_RESPONSE = os.path.join(
    script_dir, "../resources/rekognition_response.json"
)


def rekognition_response(*args, **kwargs):
    with open(SAMPLE_REKOGNITION_RESPONSE) as ff:
        return json.load(ff)


@mock_s3
@mock_dynamodb
@mock_rekognition
@mock.patch("predict_pet_image_attributes.get_breed_data")
@mock.patch("predict_pet_image_attributes.get_breed_prediction")
class TestLambdaFunction(unittest.TestCase):

    # S3 setup
    def setUp(self):
        self.s3 = boto3.resource("s3", region_name=DEFAULT_REGION)
        self.s3_bucket = self.s3.create_bucket(Bucket=S3_BUCKET_NAME)
        self.s3_bucket.put_object(Key=S3_TEST_FILE_KEY, Body=S3_TEST_FILE_CONTENT)

    def test_partition_labels(self, gbp_patch, bd_patch):
        labels = partition_labels(rekognition_response()["CustomLabels"])
        self.assertEqual("British Shorthair", labels["breed"][0]["Name"])

    def test_handler(self, gbp_patch, bd_patch):
        gbp_patch.return_value = rekognition_response()
        event = {
            "animal_type": "cat",
            "image_path": f"s3://{S3_BUCKET_NAME}/{S3_TEST_FILE_KEY}",
        }
        output = lambda_handler(event, {})
        self.assertEqual("British Shorthair", output["breed"][0]["Name"])
