## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import os
import sys
import json
from venv import create

import boto3
import smart_open


def make_label_metadata(label_name):
    metadata = {
        "confidence": 1,
        "class-name": label_name,
        "human-annotated": "yes",
        "creation-date": "1997-01-01T00:00:00.000",
        "type": "groundtruth/image-classification",
    }
    return metadata


def create_label_row(s3_path, label_dict):
    # each row of a manifest file is a json line with this information (for a labeling job)
    custom_image_label = {
        "source-ref": s3_path,
    }
    for i, key_value in enumerate(label_dict.items()):
        key, label_name = key_value
        if label_name != "":
            label_type = f"classification_{key}"
            metadata_key = (
                f"{label_type}-metadata"  # must have this form per specification
            )
            custom_image_label[
                label_type
            ] = i  # assign an integer to this type of label
            custom_image_label[metadata_key] = make_label_metadata(
                key + "-" + label_name
            )
    custom_image_label["label-names"] = sorted(
        [k + "-" + v for k, v in label_dict.items()]
    )  # convenience field
    return custom_image_label


def to_manifest(prefix_list, label_dict_list, bucket, output_path):

    counter = 0
    with smart_open.open(output_path, "wt") as cc:
        for prefix, label_dict in zip(prefix_list, label_dict_list):
            s3_path = f"s3://{bucket}/{prefix}"
            cc.write(json.dumps(create_label_row(s3_path, label_dict)) + "\n")
            counter += 1
    return counter


def main(bucket, img_prefix, output_filepath):
    prefix_list = []

    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket, Prefix=img_prefix)
    for page in pages:
        for obj in page["Contents"]:
            prefix = obj["Key"]
            if prefix.endswith(".jpg"):
                prefix_list.append(prefix)

    classlist = [ff.split("/")[-1].rsplit("_", 1)[0] for ff in prefix_list]
    label_dict_list = [
        {
            "species": "dog" if cn[0].islower() else "cat",
            "breed": cn.replace("_", " ").title(),
        }
        for cn in classlist
    ]
    count = to_manifest(prefix_list, label_dict_list, bucket, output_filepath)


if __name__ == "__main__":

    bucket = os.environ.get("S3_BUCKET")
    img_prefix = "OxfordPets/images"

    output_filepath = os.environ.get("OUTPUT_MANIFEST_PATH", "oxford-pets.manifest")
    main(bucket, img_prefix, output_filepath)
