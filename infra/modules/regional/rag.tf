resource "aws_bedrock_guardrail" "public_faq" {
  count                     = var.local_mode ? 0 : 1
  name                      = "${var.name}-public-faq"
  blocked_input_messaging   = "Un conseiller est nécessaire. A human advisor is needed."
  blocked_outputs_messaging = "Un conseiller est nécessaire. A human advisor is needed."
  content_policy_config {
    dynamic "filters_config" {
      for_each = toset(["HATE", "INSULTS", "SEXUAL", "VIOLENCE", "MISCONDUCT", "PROMPT_ATTACK"])
      content {
        type            = filters_config.value
        input_strength  = "HIGH"
        output_strength = filters_config.value == "PROMPT_ATTACK" ? "NONE" : "HIGH"
      }
    }
  }
  sensitive_information_policy_config {
    pii_entities_config {
      type   = "EMAIL"
      action = "BLOCK"
    }
    pii_entities_config {
      type   = "PHONE"
      action = "BLOCK"
    }
  }
  topic_policy_config {
    topics_config {
      name       = "ClaimDecisions"
      type       = "DENY"
      definition = "Determining personal insurance coverage, liability, eligibility for payment, or an individual's claim outcome."
      examples   = ["Am I covered for this accident?", "How much will you pay me?"]
    }
  }
}
resource "aws_bedrock_guardrail_version" "public_faq" {
  count         = var.local_mode ? 0 : 1
  guardrail_arn = aws_bedrock_guardrail.public_faq[0].guardrail_arn
  description   = "Public FAQ policy ${substr(sha256(jsonencode(aws_bedrock_guardrail.public_faq[0].content_policy_config)), 0, 12)}"
  lifecycle { replace_triggered_by = [aws_bedrock_guardrail.public_faq] }
}
resource "aws_iam_role" "knowledge" {
  count              = var.enable_rag ? 1 : 0
  name               = "${var.name}-${local.region}-knowledge"
  assume_role_policy = jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = { Service = "bedrock.amazonaws.com" }, Action = "sts:AssumeRole", Condition = { StringEquals = { "aws:SourceAccount" = local.account }, ArnLike = { "aws:SourceArn" = "arn:${local.partition}:bedrock:${local.region}:${local.account}:knowledge-base/*" } } }] })
}
resource "aws_opensearchserverless_security_policy" "encryption" {
  count  = var.enable_rag ? 1 : 0
  name   = "${var.name}-encryption"
  type   = "encryption"
  policy = jsonencode({ Rules = [{ ResourceType = "collection", Resource = ["collection/${var.name}-faq"] }], KmsARN = aws_kms_key.data.arn })
}
resource "aws_opensearchserverless_security_policy" "network" {
  count = var.enable_rag ? 1 : 0
  name  = "${var.name}-network"
  type  = "network"
  # Reachable endpoint, IAM + data policy required. Only PUBLIC FAQ documents are indexed.
  policy = jsonencode([{ Rules = [{ ResourceType = "collection", Resource = ["collection/${var.name}-faq"] }], AllowFromPublic = true }])
}
resource "aws_opensearchserverless_collection" "faq" {
  count            = var.enable_rag ? 1 : 0
  name             = "${var.name}-faq"
  type             = "VECTORSEARCH"
  standby_replicas = "ENABLED"
  depends_on       = [aws_opensearchserverless_security_policy.encryption, aws_opensearchserverless_security_policy.network]
}
resource "aws_opensearchserverless_access_policy" "faq" {
  count = var.enable_rag ? 1 : 0
  name  = "${var.name}-access"
  type  = "data"
  policy = jsonencode([
    { Rules = [
      { ResourceType = "collection", Resource = ["collection/${var.name}-faq"], Permission = ["aoss:DescribeCollectionItems"] },
      { ResourceType = "index", Resource = ["index/${var.name}-faq/*"], Permission = ["aoss:DescribeIndex", "aoss:ReadDocument", "aoss:WriteDocument"] }
    ], Principal = [aws_iam_role.knowledge[0].arn] },
    { Rules = [
      { ResourceType = "collection", Resource = ["collection/${var.name}-faq"], Permission = ["aoss:DescribeCollectionItems"] },
      { ResourceType = "index", Resource = ["index/${var.name}-faq/*"], Permission = ["aoss:CreateIndex", "aoss:UpdateIndex", "aoss:DeleteIndex", "aoss:DescribeIndex"] }
    ], Principal = [var.deployment_principal_arn] }
  ])
}
resource "aws_iam_role_policy" "knowledge" {
  count = var.enable_rag ? 1 : 0
  role  = aws_iam_role.knowledge[0].id
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["bedrock:InvokeModel"], Resource = "arn:${local.partition}:bedrock:${local.region}::foundation-model/amazon.titan-embed-text-v2:0" },
    { Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.documents.arn },
    { Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.documents.arn}/public/*" },
    { Effect = "Allow", Action = ["kms:Decrypt"], Resource = aws_kms_key.data.arn },
    { Effect = "Allow", Action = ["aoss:APIAccessAll"], Resource = aws_opensearchserverless_collection.faq[0].arn }
  ] })
}
resource "aws_cloudformation_stack" "index" {
  count         = var.enable_rag ? 1 : 0
  name          = "${var.name}-vector-index"
  template_body = file("${path.module}/templates/index.json")
  parameters    = { CollectionEndpoint = aws_opensearchserverless_collection.faq[0].collection_endpoint }
  depends_on    = [aws_opensearchserverless_access_policy.faq]
}
resource "aws_bedrockagent_knowledge_base" "faq" {
  count    = var.enable_rag ? 1 : 0
  name     = "${var.name}-faq"
  role_arn = aws_iam_role.knowledge[0].arn
  knowledge_base_configuration {
    type = "VECTOR"
    vector_knowledge_base_configuration {
      embedding_model_arn = "arn:${local.partition}:bedrock:${local.region}::foundation-model/amazon.titan-embed-text-v2:0"
    }
  }
  storage_configuration {
    type = "OPENSEARCH_SERVERLESS"
    opensearch_serverless_configuration {
      collection_arn    = aws_opensearchserverless_collection.faq[0].arn
      vector_index_name = "public-faq"
      field_mapping {
        vector_field   = "embedding"
        text_field     = "text"
        metadata_field = "metadata"
      }
    }
  }
  depends_on = [aws_cloudformation_stack.index, aws_iam_role_policy.knowledge]
}
resource "aws_bedrockagent_data_source" "faq" {
  count                = var.enable_rag ? 1 : 0
  knowledge_base_id    = aws_bedrockagent_knowledge_base.faq[0].id
  name                 = "public-documents"
  data_deletion_policy = "DELETE"
  data_source_configuration {
    type = "S3"
    s3_configuration {
      bucket_arn         = aws_s3_bucket.documents.arn
      inclusion_prefixes = ["public/"]
    }
  }
  vector_ingestion_configuration {
    chunking_configuration {
      chunking_strategy = "FIXED_SIZE"
      fixed_size_chunking_configuration {
        max_tokens         = 300
        overlap_percentage = 15
      }
    }
  }
}
