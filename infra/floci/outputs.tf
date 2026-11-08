output "endpoint" {
  value = var.endpoint
}

output "region" {
  value = var.region
}

output "pieces_bucket" {
  value = aws_s3_bucket.this["pieces"].bucket
}

output "index_bucket" {
  value = aws_s3_bucket.this["index"].bucket
}

output "sessions_bucket" {
  value = aws_s3_bucket.this["sessions"].bucket
}

output "outbox_queue_url" {
  value = aws_sqs_queue.outbox.id
}

output "outbox_queue_arn" {
  value = aws_sqs_queue.outbox.arn
}

output "outbox_dlq_url" {
  value = aws_sqs_queue.outbox_dlq.id
}

output "wakeup_queue_url" {
  value = aws_sqs_queue.wakeup.id
}

output "wakeup_queue_arn" {
  value = aws_sqs_queue.wakeup.arn
}

output "event_bus" {
  value = aws_cloudwatch_event_bus.meridian.name
}

output "scheduler_group" {
  value = aws_scheduler_schedule_group.meridian.name
}

output "task_role_arn" {
  value = aws_iam_role.task.arn
}

output "scheduler_role_arn" {
  value = aws_iam_role.scheduler.arn
}

output "secret_name" {
  value = aws_secretsmanager_secret.local.name
}

output "secret_arn" {
  value = aws_secretsmanager_secret.local.arn
}

output "kms_key_arn" {
  value = aws_kms_key.local.arn
}

output "kms_alias" {
  value = aws_kms_alias.local.name
}

output "log_groups" {
  value = [for group in aws_cloudwatch_log_group.this : group.name]
}
