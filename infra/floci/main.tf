locals {
  buckets = {
    pieces   = "${var.prefix}-pieces"
    index    = "${var.prefix}-index"
    sessions = "${var.prefix}-sessions"
  }

  queue_outbox     = "${var.prefix}-outbox"
  queue_outbox_dlq = "${var.prefix}-outbox-dlq"
  queue_wakeup     = "${var.prefix}-source-wakeup"

  event_bus       = var.prefix
  scheduler_group = var.prefix
  secret_name     = "${var.prefix}/local"

  log_groups = [
    "/meridian/api",
    "/meridian/workers",
    "/meridian/ingestion",
  ]
}

# --- Chiffrement -----------------------------------------------------------

resource "aws_kms_key" "local" {
  description             = "Clé locale Méridian (Floci)"
  deletion_window_in_days = 7
  enable_key_rotation     = false
  tags                    = var.tags
}

resource "aws_kms_alias" "local" {
  name          = "alias/${var.prefix}-local"
  target_key_id = aws_kms_key.local.key_id
}

# --- Stockage objet --------------------------------------------------------

resource "aws_s3_bucket" "this" {
  for_each = local.buckets

  bucket        = each.value
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_versioning" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  for_each = aws_s3_bucket.this

  bucket                  = each.value.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.local.arn
    }
    bucket_key_enabled = true
  }
}

# --- Files d'attente -------------------------------------------------------

resource "aws_sqs_queue" "outbox_dlq" {
  name                       = local.queue_outbox_dlq
  message_retention_seconds  = 1209600
  visibility_timeout_seconds = 60
  tags                       = var.tags
}

resource "aws_sqs_queue" "outbox" {
  name                       = local.queue_outbox
  message_retention_seconds  = 345600
  visibility_timeout_seconds = 60
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.outbox_dlq.arn
    maxReceiveCount     = 5
  })
  tags = var.tags
}

resource "aws_sqs_queue" "wakeup" {
  name                       = local.queue_wakeup
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 30
  tags                       = var.tags
}

# --- Bus d'événements et règle outbox -------------------------------------

resource "aws_cloudwatch_event_bus" "meridian" {
  name = local.event_bus
  tags = var.tags
}

resource "aws_cloudwatch_event_rule" "outbox" {
  name           = "${var.prefix}-outbox"
  event_bus_name = aws_cloudwatch_event_bus.meridian.name
  event_pattern = jsonencode({
    source = ["meridian"]
  })
  tags = var.tags
}

resource "aws_cloudwatch_event_target" "outbox" {
  rule           = aws_cloudwatch_event_rule.outbox.name
  event_bus_name = aws_cloudwatch_event_bus.meridian.name
  arn            = aws_sqs_queue.outbox.arn
}

# --- Rôles IAM -------------------------------------------------------------

data "aws_iam_policy_document" "ecs_tasks_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "${var.prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_tasks_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "task" {
  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [for bucket in aws_s3_bucket.this : bucket.arn]
  }

  statement {
    sid       = "S3Objects"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:AbortMultipartUpload"]
    resources = [for bucket in aws_s3_bucket.this : "${bucket.arn}/*"]
  }

  statement {
    sid = "Queues"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [
      aws_sqs_queue.outbox.arn,
      aws_sqs_queue.outbox_dlq.arn,
      aws_sqs_queue.wakeup.arn,
    ]
  }

  statement {
    sid       = "EventBridgeOutbox"
    actions   = ["events:PutEvents"]
    resources = [aws_cloudwatch_event_bus.meridian.arn]
  }

  statement {
    sid       = "SecretLocal"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_secretsmanager_secret.local.arn]
  }

  statement {
    sid       = "KmsLocal"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.local.arn]
  }

  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [for group in aws_cloudwatch_log_group.this : "${group.arn}:*"]
  }

  statement {
    sid       = "Bedrock"
    actions   = ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Converse", "bedrock:ConverseStream"]
    resources = var.bedrock_model_arns
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "${var.prefix}-task"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.wakeup.arn]
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "${var.prefix}-scheduler"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

# --- Autorisations des files ----------------------------------------------

data "aws_iam_policy_document" "outbox_queue" {
  statement {
    sid       = "AllowEventBridgeOutbox"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.outbox.arn]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
    # En AWS réel, ajouter une condition aws:SourceArn sur la règle EventBridge.
  }
}

resource "aws_sqs_queue_policy" "outbox" {
  queue_url = aws_sqs_queue.outbox.id
  policy    = data.aws_iam_policy_document.outbox_queue.json
}

data "aws_iam_policy_document" "wakeup_queue" {
  statement {
    sid       = "AllowSchedulerWakeup"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.wakeup.arn]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.scheduler.arn]
    }
  }
}

resource "aws_sqs_queue_policy" "wakeup" {
  queue_url = aws_sqs_queue.wakeup.id
  policy    = data.aws_iam_policy_document.wakeup_queue.json
}

# --- Scheduler -------------------------------------------------------------

resource "aws_scheduler_schedule_group" "meridian" {
  name = local.scheduler_group
  tags = var.tags
}

# --- Secrets (adaptateur optionnel ; Vault reste le coffre principal) ------

resource "aws_secretsmanager_secret" "local" {
  name                    = local.secret_name
  recovery_window_in_days = 0
  tags                    = var.tags
}

resource "aws_secretsmanager_secret_version" "local" {
  secret_id = aws_secretsmanager_secret.local.id
  secret_string = jsonencode({
    jeton          = "meridian-local"
    webhook_secret = "meridian-local-webhook"
  })
}

# --- Observabilité ---------------------------------------------------------

resource "aws_cloudwatch_log_group" "this" {
  for_each = toset(local.log_groups)

  name              = each.value
  retention_in_days = 7
  tags              = var.tags
}
