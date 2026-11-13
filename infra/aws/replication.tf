resource "aws_iam_role" "document_replication" {
  count              = var.enable_standby ? 1 : 0
  name               = "${var.name}-document-replication"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "s3.amazonaws.com" }, Action = "sts:AssumeRole" }] })
}
resource "aws_iam_role_policy" "document_replication" {
  count = var.enable_standby ? 1 : 0
  role  = aws_iam_role.document_replication[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["s3:GetReplicationConfiguration", "s3:ListBucket"], Resource = module.primary.documents_arn },
    { Effect = "Allow", Action = ["s3:GetObjectVersionForReplication", "s3:GetObjectVersionAcl", "s3:GetObjectVersionTagging"], Resource = "${module.primary.documents_arn}/public/*" },
    { Effect = "Allow", Action = ["s3:ReplicateObject", "s3:ReplicateTags"], Resource = "${module.standby[0].documents_arn}/public/*" },
    { Effect = "Allow", Action = ["kms:Decrypt"], Resource = module.primary.kms_arn },
    { Effect = "Allow", Action = ["kms:Encrypt", "kms:GenerateDataKey", "kms:Decrypt"], Resource = module.standby[0].kms_arn }
  ] })
}
resource "aws_s3_bucket_replication_configuration" "documents" {
  count  = var.enable_standby ? 1 : 0
  bucket = module.primary.documents_bucket
  role   = aws_iam_role.document_replication[0].arn
  rule {
    id       = "public-faq-to-standby"
    status   = "Enabled"
    priority = 1
    filter { prefix = "public/" }
    delete_marker_replication { status = "Disabled" }
    source_selection_criteria {
      sse_kms_encrypted_objects { status = "Enabled" }
    }
    destination {
      bucket = module.standby[0].documents_arn
      encryption_configuration { replica_kms_key_id = module.standby[0].kms_arn }
    }
  }
  depends_on = [aws_iam_role_policy.document_replication, module.primary, module.standby]
}
