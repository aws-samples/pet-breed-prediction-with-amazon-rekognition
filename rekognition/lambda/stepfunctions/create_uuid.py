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

    short_uuid = str(uuid.uuid4())[:8]

    return {
        "animal": event["animal"],
        "uuid": short_uuid,
    }
