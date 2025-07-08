locals {
  bucket_name = "bp-s3-${var.bucket_name}-${random_string.this.id}"
}

module "s3_bucket" {
  source = "terraform-aws-modules/s3-bucket/aws"
  
  bucket = local.bucket_name
  
  attach_policy                         = true
  policy                                = data.aws_iam_policy_document.bucket_policy.json
  attach_deny_insecure_transport_policy = true
  attach_require_latest_tls_policy      = true

  # S3 bucket-level Public Access Block configuration
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true

  versioning = {
    enabled = true
  }
   
  logging = {
    target_bucket = var.target_bucket
    target_prefix = "/"
  }
  
  server_side_encryption_configuration = {
    rule = {
      apply_server_side_encryption_by_default = {
        kms_master_key_id = var.kms_master_key_id
        sse_algorithm     = "aws:kms"
      }
    }
  }
}

resource "random_string" "this" {
  length      = 8
  min_numeric = 8
  special     = false
  numeric       = true
}

data "aws_iam_policy_document" "bucket_policy" {
statement {
    sid     = "AllowSSLRequestsOnly"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      "${module.s3_bucket.s3_bucket_arn}",
      "${module.s3_bucket.s3_bucket_arn}/*"
    ]

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}
