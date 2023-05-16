pip3 install -r requirements.txt \
    && export AWS_PAGER="" \
    && export VERSION=$(cat _version.py | cut -d'"' -f2) \
    && cdk deploy --require-approval never \
    && export S3_BUCKET=$(aws ssm get-parameter --name /animal-rekognition/s3/name --query "Parameter.Value" --output text --region $CDK_DEPLOY_REGION) \
    && export MACHINE_ARN=$(aws ssm get-parameter --name /animal-rekognition/state-machine/arn --query "Parameter.Value" --output text --region $CDK_DEPLOY_REGION) \
    && zip -r scripts.zip rekognition/* requirements-manifest.txt \
    && aws s3 cp scripts.zip s3://$S3_BUCKET/$VERSION/scripts.zip \
    && aws s3 cp tests/data/ s3://$S3_BUCKET/$VERSION/testing --recursive \
    && aws stepfunctions start-execution --state-machine-arn $MACHINE_ARN --input "{\"animal\" : \"cat\"}" --region $CDK_DEPLOY_REGION \
    && aws stepfunctions start-execution --state-machine-arn $MACHINE_ARN --input "{\"animal\" : \"dog\"}" --region $CDK_DEPLOY_REGION \
    && rm scripts.zip
