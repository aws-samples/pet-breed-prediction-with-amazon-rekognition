#!/usr/bin/env python3
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import os

import aws_cdk as cdk

from rekognition.rekognition_stack import RekognitionStack
from rekognition.utils.constants import *

stack_name = f"{ENV_PREFIX}-rekognition-use1-cfm"

app = cdk.App()

RekognitionStack(
    app,
    stack_name,
    env=cdk.Environment(account=ACCOUNT_ID, region=DEPLOY_REGION),
)

app.synth()
