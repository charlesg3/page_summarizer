# Start with the AWS Lambda Python 3.13 runtime
FROM public.ecr.aws/lambda/python:3.13

# Set working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Install Python dependencies
RUN pip install --no-cache-dir requests anthropic trafilatura

# Copy the rest of your function code
COPY src .

# Set the CMD to your handler
CMD [ "lambda.lambda_handler" ]
