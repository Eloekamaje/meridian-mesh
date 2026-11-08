variable "endpoint" {
  description = "Endpoint Floci (AWS local)."
  type        = string
  default     = "http://127.0.0.1:4566"
}

variable "region" {
  description = "Région AWS simulée ; doit rester cohérente avec les ARN et les clients Méridian."
  type        = string
  default     = "ca-central-1"
}

variable "prefix" {
  description = "Préfixe des ressources Méridian dans Floci."
  type        = string
  default     = "meridian"
}

variable "bedrock_model_arns" {
  description = "ARN Bedrock autorisés pour le rôle de tâche. En local, * est acceptable ; en AWS réel, restreindre aux modèles/profils utilisés."
  type        = list(string)
  default     = ["*"]
}

variable "tags" {
  description = "Tags appliqués aux ressources."
  type        = map(string)
  default = {
    Project     = "meridian"
    Environment = "floci"
    ManagedBy   = "terraform"
  }
}
