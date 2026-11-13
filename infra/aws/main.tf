resource "aws_dynamodb_table" "state" {
  name         = "${var.name}-state"
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
  stream_enabled              = true
  stream_view_type            = "NEW_AND_OLD_IMAGES"
  deletion_protection_enabled = var.deletion_protection
  server_side_encryption { enabled = true }
  point_in_time_recovery { enabled = true }
  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
  dynamic "replica" {
    for_each = var.enable_standby ? [var.standby_region] : []
    content {
      region_name            = replica.value
      point_in_time_recovery = true
      propagate_tags         = true
    }
  }
  lifecycle {
    precondition {
      condition     = var.primary_region != var.standby_region
      error_message = "Primary and standby regions must differ."
    }
  }
}
module "primary" {
  source                   = "../modules/regional"
  name                     = var.name
  table_name               = aws_dynamodb_table.state.name
  stream_arn               = aws_dynamodb_table.state.stream_arn
  archive_path             = abspath("${path.module}/../../build/lambda.zip")
  enable_voice             = var.enable_voice
  enable_rag               = var.enable_rag
  model_id                 = var.model_id
  foundation_model_id      = var.foundation_model_id
  deployment_principal_arn = var.deployment_principal_arn
  connect_instance_id      = lookup(var.connect_instance_ids, var.primary_region, "")
  alarm_actions            = lookup(var.alarm_actions, var.primary_region, [])
}
data "aws_dynamodb_table" "standby" {
  count      = var.enable_standby ? 1 : 0
  provider   = aws.standby
  name       = aws_dynamodb_table.state.name
  depends_on = [aws_dynamodb_table.state]
}
module "standby" {
  count                    = var.enable_standby ? 1 : 0
  source                   = "../modules/regional"
  providers                = { aws = aws.standby }
  name                     = var.name
  table_name               = aws_dynamodb_table.state.name
  stream_arn               = data.aws_dynamodb_table.standby[0].stream_arn
  archive_path             = abspath("${path.module}/../../build/lambda.zip")
  enable_voice             = var.enable_voice
  enable_rag               = var.enable_rag
  model_id                 = var.standby_model_id
  foundation_model_id      = var.foundation_model_id
  deployment_principal_arn = var.deployment_principal_arn
  connect_instance_id      = lookup(var.connect_instance_ids, var.standby_region, "")
  alarm_actions            = lookup(var.alarm_actions, var.standby_region, [])
}
output "table_name" { value = aws_dynamodb_table.state.name }
output "regions" {
  value = merge({ (var.primary_region) = module.primary }, var.enable_standby ? { (var.standby_region) = module.standby[0] } : {})
}
