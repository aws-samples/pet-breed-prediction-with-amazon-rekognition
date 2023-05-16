## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import os
import sys
import time
import json
from concurrent.futures import ThreadPoolExecutor

import boto3
import pandas as pd
import smart_open
from sklearn.metrics import classification_report

script_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.append(os.path.join(script_dir, "../lambda/api"))

# default values for environmental variables needed for import
os.environ.update(
    {
        "ATTRIBUTES_TO_SEND": "",
        "MINIMUM_CONFIDENCE": "1 ",
        "AWS_DEFAULT_REGION": "us-east-1",
    }
)
from predict_pet_image_attributes import partition_labels, split_name_id

rekognition_client = boto3.client("rekognition")
ssm = boto3.client("ssm")
s3 = boto3.client("s3")


def get_prediction(bucket, prefix, model_arn, min_confidence=5):  # 5% is arbitrary
    try:
        result = rekognition_client.detect_custom_labels(
            Image={"S3Object": {"Bucket": bucket, "Name": prefix}},
            MinConfidence=min_confidence,
            ProjectVersionArn=model_arn,
        )
    except Exception as e:
        print(e)
        result = {}
    return result


def predict(tup):
    return get_prediction(*tup)


if __name__ == "__main__":

    ANIMAL = os.environ.get("ANIMAL")
    S3_BUCKET = os.environ.get("S3_BUCKET")
    UUID = os.environ.get("UUID")
    MODEL_NAME = os.environ.get("MODEL_NAME")
    PROJECT_ARN = os.environ.get("PROJECT_ARN")
    VERSION = os.environ.get("VERSION")
    TEST_MANIFEST = f"s3://{S3_BUCKET}/{VERSION}/{ANIMAL}/{UUID}/{ANIMAL}-test.manifest"
    TRAIN_MANIFEST = (
        f"s3://{S3_BUCKET}/{VERSION}/{ANIMAL}/{UUID}/{ANIMAL}-test.manifest"
    )

    RESULTS_DIR = os.environ.get("RESULTS_DIR", "./")

    model_versions = rekognition_client.describe_project_versions(
        ProjectArn=PROJECT_ARN,
        VersionNames=[
            MODEL_NAME,
        ],
    )

    model_arn = ""
    versions = model_versions["ProjectVersionDescriptions"]
    for version in versions:
        if MODEL_NAME in version["ProjectVersionArn"]:
            model_arn = version["ProjectVersionArn"]

    print(f"model_arn: {model_arn}")

    manifest_lines = []
    with smart_open.open(TEST_MANIFEST) as ff:
        for line in ff:
            manifest_lines.append(json.loads(line))

    filepaths = []
    predictions = []
    y_true = []
    y_pred = []
    min_confidence = 1  # %

    for line in manifest_lines:
        if "lable-name" in line:
            true_breed = line["label-name"]
        else:
            true_breed = None
        for top_key in line.keys():
            # NB: requires breed label (and no others) to have "breed" in the name
            if "breed" in top_key and "-metadata" in top_key:
                true_breed = split_name_id(
                    line[top_key]["class-name"].split("-", maxsplit=1)[-1]
                )[0]
                break
        if true_breed is None:
            raise Exception("Can't find breed label in manifest")

        y_true.append(true_breed)
        s3path = line["source-ref"]
        bucket, prefix = s3path.replace("s3://", "").split("/", 1)
        response = get_prediction(bucket, prefix, model_arn, min_confidence)

        try:
            if len(response["CustomLabels"]) == 0:
                y_pred.append("NAN")
                predictions.append({})
            else:
                raw_labels = response["CustomLabels"]
                labels = partition_labels(raw_labels)
                y_pred.append(labels["breed"][0]["Name"])
                predictions.append(
                    {label["Name"]: label["Confidence"] for label in labels["breed"]}
                )

        except Exception as e:
            predictions.append({})
            y_pred.append("NAN")

    preds_df = pd.DataFrame(predictions)
    preds_df["y_true"] = y_true
    preds_df.to_csv(os.path.join(RESULTS_DIR, "predictions.csv"))

    metrics_dict = classification_report(y_true, y_pred, output_dict=True)
    with open(os.path.join(RESULTS_DIR, "classification_metrics.json"), "w") as ff:
        json.dump(metrics_dict, ff)
