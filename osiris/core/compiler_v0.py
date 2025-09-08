"""Minimal deterministic compiler for OML to manifest."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..components.registry import ComponentRegistry
from .canonical import canonical_json, canonical_yaml
from .fingerprint import combine_fingerprints, compute_fingerprint
from .mode_mapper import ModeMapper
from .params_resolver import ParamsResolver
from .session_logging import log_event


class CompilerV0:
    """Minimal compiler for linear pipelines only."""

    # Hardcoded secret fields for MVP (normally from Registry)
    SECRET_FIELDS = {
        "key",
        "password",
        "secret",
        "token",
        "api_key",
        "anon_key",
        "service_key",
        "dsn",
        "connection_string",
    }

    # No longer using COMPONENT_MAP - use Component Registry as single source of truth

    def __init__(self, output_dir: str = "compiled"):
        self.output_dir = Path(output_dir)
        self.resolver = ParamsResolver()
        self.fingerprints = {}
        self.errors = []
        self.registry = ComponentRegistry()

    def compile(
        self,
        oml_path: str,
        profile: Optional[str] = None,
        cli_params: Dict[str, Any] = None,
        compile_mode: str = "auto",
    ) -> Tuple[bool, str]:
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

            # Generate per-step configs
            configs = self._generate_configs(resolved_oml)

            # Write outputs
            self._write_outputs(manifest, configs, resolved_oml, profile)

            return True, f"Compilation successful: {self.output_dir}"

        except Exception as e:
            return False, f"Compilation failed: {str(e)}"

    def _extract_defaults(self, oml: Dict) -> Dict[str, Any]:
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

                # Check if this is a secret field by exact match or contains
                is_secret_field = False
                key_lower = key.lower()
                for secret_term in self.SECRET_FIELDS:
                    # Exact match or ends with the secret term
                    if key_lower == secret_term or key_lower.endswith("_" + secret_term):
                        is_secret_field = True
                        break

                if (
                    is_secret_field
                    and isinstance(value, str)
                    and value
                    and not value.startswith("${")
                    and not value.startswith("http")
                    and len(value) > 8
                ):
                    # Inline secret detected
                    self.errors.append(f"Inline secret at {current_path}")
                    return False

                # Recurse
                if not self._validate_no_secrets(value, current_path):
                    return False

        elif isinstance(data, list):
            for i, item in enumerate(data):
                if not self._validate_no_secrets(item, f"{path}[{i}]"):
                    return False

        return True

    def _compute_fingerprints(self, oml: Dict, profile: Optional[str]):
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

        # Profile
        self.fingerprints["profile"] = profile or "default"

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

    def _generate_manifest(self, oml: Dict) -> Dict:
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

            # Determine needs - respect explicit dependencies
            # If no explicit needs, leave empty (parallel execution possible)
            needs = step.get("needs", [])

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

        # Compute manifest fingerprint
        manifest_bytes = canonical_json(manifest).encode("utf-8")
        manifest["pipeline"]["fingerprints"]["manifest_fp"] = compute_fingerprint(manifest_bytes)
        self.fingerprints["manifest_fp"] = manifest["pipeline"]["fingerprints"]["manifest_fp"]

        return manifest

    def _generate_configs(self, oml: Dict) -> Dict[str, Dict]:
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

            # Filter out secrets (they'll be resolved at runtime)
            for key, value in config.items():
                if not any(secret in key.lower() for secret in self.SECRET_FIELDS):
                    step_config[key] = value
                else:
                    # Keep placeholder for secrets
                    if isinstance(value, str) and value.startswith("${"):
                        step_config[key] = value

            configs[step_id] = step_config

        return configs

    def _write_outputs(self, manifest: Dict, configs: Dict, oml: Dict, profile: Optional[str]):
        """Write all compilation outputs."""
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cfg_dir = self.output_dir / "cfg"
        cfg_dir.mkdir(exist_ok=True)

        # Write manifest.yaml
        manifest_path = self.output_dir / "manifest.yaml"
        with open(manifest_path, "w") as f:
            f.write(canonical_yaml(manifest))

        # Write per-step configs
        for step_id, config in configs.items():
            config_path = cfg_dir / f"{step_id}.json"
            with open(config_path, "w") as f:
                f.write(canonical_json(config))

        # Write meta.json
        meta_path = self.output_dir / "meta.json"
        with open(meta_path, "w") as f:
            f.write(
                canonical_json(
                    {
                        "fingerprints": self.fingerprints,
                        "profile": profile,
                        "oml_version": oml.get("oml_version", "0.1.0"),
                        "compiled_at": datetime.utcnow().isoformat() + "Z",
                    }
                )
            )

        # Write effective_config.json
        config_path = self.output_dir / "effective_config.json"
        with open(config_path, "w") as f:
            f.write(
                canonical_json({"params": self.resolver.get_effective_params(), "profile": profile})
            )
