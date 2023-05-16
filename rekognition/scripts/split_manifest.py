# Sample Input
# {
#  "version": "0.0.1",
#  "parameters": [
#    {
#      "Name": "VERSION",
#      "Type": "PLAINTEXT",
#      "Value": "0.0.1"
#    },
#    {
#      "Name": "ANIMAL",
#      "Type": "PLAINTEXT",
#      "Value": "cat"
#    },
#    {
#      "Name": "ENV_PREFIX",
#      "Type": "PLAINTEXT",
#      "Value": "dv"
#    }
#  ]
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
from http.client import ResponseNotReady
import sys
import json
import os
from collections import Counter
import boto3
import numpy as np
import pandas as pd
import smart_open
from sklearn.model_selection import StratifiedShuffleSplit


def write_jsonl_subset(json_list, line_numbers, filepath):
    with smart_open.open(filepath, "wt") as ff:
        for line_num in line_numbers:
            ff.write(json.dumps(json_list[line_num]) + "\n")


def filter_low_count_classes(line_index, class_names, min_count=2):
    """
    split off classes that occur infrequently
    the StratifiedShuffleSplit class will fail if the number of occurances
    is less than the number of splits (2 in this case)
    """
    class_counts = Counter(class_names)
    classes_to_drop = set()
    for classname, count in class_counts.items():
        if count < min_count:
            classes_to_drop.add(classname)

    # removed idx, classnames
    filtered_line_idx = []
    filtered_class_names = []

    # remaining
    new_class_names = []
    new_line_idx = []

    for idx, classname in zip(line_index, class_names):
        if classname in classes_to_drop:
            filtered_line_idx.append(idx)
            filtered_class_names.append(classname)
        else:
            new_line_idx.append(idx)
            new_class_names.append(classname)
    return filtered_line_idx, filtered_class_names, new_line_idx, new_class_names


def main(input_filepath, test_frac=0.2):
    manifest_lines = []

    with smart_open.open(input_filepath) as ff:
        for line in ff:
            manifest_lines.append(json.loads(line))

    orig_line_index = []
    orig_class_names = []
    for k, json_line in enumerate(manifest_lines):
        for key in json_line:
            if "metadata" in key:
                classname = json_line[key]["class-name"]
                orig_line_index.append(k)
                orig_class_names.append(classname)
                break

    (
        filtered_line_idx,
        filtered_class_idx,
        line_index,
        class_names,
    ) = filter_low_count_classes(orig_line_index, orig_class_names)

    splitter = StratifiedShuffleSplit(n_splits=1, test_size=test_frac, random_state=888)

    splitter = StratifiedShuffleSplit(n_splits=1, test_size=test_frac, random_state=888)

    for train_idx, test_idx in splitter.split(line_index, class_names):
        # add low number examples back in to training data
        if filtered_line_idx:
            train_idx = np.concatenate((train_idx, filtered_line_idx))
            filtered_line_idx = []
        train_filepath = input_filepath.replace(".manifest", "") + "-train.manifest"
        test_filepath = input_filepath.replace(".manifest", "") + "-test.manifest"
        write_jsonl_subset(manifest_lines, train_idx, train_filepath)
        write_jsonl_subset(manifest_lines, test_idx, test_filepath)


if __name__ == "__main__":
    s3 = boto3.client("s3")

    animal = os.environ.get("ANIMAL")
    version = os.environ.get("VERSION")
    env_prefix = os.environ.get("ENV_PREFIX")
    uuid = os.environ.get("UUID")
    s3_bucket = os.environ.get("S3_BUCKET")

    main(f"{animal}.manifest")

    response = s3.upload_file(
        f"{animal}-train.manifest",
        s3_bucket,
        f"{version}/{animal}/{uuid}/{animal}-train.manifest",
    )

    response = s3.upload_file(
        f"{animal}-test.manifest",
        s3_bucket,
        f"{version}/{animal}/{uuid}/{animal}-test.manifest",
    )
