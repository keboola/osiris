"""Minimal deterministic compiler for OML to manifest."""

from datetime import datetime
from typing import Any

from ..components.registry import ComponentRegistry
from .canonical import canonical_json, canonical_yaml
from .config import ConfigError
from .fingerprint import combine_fingerprints, compute_fingerprint
from .mode_mapper import ModeMapper
from .params_resolver import ParamsResolver
from .session_logging import log_event

COMMON_SECRET_NAMES = {
    "password",
    "passwd",
    "pwd",
    "token",
    "secret",
    "secret_key",
    "service_key",
    "service_role_key",
    "api_key",
    "access_token",
    "refresh_token",
    "auth_token",
    "bearer_token",
    "client_secret",
    "client_key",
    "key",
    "dsn",
    "connection_string",
    "anon_key",
}


class CompilerV0:
    """Minimal compiler for linear pipelines only."""

    def __init__(self, fs_contract, pipeline_slug: str):
        """Initialize compiler.

        Args:
            fs_contract: FilesystemContract instance for path resolution (required)
            pipeline_slug: Pipeline slug for building paths (required)
        """
        self.fs_contract = fs_contract
        self.pipeline_slug = pipeline_slug
        self.manifest_hash = None
        self.manifest_short = None
        self.resolver = ParamsResolver()
        self.fingerprints = {}
        self.errors = []
        self.registry = ComponentRegistry()
        self.secret_field_names = self._collect_all_secret_keys()

    def compile(
        self,
        oml_path: str,
        profile: str | None = None,
        cli_params: dict[str, Any] = None,
        compile_mode: str = "auto",
    ) -> tuple[bool, str]:
        """
        Compile OML to manifest.

        Args:
            oml_path: Path to OML YAML file
            profile: Active profile name
            cli_params: CLI parameters
            compile_mode: auto|force|never

        Returns:
            (success, message)
        """
        try:
            # Load OML
            with open(oml_path) as f:
                import yaml

                oml = yaml.safe_load(f)

            # Validate OML version
            if "oml_version" not in oml:
                return False, "Missing oml_version in OML"

            version = oml["oml_version"]
            if not version.startswith("0."):
                return False, f"Unsupported OML version: {version}"

            # Check for inline secrets BEFORE resolution
            if not self._validate_no_secrets(oml):
                return False, f"Inline secrets detected: {', '.join(self.errors)}"

            # Load parameters with precedence
            profiles_dict = oml.get("profiles", {})
            self.resolver.load_params(
                defaults=self._extract_defaults(oml),
                cli_params=cli_params,
                profile=profile,
                profiles=profiles_dict,
            )

            # Resolve parameters in OML
            resolved_oml = self.resolver.resolve_oml(oml)

            # Compute fingerprints
            self._compute_fingerprints(resolved_oml, profile)

            # Check cache if mode is auto/never
            if compile_mode in ("auto", "never"):
                cache_key = self._get_cache_key()
                if self._check_cache(cache_key):
                    if compile_mode == "auto":
                        log_event("cache_hit", cache_key=cache_key[:16])
                        return True, f"Cache hit: {cache_key}"
                else:
                    log_event("cache_miss", cache_key=cache_key[:16])
                    if compile_mode == "never":
                        return False, "No cache entry found (--compile=never)"

            # Generate manifest
            manifest = self._generate_manifest(resolved_oml)

            # Validate all components have drivers
            if not self._validate_drivers(manifest):
                missing_drivers = [
                    f"{step['id']} (component: {step['driver']})"
                    for step in manifest["steps"]
                    if not self._has_driver(step["driver"])
                ]
                return False, f"Components missing runtime drivers: {', '.join(missing_drivers)}"

            # Generate per-step configs
            configs = self._generate_configs(resolved_oml)

            # Write outputs
            self._write_outputs(manifest, configs, resolved_oml, profile)

            return True, f"Compilation successful: {manifest['meta'].get('manifest_hash', 'unknown')[:7]}"

        except Exception as e:
            return False, f"Compilation failed: {str(e)}"

    def _extract_defaults(self, oml: dict) -> dict[str, Any]:
        """Extract default values from OML params."""
        defaults = {}
        if "params" in oml:
            for name, spec in oml["params"].items():
                if isinstance(spec, dict) and "default" in spec:
                    defaults[name] = spec["default"]
                elif not isinstance(spec, dict):
                    defaults[name] = spec
        return defaults

    def _validate_no_secrets(self, data: Any, path: str = "") -> bool:
        """Validate no inline secrets in OML."""
        if isinstance(data, dict):
            for key, value in data.items():
                current_path = f"{path}.{key}" if path else key

                key_lower = key.lower()
                if (
                    key_lower in self.secret_field_names
                    and key_lower not in {"primary_key", "url"}
                    and isinstance(value, str)
                    and value
                    and not value.startswith("${")
                    and len(value) > 4
                ):
                    self.errors.append(f"Inline secret at {current_path}")
                    return False

                if not self._validate_no_secrets(value, current_path):
                    return False

        elif isinstance(data, list):
            for i, item in enumerate(data):
                if not self._validate_no_secrets(item, f"{path}[{i}]"):
                    return False

        return True

    def _compute_fingerprints(self, oml: dict, profile: str | None):
        """Compute all fingerprints."""
        # OML fingerprint (canonical JSON)
        oml_bytes = canonical_json(oml).encode("utf-8")
        self.fingerprints["oml_fp"] = compute_fingerprint(oml_bytes)

        # Registry fingerprint (static for MVP)
        self.fingerprints["registry_fp"] = compute_fingerprint("registry-v0.1")

        # Compiler fingerprint
        self.fingerprints["compiler_fp"] = compute_fingerprint("osiris-compiler/0.1")

        # Params fingerprint
        params_bytes = canonical_json(self.resolver.get_effective_params()).encode("utf-8")
        self.fingerprints["params_fp"] = compute_fingerprint(params_bytes)

        # Profile - use fs_config default if not provided
        default_profile = (
            self.fs_contract.fs_config.profiles.default if self.fs_contract.fs_config.profiles.enabled else None
        )
        self.fingerprints["profile"] = profile or default_profile

    def _get_cache_key(self) -> str:
        """Generate cache key from fingerprints."""
        return combine_fingerprints(
            [
                self.fingerprints["oml_fp"],
                self.fingerprints["registry_fp"],
                self.fingerprints["compiler_fp"],
                self.fingerprints["params_fp"],
                self.fingerprints["profile"],
            ]
        )

    def _check_cache(self, cache_key: str) -> bool:  # noqa: ARG002
        """Check if cache entry exists (stub for MVP)."""
        # TODO: Implement actual cache lookup
        return False

    def _generate_manifest(self, oml: dict) -> dict:
        """Generate manifest from resolved OML."""
        steps = []

        # Process steps (support both linear and DAG)
        for i, step in enumerate(oml.get("steps", [])):
            step_id = step.get("id", f"step_{i}")
            # Support both OML v0.1.0 'component' and legacy 'uses' field
            component = step.get("component") or step.get("uses", "")

            # Validate component exists in registry
            component_spec = self.registry.get_component(component)
            if not component_spec:
                self.errors.append(
                    f"Unknown component '{component}' in step '{step_id}'. "
                    f"Check 'osiris components list' to see available components."
                )
                driver = "unknown"
            else:
                # Use component name as driver (registry is source of truth)
                driver = component

                # Validate and map mode if specified
                if "mode" in step:
                    oml_mode = step["mode"]
                    component_modes = component_spec.get("modes", [])

                    # Check if mode is compatible
                    if not ModeMapper.is_mode_compatible(oml_mode, component_modes):
                        allowed_canonical = [
                            m
                            for m in ModeMapper.get_canonical_modes()
                            if ModeMapper.is_mode_compatible(m, component_modes)
                        ]
                        self.errors.append(
                            f"Step '{step_id}': mode '{oml_mode}' not supported by component '{component}'. "
                            f"Allowed: {', '.join(allowed_canonical)}"
                        )

            # Determine needs - respect explicit dependencies or infer linear chain
            if "needs" in step:
                # Explicit dependencies specified
                needs = step["needs"]
            elif i > 0:
                # No explicit needs and not the first step - infer linear chain
                # This maintains backward compatibility with linear pipelines
                needs = [oml["steps"][i - 1].get("id", f"step_{i-1}")]
            else:
                # First step has no dependencies
                needs = []

            steps.append(
                {
                    "id": step_id,
                    "driver": driver,
                    "cfg_path": f"cfg/{step_id}.json",  # Relative to manifest location
                    "needs": needs,
                }
            )

        # Build manifest
        manifest = {
            "pipeline": {
                "id": oml.get("name", "pipeline").lower().replace(" ", "_"),
                "version": "0.1.0",
                "fingerprints": self.fingerprints.copy(),
            },
            "steps": steps,
            "meta": {
                "oml_version": oml.get("oml_version", "0.1.0"),
                "profile": self.fingerprints["profile"],
                "run_id": "${run_id}",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "toolchain": {"compiler": "osiris-compiler/0.1", "registry": "osiris-registry/0.1"},
            },
        }

        # Preserve OML name at top level for AIOP
        if "name" in oml:
            manifest["name"] = oml["name"]

        # Preserve OML metadata for AIOP (especially intent)
        if "metadata" in oml:
            manifest["metadata"] = oml["metadata"]

        # Compute manifest fingerprint (exclude ephemeral fields for determinism)
        import copy

        manifest_for_fp = copy.deepcopy(manifest)
        if "meta" in manifest_for_fp:
            # Remove timestamp to ensure deterministic fingerprints
            manifest_for_fp["meta"].pop("generated_at", None)

        manifest_bytes = canonical_json(manifest_for_fp).encode("utf-8")
        manifest["pipeline"]["fingerprints"]["manifest_fp"] = compute_fingerprint(manifest_bytes)
        self.fingerprints["manifest_fp"] = manifest["pipeline"]["fingerprints"]["manifest_fp"]

        return manifest

    def _generate_configs(self, oml: dict) -> dict[str, dict]:
        """Generate per-step configurations."""
        configs = {}

        for step in oml.get("steps", []):
            step_id = step.get("id", "step")
            # Support both OML v0.1.0 'config' and legacy 'with' field
            config = step.get("config") or step.get("with", {})

            # Also include component and mode in the config for the runner
            # Apply mode aliasing for components
            oml_mode = step.get("mode", "")
            component_mode = ModeMapper.to_component_mode(oml_mode) if oml_mode else ""

            step_config = {
                "component": step.get("component", ""),
                "mode": component_mode,  # Use mapped mode for runtime
            }

            component_name = step.get("component", "")
            component_spec = self.registry.get_component(component_name) if component_name else None
            allowed_fields = set()
            if component_spec:
                schema = component_spec.get("configSchema", {}) or {}
                allowed_fields = set((schema.get("properties", {}) or {}).keys())

            secret_keys = {key.lower() for key in self._secret_keys_for_component(component_spec)}
            reserved_keys = {"connection"}

            # Filter out secrets (they'll be resolved at runtime)
            for key, value in config.items():
                if allowed_fields and key not in allowed_fields and key not in reserved_keys:
                    raise ConfigError(f"Unknown configuration key '{key}' for component '{component_name}'")

                key_lower = key.lower()
                if key_lower in secret_keys or (
                    key_lower in self.secret_field_names and key_lower not in {"primary_key", "url"}
                ):
                    continue

                step_config[key] = value

            # Apply component spec defaults for missing keys
            # This ensures component spec defaults are used when config values aren't provided
            if component_spec:
                schema = component_spec.get("configSchema", {}) or {}
                properties = schema.get("properties", {}) or {}
                for field_name, field_schema in properties.items():
                    if isinstance(field_schema, dict) and "default" in field_schema:
                        # Skip reserved/derived fields (mode is computed, not stored)
                        if field_name not in step_config and field_name != "mode":
                            step_config[field_name] = field_schema["default"]

            write_mode_value = config.get("write_mode", config.get("mode"))
            if write_mode_value in {"replace", "upsert"}:
                if "primary_key" not in config:
                    raise ConfigError(
                        f"Step '{step_id}' requires 'primary_key' when write_mode is '{write_mode_value}'"
                    )

            configs[step_id] = step_config

        return configs

    def _collect_all_secret_keys(self) -> set[str]:
        keys: set[str] = set()
        specs = self.registry.load_specs()
        for spec in specs.values():
            for key in self._secret_keys_for_component(spec):
                keys.add(key.lower())
        keys.update(name.lower() for name in COMMON_SECRET_NAMES)
        keys.discard("primary_key")
        return keys

    def _secret_keys_for_component(self, spec: dict[str, Any] | None) -> set[str]:
        base_keys = {name.lower() for name in COMMON_SECRET_NAMES}
        if not spec:
            return base_keys

        secret_keys: set[str] = set(base_keys)
        for field in ("secrets", "x-secret"):
            for pointer in spec.get(field, []) or []:
                segments = self._pointer_to_segments(pointer)
                if segments:
                    secret_keys.add(segments[0].lower())
        return secret_keys

    @staticmethod
    def _pointer_to_segments(pointer: str) -> list[str]:
        if not pointer:
            return []
        trimmed = pointer[1:] if pointer.startswith("/") else pointer
        if not trimmed:
            return []
        parts: list[str] = []
        for segment in trimmed.split("/"):
            segment = segment.replace("~1", "/").replace("~0", "~")
            if segment:
                parts.append(segment)
        return parts

    def _write_outputs(self, manifest: dict, configs: dict, oml: dict, profile: str | None):
        """Write all compilation outputs."""
        from .fs_paths import compute_manifest_hash

        # Compute manifest hash
        self.manifest_hash = compute_manifest_hash(manifest, self.fs_contract.ids_config.manifest_hash_algo, profile)
        self.manifest_short = self.manifest_hash[: self.fs_contract.fs_config.naming.manifest_short_len]

        # Get paths from filesystem contract
        paths = self.fs_contract.manifest_paths(
            pipeline_slug=self.pipeline_slug,
            manifest_hash=self.manifest_hash,
            manifest_short=self.manifest_short,
            profile=profile,
        )

        # Use contract paths
        output_dir = paths["base"]
        manifest_path = paths["manifest"]
        cfg_dir = paths["cfg_dir"]
        plan_path = paths["plan"]
        fingerprints_path = paths["fingerprints"]
        run_summary_path = paths["run_summary"]

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        cfg_dir.mkdir(exist_ok=True)

        # Add manifest metadata
        manifest["meta"]["manifest_hash"] = self.manifest_hash
        manifest["meta"]["manifest_short"] = self.manifest_short

        # Write manifest.yaml
        with open(manifest_path, "w") as f:
            f.write(canonical_yaml(manifest))

        # Write per-step configs
        for step_id, config in configs.items():
            config_path = cfg_dir / f"{step_id}.json"
            with open(config_path, "w") as f:
                f.write(canonical_json(config))

        # Write additional artifacts based on contract configuration
        if self.fs_contract.fs_config.artifacts.plan:
            with open(plan_path, "w") as f:
                # Simple plan: list of steps
                plan = {"steps": [{"id": step["id"], "driver": step["driver"]} for step in manifest["steps"]]}
                f.write(canonical_json(plan))

        if self.fs_contract.fs_config.artifacts.fingerprints:
            with open(fingerprints_path, "w") as f:
                f.write(canonical_json({"fingerprints": self.fingerprints}))

        if self.fs_contract.fs_config.artifacts.run_summary:
            with open(run_summary_path, "w") as f:
                f.write(
                    canonical_json(
                        {
                            "profile": profile,
                            "oml_version": oml.get("oml_version", "0.1.0"),
                            "compiled_at": datetime.utcnow().isoformat() + "Z",
                            "manifest_hash": self.manifest_hash,
                            "manifest_short": self.manifest_short,
                            "pipeline_slug": self.pipeline_slug,
                        }
                    )
                )

        # Write LATEST pointer file (3-line text file per ADR-0028)
        latest_path = output_dir.parent / "LATEST"
        if latest_path.is_symlink() or latest_path.exists():
            latest_path.unlink()
        with open(latest_path, "w") as f:
            f.write(f"{manifest_path}\n")
            f.write(f"{self.manifest_hash}\n")
            f.write(f"{profile or ''}\n")

    def _has_driver(self, component_name: str) -> bool:
        """Check if a component has a runtime driver.

        Args:
            component_name: Name of the component

        Returns:
            True if driver exists, False otherwise
        """
        if component_name == "unknown":
            return False

        spec = self.registry.get_component(component_name)
        if not spec:
            return False

        runtime_config = spec.get("x-runtime", {})
        driver_path = runtime_config.get("driver")

        if not driver_path:
            return False

        # Try to import the driver to verify it exists
        try:
            import importlib

            module_path, class_name = driver_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            getattr(module, class_name)
            return True
        except Exception:
            return False

    def _validate_drivers(self, manifest: dict) -> bool:
        """Validate all steps have runtime drivers.

        Args:
            manifest: Compiled manifest

        Returns:
            True if all drivers exist, False otherwise
        """
        return all(self._has_driver(step["driver"]) for step in manifest["steps"])
