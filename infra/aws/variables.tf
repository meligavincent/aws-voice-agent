variable "account_id" {
  type        = string
  description = "Deployment is rejected if credentials belong to another AWS account."
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "A 12-digit AWS account ID is required."
  }
}
variable "name" {
  type    = string
  default = "voice-agent"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,17}$", var.name))
    error_message = "Use 3–18 lowercase letters, numbers or hyphens, beginning with a letter."
  }
}
variable "environment" {
  type    = string
  default = "demo"
}
variable "primary_region" {
  type    = string
  default = "eu-central-1"
}
variable "standby_region" {
  type    = string
  default = "eu-west-2"
}
variable "enable_standby" {
  type        = bool
  default     = false
  description = "Provision a second regional app and a DynamoDB replica. Does not enable Connect Global Resiliency."
}
variable "enable_voice" {
  type    = bool
  default = true
}
variable "enable_rag" {
  type    = bool
  default = true
}
variable "deletion_protection" {
  type    = bool
  default = true
}
variable "deployment_principal_arn" {
  type        = string
  description = "IAM role or user ARN of the Terraform principal (not an STS assumed-role ARN); used by the index data-access policy."
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:(role|user)/.+$", var.deployment_principal_arn))
    error_message = "Use an IAM role/user ARN, not an STS session ARN."
  }
}
variable "model_id" {
  type        = string
  default     = "amazon.nova-lite-v1:0"
  description = "Regional model ID or supported inference-profile ARN. Validate access and regional availability before deploying."
}
variable "standby_model_id" {
  type    = string
  default = "amazon.nova-lite-v1:0"
}
variable "foundation_model_id" {
  type    = string
  default = "amazon.nova-lite-v1:0"
}
variable "connect_instance_ids" {
  type        = map(string)
  default     = {}
  description = "Existing regional Connect instance IDs, particularly for an AWS-enabled Global Resiliency pair. Empty map creates independent demo instances."
}
variable "alarm_actions" {
  type        = map(list(string))
  default     = {}
  description = "Regional SNS topic ARNs for an operational alert destination."
}
