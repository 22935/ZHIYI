variable "IMAGE_PREFIX" {
  default = "kinlin-ai"
}

variable "VERSION" {
  default = "1.0.0"
}

variable "GIT_SHA" {
  default = "unknown"
}

variable "CREATED" {
  default = "1970-01-01T00:00:00Z"
}

target "_common" {
  args = {
    KINLIN_VERSION  = VERSION
    KINLIN_REVISION = GIT_SHA
    KINLIN_CREATED  = CREATED
  }
  labels = {
    "org.opencontainers.image.version"  = VERSION
    "org.opencontainers.image.revision" = GIT_SHA
    "org.opencontainers.image.created"  = CREATED
  }
}

target "_release" {
  attest = [
    "type=provenance,mode=max",
    "type=sbom"
  ]
}

target "frontend" {
  inherits   = ["_common"]
  context    = "./frontend"
  dockerfile = "Dockerfile"
  tags = [
    "${IMAGE_PREFIX}/frontend:${VERSION}",
    "${IMAGE_PREFIX}/frontend:sha-${GIT_SHA}"
  ]
}

target "backend" {
  inherits   = ["_common"]
  context    = "./backend"
  dockerfile = "Dockerfile"
  tags = [
    "${IMAGE_PREFIX}/backend:${VERSION}",
    "${IMAGE_PREFIX}/backend:sha-${GIT_SHA}"
  ]
}

target "ai-service" {
  inherits   = ["_common"]
  context    = "."
  dockerfile = "agent/Dockerfile"
  tags = [
    "${IMAGE_PREFIX}/ai-service:${VERSION}",
    "${IMAGE_PREFIX}/ai-service:sha-${GIT_SHA}"
  ]
}

target "postgres" {
  inherits   = ["_common"]
  context    = "./docker/postgres"
  dockerfile = "Dockerfile"
  tags = [
    "${IMAGE_PREFIX}/postgres:${VERSION}",
    "${IMAGE_PREFIX}/postgres:sha-${GIT_SHA}"
  ]
}

target "redis" {
  inherits   = ["_common"]
  context    = "./docker/redis"
  dockerfile = "Dockerfile"
  tags = [
    "${IMAGE_PREFIX}/redis:${VERSION}",
    "${IMAGE_PREFIX}/redis:sha-${GIT_SHA}"
  ]
}

target "flyway" {
  inherits   = ["_common"]
  context    = "./docker/flyway"
  dockerfile = "Dockerfile"
  tags = [
    "${IMAGE_PREFIX}/flyway:${VERSION}",
    "${IMAGE_PREFIX}/flyway:sha-${GIT_SHA}"
  ]
}

target "frontend-amd64" {
  inherits = ["frontend", "_release"]
  platforms = ["linux/amd64"]
}
target "backend-amd64" {
  inherits = ["backend", "_release"]
  platforms = ["linux/amd64"]
}
target "ai-service-amd64" {
  inherits = ["ai-service", "_release"]
  platforms = ["linux/amd64"]
}
target "postgres-amd64" {
  inherits = ["postgres", "_release"]
  platforms = ["linux/amd64"]
}
target "redis-amd64" {
  inherits = ["redis", "_release"]
  platforms = ["linux/amd64"]
}
target "flyway-amd64" {
  inherits = ["flyway", "_release"]
  platforms = ["linux/amd64"]
}

target "frontend-arm64" {
  inherits = ["frontend", "_release"]
  platforms = ["linux/arm64"]
}
target "backend-arm64" {
  inherits = ["backend", "_release"]
  platforms = ["linux/arm64"]
}
target "ai-service-arm64" {
  inherits = ["ai-service", "_release"]
  platforms = ["linux/arm64"]
}
target "postgres-arm64" {
  inherits = ["postgres", "_release"]
  platforms = ["linux/arm64"]
}
target "redis-arm64" {
  inherits = ["redis", "_release"]
  platforms = ["linux/arm64"]
}
target "flyway-arm64" {
  inherits = ["flyway", "_release"]
  platforms = ["linux/arm64"]
}

target "frontend-multiarch" {
  inherits = ["frontend", "_release"]
  platforms = ["linux/amd64", "linux/arm64"]
}
target "backend-multiarch" {
  inherits = ["backend", "_release"]
  platforms = ["linux/amd64", "linux/arm64"]
}
target "ai-service-multiarch" {
  inherits = ["ai-service", "_release"]
  platforms = ["linux/amd64", "linux/arm64"]
}
target "postgres-multiarch" {
  inherits = ["postgres", "_release"]
  platforms = ["linux/amd64", "linux/arm64"]
}
target "redis-multiarch" {
  inherits = ["redis", "_release"]
  platforms = ["linux/amd64", "linux/arm64"]
}
target "flyway-multiarch" {
  inherits = ["flyway", "_release"]
  platforms = ["linux/amd64", "linux/arm64"]
}

group "default" {
  targets = ["all"]
}
group "all" {
  targets = ["frontend", "backend", "ai-service", "runtime-dependencies"]
}
group "runtime-dependencies" {
  targets = ["postgres", "redis", "flyway"]
}
group "release-amd64" {
  targets = ["frontend-amd64", "backend-amd64", "ai-service-amd64", "postgres-amd64", "redis-amd64", "flyway-amd64"]
}
group "release-arm64" {
  targets = ["frontend-arm64", "backend-arm64", "ai-service-arm64", "postgres-arm64", "redis-arm64", "flyway-arm64"]
}
group "release-multiarch" {
  targets = ["frontend-multiarch", "backend-multiarch", "ai-service-multiarch", "postgres-multiarch", "redis-multiarch", "flyway-multiarch"]
}
