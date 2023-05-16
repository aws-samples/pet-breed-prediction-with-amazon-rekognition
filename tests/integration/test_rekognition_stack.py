# Copyright 2011-2013 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at http://aws.amazon.com/apache2.0/
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
# from msilib.schema import Environment
import boto3, json, os, yaml, sys

# Import constants like VERSION
script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, "../.."))
from rekognition.utils.constants import *

env_perfix = os.environ.get("CDK_ENVIRONMENT", "dev")

session = boto3.Session(region_name="us-east-1")
ssm = session.client(
    "ssm",
    region_name="us-east-1",
)
bucket_name = ssm.get_parameter(Name="/animal-rekognition/s3/name")["Parameter"][
    "Value"
]


def get_config():
    config_path = os.path.join("config", f"{env_perfix}.yaml")
    with open(config_path) as fr:
        return yaml.safe_load(fr)


config = get_config()


def read_cat():
    with open("./tests/data/predict_cat_attributes.json", "r") as filehandle:
        cat = json.load(filehandle)

    return cat


def read_cat_corrections():
    with open("./tests/data/correct_cat_attributes.json", "r") as filehandle:
        cat = json.load(filehandle)

    return cat


def read_dog():
    with open("./tests/data/predict_dog_attributes.json", "r") as filehandle:
        cat = json.load(filehandle)

    return cat


def read_dog_corrections():
    with open("./tests/data/correct_dog_attributes.json", "r") as filehandle:
        cat = json.load(filehandle)

    return cat


def test_cat_image_response():

    # Get the function name from SSM
    function_name = ssm.get_parameter(
        Name="/animal-rekognition/lambda/predict_image_attributes/name"
    )["Parameter"]["Value"]

    _lambda = session.client(
        "lambda",
        region_name="us-east-1",
    )

    key = f"{bucket_name}/{VERSION}"

    test_event = read_cat()
    test_event["image_path"] = test_event["image_path"].replace("S3_BUCKET", key)

    response = _lambda.invoke(
        FunctionName=function_name,
        Payload=f"{json.dumps(test_event)}",
    )
    res_json = json.loads(response["Payload"].read().decode("utf-8"))

    assert res_json["species"][0]["Name"] in "cat"
    assert res_json["breed"][0]["Name"] in "Ragdoll"
    assert res_json["breed"][0]["Confidence"] > 0
    assert response["StatusCode"] == 200


def test_dog_image_response():

    # Get the function name from SSM
    function_name = ssm.get_parameter(
        Name="/animal-rekognition/lambda/predict_image_attributes/name"
    )["Parameter"]["Value"]

    _lambda = session.client(
        "lambda",
        region_name="us-east-1",
    )

    key = f"{bucket_name}/{VERSION}"

    test_event = read_dog()
    test_event["image_path"] = test_event["image_path"].replace("S3_BUCKET", key)

    response = _lambda.invoke(
        FunctionName=function_name,
        Payload=f"{json.dumps(test_event)}",
    )
    res_json = json.loads(response["Payload"].read().decode("utf-8"))

    assert res_json["species"][0]["Name"] in "dog"
    assert res_json["breed"][0]["Name"] in "Beagle"
    assert res_json["breed"][0]["Confidence"] > 0
    assert response["StatusCode"] == 200
