# Sample Input
# {
#   "test_dataset_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-dog-rekognition-use1-rkg/dataset/test/1648474994113",
#   "train_dataset_arn": "arn:aws:rekognition:us-east-1:123456789123:project/dv-dog-rekognition-use1-rkg/dataset/train/1648474994277",
#   "animal": "dog",
#   "status": "CREATE_COMPLETE",
#   "version": "0.0.1"
# }
## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, os, uuid, datetime, time


def handler(event, context):

    rekognition = boto3.client("rekognition")
    cloudwatch = boto3.client("cloudwatch")

    animal_type = event["animal"]
    previous_model_arn = event["previous_model_arn"]
    previous_project_arn = event["previous_project_arn"]
    version_name = event["version_name"]

    rekognition_calls = cloudwatch.get_metric_data(
        MetricDataQueries=[
            {
                "Id": "modelusage",
                "MetricStat": {
                    "Metric": {
                        "Namespace": "Petfinder/Rekognition/Model/DetectCustomLabels",
                        "MetricName": "RekognitionDetectCustomLabelsCalls",
                        "Dimensions": [
                            {"Name": "ModelArn", "Value": previous_model_arn},
                        ],
                    },
                    "Period": 60,
                    "Stat": "Sum",
                    "Unit": "Count",
                },
                "ReturnData": True,
            },
        ],
        StartTime=datetime.datetime.now() - datetime.timedelta(minutes=15),
        EndTime=datetime.datetime.now(),
    )

    detect_custom_labels_array = rekognition_calls["MetricDataResults"][0]["Values"]
    sum_of_calls = 0
    for i in detect_custom_labels_array:
        sum_of_calls += int(i)

    if sum_of_calls > 0:
        raise Exception(
            f"Waiting for Model to Drain Connections, {sum_of_calls} calls in last 15 minutes: {previous_project_arn}"
        )

    describe_project_version = rekognition.describe_project_versions(
        ProjectArn=previous_project_arn
    )

    status = describe_project_version["ProjectVersionDescriptions"][0]["Status"]

    if status == "STOPPED":
        ssm = boto3.client("ssm")
        topic_arn = ssm.get_parameter(Name="/animal-rekognition/sns/arn")["Parameter"][
            "Value"
        ]

        sns = boto3.client("sns")
        publish = sns.publish(
            TopicArn=topic_arn,
            Message=f"Model promoted: {version_name}\n Previous model 'Stopped'",
            Subject=f"Model promoted for: {animal_type}",
        )
        return {"status": "SUCCESS", "animal": animal_type}
    elif status == "RUNNING":
        stop_project_version = rekognition.stop_project_version(
            ProjectVersionArn=previous_model_arn
        )
        print(f"Stopping Model: {previous_project_arn}")
        time.sleep(30)
        raise Exception(f"Waiting for Model to Stop: {previous_project_arn}")
    elif status == "STOPPING":
        time.sleep(30)
        raise Exception(f"Waiting for Model to Stop: {previous_project_arn}")
    else:
        print(f"Previous Model Status: {status}")
