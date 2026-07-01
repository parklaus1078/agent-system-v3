# General Coding Principles

> Foundational principles that apply to all project types

---

## 1. Code Quality Principles

### DRY (Don't Repeat Yourself)
- Extract duplicated code into functions/classes
- If the same logic appears 3+ times, refactor it
- Separate configuration values into constants/environment variables

### KISS (Keep It Simple, Stupid)
- Try the simplest solution first
- Avoid unnecessary abstractions
- Use clear variable names (minimize abbreviations)

### YAGNI (You Aren't Gonna Need It)
- Only implement what is currently needed
- Do not write speculative code for hypothetical future requirements
- Add it when it's actually needed

### SOLID Principles

#### S — Single Responsibility Principle
- Each function/class should do one thing
- There should be only one reason for it to change

#### O — Open/Closed Principle
- Open for extension, closed for modification
- Use interfaces/abstract classes

#### L — Liskov Substitution Principle
- Subtypes must be substitutable for their base types

#### I — Interface Segregation Principle
- Do not depend on methods you don't use
- Prefer small, specific interfaces

#### D — Dependency Inversion Principle
- Depend on abstractions, not concretions
- Use Dependency Injection (DI)

---

## 2. Readable & Manageable Code

### Explicit over Implicit (Principle of Least Surprise)
- No hidden side effects — if a function modifies state, its name should make that obvious
- Avoid magic: no auto-coercion tricks, no reliance on import order, no behavior that depends on invisible naming conventions
- Prefer explicit arguments over global/ambient state
- Configuration should be visible, not buried in decorators or metaclasses

### Guard Clauses / Early Returns
- Handle edge cases and invalid states at the top, then proceed with the main logic un-nested
- Reduces indentation depth and makes the "happy path" immediately visible

```python
# Bad — deeply nested
def process(user):
    if user is not None:
        if user.is_active:
            if user.has_permission:
                return do_work(user)
    return None

# Good — guard clauses
def process(user):
    if user is None:
        return None
    if not user.is_active:
        return None
    if not user.has_permission:
        return None
    return do_work(user)
```

### Immutability by Default
- Prefer `const`/`final`/`let` over mutable variables
- Mutate only when there is a clear reason (performance, API contract)
- Immutable data is easier to reason about, test, and debug

```javascript
// Bad
let items = getItems();
items = items.filter(i => i.active);
items = items.map(i => i.name);

// Good
const items = getItems();
const activeNames = items.filter(i => i.active).map(i => i.name);
```

### Pure Functions Where Possible
- Same input → same output, no side effects
- Isolate I/O (network, disk, DB) at the boundaries; keep core logic pure
- Makes unit testing trivial and code easier to follow

```python
# Impure — depends on external state
def get_discount():
    if datetime.now().weekday() == 5:
        return 0.2
    return 0.0

# Pure — caller provides the dependency
def get_discount(current_weekday: int) -> float:
    if current_weekday == 5:
        return 0.2
    return 0.0
```

### Readability over Cleverness
- If a one-liner requires a comment to explain it, expand it
- Optimize for the reader's comprehension speed, not lines-of-code count
- Code is read 10x more than it is written — optimize for the common case

```python
# Clever but opaque
r = [x for x in (lambda f: f(f))(lambda f: lambda n: [n] if n <= 1 else f(f)(n-1) + [n])(10) if x % 2]

# Clear
def range_list(n):
    return list(range(1, n + 1))

odd_numbers = [x for x in range_list(10) if x % 2 != 0]
```

---

## 3. Naming Conventions

### General Rules
- **Meaningful names**: `data` → `userData`
- **Pronounceable names**: `yyyymmdd` → `currentDate`
- **Searchable names**: `7` → `MAX_RETRY_COUNT`
- **Remove unnecessary context**: `UserClass` → `User`

### Language-Specific Conventions

#### Python
- Variables/functions: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

#### JavaScript/TypeScript
- Variables/functions: `camelCase`
- Classes/components: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private (TypeScript): `private` keyword (the `#` prefix is for runtime-enforced private fields in both JS and TS)

#### Go
- Variables/functions: `camelCase` (exported: `PascalCase`)
- Interfaces: `PascalCase`
- Constants: `PascalCase` or `camelCase` (Go convention; not UPPER_SNAKE_CASE)

#### Rust
- Variables/functions: `snake_case`
- Types/traits: `PascalCase`
- Constants/statics: `UPPER_SNAKE_CASE`

#### Java
- Variables/functions: `camelCase`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Packages: `lowercase`

---

## 4. Security Fundamentals

### Input Validation
- **Never trust user input**
- Validate type, length, and allowed characters
- Prefer allowlists over denylists

### Secret Management
- **Never hardcode secrets in source code**
  - API keys, passwords, tokens, etc.
- Use environment variables (`.env` files — never commit to Git)
- Provide a `.env.example` template
- In production: use a secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)

### SQL Injection Prevention
- Use an ORM or parameterized/prepared queries
- Never build SQL by concatenating strings

### XSS (Cross-Site Scripting) Prevention
- Escape user input when inserting into HTML
- Use framework built-in protections (e.g., React's automatic escaping)

### CSRF (Cross-Site Request Forgery) Prevention
- Use CSRF tokens
- Set the `SameSite` cookie attribute

### Authentication/Authorization
- Passwords: use strong hashing algorithms (bcrypt, argon2, etc.)
- JWT: do not include sensitive data in payloads; set short expiry times
- Use HTTPS (mandatory in production)

### Error Messages
- Never expose stack traces in production
- Show generic error messages to users
- Log detailed errors server-side only

---

## 5. Error Handling

### General Rules
- **Never silently ignore errors**
- Handle expected errors explicitly
- Fail fast for unrecoverable errors

### Logging
- Use appropriate log levels:
  - `DEBUG`: Debugging information during development
  - `INFO`: General information (request handling, startup/shutdown)
  - `WARNING`: Potential issues
  - `ERROR`: Recoverable errors
  - `CRITICAL`/`FATAL`: System-breaking errors

- Never log sensitive information (passwords, tokens, etc.)
- Prefer structured logging (JSON format)

### Language-Specific Patterns

#### Python
```python
# Good
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise
```

#### JavaScript/TypeScript
```typescript
// Good
try {
  const result = await riskyOperation();
} catch (error) {
  logger.error('Operation failed', { error });
  throw error;
}
```

#### Go
```go
// Good
result, err := riskyOperation()
if err != nil {
    log.Printf("operation failed: %v", err)
    return err
}
```

---

## 6. Testing

### Test Pyramid
1. **Unit tests (70%)**: Individual functions/methods
2. **Integration tests (20%)**: Multiple modules working together
3. **E2E tests (10%)**: Full system flow

### Test Writing Principles
- **F.I.R.S.T**:
  - **Fast**: Execute quickly
  - **Independent**: Can run in isolation
  - **Repeatable**: Deterministic results
  - **Self-Validating**: Automatic pass/fail
  - **Timely**: Written alongside implementation

### AAA Pattern
```python
def test_user_creation():
    # Arrange
    user_data = {"email": "test@example.com", "password": "secret"}

    # Act
    user = create_user(user_data)

    # Assert
    assert user.email == "test@example.com"
    assert user.id is not None
```

### Coverage Targets
- Unit tests: 80%+
- Integration tests: cover all major flows
- E2E tests: cover all critical user flows

---

## 7. Git Commit Messages

### Conventional Commits

```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code formatting (no behavior change)
- `refactor`: Refactoring
- `test`: Adding/updating tests
- `chore`: Build, packages, tooling, etc.

### Example
```
feat(auth): implement JWT-based authentication

- Issue JWT token on login
- Add token validation middleware
- Set expiry time to 1 hour

Closes #123
```

---

## 8. Code Review

### Reviewer Checklist
- [ ] Does the code meet the requirements?
- [ ] Are tests included?
- [ ] Are there security vulnerabilities?
- [ ] Are there performance issues?
- [ ] Are names clear and descriptive?
- [ ] Is there unnecessary duplication?
- [ ] Is error handling appropriate?

### Author Checklist
- [ ] Self-review completed
- [ ] Tests pass
- [ ] Linter/formatter run
- [ ] Commit message conventions followed
- [ ] Changes documented

---

## 9. Documentation

### Code Comments
- **Explain why, not what** — let the code speak for itself
- Complex algorithms warrant comments
- Use `TODO`, `FIXME`, `HACK` tags

### README.md Required Sections
1. **Project description**
2. **Installation instructions**
3. **Usage**
4. **Environment variable configuration**
5. **Running tests**
6. **License**

### API Documentation (Backend)
- Use auto-generated docs via OpenAPI/Swagger
- Add descriptions to all endpoints
- Include request/response examples

---

## 10. Dependency Management

### Version Pinning
- Production dependencies: pin exact versions
- Development dependencies: ranges are acceptable.
- Use dependencies with the latest stable version, and always check the compatibility between each other.

### Security Updates
- Regularly scan dependencies for vulnerabilities
- Use automated tools (Dependabot, Snyk, etc.)

### Minimal Dependencies
- Only add libraries you actually need
- Prefer small, focused utilities over large monolithic libraries

---

## 11. Performance

### General Rules
- **Measure before optimizing** (no guessing)
- Profile to find bottlenecks
- Avoid premature optimization

### Database
- Prevent N+1 query problems
- Use appropriate indexes
- Implement pagination for large datasets

### Caching
- Cache data that changes infrequently
- Set cache expiration strategies
- Follow cache key naming conventions

---

## 12. Prohibited Practices

### Strictly Prohibited
- Hardcoded secrets
- SQL-injectable queries
- Direct execution of user input (`eval`, etc.)
- Committing `.env` files to Git
- Debug mode enabled in production
- Logging sensitive information

### Discouraged
- Excessive use of global variables
- Deep nesting (3+ levels)
- Long functions (50+ lines)
- Magic numbers (unexplained constants)
- Commented-out code (use Git history instead)

---

## 13. References

### Books
- Clean Code (Robert C. Martin)
- The Pragmatic Programmer (David Thomas, Andrew Hunt)
- Refactoring (Martin Fowler)

### Web Resources
- OWASP Top 10: https://owasp.org/www-project-top-ten/
- 12 Factor App: https://12factor.net/
- Semantic Versioning: https://semver.org/

---

**Version**: v1.0.0
**Last updated**: 2026-03-30