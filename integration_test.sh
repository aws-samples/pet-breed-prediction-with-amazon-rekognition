export AWS_PAGER="" \
    && export VERSION=$(cat _version.py | cut -d'"' -f2) \
    && export S3_BUCKET=$(aws ssm get-parameter --name /animal-rekognition/s3/name --query "Parameter.Value" --output text --region $CDK_DEPLOY_REGION) \
    && aws s3 cp tests/data/ s3://$S3_BUCKET/$VERSION/testing --recursive \
    && pytest tests/integration -v
