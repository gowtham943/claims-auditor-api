# FastAPI Feature Implementation Rules

You are an expert FastAPI developer. You must strictly follow this step-by-step layer architecture workflow when implementing any new feature. Do not skip steps, do not combine steps, and do not proceed to the next layer without user confirmation.

## Global Security Enforcer
* EVERY single API router endpoint must be authenticated.
* You must inject the user session dependency (e.g., `current_user: User = Depends(get_current_user)`) into every router function signature.

---

## Step-by-Step Workflow

### Step 1: Data Model Design & Approval
1. Propose the SQLAlchemy model definition inside a code block.
2. Outline all fields, types, relationships, foreign keys, and indexes.
3. **STOP:** Ask the user for explicit approval of the database schema layout before moving forward.

### Step 2: Create the Model
1. Once approved, write the code inside the appropriate `models/` directory file.
2. Ensure correct imports from the base database config and metadata layer.

### Step 3: Create Pydantic Schemas / DTOs
1. Create data transfer objects inside the `schemas/` directory.
2. Provide explicit schemas for:
   * `FeatureCreate` (Input validation)
   * `FeatureUpdate` (Optional input validation)
   * `FeatureResponse` (Output serialization, must include `model_config = ConfigDict(from_attributes=True)`)

### Step 4: Generate Alembic Migration
1. Generate the Alembic migration script block.
2. Verify that both the `upgrade()` and `downgrade()` methods are fully populated and handle foreign keys safely.
3. Present the CLI command to run the migration (`alembic upgrade head`).

### Step 5: Implement Repository Layer
1. Build the data access layer inside the `repositories/` directory.
2. Inherit from the project's base repository pattern if available.
3. Write clean, optimized SQLAlchemy queries utilizing the model.

### Step 6: Implement Service Layer
1. Build the core business logic inside the `services/` directory.
2. Inject the repository layer into the service class/functions.
3. Handle custom domain validation, exceptions, and business rules here.

### Step 7: Create Router / API Endpoints
1. Implement the API endpoints inside the `routers/` directory.
2. Inject the service layer using FastAPI's dependency injection (`Depends`).
3. Ensure every route includes proper status codes, tags, response models, and user authentication constraints.
