# ADR-0030: Agentic OML Generation

## Status
Proposed

## Context

Current chat-based OML generation produces inconsistent quality compared to advanced LLM interfaces like ChatGPT. The issues include:
- Insufficient context provided to the LLM
- No iterative refinement of generated OML
- Limited ability to explore alternative solutions
- Weak validation and error recovery
- Hallucinations in component configurations

The root causes:
- **Context Limitation**: Current prompt only includes basic component info
- **Single-Shot Generation**: No retry or refinement loop
- **No Exploration**: Cannot try multiple approaches
- **Static Prompting**: Same prompt regardless of complexity
- **No Learning**: Doesn't use successful patterns from memory

Organizations report:
- ChatGPT produces better OML when given full context
- Claude with proper agents generates more robust pipelines
- Current Osiris chat requires manual OML fixes
- Complex pipelines often fail on first generation

## Decision

Adopt a minimal agent loop architecture inspired by successful agent patterns (e.g., Claude master agent loop from PromptLayer) to improve OML generation quality. The approach focuses on context management, iterative refinement, and validation loops while avoiding over-engineering.

### Agent Architecture

```python
# Minimal agent loop for OML generation
class OMLGenerationAgent:
    """Agent for robust OML generation with context expansion"""

    def __init__(self, llm, memory_store, discovery_engine):
        self.llm = llm
        self.memory = memory_store
        self.discovery = discovery_engine
        self.max_iterations = 3
        self.context_budget = 8000  # tokens

    async def generate(self, user_intent: str) -> OML:
        """
        Generate OML using agent loop

        Steps:
        1. Understand intent
        2. Gather context
        3. Generate OML
        4. Validate and refine
        5. Return final OML
        """

        # Phase 1: Intent Understanding
        intent = await self.understand_intent(user_intent)

        # Phase 2: Context Gathering
        context = await self.gather_context(intent)

        # Phase 3: Generation Loop
        for iteration in range(self.max_iterations):
            # Generate OML
            oml = await self.generate_oml(intent, context)

            # Validate
            validation = self.validate_oml(oml, context)

            if validation.is_valid:
                return oml

            # Refine context based on errors
            context = self.refine_context(context, validation.errors)

        # Fallback to best effort
        return self.best_effort_oml(intent, context)
```

### Agent Phases

TODO: Detail each phase of the agent loop:

#### Phase 1: Intent Understanding
```python
async def understand_intent(self, user_input: str) -> Intent:
    """Parse and understand user intent"""

    # Check memory for similar intents
    similar = self.memory.query(
        pattern=user_input,
        tags=["intent", "successful"],
        limit=5
    )

    prompt = f"""
    Analyze this data pipeline request:
    "{user_input}"

    Similar successful requests:
    {format_similar(similar)}

    Extract:
    1. Data sources needed
    2. Transformations required
    3. Destination format
    4. Performance requirements
    5. Business context

    Return structured intent.
    """

    response = await self.llm.complete(prompt)
    return parse_intent(response)
```

#### Phase 2: Context Gathering
```python
async def gather_context(self, intent: Intent) -> Context:
    """Gather all relevant context for OML generation"""

    context = Context()

    # 1. Discovery snapshots
    for source in intent.data_sources:
        schema = await self.discovery.get_schema(source)
        context.add_schema(source, schema)

    # 2. Memory retrieval
    patterns = self.memory.query(
        tags=["pattern"] + intent.tags,
        limit=3
    )
    context.add_patterns(patterns)

    # 3. Business context
    business = self.memory.query(
        tags=["business", "context"],
        pattern=intent.business_terms,
        limit=5
    )
    context.add_business(business)

    # 4. Component capabilities
    components = self.get_relevant_components(intent)
    context.add_components(components)

    # 5. Connection information
    connections = self.get_available_connections(intent)
    context.add_connections(connections)

    # Optimize context to fit budget
    context.optimize(self.context_budget)

    return context
```

#### Phase 3: OML Generation
```python
async def generate_oml(self, intent: Intent, context: Context) -> str:
    """Generate OML with full context"""

    prompt = f"""
    Generate an OML v0.1.0 pipeline for this intent:
    {intent.summary}

    Available context:

    SCHEMAS:
    {context.schemas}

    SUCCESSFUL PATTERNS:
    {context.patterns}

    BUSINESS RULES:
    {context.business}

    COMPONENTS:
    {context.components}

    CONNECTIONS:
    {context.connections}

    Requirements:
    - Use OML v0.1.0 format exactly
    - Include only required fields: oml_version, name, steps
    - Reference connections with @family.alias syntax
    - Ensure data flow between steps is correct
    - Optimize for performance and reliability

    Generate complete OML:
    """

    response = await self.llm.complete(prompt, temperature=0.3)
    return response
```

#### Phase 4: Validation and Refinement
```python
def validate_oml(self, oml: str, context: Context) -> ValidationResult:
    """Validate generated OML"""

    result = ValidationResult()

    # 1. Schema validation
    try:
        parsed = yaml.safe_load(oml)
        validate_against_schema(parsed)
    except Exception as e:
        result.add_error("schema", str(e))

    # 2. Component validation
    for step in parsed.get("steps", []):
        component = step.get("component")
        if not self.registry.has(component):
            result.add_error("component", f"Unknown: {component}")

    # 3. Connection validation
    for step in parsed.get("steps", []):
        connection = step.get("config", {}).get("connection")
        if connection and not self.validate_connection(connection):
            result.add_error("connection", f"Invalid: {connection}")

    # 4. Data flow validation
    if not self.validate_data_flow(parsed):
        result.add_error("flow", "Incompatible data flow")

    # 5. Business rule validation
    if not self.validate_business_rules(parsed, context.business):
        result.add_error("business", "Violates business rules")

    return result

async def refine_context(self, context: Context, errors: List[Error]) -> Context:
    """Refine context based on validation errors"""

    for error in errors:
        if error.type == "schema":
            # Get more detailed schema information
            context.add_detail("schema", await self.get_schema_detail(error))

        elif error.type == "component":
            # Find alternative components
            context.add_alternatives(await self.find_alternatives(error))

        elif error.type == "connection":
            # Clarify connection requirements
            context.add_clarification(await self.clarify_connection(error))

    return context
```

### Agent Strategies

TODO: Define strategies to avoid over-agentization:

1. **Bounded Iterations**: Maximum 3 attempts to prevent infinite loops
2. **Context Budget**: Stay within token limits (8000 default)
3. **Fast Fail**: Return best effort if critical components missing
4. **Caching**: Reuse discovery and memory queries
5. **Fallback**: Always return something actionable

### Memory Integration

TODO: How agents use memory:

```python
class AgentMemory:
    """Memory specifically for agent context"""

    def remember_success(self, intent: Intent, oml: str, context: Context):
        """Store successful generation for future use"""
        self.memory.put(
            key=f"agent.success.{hash(intent)}",
            value={
                "intent": intent.to_dict(),
                "oml": oml,
                "context_summary": context.summarize(),
                "timestamp": datetime.now()
            },
            tags=["agent", "success", "pattern"] + intent.tags,
            ttl=30 * 86400  # 30 days
        )

    def learn_from_failure(self, intent: Intent, errors: List[Error]):
        """Learn from generation failures"""
        self.memory.put(
            key=f"agent.failure.{hash(intent)}",
            value={
                "intent": intent.to_dict(),
                "errors": [e.to_dict() for e in errors],
                "timestamp": datetime.now()
            },
            tags=["agent", "failure", "learning"],
            ttl=7 * 86400  # 7 days
        )
```

### Simple Agent Loop Example

TODO: Minimal implementation example:

```python
# Simple agent loop without over-engineering
async def agent_loop(user_input: str) -> str:
    """Minimal agent loop for OML generation"""

    # Step 1: Get context
    tables = discover_mentioned_tables(user_input)
    schemas = [get_schema(t) for t in tables]
    patterns = find_similar_patterns(user_input)

    # Step 2: Generate with context
    context = format_context(schemas, patterns)
    oml = await generate_with_context(user_input, context)

    # Step 3: Validate
    errors = validate_oml(oml)

    # Step 4: One retry if needed
    if errors and len(errors) < 3:  # Only retry for minor issues
        enhanced_context = add_error_context(context, errors)
        oml = await generate_with_context(user_input, enhanced_context)

    return oml
```

## Consequences

### Positive
- **Better Quality**: More accurate and complete OML generation
- **Fewer Hallucinations**: Validation catches impossible configurations
- **Learning System**: Improves over time with memory
- **Robust Recovery**: Can handle and recover from errors
- **Context-Aware**: Uses all available information

### Negative
- **Latency**: Multiple LLM calls increase generation time
- **Complexity**: More complex than single-shot generation
- **Token Cost**: More context means higher API costs
- **Debugging**: Harder to debug agent decisions

### Neutral
- **LLM Dependency**: Quality depends on underlying LLM
- **Memory Requirement**: Needs memory store (ADR-0029)
- **Tuning Needed**: Requires prompt engineering

## Implementation Plan

TODO: Phased implementation:

### Phase 1: Basic Agent Loop (Week 1)
- Intent understanding
- Simple context gathering
- Single retry on failure
- Basic validation

### Phase 2: Memory Integration (Week 2)
- Pattern retrieval
- Success/failure learning
- Context optimization
- Business rule integration

### Phase 3: Advanced Features (Week 3)
- Multiple generation strategies
- Parallel exploration
- Confidence scoring
- Explanation generation

### Phase 4: Optimization (Week 4)
- Response caching
- Context compression
- Latency optimization
- Cost management

## Evaluation Metrics

TODO: How to measure agent effectiveness:

```python
class AgentMetrics:
    """Metrics for agent performance"""

    def measure_quality(self, oml: str) -> float:
        """Measure OML quality (0-1)"""
        # Schema compliance
        # Component validity
        # Connection correctness
        # Business rule adherence

    def measure_efficiency(self, generation: Generation) -> dict:
        """Measure generation efficiency"""
        return {
            "iterations": generation.iteration_count,
            "latency_ms": generation.total_time,
            "tokens_used": generation.token_count,
            "cache_hits": generation.cache_hits
        }

    def measure_learning(self, before: List[OML], after: List[OML]) -> float:
        """Measure improvement over time"""
        # Success rate improvement
        # Quality score improvement
        # Iteration reduction
```

## References
- PromptLayer Claude master agent blog post
- LangChain agent architectures
- ADR-0029: Memory store (required dependency)
- ADR-0019: Chat state machine (to be enhanced)
- OpenAI agent best practices
