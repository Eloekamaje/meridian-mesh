provider "aws" {
  region     = var.region
  access_key = "test"
  secret_key = "test"

  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true
  skip_region_validation      = true
  s3_use_path_style           = true

  endpoints {
    s3             = var.endpoint
    sqs            = var.endpoint
    iam            = var.endpoint
    sts            = var.endpoint
    secretsmanager = var.endpoint
    kms            = var.endpoint
    logs           = var.endpoint
    events         = var.endpoint
    scheduler      = var.endpoint
  }
}
