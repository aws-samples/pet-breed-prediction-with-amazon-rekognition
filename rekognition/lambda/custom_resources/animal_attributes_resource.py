## Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
## SPDX-License-Identifier: MIT-0
import json, boto3, os, csv, time


s3 = boto3.resource("s3")
dynamodb = boto3.resource("dynamodb")
tableName = os.environ["table_name"]


def handler(event, context):
    print(f"\n Event: {event}\n")
    print(f"\n context: {context}\n")
    print(f"\nTableName: {tableName}\n")
    print(f"\nSeed Dogs\n")
    create(event, context, "dog-breeds.csv")
    print("Dog Attributes Seeded")
    time.sleep(2)
    create(event, context, "cat-breeds.csv")
    print("Cat Attributes Seeded")
    print("Seed Attributes Complete")


def create(event, context, filename):
    try:
        table = dynamodb.Table(tableName)
    except:
        print(
            "Error loading DynamoDB table. Check if table was created correctly and environment variable."
        )

    batch_size = 100
    batch = []

    # DictReader is a generator; not stored in memory
    i = 0
    with open(filename) as csv_file:
        for row in csv.DictReader(csv_file):
            print(str(i) + str(row))
            if len(batch) >= batch_size:
                write_to_dynamo(batch)
                batch.clear()

            batch.append(row)
            i = i + 1
        if batch:
            write_to_dynamo(batch)

    return {"statusCode": 200, "body": json.dumps("Uploaded to DynamoDB Table")}


def write_to_dynamo(rows):
    try:
        table = dynamodb.Table(tableName)
    except:
        print(
            "Error loading DynamoDB table. Check if table was created correctly and environment variable."
        )

    try:
        with table.batch_writer() as batch:
            for i in range(len(rows)):
                batch.put_item(Item=rows[i])
    except Exception as e:
        print(f"Error executing batch_writer: {e}")


def update(event, context):
    pass


def delete(event, context):
    pass
