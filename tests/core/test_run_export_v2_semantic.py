#!/usr/bin/env python3
# Copyright (c) 2025 Osiris Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for PR3 - Semantic/Ontology Layer."""

import json


class TestSemanticLayer:
    """Test PR3 Semantic Layer functions."""

    def test_dag_extraction(self):
        """Test 1: DAG extraction from manifest."""
        from osiris.core.run_export_v2 import extract_dag_structure

        # Input manifest with 3 steps: extract -> transform -> export
        manifest = {
            "pipeline": "test_pipeline",
            "manifest_hash": "abc123def",  # pragma: allowlist secret  # pragma: allowlist secret
            "steps": [
                {
                    "id": "extract",
                    "type": "mysql.extractor",
                    "config": {"table": "customers"},
                    "outputs": ["customers_df"],
                },
                {
                    "id": "transform",
                    "type": "transform.sql",
                    "config": {"query": "SELECT * FROM customers_df"},
                    "inputs": ["customers_df"],
                    "outputs": ["transformed_df"],
                },
                {
                    "id": "export",
                    "type": "filesystem.csv_writer",
                    "config": {"path": "/tmp/output.csv"},
                    "inputs": ["transformed_df"],
                },
            ],
        }

        result = extract_dag_structure(manifest)

        # Assert nodes are present in topological or stable order
        assert "nodes" in result
        assert "edges" in result
        assert "counts" in result

        assert result["nodes"] == ["extract", "transform", "export"]

        # Assert edges with correct relationships
        expected_edges = [
            {"from": "extract", "to": "transform", "relation": "produces"},
            {"from": "transform", "to": "export", "relation": "produces"},
        ]
        assert result["edges"] == expected_edges

        # Assert counts
        assert result["counts"]["nodes"] == 3
        assert result["counts"]["edges"] == 2

    def test_component_ontology_summary(self):
        """Test 2a: Component ontology with summary mode."""
        from osiris.core.run_export_v2 import build_component_ontology

        components = {
            "mysql.extractor": {
                "name": "mysql.extractor",
                "version": "1.0.0",
                "capabilities": ["extract", "sql"],
                "schema": {
                    "properties": {
                        "table": {"type": "string"},
                        "password": {"type": "string", "secret": True},
                    }
                },
            },
            "filesystem.csv_writer": {
                "name": "filesystem.csv_writer",
                "version": "1.0.0",
                "capabilities": ["write", "csv"],
                "schema": {
                    "properties": {
                        "path": {"type": "string"},
                        "api_key": {"type": "string", "secret": True},
                    }
                },
            },
        }

        result = build_component_ontology(components, mode="summary")

        # Each component should have @id and capabilities
        assert "mysql.extractor" in result
        assert "@id" in result["mysql.extractor"]
        assert result["mysql.extractor"]["@id"] == "osiris://component/mysql.extractor"
        assert "capabilities" in result["mysql.extractor"]
        assert result["mysql.extractor"]["capabilities"] == ["extract", "sql"]

        # No verbose schemas in summary mode
        assert "schema" not in result["mysql.extractor"]

        # No secret fields should appear
        assert "password" not in json.dumps(result)
        assert "api_key" not in json.dumps(result)

    def test_component_ontology_detailed(self):
        """Test 2b: Component ontology with detailed mode."""
        from osiris.core.run_export_v2 import build_component_ontology

        components = {
            "mysql.extractor": {
                "name": "mysql.extractor",
                "version": "1.0.0",
                "capabilities": ["extract", "sql"],
                "schema": {
                    "type": "object",
                    "properties": {
                        "table": {"type": "string", "description": "Table name"},
                        "password": {"type": "string", "secret": True},
                        "token": {"type": "string"},
                    },
                },
            }
        }

        result = build_component_ontology(components, mode="detailed")

        # Should include schema snippet
        assert "schema" in result["mysql.extractor"]
        schema = result["mysql.extractor"]["schema"]

        # Should include non-secret properties
        assert "properties" in schema
        assert "table" in schema["properties"]

        # Should exclude secret fields
        assert "password" not in schema.get("properties", {})
        assert "token" not in schema.get("properties", {})

        # Deterministic output
        result2 = build_component_ontology(components, mode="detailed")
        assert json.dumps(result, sort_keys=True) == json.dumps(result2, sort_keys=True)

    def test_semantic_layer_envelope(self):
        """Test 3: Semantic layer envelope shape."""
        from osiris.core.run_export_v2 import build_semantic_layer

        manifest = {
            "pipeline": "test_pipeline",
            "manifest_hash": "abc123def",  # pragma: allowlist secret
            "steps": [
                {"id": "extract", "type": "mysql.extractor", "outputs": ["df"]},
                {"id": "export", "type": "csv.writer", "inputs": ["df"]},
            ],
        }

        oml_spec = {
            "oml_version": "0.1.0",
            "name": "test_pipeline",
            "steps": [
                {"name": "extract", "component": "mysql.extractor"},
                {"name": "export", "component": "csv.writer"},
            ],
        }

        registry = {
            "mysql.extractor": {"name": "mysql.extractor", "capabilities": ["extract"]},
            "csv.writer": {"name": "csv.writer", "capabilities": ["write"]},
        }

        result = build_semantic_layer(manifest, oml_spec, registry, "summary")

        # Check envelope structure
        assert "@type" in result
        assert result["@type"] == "SemanticLayer"
        assert "oml_version" in result
        assert result["oml_version"] == "0.1.0"
        assert "components" in result
        assert "dag" in result

        # Check DAG structure
        assert "nodes" in result["dag"]
        assert "edges" in result["dag"]
        assert "counts" in result["dag"]

        # Check URIs match ADR rules (no trailing slash)
        json_str = json.dumps(result)
        assert "osiris://" in json_str
        assert not any(uri.endswith("/") for uri in json_str.split('"') if uri.startswith("osiris://"))

        # Keys should be sorted
        keys = list(result.keys())
        assert keys == sorted(keys)

    def test_graph_hints_generation(self):
        """Test 4: Graph hints for GraphRAG."""
        from osiris.core.run_export_v2 import generate_graph_hints

        manifest = {
            "pipeline": "test_pipeline",
            "manifest_hash": "abc123def",  # pragma: allowlist secret
            "steps": [
                {"id": "extract", "type": "mysql.extractor", "outputs": ["df"]},
                {"id": "transform", "type": "sql.transform", "inputs": ["df"], "outputs": ["df2"]},
                {"id": "export", "type": "csv.writer", "inputs": ["df2"]},
            ],
        }

        run_data = {"session_id": "run_123", "status": "success"}

        result = generate_graph_hints(manifest, run_data)

        # Check structure
        assert "triples" in result
        assert "counts" in result
        assert "triple_count" in result["counts"]

        # Check triples format
        assert len(result["triples"]) > 0
        for triple in result["triples"]:
            assert "s" in triple  # subject
            assert "p" in triple  # predicate
            assert "o" in triple  # object
            assert triple["s"].startswith("osiris://")
            assert triple["o"].startswith("osiris://")
            assert ":" in triple["p"]  # CURIE format

        # Check predicates are from context
        valid_predicates = ["osiris:produces", "osiris:consumes", "osiris:depends_on"]
        for triple in result["triples"]:
            assert triple["p"] in valid_predicates

        # Count equals actual triples
        assert result["counts"]["triple_count"] == len(result["triples"])

    def test_jsonld_conformance(self):
        """Test 5: JSON-LD conformance smoke test."""
        from osiris.core.run_export_v2 import build_semantic_layer

        manifest = {
            "pipeline": "test",
            "manifest_hash": "hash123",  # pragma: allowlist secret
            "steps": [{"id": "step1", "type": "test.component"}],
        }
        oml_spec = {"oml_version": "0.1.0", "name": "test"}
        registry = {"test.component": {"name": "test.component", "capabilities": []}}

        result = build_semantic_layer(manifest, oml_spec, registry, "summary")

        # All @id values should be strings
        def check_ids(obj):
            if isinstance(obj, dict):
                if "@id" in obj:
                    assert isinstance(obj["@id"], str)
                    assert obj["@id"].startswith("osiris://")
                if "@type" in obj:
                    assert isinstance(obj["@type"], str | list)
                for value in obj.values():
                    check_ids(value)
            elif isinstance(obj, list):
                for item in obj:
                    check_ids(item)

        check_ids(result)

    def test_no_secrets_in_output(self):
        """Test 6: No secrets in semantic output."""
        from osiris.core.run_export_v2 import build_semantic_layer

        manifest = {"pipeline": "test", "manifest_hash": "hash", "steps": []}
        oml_spec = {"oml_version": "0.1.0", "name": "test"}

        # Component with secrets
        registry = {
            "test.comp": {
                "name": "test.comp",
                "capabilities": ["test"],
                "schema": {
                    "properties": {
                        "username": {"type": "string"},
                        "password": {"type": "string", "secret": True},
                        "api_key": {"type": "string"},
                        "token": {"type": "string"},
                        "secret": {"type": "string"},
                    }
                },
            }
        }

        result = build_semantic_layer(manifest, oml_spec, registry, "detailed")

        # Convert to JSON string to search
        json_str = json.dumps(result).lower()

        # Assert no secret field names appear
        assert "password" not in json_str
        assert "api_key" not in json_str
        assert "token" not in json_str
        assert "secret" not in json_str

    def test_dag_extraction_with_depends_on(self):
        """Test 7: DAG extraction reads depends_on field."""
        from osiris.core.run_export_v2 import extract_dag_structure

        manifest = {
            "name": "customer_etl_pipeline",
            "manifest_hash": "abc123",  # pragma: allowlist secret
            "steps": [
                {"id": "extract", "outputs": ["raw_data"]},
                {
                    "id": "transform",
                    "depends_on": ["extract"],
                    "inputs": ["raw_data"],
                    "outputs": ["clean_data"],
                },
                {"id": "export", "depends_on": ["transform"], "inputs": ["clean_data"]},
            ],
        }

        dag = extract_dag_structure(manifest)

        # Should have both produces and depends_on edges
        assert len(dag["edges"]) >= 2

        # Check for depends_on edges
        depends_edges = [e for e in dag["edges"] if e["relation"] == "depends_on"]
        assert len(depends_edges) == 2
        assert {"from": "extract", "to": "transform", "relation": "depends_on"} in dag["edges"]
        assert {"from": "transform", "to": "export", "relation": "depends_on"} in dag["edges"]

    def test_pipeline_uri_exposure(self):
        """Test 8: Pipeline URI exposed in semantic layer."""
        from osiris.core.run_export_v2 import build_semantic_layer

        manifest = {
            "pipeline": "test_pipeline",
            "manifest_hash": "abc123def",  # pragma: allowlist secret
            "steps": [{"id": "step1", "type": "test.component"}],
        }
        oml_spec = {"oml_version": "0.1.0", "name": "test_pipeline"}
        registry = {"test.component": {"name": "test.component", "capabilities": []}}

        result = build_semantic_layer(manifest, oml_spec, registry, "summary")

        # Check pipeline URI is exposed
        assert "@id" in result or "pipeline_id" in result

        # Get the URI (could be in either field)
        pipeline_uri = result.get("@id") or result.get("pipeline_id")
        assert pipeline_uri is not None
        assert pipeline_uri == "osiris://pipeline/@abc123def"  # pragma: allowlist secret

    def test_graph_hints_generates_triples(self):
        """Test 9: Graph hints generates triples from DAG edges."""
        from osiris.core.run_export_v2 import generate_graph_hints

        manifest = {
            "pipeline": "test_pipeline",
            "manifest_hash": "abc123def",  # pragma: allowlist secret
            "steps": [
                {"id": "extract", "type": "mysql.extractor", "outputs": ["df"]},
                {
                    "id": "transform",
                    "type": "sql.transform",
                    "inputs": ["df"],
                    "outputs": ["df2"],
                    "depends_on": ["extract"],
                },
                {
                    "id": "export",
                    "type": "csv.writer",
                    "inputs": ["df2"],
                    "depends_on": ["transform"],
                },
            ],
        }

        run_data = {"session_id": "run_123", "status": "success"}

        result = generate_graph_hints(manifest, run_data)

        # Should have triples
        assert len(result["triples"]) > 0
        assert result["counts"]["triple_count"] > 0

        # Check for specific relationships
        triples_str = json.dumps(result["triples"])

        # Should have produces relationships from outputs
        assert "osiris:produces" in triples_str

        # Should have depends_on relationships
        assert "osiris:depends_on" in triples_str

        # Verify specific triple exists
        # pragma: allowlist secret
        extract_transform_dep = any(
            t["s"] == "osiris://pipeline/@abc123def/step/extract"
            and t["p"] == "osiris:depends_on"
            and t["o"] == "osiris://pipeline/@abc123def/step/transform"
            for t in result["triples"]
        ) or any(
            t["s"] == "osiris://pipeline/@abc123def/step/transform"
            and t["p"] == "osiris:depends_on"
            and t["o"] == "osiris://pipeline/@abc123def/step/extract"
            for t in result["triples"]
        )
        assert extract_transform_dep
