mock_provider "aws" {
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_region" { defaults = { region = "eu-central-1" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
}
mock_provider "aws" {
  alias = "standby"
  mock_data "aws_caller_identity" { defaults = { account_id = "123456789012" } }
  mock_data "aws_region" { defaults = { region = "eu-west-2" } }
  mock_data "aws_partition" { defaults = { partition = "aws" } }
}
variables {
  account_id               = "123456789012"
  deployment_principal_arn = "arn:aws:iam::123456789012:role/TestDeployment"
}
run "single_region_full_voice_and_rag" {
  command = plan
  assert {
    condition     = length(keys(output.regions)) == 1
    error_message = "The cost-conscious default must deploy only one region."
  }
  assert {
    condition     = aws_dynamodb_table.state.deletion_protection_enabled
    error_message = "AWS business state must be protected from accidental deletion."
  }
}
run "optional_warm_standby" {
  command = plan
  variables { enable_standby = true }
  assert {
    condition     = length(keys(output.regions)) == 2
    error_message = "Standby mode must expose both regional application stacks."
  }
}
