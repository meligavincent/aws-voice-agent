resource "aws_dynamodb_table" "state" {
  name         = "voice-agent-local"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  attribute {
    name = "pk"
    type = "S"
  }
  attribute {
    name = "gsi_pk"
    type = "S"
  }
  attribute {
    name = "gsi_sk"
    type = "S"
  }
  global_secondary_index {
    name            = "work"
    hash_key        = "gsi_pk"
    range_key       = "gsi_sk"
    projection_type = "ALL"
  }
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  point_in_time_recovery { enabled = true }
}
module "regional" {
  source       = "../modules/regional"
  name         = "voice-agent-local"
  table_name   = aws_dynamodb_table.state.name
  stream_arn   = aws_dynamodb_table.state.stream_arn
  archive_path = abspath("${path.root}/../../build/lambda.zip")
  local_mode   = true
  enable_voice = false
  enable_rag   = false
}
output "agent_function" { value = module.regional.agent_function }
output "queue_url" { value = module.regional.queue_url }
output "dlq_url" { value = module.regional.dlq_url }
output "documents_bucket" { value = module.regional.documents_bucket }
output "table_name" { value = aws_dynamodb_table.state.name }
