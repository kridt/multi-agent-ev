# EV Systems --- AI Soccer Betting Platform

*More AI tools and guides: https://gptonline.ai/da/*

Built using the **Optic Odds API**\
(413 leagues, 155+ player statistics per match, historical data from
March 2024)

------------------------------------------------------------------------

# System Overview

The platform processes sports data through a structured pipeline:

1.  Data ingestion from external providers
2.  Data normalization and entity resolution
3.  Statistical modeling of player and team performance
4.  Odds comparison across bookmakers
5.  Expected value calculation
6.  Risk filtering and stake sizing
7.  Historical tracking and forward backtesting

All probability estimates are generated using **mathematical models and
code**, not LLMs.

LLMs such as Claude are used for:

-   orchestration
-   reasoning about anomalies
-   contextual interpretation (injuries, lineup changes, edge cases)

------------------------------------------------------------------------

# Core Statistical Models

## Poisson Models

Used for goal scoring and general event probabilities.

## Negative Binomial Models

Used for player statistics where variance exceeds Poisson assumptions.

## Dixon-Coles Model

Used for improving football goal prediction accuracy.

------------------------------------------------------------------------

# Target Betting Markets

## Tier 1 --- Player Props

-   Player shots (O/U)
-   Player tackles (O/U)
-   Player passes (O/U)
-   Anytime goalscorer
-   Player cards

## Tier 2 --- Team Markets

-   Team corners
-   Team goals
-   Both Teams To Score (BTTS)

## Tier 3 --- Match Markets

-   Match result (1X2)
-   Asian handicap

------------------------------------------------------------------------

# Key Statistical Features

## Per‑90 Normalization

Player statistics normalized to 90 minutes.

## Opponent Adjustments

Stats adjusted relative to opponent strength.

## Consistency Scoring

Variance analysis to avoid misleading averages.

## Rolling Windows

-   last 3 matches
-   last 5 matches
-   last 10 matches

## Walk‑Forward Backtesting

Training uses only past data before predictions.

## Drift Detection

Detects statistical performance changes over time.

------------------------------------------------------------------------

# Expected Value Calculation

EV = (Model Probability × Decimal Odds) − 1

Minimum EV threshold: **3%**

------------------------------------------------------------------------

# Risk Management

### Position Sizing

Quarter‑Kelly staking.

### Limits

-   Max **3% bankroll per bet**
-   Max **10% daily exposure**
-   Max **5% per fixture**

### Odds Range

-   Minimum odds: **1.50**
-   Maximum odds: **4.00**

### Stop Conditions

-   Stop if **daily loss \> 5%**
-   Stop if **drawdown \> 20% from peak**

------------------------------------------------------------------------

# Forward Backtesting System

The system records every detected value bet.

Stored data includes:

-   predicted probability
-   available odds
-   stake size
-   event result

This allows continuous evaluation of:

-   ROI
-   Brier score
-   drawdown
-   closing line value

------------------------------------------------------------------------

# External Data Sources

Primary provider:

**Optic Odds API**

Additional provider:

**The Odds API** (for bookmaker odds)

------------------------------------------------------------------------

# Multi‑Agent Development System

The platform is built using a **10‑agent architecture**.

------------------------------------------------------------------------

# Agent 1 --- Lead Orchestrator Agent

### Role

Project manager coordinating all agents.

### Responsibilities

-   interpret project instructions
-   break objectives into tasks
-   assign tasks to agents
-   coordinate dependencies
-   monitor progress
-   resolve uncertainties

### Output

-   completed tasks
-   design decisions
-   discovered issues
-   recommended next tasks

------------------------------------------------------------------------

# Agent 2 --- System Architect Agent

Designs backend architecture ensuring:

-   scalability
-   modularity
-   maintainability

### Output

-   architecture diagrams
-   service descriptions
-   API contracts

------------------------------------------------------------------------

# Agent 3 --- Backend Builder Agent

Implements backend services.

### Responsibilities

-   APIs
-   processing pipelines
-   background workers
-   scheduled jobs

Core processes:

-   data ingestion
-   normalization
-   entity matching
-   odds comparison
-   EV calculation
-   storage

------------------------------------------------------------------------

# Agent 4 --- Data Integration Agent

Handles external API connections.

### Responsibilities

-   retrieve odds
-   retrieve event data
-   retrieve player stats
-   handle rate limits
-   retry logic

All **raw data must be stored before transformation**.

------------------------------------------------------------------------

# Agent 5 --- Entity Resolution Agent

Handles **team, league, and event name mismatches**.

Example:

-   FC Barcelona
-   Barcelona
-   Barca
-   FC Barca

### Techniques

-   alias tables
-   fuzzy matching
-   contextual checks
-   confidence scoring

------------------------------------------------------------------------

# Agent 6 --- Odds & Value Analysis Agent

Handles betting market analysis.

### Responsibilities

-   compare bookmaker odds
-   calculate implied probabilities
-   detect best price
-   compute EV
-   filter unreliable signals

------------------------------------------------------------------------

# Agent 7 --- Database & Data Model Agent

Designs database schema.

### Tables include

-   raw events
-   raw odds
-   normalized entities
-   aliases
-   matched events
-   odds history
-   value signals
-   model predictions
-   bet tracking

Database:

-   SQLite (development)
-   PostgreSQL (production)

------------------------------------------------------------------------

# Agent 8 --- QA & Testing Agent

Validates system behavior.

### Tests

-   API connectors
-   entity resolution
-   statistical models
-   EV calculations

Outputs:

-   unit tests
-   integration tests
-   validation reports

------------------------------------------------------------------------

# Agent 9 --- Critic / Design Review Agent

Challenges assumptions.

Responsibilities:

-   identify architectural risks
-   simplify overly complex systems
-   suggest improvements

------------------------------------------------------------------------

# Agent 10 --- Documentation & Delivery Agent

Compiles final system documentation.

### Nightly Report

-   completed tasks
-   architecture decisions
-   module changes
-   test results
-   risks
-   next steps

------------------------------------------------------------------------

# Development Phases

## Phase 1--2 --- Data Infrastructure (4 weeks)

Build:

-   API clients
-   ingestion pipelines
-   database schema
-   entity resolution system
-   feature pipeline

The system must automatically detect **name mismatches**.

------------------------------------------------------------------------

## Phase 3 --- Statistical Modeling (3 weeks)

Implement statistical models for:

-   player props
-   team stats
-   match outcomes

------------------------------------------------------------------------

## Phase 4 --- EV Engine + Forward Backtesting (2 weeks)

Build value detection engine.

Store:

-   odds
-   predictions
-   stake size
-   final results

------------------------------------------------------------------------

## Phase 5 --- Multi‑Agent System with Claude (3 weeks)

Claude coordinates:

-   orchestration
-   agent communication
-   anomaly reasoning

------------------------------------------------------------------------

## Phase 6 --- Live Operation

Launch with **small stakes**.

Only bets within:

-   EV threshold
-   odds range
-   risk rules

are executed.

------------------------------------------------------------------------

# Go‑Live Criteria

-   Brier Score \< **0.22**
-   ROI \> **3% over 500+ bets**
-   Max drawdown \< **15%**
-   Beat closing line **\>55%**

------------------------------------------------------------------------

# Technology Stack

Python **3.12**

Libraries:

-   httpx
-   statsmodels
-   scikit‑learn
-   XGBoost

Database:

-   SQLite → PostgreSQL

CLI:

-   typer
-   rich

LLM orchestration:

-   Claude API

------------------------------------------------------------------------

*More AI tools and guides: https://gptonline.ai/da/*
