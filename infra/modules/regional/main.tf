data "aws_region" "current" {}
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
locals {
  region    = data.aws_region.current.region
  account   = data.aws_caller_identity.current.account_id
  partition = data.aws_partition.current.partition
  table_arn = "arn:${local.partition}:dynamodb:${local.region}:${local.account}:table/${var.table_name}"
  functions = { agent = "voice_agent.handlers.lex", publisher = "voice_agent.handlers.publish", worker = "voice_agent.handlers.worker" }
}
resource "aws_kms_key" "data" {
  description             = "${var.name} regional data encryption"
  enable_key_rotation     = true
  deletion_window_in_days = 30
}
resource "aws_kms_alias" "data" {
  name          = "alias/${var.name}"
  target_key_id = aws_kms_key.data.key_id
}
resource "aws_s3_bucket" "documents" {
  bucket        = "${var.name}-${local.account}-${local.region}-docs"
  force_destroy = var.local_mode
}
resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    id     = "retain-history-90-days"
    status = "Enabled"
    filter { prefix = "" }
    noncurrent_version_expiration { noncurrent_days = 90 }
    abort_incomplete_multipart_upload { days_after_initiation = 7 }
  }
}
resource "aws_s3_bucket_policy" "documents" {
  bucket = aws_s3_bucket.documents.id
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Sid = "TLSOnly", Effect = "Deny", Principal = "*", Action = "s3:*", Resource = [aws_s3_bucket.documents.arn, "${aws_s3_bucket.documents.arn}/*"], Condition = { Bool = { "aws:SecureTransport" = "false" } } }] })
}
resource "aws_sqs_queue" "dead_letters" {
  name                      = "${var.name}-dlq"
  message_retention_seconds = 1209600
  kms_master_key_id         = aws_kms_key.data.arn
}
resource "aws_sqs_queue" "work" {
  name                       = "${var.name}-work"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 10
  kms_master_key_id          = aws_kms_key.data.arn
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dead_letters.arn, maxReceiveCount = 5 })
}
resource "aws_sqs_queue_redrive_allow_policy" "work" {
  queue_url            = aws_sqs_queue.dead_letters.url
  redrive_allow_policy = jsonencode({ redrivePermission = "byQueue", sourceQueueArns = [aws_sqs_queue.work.arn] })
}
resource "aws_iam_role" "lambda" {
  for_each           = local.functions
  name               = "${var.name}-${local.region}-${each.key}"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_cloudwatch_log_group" "lambda" {
  for_each          = local.functions
  name              = "/aws/lambda/${var.name}-${each.key}"
  retention_in_days = 14
}
resource "aws_iam_role_policy" "lambda" {
  for_each = local.functions
  role     = aws_iam_role.lambda[each.key].id
  policy = jsonencode({ Version = "2012-10-17", Statement = concat(
    [{ Effect = "Allow", Action = ["logs:CreateLogStream", "logs:PutLogEvents"], Resource = ["${aws_cloudwatch_log_group.lambda[each.key].arn}:*"] },
    { Effect = "Allow", Action = ["kms:Decrypt", "kms:GenerateDataKey"], Resource = [aws_kms_key.data.arn] }],
    each.key == "agent" ? [
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = [local.table_arn] },
      { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = ["arn:${local.partition}:bedrock:*::foundation-model/${var.foundation_model_id}", startswith(var.model_id, "arn:") ? var.model_id : "arn:${local.partition}:bedrock:${local.region}:${local.account}:inference-profile/${var.model_id}"] },
      { Effect = "Allow", Action = ["bedrock:ApplyGuardrail"], Resource = [var.local_mode ? "arn:${local.partition}:bedrock:${local.region}:${local.account}:guardrail/local" : aws_bedrock_guardrail.public_faq[0].guardrail_arn] }
    ] : [],
    each.key == "agent" && var.enable_rag ? [{ Effect = "Allow", Action = ["bedrock:Retrieve"], Resource = [aws_bedrockagent_knowledge_base.faq[0].arn] }] : [],
    each.key == "publisher" ? [
      { Effect = "Allow", Action = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"], Resource = ["${local.table_arn}/stream/*"] },
      { Effect = "Allow", Action = ["dynamodb:ListStreams"], Resource = ["*"] },
      { Effect = "Allow", Action = ["sqs:SendMessage"], Resource = [aws_sqs_queue.work.arn, aws_sqs_queue.dead_letters.arn] }
    ] : [],
    each.key == "worker" ? [
      { Effect = "Allow", Action = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem"], Resource = [local.table_arn] },
      { Effect = "Allow", Action = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"], Resource = [aws_sqs_queue.work.arn] }
    ] : []
  ) })
}
resource "aws_lambda_function" "app" {
  for_each                       = local.functions
  function_name                  = "${var.name}-${each.key}"
  role                           = aws_iam_role.lambda[each.key].arn
  filename                       = var.archive_path
  source_code_hash               = filebase64sha256(var.archive_path)
  runtime                        = "python3.12"
  handler                        = each.value
  timeout                        = each.key == "agent" ? 12 : 20
  memory_size                    = 256
  publish                        = true
  reserved_concurrent_executions = 5
  environment {
    variables = {
      APP_ENV           = var.local_mode ? "local" : "aws"
      AI_MODE           = var.local_mode ? "stub" : "bedrock"
      TABLE_NAME        = var.table_name
      QUEUE_URL         = aws_sqs_queue.work.url
      MODEL_ID          = var.model_id
      KNOWLEDGE_BASE_ID = var.enable_rag ? aws_bedrockagent_knowledge_base.faq[0].id : ""
      GUARDRAIL_ID      = var.local_mode ? "" : aws_bedrock_guardrail.public_faq[0].guardrail_id
      GUARDRAIL_VERSION = var.local_mode ? "" : aws_bedrock_guardrail_version.public_faq[0].version
    }
  }
  depends_on = [aws_iam_role_policy.lambda, aws_cloudwatch_log_group.lambda]
}
resource "aws_lambda_alias" "live" {
  for_each         = local.functions
  name             = "live"
  function_name    = aws_lambda_function.app[each.key].function_name
  function_version = aws_lambda_function.app[each.key].version
}
resource "aws_lambda_event_source_mapping" "outbox" {
  event_source_arn               = var.stream_arn
  function_name                  = aws_lambda_alias.live["publisher"].arn
  starting_position              = "TRIM_HORIZON"
  batch_size                     = 10
  maximum_retry_attempts         = 5
  maximum_record_age_in_seconds  = 3600
  bisect_batch_on_function_error = true
  function_response_types        = ["ReportBatchItemFailures"]
  destination_config {
    on_failure { destination_arn = aws_sqs_queue.dead_letters.arn }
  }
  filter_criteria {
    filter { pattern = jsonencode({ eventName = ["INSERT", "MODIFY"], dynamodb = { NewImage = { kind = { S = ["OUTBOX"] }, status = { S = ["PENDING"] }, home_region = { S = [local.region] } } } }) }
  }
}
resource "aws_lambda_event_source_mapping" "work" {
  event_source_arn        = aws_sqs_queue.work.arn
  function_name           = aws_lambda_alias.live["worker"].arn
  batch_size              = 10
  function_response_types = ["ReportBatchItemFailures"]
  scaling_config { maximum_concurrency = 2 }
}
resource "aws_cloudwatch_metric_alarm" "dlq" {
  count               = var.local_mode ? 0 : 1
  alarm_name          = "${var.name}-dlq-not-empty"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 0
  dimensions          = { QueueName = aws_sqs_queue.dead_letters.name }
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "errors" {
  for_each            = var.local_mode ? {} : local.functions
  alarm_name          = "${var.name}-${each.key}-errors"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  dimensions          = { FunctionName = aws_lambda_function.app[each.key].function_name }
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "application_failure" {
  count               = var.local_mode ? 0 : 1
  alarm_name          = "${var.name}-application-failure"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApplicationFailure"
  namespace           = "VoiceAgent"
  period              = 60
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "queue_age" {
  count               = var.local_mode ? 0 : 1
  alarm_name          = "${var.name}-old-work"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Maximum"
  threshold           = 120
  dimensions          = { QueueName = aws_sqs_queue.work.name }
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}
resource "aws_cloudwatch_metric_alarm" "stream_age" {
  count               = var.local_mode ? 0 : 1
  alarm_name          = "${var.name}-stream-lag"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "IteratorAge"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Maximum"
  threshold           = 60000
  dimensions          = { FunctionName = aws_lambda_function.app["publisher"].function_name }
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.alarm_actions
}
