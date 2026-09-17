# P1A Test Matrix — spec §12 traceability map

Spec source: `docs/spec/CostGuard_Split_P1A_Usage_Ingestion_Spec_v0.1.md`
§12 (Testing Matrix). Machine-checked twin: `MATRIX` in
`tests/split_p1a_matrix_test.py` — if a test below is deleted or renamed,
`MatrixIndexTests` fails. Status: P1A-08 slice.

| ID | Case | Tests (file :: TestCase :: test) |
|----|------|----------------------------------|
| U1 | UsageEventClaim rejects float tokens | tests/split_p1a_claim_test.py :: UsageEventClaimBoundaryTests :: test_every_counter_rejects_bool_float_string_and_negative |
| U2 | Forbidden authority fields rejected | tests/split_p1a_claim_test.py :: UsageEventClaimBoundaryTests :: test_server_authority_money_and_private_fields_are_all_rejected |
| U3 | Claude cache token classes round-trip | tests/split_p1a_provider_test.py :: ClaudeConnectorTests :: test_normalize_maps_all_token_classes_and_identity |
| U4 | canonical_source_event_id stable + distinct | tests/split_p1a_ingest_test.py :: UsageIngestTests :: test_missing_source_event_id_is_deterministic_and_payload_sensitive |
| U5 | same-second different payloads → different ids | tests/split_p1a_ingest_test.py :: UsageIngestTests :: test_same_session_and_timestamp_with_distinct_event_ids_both_insert |
| I1 | first ingest created | tests/split_api_usage_test.py :: SingleEventTests :: test_created_returns_201_and_event_shape |
| I2 | identical retransmit duplicate, same server id | tests/split_api_usage_test.py :: SingleEventTests :: test_duplicate_replay_returns_200_same_id |
| I3 | batch partial success | tests/split_api_usage_test.py :: BatchTests :: test_mixed_results_partial_success |
| I4 | event-time member_at derivation | tests/split_p1a_ingest_test.py :: UsageIngestTests :: test_member_is_derived_from_assignment_at_event_start |
| I5 | unassigned device → member_id NULL | tests/split_p1a_ingest_test.py :: UsageIngestTests :: test_unassigned_event_has_null_member |
| S1 | spoof cost/org/member → 422 + zero rows | tests/split_api_usage_test.py :: SingleEventTests :: test_forbidden_and_server_fields_are_422 |
| S2 | cross-org device_uid event → 404/reject, no leak | tests/split_api_usage_test.py :: SingleEventTests :: test_unknown_device_is_404_hidden_without_usage_write |
| S3 | foreign event GET → 404 | tests/split_api_usage_test.py :: ReadEventTests :: test_get_foreign_event_is_404_hidden |
| C1 | ClaudeConnector normalize fixture | tests/split_p1a_provider_test.py :: ClaudeConnectorTests :: test_normalize_maps_all_token_classes_and_identity |
| C2 | CodexConnector normalize fixture | tests/split_p1a_provider_test.py :: CodexConnectorTests :: test_discover_and_normalize_full_turn |
| C3 | adding FakeProvider requires no core edit | tests/split_p1a_matrix_test.py :: FakeProviderIsolationTests :: test_c3_new_provider_requires_no_core_edit (baseline guard: test_core_tree_is_clean_baseline_for_c3) |
| M1 | migration v2→v3 idempotent | tests/split_p1a_matrix_test.py :: MigrationSurvivalTests :: test_m1_p0_data_survives_v2_to_v3_field_by_field (deep: orgs/members/devices/audit field-by-field + derived assignments + v3 composite-FK tenancy) |
| M2 | fresh DB → v3 | tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_fresh_database_reaches_v3_and_repeat_is_noop |
| X1 | no REAL/FLOAT money columns guard | tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_migration_guard_rejects_all_float_money_types |
| P1 | public price apply optional path Decimal-safe | DEFERRED — P1A-2 slice (feature-flagged); pricing logic must not exist in P1A core |

Additional M1/M2 depth coverage (pre-existing, complements the IDs above):
- tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_v2_upgrades_to_v3_without_losing_p0_data
- tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_usage_columns_indexes_and_numeric_types
- tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_identity_unique_but_same_timestamp_distinct_event_is_allowed
- tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_composite_device_and_member_foreign_keys_enforce_tenant
- tests/split_p1a_schema_test.py :: SchemaV3Tests :: test_database_rejects_each_negative_counter

Rules:
- All tests run against temporary DBs / COSTGUARD_HOME; no host `~/.costguard`
  dependence (spec §12:589).
- The matrix index is enforced by
  tests/split_p1a_matrix_test.py :: MatrixIndexTests; any ID above whose
  target test disappears fails the suite.
