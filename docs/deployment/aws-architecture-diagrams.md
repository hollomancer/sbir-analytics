# AWS Infrastructure Architecture Diagrams

This document contains visual diagrams of the AWS infrastructure architecture for the SBIR ETL pipeline.

## High-Level Architecture

```mermaid
graph TB
    subgraph "GitHub Actions"
        GA[GitHub Actions<br/>Weekly Schedule/Manual Trigger]
    end
    
    subgraph "AWS us-east-2"
        subgraph "Orchestration"
            SF[Step Functions<br/>State Machine]
        end
        
        subgraph "Compute"
            L1[Lambda: download-csv<br/>Container Image]
            L2[Lambda: validate-dataset<br/>Layer]
            L3[Lambda: profile-inputs<br/>Layer]
            L4[Lambda: ingestion-checks<br/>Container Image]
            L5[Lambda: enrichment-checks<br/>Layer]
            L6[Lambda: reset-neo4j<br/>Layer]
            L7[Lambda: load-neo4j<br/>Container Image]
            L8[Lambda: smoke-checks<br/>Layer]
            L9[Lambda: create-pr<br/>Layer]
        end
        
        subgraph "Storage"
            S3[S3 Bucket<br/>sbir-etl-production-data]
            SM[Secrets Manager<br/>neo4j-aura credentials]
        end
        
        subgraph "External"
            NEO4J[Neo4j Aura<br/>Cloud Database]
            GH[GitHub API<br/>PR Creation]
            SBIR[SBIR.gov<br/>CSV Download]
        end
    end
    
    GA -->|OIDC Auth| SF
    SF --> L1
    SF --> L2
    SF --> L3
    SF --> L4
    SF --> L5
    SF --> L6
    SF --> L7
    SF --> L8
    SF --> L9
    
    L1 --> S3
    L1 --> SBIR
    L2 --> S3
    L3 --> S3
    L4 --> S3
    L5 --> S3
    L6 --> SM
    L6 --> NEO4J
    L7 --> SM
    L7 --> S3
    L7 --> NEO4J
    L8 --> SM
    L8 --> NEO4J
    L9 --> S3
    L9 --> SM
    L9 --> GH
    
    SM -.->|Provides Credentials| L6
    SM -.->|Provides Credentials| L7
    SM -.->|Provides Credentials| L8
    SM -.->|Provides Token| L9
    
    style GA fill:#2088ff
    style SF fill:#ff9900
    style S3 fill:#569a31
    style SM fill:#ff9900
    style NEO4J fill:#008cc1
    style GH fill:#2088ff
    style SBIR fill:#0066cc
```

## Step Functions State Machine Flow

```mermaid
stateDiagram-v2
    [*] --> DownloadCSV
    
    DownloadCSV --> CheckChanges: Success
    
    CheckChanges --> ProcessPipeline: Changed or ForceRefresh
    CheckChanges --> EndNoChanges: No Changes
    
    state ProcessPipeline {
        [*] --> ValidateDataset
        [*] --> ProfileInputs
        ValidateDataset --> [*]
        ProfileInputs --> [*]
    }
    
    ProcessPipeline --> IngestionChecks: Both Complete
    IngestionChecks --> EnrichmentChecks: Success
    EnrichmentChecks --> ResetNeo4j: Success
    ResetNeo4j --> LoadNeo4j: Success (Optional)
    LoadNeo4j --> SmokeChecks: Success
    SmokeChecks --> CreatePR: Success
    CreatePR --> [*]: Success
    
    CheckChanges --> EndNoChanges: No Changes
    EndNoChanges --> [*]
    
    DownloadCSV --> ErrorHandler: Error
    ValidateDataset --> ErrorHandler: Error
    ProfileInputs --> ErrorHandler: Error
    IngestionChecks --> ErrorHandler: Error
    EnrichmentChecks --> ErrorHandler: Error
    ResetNeo4j --> ErrorHandler: Error
    LoadNeo4j --> ErrorHandler: Error
    SmokeChecks --> ErrorHandler: Error
    CreatePR --> ErrorHandler: Error
    
    ErrorHandler --> [*]
    
    note right of ProcessPipeline
        Parallel Execution
        Both branches run simultaneously
    end note
    
    note right of ResetNeo4j
        Optional Step
        Can be skipped via config
    end note
```

## Data Flow Diagram

```mermaid
flowchart LR
    subgraph "Input"
        SBIR[SBIR.gov CSV]
        CONFIG[Workflow Config]
    end
    
    subgraph "S3 Bucket Structure"
        RAW[raw/awards/<br/>YYYY-MM-DD/<br/>award_data.csv]
        PROC[processed/<br/>validation/<br/>profiles/<br/>ingestion/<br/>enrichment/]
        ART[artifacts/<br/>YYYY-MM-DD/<br/>*.json<br/>*.md]
    end
    
    subgraph "Processing"
        L1[Download]
        L2[Validate]
        L3[Profile]
        L4[Ingestion]
        L5[Enrichment]
        L6[Load]
        L7[Smoke]
        L8[PR]
    end
    
    subgraph "Output"
        NEO4J[(Neo4j Aura)]
        GH[GitHub PR]
    end
    
    SBIR -->|HTTP GET| L1
    L1 -->|Upload| RAW
    RAW -->|Read| L2
    L2 -->|Write| PROC
    PROC -->|Read| L3
    L3 -->|Write| PROC
    PROC -->|Read| L4
    L4 -->|Write| PROC
    PROC -->|Read| L5
    L5 -->|Write| PROC
    PROC -->|Read| L6
    L6 -->|Write| ART
    L6 -->|Load| NEO4J
    ART -->|Read| L7
    L7 -->|Query| NEO4J
    ART -->|Read| L8
    L8 -->|Create| GH
    
    CONFIG -.->|Controls Flow| L1
    CONFIG -.->|Controls Flow| L2
    CONFIG -.->|Controls Flow| L3
    CONFIG -.->|Controls Flow| L4
    CONFIG -.->|Controls Flow| L5
    CONFIG -.->|Controls Flow| L6
    CONFIG -.->|Controls Flow| L7
    CONFIG -.->|Controls Flow| L8
```

## AWS Services Relationship Diagram

```mermaid
graph TB
    subgraph "Identity & Access"
        IAM1[IAM Role<br/>Lambda Execution]
        IAM2[IAM Role<br/>Step Functions]
        IAM3[IAM Role<br/>GitHub Actions OIDC]
    end
    
    subgraph "Compute & Orchestration"
        SF[Step Functions<br/>State Machine]
        L1[Lambda Functions<br/>9 functions]
        LC[Lambda Layers<br/>Dependencies]
        ECR[ECR Repositories<br/>Container Images]
    end
    
    subgraph "Storage & Secrets"
        S3[S3 Bucket<br/>sbir-etl-production-data]
        SM[Secrets Manager<br/>neo4j-aura]
    end
    
    subgraph "Monitoring"
        CW[CloudWatch Logs]
        CM[CloudWatch Metrics]
    end
    
    subgraph "External Services"
        NEO4J[Neo4j Aura]
        GH[GitHub API]
        SBIR[SBIR.gov]
    end
    
    IAM3 -->|Assume Role| SF
    IAM2 -->|Invoke| L1
    IAM1 -->|Execute| L1
    IAM1 -->|Read/Write| S3
    IAM1 -->|Read| SM
    
    SF -->|Orchestrates| L1
    L1 -->|Uses| LC
    L1 -->|Uses| ECR
    
    L1 -->|Read/Write| S3
    L1 -->|Read| SM
    L1 -->|Logs| CW
    L1 -->|Metrics| CM
    
    SM -->|Credentials| NEO4J
    L1 -->|Connect| NEO4J
    L1 -->|API Calls| GH
    L1 -->|Download| SBIR
    
    SF -->|Logs| CW
    SF -->|Metrics| CM
    
    style IAM1 fill:#ff9900
    style IAM2 fill:#ff9900
    style IAM3 fill:#ff9900
    style SF fill:#ff9900
    style S3 fill:#569a31
    style SM fill:#ff9900
    style CW fill:#ff4d00
    style CM fill:#ff4d00
```

## Lambda Packaging Strategy Diagram

```mermaid
graph TB
    subgraph "Packaging Option A: Lambda Layers"
        LAYER[Lambda Layer<br/>python-dependencies<br/>pandas, neo4j, boto3]
        FUNC1[Function Code<br/>validate-dataset<br/>profile-inputs<br/>smoke-checks]
        FUNC1 -->|Uses| LAYER
    end
    
    subgraph "Packaging Option B: Container Images"
        ECR[ECR Repository<br/>sbir-etl-lambda]
        CONTAINER[Docker Image<br/>Python 3.11<br/>+ Dependencies<br/>+ Dagster]
        FUNC2[Function Code<br/>ingestion-checks<br/>load-neo4j]
        CONTAINER -->|Contains| FUNC2
        FUNC2 -->|Deployed as| ECR
    end
    
    subgraph "Packaging Option C: Hybrid"
        HYBRID[Combination<br/>Layers for simple<br/>Containers for Dagster]
        HYBRID --> LAYER
        HYBRID --> CONTAINER
    end
    
    style LAYER fill:#569a31
    style CONTAINER fill:#008cc1
    style HYBRID fill:#ff9900
```

