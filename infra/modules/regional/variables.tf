terraform {
  required_providers { aws = { source = "hashicorp/aws" } }
}
variable "name" { type = string }
variable "table_name" { type = string }
variable "stream_arn" { type = string }
variable "archive_path" { type = string }
variable "local_mode" {
  type    = bool
  default = false
}
variable "enable_voice" {
  type    = bool
  default = true
}
variable "enable_rag" {
  type    = bool
  default = false
}
variable "model_id" {
  type    = string
  default = ""
}
variable "foundation_model_id" {
  type    = string
  default = "amazon.nova-lite-v1:0"
}
variable "connect_instance_id" {
  type    = string
  default = ""
}
variable "connect_identity_type" {
  type    = string
  default = "CONNECT_MANAGED"
}
variable "deployment_principal_arn" {
  type    = string
  default = ""
}
variable "alarm_actions" {
  type    = list(string)
  default = []
}
