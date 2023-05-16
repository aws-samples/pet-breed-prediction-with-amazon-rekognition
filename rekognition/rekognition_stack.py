# Copyright 2011-2013 Amazon.com, Inc. or its affiliates. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at http://aws.amazon.com/apache2.0/
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
from codecs import Codec
from pyclbr import Function
from re import S
from aws_cdk import (
    Duration,
    Stack,
    aws_rekognition as rekognition,
    aws_lambda as _lambda,
    aws_ssm as ssm,
    aws_iam as iam,
    aws_ec2 as ec2,
    aws_stepfunctions as stepfunctions,
    aws_stepfunctions_tasks as tasks,
    aws_dynamodb as dynamodb,
    aws_ecr as ecr,
    custom_resources as cr,
    aws_codebuild as codebuild,
    aws_s3 as s3,
    aws_logs as logs,
    aws_kms as kms,
    aws_sns as sns,
    aws_events as events,
    aws_events_targets as targets,
)

import aws_cdk as cdk
import json
from constructs import Construct
from rekognition.utils.constants import *

config = get_config()


class RekognitionStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.create_kms_key()
        self.create_dynamo_table()
        self.create_sns_topic()
        self.create_s3_bucket()
        self.create_iam_role()
        self.create_codebuild_project()
        self.create_lambdas()
        self.seed_dynamo_table()
        self.create_stepfunction_tasks()
        self.create_state_machine()
        self.create_ssm_entries()

    def create_kms_key(self):
        self.kms_key = kms.Key(
            self,
            resource_name(kms.Key, "rekognition-key"),
            alias=resource_name(kms.Key, "rekognition-key"),
            enable_key_rotation=True,
            policy=iam.PolicyDocument(
                statements=[
                    iam.PolicyStatement(
                        actions=[
                            "kms:*",
                        ],
                        principals=[iam.AccountRootPrincipal()],
                        resources=[
                            "*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "kms:Encrypt*",
                            "kms:Decrypt*",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:Describe*",
                        ],
                        principals=[
                            iam.ServicePrincipal(f"events.amazonaws.com"),
                            iam.ServicePrincipal(f"cloudwatch.amazonaws.com"),
                        ],
                        resources=[
                            f"arn:aws:states:{DEPLOY_REGION}:{ACCOUNT_ID}:stateMachine:{ENV_PREFIX}-rekognition-state-machine-use1-stm",
                            f"arn:aws:states:{DEPLOY_REGION}:{ACCOUNT_ID}:execution:{ENV_PREFIX}-rekognition-state-machine-use1-stm:*",
                            f"arn:aws:sns:{DEPLOY_REGION}:{ACCOUNT_ID}:{ENV_PREFIX}-rekognition-topic-use1-sns",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "kms:GenerateDataKey*",
                            "kms:Decrypt*",
                        ],
                        principals=[
                            iam.ServicePrincipal("sns.amazonaws.com"),
                            iam.ServicePrincipal(f"events.amazonaws.com"),
                        ],
                        resources=[
                            "*",
                        ],
                    ),
                    iam.PolicyStatement(
                        actions=[
                            "kms:Encrypt*",
                            "kms:Decrypt*",
                            "kms:ReEncrypt*",
                            "kms:GenerateDataKey*",
                            "kms:Describe*",
                        ],
                        principals=[
                            iam.ServicePrincipal(f"logs.{DEPLOY_REGION}.amazonaws.com"),
                        ],
                        resources=[
                            "*",
                        ],
                        conditions={
                            "ArnEquals": {
                                "kms:EncryptionContext:aws:logs:arn": f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-rekognition-state-machine-logs-use1-log"
                            }
                        },
                    ),
                ]
            ),
        )

    def create_s3_bucket(self):
        self.s3_bucket = s3.Bucket(
            self,
            resource_name(s3.Bucket, "rekognition-bucket"),
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self.kms_key,
            server_access_logs_prefix="logs",
            versioned=True,
            enforce_ssl=True,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

    def create_state_machine(self):
        log_group_name = resource_name(logs.LogGroup, "rekognition-state-machine-logs")
        self.state_machine_log_group = logs.LogGroup(
            self,
            "Recognition State Machine Log Group",
            log_group_name=log_group_name,
            encryption_key=self.kms_key,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )
        # Create state machine role for triggering machine and sending sns notifications
        rekognition_state_machine_name = resource_name(
            stepfunctions.StateMachine, "rekognition-state-machine"
        )
        self.state_machine_role = iam.Role(
            self,
            resource_name(iam.Role, "rekognition-statemachine-role"),
            role_name=resource_name(iam.Role, "rekognition-statemachine-role"),
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
            inline_policies={
                "StatePermissions": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=[
                                "kms:Encrypt*",
                                "kms:Decrypt*",
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:Describe*",
                            ],
                            resources=[
                                self.kms_key.key_arn,
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "sns:Publish*",
                            ],
                            resources=[
                                self.sns_topic.topic_arn,
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "events:PutTargets",
                                "events:PutRule",
                                "events:DescribeRule",
                            ],
                            resources=[
                                f"arn:aws:events:{DEPLOY_REGION}:{ACCOUNT_ID}:rule/StepFunctionsGetEventsForStepFunctionsExecutionRule",
                                f"arn:aws:events:{DEPLOY_REGION}:{ACCOUNT_ID}:rule/StepFunctionsGetEventForCodeBuildStartBuildRule",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "states:StartExecution",
                                "states:DescribeExecution",
                                "states:ListExecutions",
                            ],
                            resources=[
                                f"arn:aws:states:{DEPLOY_REGION}:{ACCOUNT_ID}:stateMachine:{rekognition_state_machine_name}*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "lambda:InvokeFunction",
                            ],
                            resources=[
                                f"arn:aws:lambda:{DEPLOY_REGION}:{ACCOUNT_ID}:function:{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "codebuild:StartBuild",
                                "codebuild:StopBuild",
                                "codebuild:BatchGetBuilds",
                                "codebuild:BatchGetReports",
                            ],
                            resources=[
                                f"arn:aws:codebuild:{DEPLOY_REGION}:{ACCOUNT_ID}:project/{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "logs:CreateLogDelivery",
                                "logs:GetLogDelivery",
                                "logs:UpdateLogDelivery",
                                "logs:DeleteLogDelivery",
                                "logs:ListLogDeliveries",
                                "logs:PutLogEvents",
                                "logs:PutResourcePolicy",
                                "logs:DescribeResourcePolicies",
                                "logs:DescribeLogGroups",
                            ],
                            resources=[
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{log_group_name}/*",
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{log_group_name}*",
                            ],
                        ),
                    ]
                )
            },
        )
        self.state_machine_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchEventsFullAccess")
        )
        self.state_machine_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchLogsFullAccess")
        )

        # Create state machine definition
        self.state_machine_definition = self.create_uuid_job.next(
            self.create_manifest_job.next(
                self.create_dataset_job.next(
                    self.describe_dataset_job.next(
                        self.train_model_job.next(
                            self.describe_model_training_job.next(
                                self.start_model_inference_job.next(
                                    self.describe_model_inference_job.next(
                                        self.create_evaluation_metrics_job.next(
                                            self.evaluate_model_job.next(
                                                stepfunctions.Choice(
                                                    self,
                                                    "Promote Project Model Choice",
                                                )
                                                .when(
                                                    stepfunctions.Condition.boolean_equals(
                                                        "$.promote", False
                                                    ),
                                                    self.skip_promotion_stop_model_job.next(
                                                        self.do_not_promote
                                                    ),
                                                )
                                                .when(
                                                    stepfunctions.Condition.boolean_equals(
                                                        "$.promote", True
                                                    ),
                                                    self.update_model_ssm_job.next(
                                                        stepfunctions.Choice(
                                                            self,
                                                            "Stop Previous Model Inference",
                                                        )
                                                        .when(
                                                            stepfunctions.Condition.boolean_equals(
                                                                "$.previous_model_running",
                                                                True,
                                                            ),
                                                            self.wait_before_stop_previous_model.next(
                                                                self.stop_previous_model_job.next(
                                                                    self.model_promote_and_previous_model_stopped
                                                                )
                                                            ),
                                                        )
                                                        .when(
                                                            stepfunctions.Condition.boolean_equals(
                                                                "$.previous_model_running",
                                                                False,
                                                            ),
                                                            self.model_deployed,
                                                        )
                                                    ),
                                                )
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            )
        )

        # create state machine using definition
        self.training_state_machine = stepfunctions.StateMachine(
            self,
            "Training Rekognition State Machine",
            state_machine_name=resource_name(
                stepfunctions.StateMachine, "rekognition-state-machine"
            ),
            definition=self.state_machine_definition,
            logs=stepfunctions.LogOptions(
                destination=self.state_machine_log_group,
                level=stepfunctions.LogLevel.ALL,
            ),
            timeout=Duration.hours(24),
            role=self.state_machine_role.without_policy_updates(),
        )
        # notify on Failure, abort, or time out
        self.failure_notification = events.Rule(
            self,
            "rekognition-failure-notification",
            rule_name=resource_name(events.Rule, "rekognition-failure-notification"),
            event_pattern=events.EventPattern(
                source=["aws.states"],
                detail={
                    "stateMachineArn": [self.training_state_machine.state_machine_arn],
                    "status": ["FAILED", "ABORTED", "TIMED_OUT"],
                },
                detail_type=["Step Functions Execution Status Change"],
            ),
        )

        self.failure_notification.add_target(targets.SnsTopic(self.sns_topic))

        self.trigger_role = iam.Role(
            self,
            "rekognition-trigger-role",
            role_name=resource_name(iam.Role, "rekognition-trigger-role"),
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
        )
        # Trigger every week in production
        self.event_trigger = events.Rule(
            self,
            "rekognition-statemachine-trigger",
            rule_name=resource_name(events.Rule, "rekognition-statemachine-trigger"),
            schedule=events.Schedule.rate(cdk.Duration.days(7)),
        )
        self.event_trigger.add_target(
            targets.SfnStateMachine(
                self.training_state_machine,
                input=events.RuleTargetInput.from_object({"animal": "dog"}),
                role=self.trigger_role,
            )
        )
        self.event_trigger.add_target(
            targets.SfnStateMachine(
                self.training_state_machine,
                input=events.RuleTargetInput.from_object({"animal": "cat"}),
                role=self.trigger_role,
            )
        )

    def create_sns_topic(self):
        self.sns_topic = sns.Topic(
            self,
            resource_name(sns.Topic, "rekognition-topic"),
            topic_name=resource_name(sns.Topic, "rekognition-topic"),
            master_key=self.kms_key,
        )
        self.sns_topic.add_to_resource_policy(
            iam.PolicyStatement(
                principals=[iam.ServicePrincipal("events.amazonaws.com")],
                actions=[
                    "sns:Publish",
                ],
                resources=[
                    f"arn:aws:sns:{DEPLOY_REGION}:{ACCOUNT_ID}:{ENV_PREFIX}-rekognition-topic-use1-sns",
                ],
            ),
        )

    def create_dynamo_table(self):

        # Create dynamo table for animal attribuges
        self.animal_attributes_table = dynamodb.CfnTable(
            self,
            resource_name(dynamodb.Table, "rekognition-animal-attributes-table"),
            table_name=resource_name(
                dynamodb.Table, "rekognition-animal-attributes-table"
            ),
            key_schema=[
                dynamodb.CfnTable.KeySchemaProperty(
                    attribute_name="uuid", key_type="HASH"
                ),
            ],
            attribute_definitions=[
                dynamodb.CfnTable.AttributeDefinitionProperty(
                    attribute_name="uuid",
                    attribute_type="S",
                ),
            ],
            sse_specification=dynamodb.CfnTable.SSESpecificationProperty(
                sse_enabled=True,
                kms_master_key_id=self.kms_key.key_arn,
                sse_type="KMS",
            ),
            billing_mode="PAY_PER_REQUEST",
            point_in_time_recovery_specification=dynamodb.CfnTable.PointInTimeRecoverySpecificationProperty(
                point_in_time_recovery_enabled=True
            ),
        )

    def seed_dynamo_table(self):
        # pass
        # Seed animal attributes table
        self.dynamo_seed_attributes_cr = cr.AwsCustomResource(
            self,
            resource_name(cr.AwsCustomResource, "rekognition-attributes-data-init"),
            function_name=resource_name(
                cr.AwsCustomResource, "rekognition-attributes-data-init"
            ),
            role=self.predict_image_attributes_execution_role,
            install_latest_aws_sdk=False,
            on_create=cr.AwsSdkCall(
                service="Lambda",
                action="invoke",
                parameters={
                    "FunctionName": self.seed_animal_attributes_lambda.function_name,
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    resource_name(
                        dynamodb.Table, "rekognition-animal-attributes-table"
                    ),
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=[
                    f"arn:aws:dynamodb:{DEPLOY_REGION}:{ACCOUNT_ID}:table/{self.animal_attributes_table.table_name}",
                ]
            ),
            timeout=Duration.minutes(10),
        )

    def create_codebuild_project(self):

        # Create manifest codebuild project
        self.create_manifest_project = codebuild.Project(
            self,
            resource_name(codebuild.Project, "rekognition-create-manifest"),
            project_name=resource_name(
                codebuild.Project, "rekognition-create-manifest"
            ),
            source=codebuild.Source.s3(
                bucket=self.s3_bucket, path=f"{VERSION}/scripts.zip"
            ),
            role=self.rekognition_execution_role,
            timeout=Duration.hours(3),
            build_spec=codebuild.BuildSpec.from_source_filename(
                filename="rekognition/statemachine_spec/create_manifest_spec.yml"
            ),
            environment=codebuild.BuildEnvironment(
                compute_type=codebuild.ComputeType.LARGE,
                build_image=codebuild.LinuxBuildImage.STANDARD_4_0,
            ),
            encryption_key=self.kms_key,
        )
        # codebuild project for evaluating models
        self.evaluate_model_project = codebuild.Project(
            self,
            resource_name(codebuild.Project, "rekognition-create-evaluation"),
            project_name=resource_name(
                codebuild.Project, "rekognition-create-evaluation"
            ),
            source=codebuild.Source.s3(
                bucket=self.s3_bucket, path=f"{VERSION}/scripts.zip"
            ),
            role=self.rekognition_execution_role,
            timeout=Duration.hours(3),
            build_spec=codebuild.BuildSpec.from_source_filename(
                filename="rekognition/statemachine_spec/create_evaluation_spec.yml"
            ),
            environment=codebuild.BuildEnvironment(
                compute_type=codebuild.ComputeType.LARGE,
                build_image=codebuild.LinuxBuildImage.STANDARD_4_0,
            ),
            encryption_key=self.kms_key,
        )

    def create_iam_role(self):
        # role for predict image attributes
        self.predict_image_attributes_execution_role = iam.Role(
            self,
            resource_name(iam.Role, "rekognition-predict-attributes-role"),
            role_name=resource_name(iam.Role, "rekognition-predict-attributes-role"),
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    resource_name(iam.Policy, "rekognition-predict-attributes-policy"),
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
                ),
            ],
            inline_policies={
                "LambdaPermission": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["ssm:Get*", "ssm:Put*"],
                            resources=[
                                f"arn:aws:ssm:{DEPLOY_REGION}:{ACCOUNT_ID}:parameter/animal-rekognition*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "kms:Encrypt*",
                                "kms:Decrypt*",
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:Describe*",
                            ],
                            resources=[
                                self.kms_key.key_arn,
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "s3:List*",
                                "s3:Get*",
                                "s3:Put*",
                                "s3:DeleteObject",
                            ],
                            resources=[
                                f"arn:aws:s3:::{self.s3_bucket.bucket_name}",
                                f"arn:aws:s3:::{self.s3_bucket.bucket_name}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "cloudwatch:PutMetricData",
                            ],
                            resources=[
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-rekognition*",
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:/aws/lambda/{ENV_PREFIX}-rekognition*:*",
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:/aws/lambda/{ENV_PREFIX}-rekognition*",
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:/aws/codebuild/{ENV_PREFIX}-rekognition*:*",
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:/aws/codebuild/{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "cloudwatch:PutMetricData",
                            ],
                            resources=[
                                "*",
                            ],
                            conditions={
                                "StringEquals": {
                                    "cloudwatch:namespace": "Petfinder/Rekognition/Model/DetectCustomLabels"
                                }
                            },
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "rekognition:Detect*",
                            ],
                            resources=[
                                f"arn:aws:rekognition:{DEPLOY_REGION}:{ACCOUNT_ID}:project/{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "dynamodb:BatchWrite*",
                                "dynamodb:Get*",
                                "dynamodb:BatchGet*",
                                "dynamodb:Describe*",
                                "dynamodb:List*",
                                "dynamodb:Update*",
                                "dynamodb:Scan",
                                "dynamodb:Query",
                                "dynamodb:Put*",
                            ],
                            resources=[
                                self.animal_attributes_table.attr_arn,
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "lambda:InvokeFunction",
                            ],
                            resources=[
                                f"arn:aws:lambda:{DEPLOY_REGION}:{ACCOUNT_ID}:function:{ENV_PREFIX}-rekognition-seed-attributes-lambda-use1-lbd"
                            ],
                        ),
                    ]
                )
            },
        )

        # Lambda Execution Role
        self.rekognition_execution_role = iam.Role(
            self,
            resource_name(iam.Role, "rekognition-execution-role"),
            role_name=resource_name(iam.Role, "rekognition-execution-role"),
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("lambda.amazonaws.com"),
                iam.ServicePrincipal("codebuild.amazonaws.com"),
            ),
            managed_policies=[
                iam.ManagedPolicy.from_managed_policy_arn(
                    self,
                    resource_name(iam.Policy, "rekognition-execution-policy"),
                    "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole",
                ),
            ],
            inline_policies={
                "LambdaPermission": iam.PolicyDocument(
                    statements=[
                        iam.PolicyStatement(
                            actions=["ssm:Get*", "ssm:Put*"],
                            resources=[
                                f"arn:aws:ssm:{DEPLOY_REGION}:{ACCOUNT_ID}:parameter/animal-rekognition*"
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "lambda:Update*",
                                "lambda:Get*",
                                "lambda:GetFunctionConfiguration",
                                "lambda:InvokeFunction",
                            ],
                            resources=[
                                f"arn:aws:lambda:{DEPLOY_REGION}:{ACCOUNT_ID}:function:{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "kms:Encrypt*",
                                "kms:Decrypt*",
                                "kms:ReEncrypt*",
                                "kms:GenerateDataKey*",
                                "kms:Describe*",
                            ],
                            resources=[
                                self.kms_key.key_arn,
                                f"arn:aws:logs:{DEPLOY_REGION}:{ACCOUNT_ID}:log-group:{ENV_PREFIX}-rekognition*",
                                f"arn:aws:sns:{DEPLOY_REGION}:{ACCOUNT_ID}:{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "s3:List*",
                                "s3:Get*",
                                "s3:Put*",
                                "s3:DeleteObject",
                            ],
                            resources=[
                                f"arn:aws:s3:::{self.s3_bucket.bucket_name}",
                                f"arn:aws:s3:::{self.s3_bucket.bucket_name}/*",
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "sns:Publish*",
                            ],
                            resources=[
                                self.sns_topic.topic_arn,
                            ],
                        ),
                        iam.PolicyStatement(
                            actions=[
                                "rekognition:Create*",
                                "rekognition:Delete*",
                                "rekognition:Detect*",
                                "rekognition:List*",
                                "rekognition:Describe*",
                                "rekognition:Search*",
                                "rekognition:Start*",
                                "rekognition:Stop*",
                                "rekognition:Update*",
                            ],
                            resources=[
                                f"arn:aws:rekognition:{DEPLOY_REGION}:{ACCOUNT_ID}:project/{ENV_PREFIX}-rekognition*",
                                f"arn:aws:rekognition:{DEPLOY_REGION}:{ACCOUNT_ID}:collection/{ENV_PREFIX}-rekognition*",
                            ],
                        ),
                    ]
                )
            },
        )
        self.rekognition_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "CloudWatchLogsReadOnlyAccess"
            )
        )
        self.rekognition_execution_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchReadOnlyAccess")
        )

    def create_lambdas(self):

        # lambda used in seed attributes custom resource
        self.seed_animal_attributes_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-seed-attributes-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-seed-attributes-lambda"
            ),
            handler="animal_attributes_resource.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/custom_resources"),
            role=self.predict_image_attributes_execution_role,
            environment_encryption=self.kms_key,
            environment={
                "table_name": self.animal_attributes_table.table_name,
            },
            timeout=Duration.minutes(10),
            memory_size=1024,
        )

        atrributes_to_send = config["attributesToSend"]
        attributes_comma_delim = ",".join(atrributes_to_send)
        # predict attributes api lambda
        self.predict_image_attributes_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-predict-attributes-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-predict-attributes-lambda"
            ),
            handler="predict_pet_image_attributes.lambda_handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/api"),
            role=self.predict_image_attributes_execution_role,
            timeout=Duration.minutes(15),
            environment_encryption=self.kms_key,
            memory_size=512,
            environment={
                "CAT_MODEL_SSM": config["catModelArn"],
                "DOG_MODEL_SSM": config["dogModelArn"],
                "ATTRIBUTES_TO_SEND": attributes_comma_delim,
                "ANIMAL_ATTRIBUTES_DDB_TBL": self.animal_attributes_table.table_name,
                "MINIMUM_CONFIDENCE": str(config["minConfidence"]),
            },
        )

        # create dataset task
        self.create_uuid_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-create-uuid-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-create-uuid-lambda"
            ),
            handler="create_uuid.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            timeout=Duration.minutes(1),
            environment_encryption=self.kms_key,
        )

        # create dataset task
        self.create_dataset_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-create-training-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-create-training-lambda"
            ),
            environment={
                "s3_bucket_name": self.s3_bucket.bucket_name,
                "iam_role": self.rekognition_execution_role.role_arn,
                "env_prefix": ENV_PREFIX,
                "version": VERSION,
            },
            handler="create_dataset.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            timeout=Duration.minutes(10),
            environment_encryption=self.kms_key,
        )
        # check if dataset is ready
        self.describe_dataset_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-describe-dataset-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-describe-dataset-lambda"
            ),
            handler="describe_dataset.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "s3_bucket_name": self.s3_bucket.bucket_name,
                "iam_role": self.rekognition_execution_role.role_arn,
                "env_prefix": ENV_PREFIX,
                "version": VERSION,
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # create new model
        self.train_model_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-train-model-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-train-model-lambda"
            ),
            handler="train_model.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "s3_bucket_name": self.s3_bucket.bucket_name,
                "iam_role": self.rekognition_execution_role.role_arn,
                "env_prefix": ENV_PREFIX,
                "version": VERSION,
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # check if model has completed training
        self.describe_model_training_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-describe-project-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-describe-project-lambda"
            ),
            handler="describe_model_training.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "sns_topic": self.sns_topic.topic_arn,
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # update ssm with newly promoted model
        self.update_model_ssm_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-update-ssm-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-update-ssm-lambda"
            ),
            handler="update_model_ssm.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "s3_bucket_name": self.s3_bucket.bucket_name,
                "iam_role": self.rekognition_execution_role.role_arn,
                "env_prefix": ENV_PREFIX,
                "version": VERSION,
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # start rekognition model
        self.start_model_inference_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-start-project-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-start-project-lambda"
            ),
            handler="start_model_inference.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "s3_bucket_name": self.s3_bucket.bucket_name,
                "iam_role": self.rekognition_execution_role.role_arn,
                "env_prefix": ENV_PREFIX,
                "version": VERSION,
                "inference_units": str(config["minInferenceUnits"]),
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # check if model has been started successfully
        self.describe_model_inference_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-describe-inference-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-describe-inference-lambda"
            ),
            handler="describe_model_inference.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "s3_bucket_name": self.s3_bucket.bucket_name,
                "iam_role": self.rekognition_execution_role.role_arn,
                "env_prefix": ENV_PREFIX,
                "version": VERSION,
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # check evaluation metrics pushed to s3
        self.evaluate_model_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-evaluate-model-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-evaluate-model-lambda"
            ),
            handler="evaluate_model.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment={
                "sns_topic": self.sns_topic.topic_arn,
                "dog_accuracy": str(config["dogAccuracy"]),
                "cat_accuracy": str(config["catAccuracy"]),
            },
            environment_encryption=self.kms_key,
            timeout=Duration.seconds(30),
        )
        # stop previous model version
        self.stop_previous_model_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-stop-model-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-stop-model-lambda"
            ),
            handler="stop_previous_model_inference.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment_encryption=self.kms_key,
            timeout=Duration.minutes(5),
        )
        # stop new model since it did not pass evaluation criteria
        self.skip_promotion_stop_model_lambda = _lambda.Function(
            self,
            resource_name(_lambda.Function, "rekognition-stop-new-model-lambda"),
            function_name=resource_name(
                _lambda.Function, "rekognition-stop-new-model-lambda"
            ),
            handler="stop_new_model_inference.handler",
            runtime=_lambda.Runtime.PYTHON_3_9,
            code=_lambda.Code.from_asset("rekognition/lambda/stepfunctions"),
            role=self.rekognition_execution_role,
            environment_encryption=self.kms_key,
            timeout=Duration.minutes(5),
        )

    # create tasks associated to lambdas
    def create_stepfunction_tasks(self):

        self.create_uuid_job = tasks.LambdaInvoke(
            self,
            "Create UUID",
            lambda_function=self.create_uuid_lambda,
            output_path="$.Payload",
        )

        # Create manifest task
        self.create_manifest_job = tasks.CodeBuildStartBuild(
            self,
            "Create-Rekognition-Manifest",
            project=self.create_manifest_project,
            environment_variables_override={
                "ANIMAL": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=stepfunctions.JsonPath.string_at("$.animal"),
                ),
                "VERSION": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=VERSION,
                ),
                "ENV_PREFIX": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=ENV_PREFIX,
                ),
                "UUID": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=stepfunctions.JsonPath.string_at("$.uuid"),
                ),
                "S3_BUCKET": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=self.s3_bucket.bucket_name,
                ),
            },
            result_selector={
                "parameters": stepfunctions.JsonPath.string_at(
                    "$.Build.Environment.EnvironmentVariables"
                ),
                "version": VERSION,
            },
            # output_path="$.Input",
            integration_pattern=stepfunctions.IntegrationPattern.RUN_JOB,
            timeout=Duration.hours(3),
        )
        # evaluate model task
        self.create_evaluation_metrics_job = tasks.CodeBuildStartBuild(
            self,
            "Create Evaluation Metrics",
            project=self.evaluate_model_project,
            environment_variables_override={
                "ANIMAL": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=stepfunctions.JsonPath.string_at("$.animal"),
                ),
                "VERSION": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=VERSION,
                ),
                "ENV_PREFIX": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=ENV_PREFIX,
                ),
                "UUID": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=stepfunctions.JsonPath.string_at("$.uuid"),
                ),
                "MODEL_NAME": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=stepfunctions.JsonPath.string_at("$.version_name"),
                ),
                "S3_BUCKET": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=self.s3_bucket.bucket_name,
                ),
                "PROJECT_ARN": codebuild.BuildEnvironmentVariable(
                    type=codebuild.BuildEnvironmentVariableType.PLAINTEXT,
                    value=stepfunctions.JsonPath.string_at("$.project_arn"),
                ),
            },
            result_selector={
                "parameters": stepfunctions.JsonPath.string_at(
                    "$.Build.Environment.EnvironmentVariables"
                ),
                "version": VERSION,
            },
            integration_pattern=stepfunctions.IntegrationPattern.RUN_JOB,
            timeout=Duration.hours(1),
        )

        self.create_dataset_job = tasks.LambdaInvoke(
            self,
            "Create Rekognition Dataset",
            lambda_function=self.create_dataset_lambda,
            output_path="$.Payload",
        )

        self.train_model_job = tasks.LambdaInvoke(
            self,
            "Train Rekognition Project Version",
            lambda_function=self.train_model_lambda,
            output_path="$.Payload",
        )

        self.describe_dataset_job = tasks.LambdaInvoke(
            self,
            "Describe Rekognition Dataset",
            lambda_function=self.describe_dataset_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=False,
        )

        # Retry every 5 minutes 5 times to check if dataset is available
        self.describe_dataset_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.seconds(300),
            max_attempts=5,
        )

        self.describe_model_training_job = tasks.LambdaInvoke(
            self,
            "Describe Rekognition Model Training",
            lambda_function=self.describe_model_training_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=False,
        )
        # retry every 15 minutes for 32 hours to see if model is available
        self.describe_model_training_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.seconds(900),
            max_attempts=128,
        )

        self.update_model_ssm_job = tasks.LambdaInvoke(
            self,
            "Update Rekognition Project Version in SSM",
            lambda_function=self.update_model_ssm_lambda,
            output_path="$.Payload",
        )

        self.start_model_inference_job = tasks.LambdaInvoke(
            self,
            "Start Rekognition Project Model",
            lambda_function=self.start_model_inference_lambda,
            output_path="$.Payload",
        )

        self.describe_model_inference_job = tasks.LambdaInvoke(
            self,
            "Describe Rekognition Project Model",
            lambda_function=self.describe_model_inference_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=False,
        )
        # retry every 2 minutes for 1 hour to see if inference model is available
        self.describe_model_inference_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.seconds(120),
            max_attempts=30,
        )

        self.evaluate_model_job = tasks.LambdaInvoke(
            self,
            "Evaluate Rekognition Project Model",
            lambda_function=self.evaluate_model_lambda,
            output_path="$.Payload",
        )

        self.stop_previous_model_job = tasks.LambdaInvoke(
            self,
            "Stop Previous Project Model",
            lambda_function=self.stop_previous_model_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=False,
        )

        self.wait_before_stop_previous_model = stepfunctions.Wait(
            self,
            "Wait 20 Minutes",
            time=stepfunctions.WaitTime.duration(Duration.minutes(20)),
        )
        # Retry every 2 minutes for 1 hour
        self.stop_previous_model_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.seconds(120),
            max_attempts=30,
        )

        self.do_not_promote = stepfunctions.Succeed(
            self,
            "Do Not Promote Model",
            comment="Check Model Performance",
        )

        self.skip_training_message = tasks.SnsPublish(
            self,
            "Notify Skip Training",
            topic=self.sns_topic,
            message=stepfunctions.TaskInput.from_object(
                {"default": {"Status": "Skipping Training"}}
            ),
            subject=f"Rekognition {ENV_PREFIX} Skipping Training",
        )

        self.model_deployed = stepfunctions.Succeed(
            self,
            "Model Deployed",
            comment="Model Deployed",
        )

        self.model_promote_and_previous_model_stopped = stepfunctions.Succeed(
            self,
            "Model Promoted and Previous Model Stopped",
            comment="Model Promoted and Previous Model Stopped",
        )

        self.skip_promotion_stop_model_job = tasks.LambdaInvoke(
            self,
            "Stop New Inference and Send Notification",
            lambda_function=self.skip_promotion_stop_model_lambda,
            output_path="$.Payload",
            retry_on_service_exceptions=False,
        )

        # retry every 5 minutes for 30min to wait for inference endpoint to stop
        self.skip_promotion_stop_model_job.add_retry(
            backoff_rate=1.0,
            interval=Duration.seconds(300),
            max_attempts=6,
        )

    def create_ssm_entries(self):

        ssm_s3_bucket = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "rekognition-s3-ssm"),
            string_value=self.s3_bucket.bucket_name,
            parameter_name="/animal-rekognition/s3/name",
        )

        ssm_state_machine_name = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "rekognition-statemachine-arn-ssm"),
            string_value=self.training_state_machine.state_machine_arn,
            parameter_name="/animal-rekognition/statemachine/arn",
        )

        ssm_create_dataset_name = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "rekognition-create-dataset-ssm"),
            string_value=self.create_dataset_lambda.function_name,
            parameter_name="/animal-rekognition/lambda/create_dataset/name",
        )

        ssm_sns_topic_name = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "rekognition-sns-topic-ssm"),
            string_value=self.sns_topic.topic_arn,
            parameter_name="/animal-rekognition/sns/arn",
        )

        ssm_animal_attributes_name = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "animal-attributes-ssm"),
            string_value=self.predict_image_attributes_lambda.function_name,
            parameter_name="/animal-rekognition/lambda/predict_image_attributes/name",
        )

        ssm_kms_key_arn = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "kms-key-ssm"),
            string_value=self.kms_key.key_arn,
            parameter_name="/animal-rekognition/kms-key/arn",
        )

        ssm_state_machine_arn = ssm.StringParameter(
            self,
            resource_name(ssm.StringParameter, "statemachine-ssm"),
            string_value=self.training_state_machine.state_machine_arn,
            parameter_name="/animal-rekognition/state-machine/arn",
        )
