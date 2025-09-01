


# 0009 Secrets Handling Strategy

## Status  
Accepted

## Context  
Secrets management in Osiris is critical for both security and usability.  
So far, secrets masking relied on static regex patterns and environment variables, but this approach is incomplete:  
- Not all environment variables are masked (e.g., custom keys like `padak_pw`).  
- Generated YAML or logs might inadvertently expose credentials.  
- New components may introduce credentials with different naming conventions.  

At the same time, we don’t want to over-engineer secrets detection or create brittle heuristics that mask non-sensitive values.

## Decision  
- Secrets handling will be **component-spec driven**. Each component’s specification (JSON Schema) will explicitly identify which fields are secrets.  
- Credentials will be stored separately under identifiers (e.g., `obchodni_databaze`, `zakaznicka_databaze`), rather than directly in pipeline YAML.  
- The masking layer will:  
  - Automatically detect and replace secret values with `***` in logs, YAML, and artifacts.  
  - Remain backward-compatible with static regex fallbacks until all components declare specs.  
- Future-proofing: When a new component is added (e.g., Shopify extractor), its schema defines which keys are sensitive (e.g., `shpfpw`), so the masking system knows exactly what to protect.  

## Consequences  
- **Security**: No secrets are ever persisted in plaintext logs or pipeline YAML.  
- **Clarity**: Secrets are explicitly defined in component specs, reducing guesswork.  
- **Maintainability**: Adding new components automatically extends the masking system without central code changes.  
- **Interoperability**: Pipelines reference secret identifiers, which can be swapped depending on environment (dev, staging, prod).  
- **Transition cost**: Until all components migrate to schema-driven specs, static regexes will still be needed as a fallback.  
