# Packages interceptor/{handler.py, policies/, bin/opa} into the Lambda
# deployment zip. bin/opa (the static OPA binary) is not committed to git --
# ../../interceptor/build.sh downloads it before this data source can
# produce a real zip; run it (and re-run `terraform plan`/`apply`) first.
data "archive_file" "interceptor" {
  type        = "zip"
  source_dir  = "${path.module}/../../../interceptor"
  output_path = "${path.module}/../../../interceptor/.build/interceptor.zip"
  excludes = [
    ".build",
    ".git",
    ".gitignore",
    "README.md",
    "build.sh",
    "tests",
    "__pycache__",
    ".pytest_cache",
    # bin/opa-local is build.sh's host-platform copy for running tests on
    # the dev machine (e.g. darwin/arm64) -- only bin/opa (linux/arm64,
    # what the Lambda runtime actually needs) belongs in the deployment
    # package. Omitting this line was a real bug: it doubled the package
    # size and pushed CreateFunction's direct-upload request over Lambda's
    # ~70MB limit.
    "bin/opa-local",
  ]
}

resource "aws_lambda_function" "interceptor" {
  function_name = "asl-interceptor-${var.environment}"
  description   = "AgentCore Gateway REQUEST interceptor -- normalizes the MCP tool call and evaluates it against the OPA policy bundled in policies/main.rego (see interceptor/README.md)."

  filename         = data.archive_file.interceptor.output_path
  source_code_hash = data.archive_file.interceptor.output_base64sha256

  role          = aws_iam_role.interceptor.arn
  handler       = "handler.handler"
  runtime       = "python3.13"
  architectures = ["arm64"]
  timeout       = 10
  memory_size   = 256

  environment {
    variables = {
      LOG_LEVEL = var.log_level
    }
  }

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "interceptor" {
  name              = "/aws/lambda/${aws_lambda_function.interceptor.function_name}"
  retention_in_days = 14
  tags              = var.tags
}
