resource "aws_connect_instance" "voice" {
  count                     = var.enable_voice && var.connect_instance_id == "" ? 1 : 0
  identity_management_type  = var.connect_identity_type
  instance_alias            = "${var.name}-${local.account}-${local.region}"
  inbound_calls_enabled     = true
  outbound_calls_enabled    = false
  contact_flow_logs_enabled = false
  contact_lens_enabled      = false
}
locals {
  connect_id  = var.connect_instance_id != "" ? var.connect_instance_id : try(aws_connect_instance.voice[0].id, "")
  connect_arn = "arn:${local.partition}:connect:${local.region}:${local.account}:instance/${local.connect_id}"
}
resource "aws_iam_role" "lex" {
  count              = var.enable_voice ? 1 : 0
  name               = "${var.name}-${local.region}-lex"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "lexv2.amazonaws.com" }, Action = "sts:AssumeRole", Condition = { StringEquals = { "aws:SourceAccount" = local.account }, ArnLike = { "aws:SourceArn" = "arn:${local.partition}:lex:${local.region}:${local.account}:bot/*" } } }] })
}
resource "aws_iam_role_policy" "lex" {
  count = var.enable_voice ? 1 : 0
  role  = aws_iam_role.lex[0].id
  # Polly does not support resource-level permissions for these calls.
  policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Action = ["polly:SynthesizeSpeech"], Resource = "*" }] })
}
resource "aws_cloudformation_stack" "voice" {
  count         = var.enable_voice ? 1 : 0
  name          = "${var.name}-voice"
  template_body = file("${path.module}/templates/voice.json")
  parameters    = { BotName = var.name, RoleArn = aws_iam_role.lex[0].arn, LambdaArn = aws_lambda_alias.live["agent"].arn, ConnectArn = local.connect_arn }
  depends_on    = [aws_iam_role_policy.lex]
}
resource "aws_lambda_permission" "lex" {
  count          = var.enable_voice ? 1 : 0
  statement_id   = "AllowLexAlias"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.app["agent"].function_name
  qualifier      = aws_lambda_alias.live["agent"].name
  principal      = "lexv2.amazonaws.com"
  source_account = local.account
  source_arn     = aws_cloudformation_stack.voice[0].outputs["AliasArn"]
}
resource "aws_connect_hours_of_operation" "advisors" {
  count       = var.enable_voice ? 1 : 0
  instance_id = local.connect_id
  name        = "${var.name}-advisors"
  time_zone   = "Europe/Paris"
  dynamic "config" {
    for_each = toset(["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"])
    content {
      day = config.value
      start_time {
        hours   = 9
        minutes = 0
      }
      end_time {
        hours   = 17
        minutes = 0
      }
    }
  }
}
resource "aws_connect_queue" "advisors" {
  count                 = var.enable_voice ? 1 : 0
  instance_id           = local.connect_id
  name                  = "${var.name}-advisors"
  hours_of_operation_id = aws_connect_hours_of_operation.advisors[0].hours_of_operation_id
  max_contacts          = 10
}
resource "aws_connect_contact_flow" "inbound" {
  count       = var.enable_voice ? 1 : 0
  instance_id = local.connect_id
  name        = "${var.name}-inbound"
  type        = "CONTACT_FLOW"
  description = "Insurance service demo: authenticated lookup, confirmed callback and public FAQ. Staff the advisor queue before enabling calls."
  content = templatefile("${path.module}/templates/flow.json.tftpl", {
    alias_arn = aws_cloudformation_stack.voice[0].outputs["AliasArn"]
    queue_arn = aws_connect_queue.advisors[0].arn
  })
  depends_on = [aws_lambda_permission.lex]
}
output "advisor_queue_id" { value = var.enable_voice ? aws_connect_queue.advisors[0].queue_id : null }
output "lex_bot_id" { value = var.enable_voice ? aws_cloudformation_stack.voice[0].outputs["BotId"] : null }
output "lex_alias_id" { value = var.enable_voice ? aws_cloudformation_stack.voice[0].outputs["AliasId"] : null }
