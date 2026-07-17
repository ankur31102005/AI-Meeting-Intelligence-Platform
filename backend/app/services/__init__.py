"""Service layer — ALL business logic. Owns transactions (commit/rollback).

Services know nothing about HTTP (no Request/Response imports) and nothing
about SQL (queries live in repositories). That is the Clean Architecture
boundary that keeps this logic testable and transport-agnostic.
"""
