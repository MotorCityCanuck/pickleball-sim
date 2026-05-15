**Student Guide: AI-Integrated Local Development Environment**

Prepared: 2026-05-06

# 1. Overview

This course uses a modern AI-assisted software development workflow
based on Visual Studio Code, Docker Desktop, Dev Containers, GitHub, and
optional AI coding assistants such as Claude, Codex/OpenAI, Continue,
and GitHub Copilot.

The goal is to teach students how modern industry development
increasingly works: through containerized environments, AI-assisted
coding, Git-based collaboration, and iterative prompt-driven engineering
workflows.

# 2. What You Will Learn

## Containerized software development

Students will learn how modern applications are packaged and executed
inside Docker containers rather than directly on the host operating
system. This approach improves reproducibility, reduces dependency
conflicts, and creates environments that behave consistently across
Windows and macOS systems. Students will also learn how containers
support modern cloud-native development workflows.

## AI-assisted software engineering

Students will learn how AI coding systems such as Claude, Codex/OpenAI,
and GitHub Copilot can accelerate software development workflows. The
course will emphasize practical AI usage patterns including architecture
planning, debugging assistance, implementation support, test generation,
and code review workflows. Students will also learn how to critically
evaluate and validate AI-generated outputs.

## GitHub collaboration workflows

Students will learn professional GitHub workflows including cloning
repositories, branching strategies, commits, pull requests, merges, and
collaborative project management. The course will reinforce
industry-standard source control practices and teach students how
distributed teams coordinate software development. Students will also
learn how GitHub integrates into modern AI-assisted development
ecosystems.

## Prompt-driven development

Students will learn how effective prompting dramatically improves the
quality of AI-generated code and technical guidance. The course will
emphasize iterative prompting strategies, architecture-first prompting,
debugging prompts, and context-rich implementation requests. Students
will practice using prompts as a structured engineering communication
mechanism.

## Modern debugging and testing practices

Students will learn systematic debugging approaches using logs, stack
traces, runtime inspection, and AI-assisted troubleshooting workflows.
The course will reinforce the importance of testing AI-generated code
rather than blindly trusting outputs. Students will also learn how to
generate unit tests, validation checks, and debugging strategies using
AI tools.

## Infrastructure-aware application development

Students will learn that modern software development increasingly
requires awareness of infrastructure, deployment environments,
networking, and service dependencies. By working inside Docker-based
environments, students will understand how applications interact with
databases, APIs, and supporting services. This provides a more realistic
view of enterprise application development.

## Multi-service application development

Students will learn how modern applications are often composed of
multiple interacting services such as web applications, databases, APIs,
and analytics components. Using Docker Compose, students will gain
experience managing these services together inside a unified development
environment. This mirrors modern production and cloud-native
architectures.

## Responsible AI usage and validation

Students will learn that AI-generated code must always be validated,
tested, reviewed, and understood before use. The course will emphasize
responsible AI usage practices including security awareness,
verification, and critical evaluation of generated outputs. Students
will be expected to understand and explain the solutions they submit,
regardless of how the code was produced.

# 3. Required Software

## Git

Git is the industry-standard distributed version control system used for
tracking code changes, managing collaboration, and synchronizing work
with GitHub repositories. Students will use Git for cloning
repositories, committing code, creating branches, and managing project
history throughout the course. Download Git from: https://git-scm.com

## Visual Studio Code

Visual Studio Code is the primary integrated development environment
(IDE) used for the course. VS Code provides support for Python, Docker,
GitHub integration, Jupyter notebooks, debugging tools, extensions, and
AI coding assistants such as Continue and GitHub Copilot. Download VS
Code from: https://code.visualstudio.com

## Docker Desktop

Docker Desktop provides the container runtime used to run the
standardized course development environment. Docker allows all students
to work inside consistent Linux-based environments regardless of whether
they use Windows or macOS systems. Download Docker Desktop from:
https://www.docker.com/products/docker-desktop

## VS Code Dev Containers Extension

The Dev Containers extension allows VS Code to automatically open
projects inside containerized development environments. This extension
enables students to work inside fully configured development
environments with pre-installed dependencies, databases, and tooling.
Install the extension from the VS Code Extensions Marketplace by
searching for \'Dev Containers\'.

# 4. Optional AI Tooling

## Continue Extension

Continue is a VS Code extension that provides unified integration with
multiple AI coding models including Claude and OpenAI/Codex. It enables
inline code generation, AI chat interfaces, repository-aware prompting,
debugging support, and AI-assisted implementation workflows directly
inside VS Code. Continue can be installed from the VS Code Extensions
Marketplace or from: https://continue.dev

## Claude

Claude is an advanced AI reasoning and coding assistant produced by
Anthropic. In this course, Claude is especially useful for architecture
design, debugging workflows, refactoring strategies, reasoning through
implementation problems, and explaining complex concepts. Claude can be
accessed through: https://claude.ai

## Codex/OpenAI

OpenAI coding models such as Codex and GPT-based development assistants
are highly effective for implementation acceleration, test generation,
repetitive coding tasks, and rapid prototyping workflows. Students may
use OpenAI integrations directly through VS Code extensions, Continue,
or browser-based interfaces. OpenAI services can be accessed through:
https://platform.openai.com

## GitHub Copilot

GitHub Copilot provides inline AI code suggestions directly inside
Visual Studio Code. It is particularly effective for boilerplate
generation, repetitive coding tasks, autocompletion, and accelerating
routine development workflows. GitHub Copilot can be installed from the
VS Code Extensions Marketplace or accessed through:
https://github.com/features/copilot

# 5. Installation Steps

## Install Git

Begin by installing Git, which will be used throughout the course for
source control, GitHub synchronization, and collaborative development
workflows. During installation, the default configuration options are
typically appropriate for most students. After installation, verify Git
is available by opening a terminal and running \'git \--version\'.

Download Git from: https://git-scm.com

## Install Visual Studio Code

Install Visual Studio Code as the primary integrated development
environment used for the course. VS Code supports Python development,
Docker integration, GitHub workflows, debugging tools, Jupyter
notebooks, and AI coding assistant integrations such as Continue and
GitHub Copilot. After installation, launch VS Code once to allow the
application to complete its initial setup process.

Download VS Code from: https://code.visualstudio.com

## Install Docker Desktop

Install Docker Desktop, which provides the container runtime required
for the standardized development environment used throughout the course.
Docker Desktop allows applications, databases, APIs, and other services
to run inside isolated containers with consistent behavior across
Windows and macOS systems.

After installation, launch Docker Desktop and allow it to fully
initialize before opening course projects. Windows students should
ensure WSL2 integration is enabled during installation. macOS students
should verify that Docker Desktop has sufficient permissions and memory
allocation.

Download Docker Desktop from:
https://www.docker.com/products/docker-desktop

## Install VS Code Extensions

The course environment depends on several VS Code extensions that
support containerized development, Python programming, Jupyter
notebooks, Git workflows, Docker integration, and optional AI-assisted
development tools. Extensions can be installed directly from the VS Code
Extensions Marketplace by searching for the extension name.

## Dev Containers

Allows VS Code to automatically open projects inside Docker-based
development containers.

## Python

Provides Python language support, debugging tools, linting, environment
management, and IntelliSense features.

## Docker

Adds Docker container management, image inspection, and container
monitoring directly inside VS Code.

## Jupyter

Provides notebook support for analytics, experimentation, and data
science workflows.

## GitLens

Enhances Git visibility and repository inspection workflows inside VS
Code.

## Continue (optional)

Provides unified integration with AI coding assistants such as Claude
and Codex/OpenAI.

# 6. Windows Setup Guidance

Windows students should use Docker Desktop with WSL2 (Windows Subsystem
for Linux 2) integration enabled. WSL2 provides a lightweight Linux
execution environment that dramatically improves Docker compatibility,
filesystem behavior, terminal tooling, package management, and container
runtime performance compared to legacy Windows container workflows.

This course intentionally standardizes development around Linux-based
container environments because nearly all modern cloud-native
application development, AI infrastructure, data engineering platforms,
CI/CD pipelines, Kubernetes deployments, and production hosting
environments operate primarily on Linux systems. Using WSL2 allows
Windows students to work in an environment that behaves much more
similarly to real-world production infrastructure.

## Why WSL2 Matters

Traditional Windows-native development environments often suffer from:

- Dependency conflicts

- Python environment inconsistencies

- Package installation instability

- File permission differences

- Path separator incompatibilities

- Slower Docker volume mounting performance

- Inconsistent shell tooling

WSL2 significantly reduces these problems by allowing development tools
and Docker containers to operate inside a true Linux kernel environment
while still integrating cleanly with Windows.

Students should think of WSL2 as:

- A lightweight Linux operating system integrated into Windows

- The preferred runtime environment for Docker Desktop

- The foundation for modern containerized Windows development workflows

## Install and Verify WSL2

Most modern Windows 11 systems already support WSL2, but students should
verify installation before beginning the course.

Open PowerShell as Administrator and run:

> wsl \--install

If WSL is already installed, verify the version using:

> wsl -l -v

The installed Linux distribution should report:

- VERSION 2

Ubuntu is the recommended Linux distribution for this course because:

- Most Docker examples assume Ubuntu/Linux tooling

- Package installation documentation commonly targets Ubuntu

- AI-generated troubleshooting guidance frequently assumes Ubuntu-based
  environments

## Recommended Repository Storage Location

Students are strongly encouraged to store repositories inside the Linux
filesystem rather than directly on the Windows filesystem.

Recommended:

> /home/\<username\>/projects

Avoid storing repositories in:

> C:\\Users\\\<username\>\\Documents

### Why This Matters

Docker performs substantially better when:

- Source code exists inside the Linux filesystem

- Containers mount Linux-native paths

- File synchronization remains within WSL2

Storing repositories inside the Windows filesystem can cause:

- Slow container startup times

- Slow dependency installation

- File watcher instability

- Hot reload problems

- Permission inconsistencies

- High CPU utilization during builds

This becomes especially important when:

- Using Node.js environments

- Running large Python dependency trees

- Mounting databases

- Using Docker Compose multi-service stacks

- Running AI-assisted indexing or code analysis tools

## Recommended VS Code Workflow on Windows

Students should launch VS Code from inside the Linux environment
whenever possible.

Recommended workflow:

- Open Ubuntu/WSL terminal

- Navigate to repository directory

- Run the code command from the project folder

> code .

This ensures:

- VS Code connects directly into WSL2

- Terminal sessions run natively in Linux

- Docker integrations behave consistently

- File permissions remain stable

- Git operations use Linux-native tooling

Students should avoid editing Linux filesystem repositories directly
through Windows Explorer whenever possible.

## Docker Desktop Configuration Recommendations

After installing Docker Desktop, students should enable:

- WSL2 backend

- Integration with Ubuntu distribution

- Docker Compose support

Verify these settings in Docker Desktop under Settings -\> Resources -\>
WSL Integration.

Ensure:

- Ubuntu integration is enabled

- The default WSL distribution is selected

## Recommended Docker Resource Allocation

Modern AI-assisted development environments can consume substantial
system resources.

Recommended minimum Docker allocations:

- 6-8 GB RAM

- 4 CPU cores

- 50+ GB available disk space

Students running large language model tooling, multi-service Docker
Compose stacks, databases, Jupyter notebooks, or AI indexing tools may
require additional resources.

Insufficient Docker memory commonly causes:

- Container crashes

- Random build failures

- Database instability

- Extremely slow builds

- VS Code Dev Container failures

## Understanding Dev Containers on Windows

When using Dev Containers:

- VS Code itself runs on Windows

- The development environment runs inside Linux containers

- The terminal operates inside Linux

- Dependencies install inside the container

- Applications execute inside the container

This separation is intentional and mirrors modern production engineering
environments.

Students should avoid installing large numbers of Python packages
directly on Windows itself unless specifically instructed.

## Common Windows Problems

### Docker Desktop Fails to Start

Common causes include:

- Virtualization disabled in BIOS

- WSL2 not installed

- Hyper-V conflicts

- Insufficient memory allocation

### Slow Container Performance

This is usually caused by:

- Repositories stored on the Windows filesystem

- Antivirus scanning Docker volumes

- Insufficient Docker memory

### Permission Errors

These are typically caused by:

- Mixing Windows and Linux file ownership

- Editing Linux files through Windows applications

### Line Ending Problems

Windows sometimes introduces CRLF line endings that can break Linux
scripts.

Recommended Git configuration:

> git config \--global core.autocrlf input

This preserves Linux-compatible line endings inside repositories.

# 7. macOS Setup Guidance

macOS provides an excellent environment for containerized software
development because it already includes a Unix-based operating system
with strong terminal tooling and native compatibility with many
Linux-oriented development workflows.

Students using macOS generally experience fewer filesystem compatibility
problems than Windows users, but proper Docker configuration and
resource management are still important for stable containerized
development.

## 7.1 Docker Desktop Initialization

After installing Docker Desktop:

- Launch Docker Desktop manually

- Wait for initialization to fully complete

- Verify Docker is running before opening course repositories

The Docker icon should appear in the macOS menu bar indicating:

- Docker Engine is active

- Containers can be started

- Dev Containers can connect successfully

Opening VS Code before Docker fully initializes commonly causes:

- Dev Container connection failures

- Missing Docker socket errors

- Container startup failures

## 7.2 Approving macOS Permissions

macOS may request permissions for:

- Filesystem access

- Network access

- Background services

- Virtualization support

Students should approve these permissions when prompted.

Failure to approve permissions can cause:

- Container mount failures

- Missing repository visibility

- Networking problems

- VS Code integration failures

## 7.3 Apple Silicon vs Intel Macs

Modern macOS systems may use:

- Apple Silicon (M1/M2/M3 series)

- Intel processors

Docker works on both platforms, but architecture differences matter.

### Apple Silicon Considerations

Many containers now support ARM64 architecture natively, but some older
images may still target x86/amd64 architectures.

Occasionally students may need to specify the following inside Docker
Compose configurations for older images:

> platform: linux/amd64

This is normal and increasingly common in enterprise environments where
mixed architectures exist.

## 7.4 Recommended Docker Resource Allocation

Recommended minimum Docker allocations:

- 6-8 GB RAM

- 4 CPU cores

- Adequate disk allocation for container images

Containerized environments frequently include:

- Databases

- APIs

- Python environments

- Jupyter notebooks

- AI tooling

- Node.js services

These services can consume significant memory.

Insufficient memory allocation often causes:

- Containers exiting unexpectedly

- Database corruption

- Extremely slow package installations

- Dev Container instability

## 7.5 Recommended Terminal Workflow

macOS students should become comfortable using terminal workflows
throughout the course.

Recommended terminal applications:

- Terminal.app

- iTerm2 (optional advanced terminal)

Students will frequently use:

- Git commands

- Docker commands

- Docker Compose

- Python tooling

- AI CLI integrations

- Linux shell utilities

Modern software engineering increasingly assumes strong terminal
proficiency.

## 7.6 Filesystem and Repository Recommendations

Students should store repositories in standard user directories such as:

> \~/projects

Avoid:

- External network drives

- Cloud-synchronized folders for active development

- Slow removable storage

Actively developing inside Dropbox, OneDrive, or iCloud synchronized
directories can occasionally create:

- File locking conflicts

- Git synchronization issues

- Container mount instability

## 7.7 Understanding Containerized Development on macOS

Although macOS is Unix-based, Docker containers still run inside a
lightweight virtualization layer.

Students should understand:

- Containers are isolated environments

- Dependencies exist inside containers

- The container is the authoritative runtime environment

- Host-machine Python installations are not the primary development
  target

This mirrors real-world infrastructure engineering practices where
applications are deployed into isolated runtime environments rather than
relying on developer workstation configuration.

## 7.8 Common macOS Problems

### Docker Uses Excessive Memory

Docker containers continue running in the background unless stopped. Use
the following commands to review and stop unused environments:

> docker ps
>
> docker compose down

### Container Build Failures on Apple Silicon

Older images may lack ARM support. A potential Docker Compose setting
is:

> platform: linux/amd64

### VS Code Cannot Connect to Container

This is usually caused by:

- Docker not fully initialized

- Corrupted container build cache

- Invalid Docker Compose configuration

Common corrective actions include:

- Use Rebuild Container

- Restart Docker Desktop

- Reopen VS Code

### Disk Space Consumption

Docker images, containers, and build caches can grow very large over
time.

Students should periodically clean unused resources:

> docker system prune

Use caution, as this removes unused Docker artifacts globally.

# 8. Cloning the Repository

## Understanding GitHub Repositories

Throughout this course, students will work from GitHub repositories that
contain:

- Application source code

- Docker configuration files

- Dev Container configuration

- Environment setup instructions

- Docker Compose definitions

- Assignment materials

- Documentation

- Sample datasets

- CI/CD configuration files

Students should think of the GitHub repository as the authoritative
source for the entire project environment. Modern development teams
increasingly treat repositories as complete infrastructure definitions
rather than simply collections of source code files.

Repositories may include:

- .devcontainer/

- Dockerfile

- docker-compose.yml

- .env.example

- requirements.txt

- package.json

- GitHub Actions workflows

- Documentation files

Understanding how these files work together is an important learning
objective of the course.

## Cloning a Repository

To begin working on a project, students must first clone the repository
from GitHub onto their local machine.

Basic cloning workflow:

git clone \<repository-url\>

cd course-project

code .

Example:

git clone https://github.com/example-org/course-project.git

cd course-project

code .

This process:

1.  Downloads the repository

2.  Preserves full Git history

3.  Creates a local working copy

4.  Allows synchronization with GitHub

5.  Enables collaboration workflows

## Recommended Repository Organization

Students are encouraged to create a dedicated projects directory.

Recommended structure:

### Windows (inside WSL2)

/home/\<username\>/projects

### macOS

\~/projects

Organized repository structures improve:

- Git workflow management

- Multi-project navigation

- Dev Container stability

- AI indexing performance

- Backup workflows

## Authenticating with GitHub

Students may need to authenticate with GitHub during:

- Cloning

- Pushing commits

- Pulling changes

- Creating pull requests

Recommended authentication methods:

- GitHub CLI

- Personal Access Tokens

- Git Credential Manager

Students should avoid embedding passwords directly into Git URLs.

## Understanding Git Branches

Modern software engineering rarely occurs directly on the main branch.

Students will commonly use:

- main

- develop

- feature branches

- bugfix branches

Example workflow:

git checkout -b feature-data-cleaning

Branches allow:

- Isolated experimentation

- Safer collaboration

- Parallel development

- Easier rollback

- Cleaner pull requests

## Pulling Latest Changes

Before beginning work, students should synchronize with GitHub:

git pull

This ensures:

- Local repositories are current

- Assignment updates are received

- Team changes are synchronized

- Environment definitions remain aligned

Failure to regularly pull updates can lead to:

- Merge conflicts

- Outdated environments

- Broken dependencies

- Inconsistent project states

## Understanding Repository Files

Students should gradually become familiar with common repository
components.

Examples include:

- .devcontainer/ --- Dev Container configuration

- Dockerfile --- Defines container image

- docker-compose.yml --- Defines multi-service environments

- .gitignore --- Excludes files from Git

- requirements.txt --- Python dependencies

- package.json --- Node.js dependencies

- .env.example --- Environment variable template

- .github/workflows/ --- CI/CD automation

Understanding these files is an important industry-aligned skill.

## Recommended Git Workflow Habits

Students should:

- Commit frequently

- Use meaningful commit messages

- Pull before pushing

- Keep branches focused

- Push changes regularly

- Avoid large uncommitted changes

Good commit example:

git commit -m \"Add customer churn feature engineering pipeline\"

Poor commit example:

git commit -m \"stuff\"

Professional Git hygiene becomes increasingly important in collaborative
engineering environments.

# 9. Opening the Dev Container

## What Is a Dev Container?

A Dev Container is a fully configured development environment defined as
code.

Rather than manually installing:

- Python

- Databases

- Libraries

- SDKs

- Runtime dependencies

- Toolchains

the environment is automatically provisioned inside a Docker container.

This ensures:

- Consistent environments

- Reproducible builds

- Easier onboarding

- Reduced "works on my machine" problems

- Industry-aligned workflows

## Opening the Repository in VS Code

After cloning the repository:

code .

VS Code should detect the .devcontainer configuration automatically.

Students will typically see a prompt:

"Reopen in Container"

Select:

- Reopen in Container

VS Code will then:

6.  Build the container image

7.  Start the container

8.  Install dependencies

9.  Connect VS Code into the container

10. Configure extensions automatically

## Understanding the Initial Build Process

The first Dev Container startup may take several minutes.

This process may include:

- Downloading base Docker images

- Installing Python packages

- Installing Node.js dependencies

- Configuring development tools

- Building Docker layers

- Installing VS Code extensions

Subsequent builds are usually much faster due to Docker layer caching.

## Understanding Docker Layer Caching

Docker builds images in layers.

For example:

- Base Linux image

- Python installation

- Dependency installation

- Application files

- Runtime configuration

Docker caches unchanged layers to improve rebuild speed.

Students should understand:

- Dependency changes often trigger rebuilds

- Small Dockerfile changes can invalidate cache

- Container builds are incremental

This mirrors real-world CI/CD infrastructure behavior.

## Verifying You Are Inside the Container

Once connected:

- The VS Code lower-left corner should indicate the container name

- Terminal sessions should run inside Linux

- Installed dependencies should already be available

Students can verify using:

uname -a

and:

which python

The terminal should reflect Linux/containerized execution rather than
the host operating system.

## Understanding Dev Container Isolation

The Dev Container is intentionally isolated from the host machine.

This means:

- Dependencies exist inside the container

- Python packages remain containerized

- Services run inside Docker networks

- Environments remain reproducible

Students should avoid:

- Installing large project dependencies globally

- Mixing host Python with container Python

- Running project services outside the container unless instructed

## Rebuilding the Container

Sometimes containers must be rebuilt after:

- Dependency changes

- Dockerfile updates

- Extension updates

- Environment corruption

Recommended rebuild workflow:

Open Command Palette:

Ctrl+Shift+P

Then select:

Dev Containers: Rebuild Container

Rebuilding is a normal part of containerized development workflows.

## Common Dev Container Problems

### Container Build Fails

Possible causes:

- Internet connectivity

- Docker not running

- Invalid Dockerfile

- Dependency conflicts

### VS Code Cannot Attach

Possible causes:

- Docker initialization incomplete

- Corrupted container state

- Invalid Docker Compose configuration

### Extensions Missing

Possible causes:

- Extension installation timeout

- Dev Container configuration mismatch

### Slow Startup

Possible causes:

- Insufficient Docker resources

- Large dependency installations

- Repositories stored on slow filesystems

# 10. Verifying Your Environment

## Why Environment Verification Matters

Modern software systems rely on many interconnected tools:

- Docker

- Git

- Python

- Package managers

- Databases

- AI integrations

- Container networking

Verifying the environment early helps identify configuration issues
before substantial development work begins.

Environment verification is a standard professional engineering
practice.

## Verify Python Installation

Run:

python \--version

Students should verify:

- Python executes successfully

- Correct version is installed

- Command runs inside the container

The exact version may vary by assignment.

## Verify Docker Connectivity

Run:

docker ps

This verifies:

- Docker Engine is running

- The container can communicate with Docker

- Container services are operational

Expected output should list running containers.

## Verify Git Functionality

Run:

git \--version

Students should also verify Git identity configuration:

git config \--global user.name

git config \--global user.email

These settings are important because GitHub commits rely on properly
configured identities.

## Verify Container Context

Students should confirm they are operating inside the Dev Container.

Useful commands:

pwd

uname -a

whoami

These commands help students understand:

- Filesystem context

- Linux runtime behavior

- User permissions

- Containerized execution

## Verify AI Tooling

If using AI integrations, students should verify:

- Continue extension connectivity

- Claude authentication

- OpenAI API access

- GitHub Copilot activation

Students should also confirm:

- AI chat interfaces open correctly

- Inline completion functions properly

- Repository-aware indexing works

## Verify Port Accessibility

Many applications expose services through ports such as:

- 3000

- 5000

- 8000

- 8888

- 5432

Students should understand:

- Containers expose ports

- VS Code forwards ports automatically

- Browser access may require forwarded URLs

Port conflicts are extremely common in development environments.

## Understanding Environment Variables

Projects commonly use environment variables for:

- Database credentials

- API keys

- Configuration settings

- Runtime behavior

Students may encounter:

- .env

- .env.example

- Compose environment definitions

Students should never commit:

- Secrets

- Passwords

- API tokens

- Private credentials

to GitHub repositories.

# 11. Starting Application Services

## Understanding Docker Compose

Modern applications often consist of multiple interconnected services.

Examples include:

- Frontend applications

- Backend APIs

- Databases

- Redis caches

- Analytics engines

- Message queues

- AI inference services

Docker Compose allows these services to be defined and launched
together.

This mirrors modern cloud-native and enterprise application
architectures.

## Starting Services

To start services:

docker compose up

This command:

- Builds images if necessary

- Starts containers

- Creates Docker networks

- Mounts volumes

- Connects services together

Students should expect logs to appear in the terminal.

## Detached Mode

To run services in the background:

docker compose up -d

Detached mode allows:

- Continued terminal usage

- Multiple concurrent workflows

- Easier debugging in separate terminals

Students will commonly use detached mode in professional workflows.

## Stopping Services

To stop services:

docker compose down

This:

- Stops running containers

- Removes container instances

- Preserves volumes unless explicitly removed

Stopping unused environments helps conserve system resources.

## Viewing Running Containers

Students can inspect active containers using:

docker ps

This shows:

- Container names

- Running status

- Port mappings

- Uptime

Understanding container state visibility is important for debugging.

## Viewing Logs

Logs are critical for debugging distributed systems.

Students can inspect logs using:

docker compose logs

or:

docker compose logs -f

The -f flag streams logs continuously.

Logs often reveal:

- Startup failures

- Dependency problems

- Database connectivity issues

- Runtime exceptions

- Port conflicts

## Restarting Services

Some changes require service restarts.

Restart all services:

docker compose restart

Restart a specific service:

docker compose restart api

Students should learn to restart only the affected services when
possible.

## Rebuilding Services

Dependency or Dockerfile changes may require rebuilding images:

docker compose up \--build

This forces Docker to rebuild containers before startup.

Students should understand the distinction between:

- Restarting containers

- Rebuilding images

These are not the same operation.

## Understanding Volumes and Persistent Data

Databases commonly use Docker volumes to persist data.

Without persistent volumes:

- Database contents disappear when containers stop

Students should understand:

- Volumes preserve state

- Containers are ephemeral

- Data persistence must be intentionally configured

This is a foundational cloud-native engineering concept.

## Multi-Service Architecture Awareness

Students should gradually learn how services communicate:

- Through Docker networks

- Via exposed ports

- Using internal service names

Example:

- Web app connects to database container

- API connects to Redis

- Analytics service connects to PostgreSQL

Modern distributed systems increasingly rely on these patterns.

  -----------------------------------------------------------------------
  Problem                             Solution
  ----------------------------------- -----------------------------------
  Docker Desktop not running          Start Docker Desktop before opening
                                      VS Code

  Container build fails               Retry build and verify internet
                                      connectivity

  VS Code cannot connect to container Use Rebuild Container from the
                                      command palette

  Port conflicts                      Stop conflicting applications or
                                      restart Docker

  AI extension not working            Verify authentication and API
                                      configuration

  WSL2 problems on Windows            Verify WSL2 integration is enabled
                                      in Docker Desktop
  -----------------------------------------------------------------------

# 12. Recommended AI Workflow

## Understanding AI-Assisted Development

Modern software engineering increasingly incorporates AI systems into
daily development workflows. AI coding assistants are not intended to
replace software engineers; rather, they function as productivity
accelerators, research assistants, implementation collaborators,
debugging aids, and architecture support systems.

Throughout this course, students will learn how professional engineers
increasingly integrate AI into:

• Architecture planning

• Feature implementation

• Test generation

• Refactoring

• Debugging

• Documentation

• API integration

• Infrastructure configuration

• DevOps workflows

Students should understand that AI-assisted development is rapidly
becoming a core industry skill across software engineering, data
engineering, analytics engineering, and AI platform development.

## Recommended Role Specialization for AI Tools

Different AI systems often perform better for different development
tasks.

Recommended workflow patterns include:

Claude

Best suited for:

• Architecture reasoning

• Large-scale refactoring guidance

• Debugging analysis

• Explaining complex systems

• Infrastructure reasoning

• Multi-step implementation planning

OpenAI/Codex

Best suited for:

• Implementation acceleration

• Test generation

• Boilerplate generation

• API integration assistance

• Rapid iteration workflows

GitHub Copilot

Best suited for:

• Inline autocomplete

• Repetitive coding tasks

• Syntax assistance

• Small utility functions

• Productivity acceleration

Students should experiment with combining tools together rather than
relying exclusively on a single AI platform.

## Architecture-First Development

Students are strongly encouraged to design architecture before
requesting implementation code from AI systems.

Recommended workflow:

1\. Define the system architecture

2\. Identify major services/components

3\. Define data flows

4\. Define APIs and interfaces

5\. Plan database structures

6\. Plan container interactions

7\. Request implementation incrementally

Students who skip architecture planning often experience:

• Fragile codebases

• Inconsistent implementations

• Integration failures

• Poor maintainability

• AI-generated technical debt

Modern engineering increasingly emphasizes system design and
orchestration rather than isolated coding tasks.

## AI-Assisted Debugging Workflows

AI systems are highly effective debugging collaborators when provided
with sufficient context.

Effective debugging prompts typically include:

• Full error messages

• Stack traces

• Relevant code snippets

• Runtime behavior descriptions

• Environment details

• Container logs

• Expected vs actual behavior

Poor debugging prompts often lack sufficient technical detail.

Good debugging prompt example:

"The Flask API container starts successfully, but requests to the
PostgreSQL database fail with connection refused errors. Here is the
docker-compose.yml configuration and the container logs."

Students should learn to treat debugging as a structured investigative
process rather than random experimentation.

## AI-Assisted Test Generation

AI systems can help generate:

• Unit tests

• Integration tests

• API tests

• Validation logic

• Mock datasets

• Edge case scenarios

Students should still review and validate all generated tests carefully.

The course emphasizes:

• Understanding test intent

• Reviewing assertions

• Verifying coverage

• Validating assumptions

AI-generated tests may appear correct while still missing important edge
cases.

## Recommended Prompt Engineering Practices

Students should:

• Provide clear objectives

• Include relevant architecture context

• Break large problems into smaller tasks

• Use iterative refinement

• Request explanations

• Ask for assumptions explicitly

• Validate outputs incrementally

Effective prompting is increasingly becoming an important engineering
communication skill.

## Repository-Aware AI Usage

Modern AI tools increasingly support repository-aware indexing and
contextual analysis.

This allows AI systems to:

• Understand project structure

• Reference existing code

• Suggest architecture-consistent implementations

• Analyze dependencies

• Understand coding patterns

Students should still verify all outputs independently.

## AI Usage Expectations for the Course

AI usage is encouraged throughout the course provided that:

• Students understand submitted work

• Students can explain their implementations

• Students validate generated outputs

• Students comply with course integrity policies

Students should think of AI as a collaborator rather than an automated
answer machine.

# 13. Effective Prompting Strategies

## Why Prompt Quality Matters

AI output quality depends heavily on prompt quality.

Ambiguous prompts often produce:

• Generic responses

• Incorrect assumptions

• Fragile code

• Missing edge cases

• Incomplete implementations

Well-structured prompts significantly improve:

• Technical accuracy

• Architectural consistency

• Code quality

• Debugging effectiveness

• Explanation clarity

Prompt engineering is increasingly viewed as a practical software
engineering skill.

## Architecture-Oriented Prompting

Students should describe the larger system before requesting
implementation details.

Example:

Instead of:

"Write a Flask API."

Prefer:

"Create a Flask API running inside Docker that connects to PostgreSQL
using SQLAlchemy, supports JWT authentication, exposes REST endpoints
for customer analytics, and follows a modular service architecture."

Context-rich prompts produce substantially better engineering outcomes.

## Iterative Development Prompting

Students should avoid extremely large one-shot prompts whenever
possible.

Recommended approach:

1\. Define architecture

2\. Generate project structure

3\. Implement individual services

4\. Add database integration

5\. Add testing

6\. Add debugging

7\. Refine incrementally

Iterative prompting generally improves:

• Reliability

• Maintainability

• Debuggability

• Learning outcomes

## Debugging Prompting Strategies

Effective debugging prompts should include:

• Exact error messages

• Relevant logs

• Runtime environment

• Container details

• Expected behavior

• Reproduction steps

Students should avoid vague prompts such as:

"My app doesn't work."

Specific technical detail dramatically improves AI troubleshooting
effectiveness.

## Requesting Explanations

Students are encouraged to request:

• Architectural explanations

• Dependency explanations

• Security implications

• Runtime behavior analysis

• Performance tradeoffs

• Alternative implementation approaches

Understanding generated code is more important than simply producing
code quickly.

## Using AI for Refactoring

AI systems can assist with:

• Code cleanup

• Modularization

• Naming improvements

• Dependency reduction

• Performance optimization

• Documentation generation

Students should still review all changes carefully before accepting
them.

## Security-Aware Prompting

Students should increasingly consider:

• Authentication

• Authorization

• Secrets management

• Input validation

• Dependency risks

• SQL injection prevention

• API security

AI-generated code is not automatically secure.

Students must review security implications independently.

## Prompt Iteration and Refinement

Professional AI-assisted development frequently involves multiple prompt
iterations.

Students should:

• Refine prompts progressively

• Correct AI assumptions

• Add missing context

• Request alternatives

• Narrow implementation scope when necessary

Iterative refinement is normal in modern AI-assisted engineering
workflows.

# 14. Responsible AI Usage

## AI Is a Development Accelerator, Not a Substitute for Learning

This course emphasizes understanding, validation, and engineering
judgment.

Students remain responsible for:

• Understanding submitted work

• Explaining architectural decisions

• Debugging generated code

• Verifying correctness

• Evaluating security implications

Blindly submitting AI-generated code without understanding it is not
acceptable.

## Validating AI-Generated Code

Students should always:

• Run generated code

• Test outputs

• Review dependencies

• Validate assumptions

• Check edge cases

• Review container behavior

• Verify configuration correctness

AI systems can generate convincing but incorrect solutions.

## Security and Privacy Considerations

Students should avoid submitting:

• Sensitive credentials

• Production secrets

• Personal information

• Private datasets

• Proprietary enterprise code

into public AI systems unless explicitly permitted.

Modern engineering increasingly requires awareness of data governance
and AI privacy implications.

## Reviewing Dependencies Carefully

AI-generated code may introduce:

• Vulnerable packages

• Deprecated libraries

• Poor architectural choices

• Excessive dependencies

Students should review dependency selections critically.

## Understanding Technical Debt

AI systems can accelerate implementation speed, but they can also
accelerate creation of technical debt.

Examples include:

• Duplicate logic

• Poor abstractions

• Inconsistent architecture

• Weak testing

• Excessive complexity

Students should prioritize maintainability and clarity over rapid
generation.

## Ethical and Professional Expectations

Students should:

• Credit collaborators appropriately

• Follow course integrity policies

• Use AI responsibly

• Avoid deceptive practices

• Maintain professional engineering standards

Responsible AI usage is increasingly important across industry and
academia.

## AI Hallucinations and Incorrect Outputs

AI systems sometimes produce:

• Incorrect APIs

• Invalid libraries

• Nonexistent configuration options

• Fabricated documentation

• Incorrect assumptions

Students should independently verify technical claims.

## Long-Term Professional Relevance

AI-assisted development is rapidly reshaping:

• Software engineering

• Data engineering

• Analytics engineering

• DevOps

• Infrastructure engineering

• AI platform operations

Students who learn to combine:

• Strong technical fundamentals

• Critical thinking

• AI collaboration

• Containerized workflows

• Git-based collaboration

will be substantially better prepared for modern engineering
environments.

# 15. Common Problems and Solutions

## Docker Desktop Not Running

Symptoms:

• Dev Containers fail to start

• Docker commands fail

• VS Code cannot attach to containers

Solutions:

• Start Docker Desktop manually

• Wait for initialization to complete

• Verify Docker Engine is active

• Restart Docker Desktop if necessary

## Container Build Failures

Common causes include:

• Internet connectivity problems

• Invalid Dockerfiles

• Dependency conflicts

• Corrupted Docker cache

• Registry download failures

Potential solutions:

• Retry the build

• Rebuild containers

• Clear Docker cache

• Verify internet connectivity

• Review build logs carefully

## VS Code Cannot Connect to Container

Possible causes:

• Docker not initialized

• Corrupted container state

• Invalid Dev Container configuration

• Extension conflicts

Potential solutions:

• Restart Docker Desktop

• Use "Rebuild Container"

• Restart VS Code

• Delete and rebuild containers

## Port Conflicts

Symptoms:

• Services fail to start

• "Port already in use" errors

• Containers exit immediately

Common conflicting ports:

• 3000

• 5000

• 5432

• 8000

• 8888

Potential solutions:

• Stop conflicting applications

• Change port mappings

• Restart Docker

## AI Extension Problems

Possible causes:

• Authentication failures

• Expired API keys

• Extension conflicts

• Rate limiting

• Network restrictions

Potential solutions:

• Reauthenticate

• Verify API configuration

• Restart VS Code

• Verify subscription access

## WSL2 Problems on Windows

Possible issues:

• WSL integration disabled

• Virtualization disabled in BIOS

• Filesystem performance issues

• Linux distribution corruption

Potential solutions:

• Verify WSL2 installation

• Enable virtualization

• Store repositories inside Linux filesystem

• Restart WSL

## Slow Docker Performance

Common causes:

• Insufficient RAM allocation

• Repositories stored on slow filesystems

• Excessive container resource usage

• Antivirus scanning

Potential solutions:

• Increase Docker resources

• Move repositories into Linux filesystem

• Stop unused containers

• Reduce concurrent workloads

## Database Connection Problems

Possible causes:

• Incorrect environment variables

• Service startup timing

• Invalid credentials

• Network configuration errors

Potential solutions:

• Verify docker-compose.yml configuration

• Check container logs

• Verify exposed ports

• Confirm service names

## Git Problems

Common issues:

• Merge conflicts

• Authentication failures

• Incorrect branch usage

• Uncommitted changes

Potential solutions:

• Pull frequently

• Commit regularly

• Verify Git authentication

• Review Git status carefully

## Debugging Mindset

Students should develop systematic debugging habits:

• Read logs carefully

• Reproduce issues consistently

• Isolate variables

• Test incrementally

• Validate assumptions

• Use AI as a debugging collaborator

Modern debugging is increasingly interdisciplinary and
infrastructure-aware.

# 16. Final Notes

## Course Philosophy

This environment is intentionally designed to mirror modern professional
engineering workflows.

Students will gain experience with:

• Containerized development

• AI-assisted engineering

• GitHub collaboration

• Infrastructure-aware development

• Distributed application architectures

• Reproducible environments

These workflows increasingly reflect real-world industry practices.

## The Importance of Reproducibility

One of the central goals of containerized development is
reproducibility.

Students should understand that modern engineering increasingly
prioritizes:

• Environment consistency

• Infrastructure automation

• Version-controlled configuration

• Deterministic builds

• Deployment portability

Reproducibility is foundational to modern cloud-native engineering.

## Thinking Beyond Individual Scripts

Students should increasingly think in terms of:

• Systems

• Services

• APIs

• Infrastructure

• Pipelines

• Automation

• Scalability

Modern engineering increasingly involves orchestrating interconnected
systems rather than building isolated programs.

## Developing Professional Engineering Habits

Students are encouraged to develop:

• Strong Git discipline

• Structured debugging habits

• Clear documentation practices

• Security awareness

• Architecture-first thinking

• Incremental development workflows

These habits become increasingly valuable in collaborative engineering
environments.

## AI as a Long-Term Engineering Tool

AI-assisted development will likely continue evolving rapidly.

Students who combine:

• Strong technical fundamentals

• Systems thinking

• Infrastructure understanding

• Prompt engineering

• Critical evaluation skills

will be better positioned to adapt to future engineering workflows.

## Final Recommendation

Students are strongly encouraged to:

• Experiment actively

• Break and rebuild environments

• Explore container tooling deeply

• Use Git frequently

• Practice debugging systematically

• Validate AI outputs carefully

• Ask questions continuously

The goal of this course is not merely to complete assignments, but to
help students become comfortable operating inside modern AI-assisted
software engineering ecosystems.
