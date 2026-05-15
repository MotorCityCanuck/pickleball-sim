**Instructor Implementation Guide: AI-Integrated Development
Environment**

Prepared: 2026-05-06

# 1. Purpose and Strategic Vision

This document provides a complete implementation guide for building and
distributing a standardized, AI-integrated software development
environment for graduate-level students using Visual Studio Code, Docker
Desktop, Dev Containers, GitHub, and modern AI coding systems such as
Claude, Codex/OpenAI, Continue, and GitHub Copilot.

The objective is not simply to provide a coding environment. The
objective is to teach students how modern software engineering is
increasingly performed in industry: using containerized environments,
AI-assisted development workflows, reproducible infrastructure,
Git-based collaboration, and iterative prompt-driven engineering
practices.

# 2. Core Educational Goals

- Teach students how to work inside standardized containerized
  environments.

- Reduce setup friction across mixed Windows and macOS classrooms.

- Introduce AI-assisted software engineering practices.

- Teach prompt engineering and iterative debugging workflows.

- Normalize GitHub-based collaboration and source control.

- Teach infrastructure-aware application development.

- Create reproducible environments suitable for team-based projects.

- Enable students to rapidly prototype analytics and application
  solutions.

- Teach students how to validate and critically evaluate AI-generated
  code.

# 3. Why VS Code + Docker + Dev Containers

Visual Studio Code was selected because it has become the dominant
cross-platform development environment for AI-assisted software
engineering. Docker and Dev Containers provide environment
reproducibility and greatly reduce platform inconsistencies between
Windows and macOS machines.

AI coding systems such as Claude and Codex perform significantly better
when operating inside predictable Linux-based execution environments.
Containerization improves the reliability of package installation,
runtime behavior, dependency management, networking, and debugging
workflows.

- Eliminates many Windows vs macOS dependency conflicts.

- Avoids inconsistent Python, Node, or database installations.

- Allows students to destroy and rebuild environments safely.

- Supports multi-service architectures using Docker Compose.

- Improves reproducibility of assignments and projects.

- Creates industry-aligned infrastructure practices.

- Provides cleaner support for AI-generated code.

- Allows instructors to distribute complete working environments.

# 4. Recommended Technology Stack

  --------------------------------------------------------------
  Layer                Recommended          Purpose
                       Technology           
  -------------------- -------------------- --------------------
  IDE                  Visual Studio Code   Primary development
                                            interface

  Container Runtime    Docker Desktop       Container execution
                                            environment

  Dev Environment      VS Code Dev          Standardized
                       Containers           development
                                            environment

  Source Control       Git + GitHub         Version control and
                                            collaboration

  Backend Runtime      Python               Application and
                                            analytics
                                            development

  Database             PostgreSQL           Relational data
                                            storage

  Notebook Environment Jupyter              Analytics and
                                            experimentation

  AI Integration       Continue             Unified AI model
                                            routing

  AI Models            Claude +             Reasoning and
                       Codex/OpenAI         implementation

  Optional AI          GitHub Copilot       Inline completions

  Database             DBeaver              Database inspection
  Administration                            and querying

  API Testing          Postman or Bruno     API validation and
                                            testing
  --------------------------------------------------------------

# 5. Recommended Repository Structure

The course repository should contain all application code,
infrastructure configuration, container configuration, notebooks, sample
data, environment templates, and documentation.

course-project/\
├── .devcontainer/\
│ └── devcontainer.json\
├── backend/\
│ ├── app/\
│ ├── requirements.txt\
│ └── Dockerfile\
├── frontend/\
├── notebooks/\
├── data/\
├── scripts/\
├── docs/\
├── docker-compose.yml\
├── .env.example\
├── README.md\
└── setup-check.py

# 6. Recommended Student Installation Requirements

- Git

- Visual Studio Code

- Docker Desktop

- Dev Containers VS Code extension

- Internet access for pulling Docker images and VS Code extensions

# 7. Windows-Specific Guidance

- Require Windows 10 or Windows 11.

- Require Docker Desktop with WSL2 backend enabled.

- Strongly encourage storing repositories inside the Linux filesystem
  rather than the Windows filesystem.

- Test the environment using WSL2 before classroom rollout.

- Ensure virtualization is enabled in BIOS if required.

# 8. Windows From-Scratch Development Environment Build Guide

This section provides a detailed, step-by-step build procedure for
creating the complete course development environment on a clean Windows
machine. It is written for instructors preparing a reference machine,
classroom lab machine, or student setup guide. The target outcome is a
reproducible Windows 10 or Windows 11 workstation that can run VS Code,
Docker Desktop, Dev Containers, GitHub-based repositories, PostgreSQL,
notebooks, and AI-assisted coding tools with minimal local dependency
conflicts.

## 8.1 Target End State

- Windows 10 or Windows 11 is fully updated and virtualization is
  enabled.

- WSL2 is installed and Ubuntu is available as the Linux development
  shell.

- Docker Desktop is installed and configured to use the WSL2 backend.

- Visual Studio Code is installed with Dev Containers, Docker, Python,
  Jupyter, GitLens, and Continue extensions.

- Git is installed, GitHub authentication is configured, and
  repositories can be cloned into the WSL filesystem.

- The course repository opens successfully inside a VS Code Dev
  Container.

- Docker Compose starts the application container and PostgreSQL service
  successfully.

- DBeaver can connect to the local PostgreSQL database.

- AI tools are configured sufficiently for students to use Claude,
  Codex/OpenAI, Continue, and optionally GitHub Copilot.

## 8.2 Pre-Installation Checklist

- Confirm the machine is running Windows 10 version 22H2 or Windows 11.
  Windows 11 is preferred for classroom consistency.

- Confirm the user has local administrator rights. Docker Desktop, WSL2,
  virtualization features, and some security prompts require
  administrator approval.

- Run Windows Update until no critical updates remain. Reboot before
  installing Docker Desktop or WSL2 components.

- Confirm at least 16 GB RAM is available. 32 GB is strongly preferred
  for Docker, PostgreSQL, notebooks, and AI-assisted development
  workflows.

- Confirm at least 40 GB of free disk space. Docker images, PostgreSQL
  volumes, and generated datasets can grow quickly.

- Confirm virtualization is enabled in BIOS/UEFI. On many systems this
  appears as Intel VT-x, Intel Virtualization Technology, AMD-V, or SVM
  Mode.

- Disable or adjust corporate security tools only if they block Docker
  networking, WSL file access, or localhost ports. Coordinate with IT
  before changing managed endpoint policies.

## 8.3 Install and Validate WSL2

Open PowerShell as Administrator and install WSL with the default Ubuntu
distribution:

wsl \--install

Restart Windows when prompted. After restart, launch Ubuntu from the
Start menu and complete the initial Linux username and password setup.
The Linux username does not need to match the Windows username.

If WSL is already installed, confirm the installed distributions and WSL
version:

wsl \--list \--verbose

Ubuntu should show VERSION 2. If it shows VERSION 1, convert it to WSL2:

wsl \--set-version Ubuntu 2

Set WSL2 as the default for future distributions:

wsl \--set-default-version 2

Inside the Ubuntu terminal, update packages:

sudo apt update && sudo apt upgrade -y

Instructor validation: from PowerShell, run wsl \--status. From Ubuntu,
run pwd and confirm the shell opens in the Linux environment. Students
should understand that this Linux shell is where course repositories
should generally live.

## 8.4 Install Git and Configure GitHub Identity

Install Git for Windows from the official Git download page or through
winget if available:

winget install \--id Git.Git -e

Also install Git inside Ubuntu so Linux-based Dev Container workflows
have direct access to Git tooling:

sudo apt install git -y

Configure the student or instructor Git identity inside Ubuntu:

git config \--global user.name \"Your Name\"\
git config \--global user.email \"your.email@example.com\"\
git config \--global init.defaultBranch main

Recommended GitHub authentication options:

- Option A (preferred): GitHub CLI authentication. Install GitHub CLI,
  then run gh auth login and follow the browser-based authentication
  flow.

- Option B: SSH authentication. Generate an SSH key in Ubuntu, add the
  public key to GitHub, then clone repositories using the git@github.com
  format.

- Option C: HTTPS authentication. Use browser/device authentication when
  prompted by VS Code or Git Credential Manager.

For SSH-based authentication inside Ubuntu:

ssh-keygen -t ed25519 -C \"your.email@example.com\"\
cat \~/.ssh/id_ed25519.pub

Copy the public key output into GitHub under Settings -\> SSH and GPG
keys. Validate access:

ssh -T git@github.com

## 8.5 Install Visual Studio Code and Required Extensions

Install Visual Studio Code using the official installer or winget:

winget install \--id Microsoft.VisualStudioCode -e

Open VS Code and install the required extensions:

- Dev Containers - required for opening the course repository inside a
  containerized environment.

- Docker - useful for viewing containers, images, volumes, logs, and
  Compose services.

- Python - required for Python editing, debugging, linting, and
  interpreter discovery.

- Jupyter - required for notebooks and exploratory analytics workflows.

- GitLens - useful for Git history, blame, branches, and student
  collaboration workflows.

- Continue - used as the primary AI model routing and AI-assisted
  development interface.

- GitHub Pull Requests and Issues - optional, but useful for classroom
  workflows using pull requests.

- GitHub Copilot - optional, if students or the institution have
  licenses.

Install the VS Code WSL extension as well. It allows VS Code to open
folders directly from the Ubuntu filesystem and keeps file operations
aligned with the Linux-based container workflow.

## 8.6 Install Docker Desktop and Configure WSL2 Backend

For the Windows 11 + WSL2 development architecture used in this course,
Docker should be installed using Docker Desktop on Windows, with the
WSL2 backend enabled. Do not install the standalone Docker Engine
directly inside the Ubuntu distribution unless explicitly instructed, as
Docker Desktop provides the supported integration layer between Windows,
WSL2, VS Code, Dev Containers, and containerized services.

Install Docker Desktop using either the official installer or winget:

winget install \--id Docker.DockerDesktop -e

After installation:

1.  Restart Windows.

2.  Launch Docker Desktop.

3.  Complete any first-run initialization prompts.

In Docker Desktop settings:

- Enable:

  - Use the WSL 2 based engine

- Under:

  - Resources -\> WSL Integration

  - Enable integration for the Ubuntu WSL distribution.

- Enable Docker Compose V2 (normally enabled by default in current
  releases).

- Leave Kubernetes disabled unless specifically required.

- If resource controls are exposed, allocate sufficient resources for
  local analytics and container workloads.

Recommended minimum configuration for this course environment:

- 4 CPUs

- 8 GB RAM

Recommended configuration for higher-performance systems (strongly
recommended for modern AI-assisted development workflows):

- 8 CPUs

- 16 GB RAM

This higher allocation is especially beneficial when simultaneously
running:

- Postgres containers

- Python/Jupyter workloads

- VS Code Dev Containers

- AI-assisted development tools

- Multiple containerized services

Validate Docker from Windows PowerShell:

> docker \--version
>
> docker compose version
>
> docker run hello-world

Then validate Docker access from the Ubuntu WSL environment:

> docker \--version
>
> docker compose version
>
> docker run hello-world

If Docker commands work successfully inside Ubuntu without separately
installing Docker Engine in Ubuntu, then WSL integration is functioning
correctly.

If Docker commands fail inside Ubuntu:

1.  Reopen Docker Desktop.

2.  Recheck:

    - Settings -\> Resources -\> WSL Integration

3.  Confirm Ubuntu integration is enabled.

4.  Restart Docker Desktop.

5.  Restart the WSL session: wsl --shutdown

Then reopen Ubuntu and retest the Docker commands.

Once complete, the environment will support:

- Linux-native development inside WSL2

- VS Code Dev Containers

- Containerized databases and services

- AI-assisted development workflows

- Local analytics and simulation platforms

- Multi-service Docker Compose environments

## 8.7 Store Course Repositories in the WSL Filesystem

For performance and reliability, students should clone course
repositories into the Ubuntu filesystem rather than into C:\\Users or
OneDrive-synced folders. This avoids slow file sharing, path issues,
file locking problems, and inconsistent container volume behavior.

Recommended repository location inside Ubuntu:

mkdir -p \~/course-projects\
cd \~/course-projects

Clone the course repository from GitHub:

git clone git@github.com:YOUR-ORG/YOUR-COURSE-REPO.git\
cd YOUR-COURSE-REPO

If using HTTPS instead of SSH:

git clone https://github.com/YOUR-ORG/YOUR-COURSE-REPO.git

From the Ubuntu terminal, open the repository in VS Code:

code .

VS Code should display a WSL indicator in the lower-left corner. This
confirms that the editor is attached to the Linux filesystem rather than
opening the repository through the Windows path.

## 8.8 Create or Verify the Repository Environment Files

A working course repository should include the .devcontainer folder,
docker-compose.yml, application Dockerfile, dependency files, and
environment template. At minimum, verify the following files exist:

- .devcontainer/devcontainer.json

- docker-compose.yml

- backend/Dockerfile or a root-level Dockerfile, depending on repository
  structure

- backend/requirements.txt or pyproject.toml for Python dependencies

- .env.example for non-secret local settings

- README.md with course-specific setup instructions

- setup-check.py for validating the local environment

Create a working local environment file from the template:

> cp .env.example .env

Students should never commit real secrets, API keys, personal access
tokens, database passwords beyond classroom defaults, or paid AI model
keys into GitHub. The .env file should be listed in .gitignore.

## 8.9 Open the Project in a Dev Container

In VS Code, use the command palette: Dev Containers: Reopen in
Container. VS Code will build the container image, start the Docker
Compose services, attach to the app container, install configured
extensions inside the container, and mount the project into the
container workspace.

During the first build, students should expect Docker to download base
images and install dependencies. The first build is slower than later
rebuilds.

Validate the container shell from the VS Code terminal:

pwd\
python \--version\
pip \--version\
git \--version

If the shell path is /workspace or the configured workspace folder, the
student is operating inside the intended Dev Container.

## 8.10 Start and Validate Docker Compose Services

From inside the repository or Dev Container terminal, start the services
if they are not already running:

docker compose up -d

Confirm service status:

docker compose ps

Review logs when troubleshooting:

docker compose logs app\
docker compose logs postgres

Validate PostgreSQL connectivity using the configured classroom
defaults:

psql postgresql://student:student@postgres:5432/course_db

If psql is not installed in the app container, either add the PostgreSQL
client to the Dockerfile or validate connectivity through SQLAlchemy,
DBeaver, or a setup-check.py script.

## 8.11 Install and Configure DBeaver

Install DBeaver Community Edition using the official installer or
winget:

winget install \--id dbeaver.dbeaver -e

Create a PostgreSQL connection with the following default classroom
settings:

- Host: localhost

- Port: 5432

- Database: course_db

- Username: student

- Password: student

DBeaver connects from Windows to the PostgreSQL port published by Docker
Compose. If the connection fails, confirm the postgres service is
running, confirm port 5432 is not already in use, and confirm Docker
Desktop is running.

## 8.12 Configure AI Coding Tools

The instructor should decide which AI tools are required, optional, or
demonstration-only. A practical classroom default is Continue for
IDE-based AI workflows, with Claude and OpenAI/Codex configured through
model-provider keys when available. GitHub Copilot may be optional
depending on institutional licensing.

Recommended setup sequence:

1.  Install the Continue extension in VS Code.

2.  Open Continue settings and configure the approved model providers
    for the course.

3.  Store API keys in the supported local secret mechanism or
    environment variables, not in the Git repository.

4.  Create a short course policy explaining acceptable AI use,
    attribution expectations, code review responsibilities, and
    prohibited shortcuts.

5.  Install GitHub Copilot only where licensing allows and clarify that
    Copilot suggestions must be reviewed and tested like any other
    AI-generated code.

Recommended instructor validation prompts:

- Ask the AI assistant to explain the repository structure.

- Ask the AI assistant to identify where Docker Compose defines
  PostgreSQL.

- Ask the AI assistant to propose a test plan for setup-check.py.

- Ask the AI assistant to explain one generated code change before
  accepting it.

## 8.13 Run the Final Setup Validation

Each student machine should pass a simple validation checklist before
course project work begins:

- VS Code opens the course repository from the WSL filesystem.

- Dev Containers: Reopen in Container completes without build errors.

- docker compose ps shows the app and postgres services running.

- Python runs inside the container.

- Jupyter notebooks can open and execute a simple cell.

- The application can connect to PostgreSQL.

- DBeaver can connect to PostgreSQL from Windows.

- Git can pull, commit, and push to GitHub.

- Continue or the approved AI tool can read repository context and
  answer a repository-specific question.

- The student can rebuild the container after deleting it, proving the
  environment is reproducible.

Recommended setup-check.py responsibilities:

- Print Python version and platform information.

- Import required packages.

- Connect to PostgreSQL.

- Create and drop a small test table or run a harmless SELECT query.

- Confirm expected environment variables are present.

- Print a clear PASS or FAIL result with remediation guidance.

## 8.14 Common Windows Failure Points and Fixes

  -----------------------------------------------------------------------
  Issue                               Recommended Fix
  ----------------------------------- -----------------------------------
  Docker Desktop starts but           Restart Docker Desktop, confirm WSL
  containers fail                     integration, and run docker compose
                                      logs for the failing service.

  WSL command not found or Ubuntu     Run wsl \--install from
  missing                             Administrator PowerShell and
                                      reboot. Confirm Windows optional
                                      features are enabled.

  Very slow file operations           Move the repository from C:\\Users,
                                      Desktop, Documents, or OneDrive
                                      into \~/course-projects inside
                                      Ubuntu.

  PostgreSQL port conflict            Stop the local PostgreSQL service
                                      using port 5432 or change the
                                      Compose port mapping to another
                                      host port such as 5433.

  Dev Container build fails during    Rebuild without cache, verify
  package install                     internet access, and check whether
                                      dependency versions are pinned
                                      correctly.

  VS Code opens Windows path instead  Open the repository from the Ubuntu
  of WSL path                         terminal using code . or use Remote
                                      Explorer -\> WSL.

  AI extension cannot see project     Confirm VS Code is attached to the
  files                               WSL folder or Dev Container
                                      workspace, then reload the window.

  DBeaver cannot connect              Confirm Docker Compose publishes
                                      5432 to localhost, confirm the
                                      database credentials, and confirm
                                      the postgres container is healthy.
  -----------------------------------------------------------------------

## 8.15 Instructor Rollout Recommendations

- Build and test the full environment on a clean Windows reference
  machine before distributing instructions to students.

- Record a short setup walkthrough showing WSL installation, Docker
  Desktop configuration, repository cloning, and Dev Container launch.

- Provide students with a known-good repository zip or GitHub Classroom
  template so setup problems are not confused with incomplete project
  files.

- Schedule setup validation before the first graded coding assignment.

- Create a discussion board or issue tracker label for setup failures
  and common fixes.

- Ask students to submit screenshots or terminal output from
  setup-check.py as proof that the environment is ready.

- Keep the course image and dependency versions stable during an active
  term unless a security issue requires an update.

# 9. macOS-Specific Guidance

- Require current Docker Desktop release.

- Test Apple Silicon compatibility before course delivery.

- Avoid x86-only dependencies when possible.

- Verify container performance and memory allocation settings.

# 10. Dockerfile Example

A simple Python-based Dockerfile suitable for analytics and application
development:

FROM python:3.11\
\
WORKDIR /workspace\
\
COPY requirements.txt .\
RUN pip install \--no-cache-dir -r requirements.txt\
\
COPY . .\
\
EXPOSE 5000\
\
CMD \[\"bash\"\]

# 11. docker-compose.yml Example

version: \'3.9\'\
\
services:\
\
app:\
build: .\
volumes:\
- .:/workspace\
ports:\
- \"5000:5000\"\
depends_on:\
- postgres\
\
postgres:\
image: postgres:16\
environment:\
POSTGRES_USER: student\
POSTGRES_PASSWORD: student\
POSTGRES_DB: course_db\
ports:\
- \"5432:5432\"\
volumes:\
- postgres-data:/var/lib/postgresql/data\
\
volumes:\
postgres-data:

# 12. Dev Container Configuration

{\
\"name\": \"Graduate AI Development Environment\",\
\"dockerComposeFile\": \"../docker-compose.yml\",\
\"service\": \"app\",\
\"workspaceFolder\": \"/workspace\",\
\"customizations\": {\
\"vscode\": {\
\"extensions\": \[\
\"ms-python.python\",\
\"ms-toolsai.jupyter\",\
\"ms-azuretools.vscode-docker\",\
\"eamodio.gitlens\",\
\"Continue.continue\"\
\]\
}\
}\
}

# 13. AI Integration Strategy

The environment is intentionally designed to support AI-assisted
development workflows. Instructors should explicitly teach students how
different AI systems are better suited for different engineering
activities.

  --------------------------------------------------------------
  AI Tool              Best Use Cases       Instructor
                                            Recommendations
  -------------------- -------------------- --------------------
  Claude               Architecture,        Encourage detailed
                       debugging,           reasoning prompts
                       reasoning,           
                       refactoring          

  Codex/OpenAI         Implementation,      Use for rapid
                       tests, repetitive    feature iteration
                       coding               

  Continue             Unified routing and  Standardize AI
                       IDE integration      access across
                                            students

  GitHub Copilot       Inline suggestions   Use as productivity
                       and boilerplate      accelerator
  --------------------------------------------------------------

# 14. Recommended AI Development Workflow

- Students use Claude to design application architecture and debugging
  strategies.

- Students use Codex/OpenAI for implementation acceleration and test
  generation.

- Students use GitHub Copilot for inline productivity improvements.

- Students validate all AI-generated code through testing and
  inspection.

- Students commit frequently to GitHub using feature branches.

- Students document architecture decisions and prompting strategies.

- Students use Docker Compose to manage application infrastructure.

- Students learn iterative prompt engineering workflows.

# 15. Recommended Classroom Policies

- Require GitHub repositories for all assignments and projects.

- Require reproducible containerized environments.

- Require README documentation and architecture summaries.

- Require students to explain AI-generated code during presentations.

- Require students to validate AI-generated outputs through testing.

- Encourage pull requests and peer reviews.

- Encourage prompt documentation for major implementation decisions.

# 16. Troubleshooting Guidance

- Docker Desktop not running

- WSL2 not enabled on Windows

- Insufficient memory allocated to Docker

- Port conflicts on PostgreSQL or Flask services

- Repository stored on Windows filesystem rather than WSL filesystem

- Corporate antivirus interfering with Docker networking

- Docker image build failures caused by dependency incompatibilities

# 17. Advanced Teaching Opportunities

- Teach prompt engineering for software development.

- Introduce agentic software engineering workflows.

- Compare AI-generated vs manually written implementations.

- Teach CI/CD pipelines using GitHub Actions.

- Introduce infrastructure-as-code concepts.

- Teach microservice architecture patterns.

- Teach scalable analytics application development.

- Teach responsible AI usage and verification workflows.

8.5.1 Important VS Code + WSL Validation Notes

During initial classroom rollout testing, a number of common WSL
integration issues were encountered that should be addressed proactively
in instructor guidance.

Recommended validation workflow:

• Install the Microsoft WSL extension directly inside Visual Studio
Code.

• Open the repository from the Ubuntu terminal using: code .

• Confirm the lower-left corner of VS Code displays "WSL: Ubuntu".

• If VS Code opens without the WSL indicator, the repository is being
opened through the Windows filesystem rather than the Linux filesystem.

• Students should avoid opening Linux repositories through Windows
Explorer paths such as \\\\wsl\$ unless specifically required.

Recommended instructor guidance:

• Explain that the "code ." command means "open the current Linux
directory in VS Code."

• Explain that "." refers to the current directory.

• Explain that Linux filesystem paths are case-sensitive.

• Explain that repositories should generally remain inside
/home/\<username\>/course-projects.

Potential issue: Cursor intercepting the code command

Some students may have Cursor installed alongside Visual Studio Code. In
these situations, the "code" command may incorrectly launch Cursor
rather than VS Code.

Validation command:

which code

Correct VS Code example:

/mnt/c/Users/\<username\>/AppData/Local/Programs/Microsoft VS
Code/bin/code

Incorrect example:

/mnt/c/Users/\<username\>/AppData/Local/Programs/cursor/resources/app/bin/code

If Cursor intercepts the code command:

• Reinstall or re-enable the VS Code shell command integration.

• Reopen Ubuntu after PATH changes.

• Validate the code command again before continuing.

8.5.2 Recommended GitHub CLI Workflow

The preferred GitHub authentication approach for classroom environments
is GitHub CLI using browser-based authentication.

Install GitHub CLI inside Ubuntu:

sudo apt install gh -y

Authenticate:

gh auth login

Recommended options:

• GitHub.com

• HTTPS

• Login with a web browser

• Authenticate Git with GitHub credentials: Yes

Validation:

gh auth status

This approach generally produces fewer authentication issues than SSH
for mixed-experience student populations while still supporting
professional GitHub workflows.

8.6.1 Docker Desktop Installation Guidance and Common Failure Modes

Docker Desktop installations may appear stalled during initial
installation, especially on systems where virtualization or WSL2 was
recently enabled.

Observed classroom testing behavior:

• winget installations occasionally appear to hang for 15--20 minutes.

• Docker installer windows may appear behind other windows.

• Docker initialization may pause while configuring WSL integration.

• Initial startup after installation may take several minutes.

Recommended instructor guidance:

• If Docker Desktop appears frozen for more than approximately 20
minutes, cancel the installation, reboot Windows, and install using the
graphical installer from the official Docker website instead of winget.

• Always reboot Windows after enabling BIOS virtualization settings or
installing WSL2.

• Confirm Docker Desktop reaches "Docker Desktop is running" before
validating commands.

• Confirm Ubuntu integration is enabled under Docker Desktop -\>
Settings -\> Resources -\> WSL Integration.

Recommended validation sequence:

From PowerShell:

docker \--version

docker compose version

docker run hello-world

From Ubuntu:

docker \--version

docker compose version

docker run hello-world

Students should understand that Docker commands inside Ubuntu should
function without separately installing Docker Engine inside Ubuntu.

8.7.1 Recommended PostgreSQL Container Approach

For classroom consistency and reproducibility, instructors should
strongly prefer PostgreSQL running as a Docker Compose service rather
than as a direct installation inside Ubuntu or Windows.

Recommended benefits:

• Consistent PostgreSQL version across all students.

• Easier environment rebuilds.

• Cleaner Dev Container integration.

• Reduced local dependency conflicts.

• Simpler classroom troubleshooting.

Recommended starter compose service:

services:

postgres:

image: postgres:16

container_name: course-postgres

environment:

POSTGRES_USER: student

POSTGRES_PASSWORD: student

POSTGRES_DB: course_db

ports:

\- \"5432:5432\"

volumes:

\- postgres_data:/var/lib/postgresql/data

volumes:

postgres_data:

Recommended Docker commands:

docker compose up -d

docker compose ps

docker compose logs

docker compose down

8.12.1 Continue Extension Configuration Guidance

Recent Continue extension versions increasingly rely on UI-driven
configuration workflows rather than older manually-managed YAML-only
workflows.

Important instructor observations:

• Continue configuration may be stored on the Windows side even while VS
Code is attached to WSL.

• Environment variables used by Continue may therefore need to exist as
Windows environment variables rather than only Linux shell variables.

• Continue configuration workflows have changed significantly across
extension versions.

Recommended environment variable setup on Windows:

OPENAI_API_KEY

ANTHROPIC_API_KEY

Recommended validation from PowerShell:

echo \$env:OPENAI_API_KEY

echo \$env:ANTHROPIC_API_KEY

Recommended Continue configuration file location:

C:\\Users\\\<username\>\\.continue\\config.yaml

Recommended model configuration example:

models:

\- name: Claude Sonnet 4.5

provider: anthropic

model: claude-sonnet-4-5

apiKey: \$ANTHROPIC_API_KEY

\- name: Claude Haiku

provider: anthropic

model: claude-haiku-4-5

apiKey: \$ANTHROPIC_API_KEY

\- name: GPT-5

provider: openai

model: gpt-5

apiKey: \$OPENAI_API_KEY

Recommended instructor guidance:

• Students should fully restart VS Code after modifying Windows
environment variables.

• Students should confirm the lower-left VS Code indicator displays
"WSL: Ubuntu".

• Students should validate API key visibility before troubleshooting
Continue.

• Continue configuration formats may vary between extension releases.

8.14.1 Additional Linux Command Guidance for Students

Students unfamiliar with Linux terminals frequently struggle with basic
filesystem navigation. Instructors should consider providing a short
Linux command quick-reference.

Recommended minimum commands:

pwd Show current directory

ls List files/directories

ls -la List hidden files/directories

cd .. Move up one directory

cd \~ Return to home directory

mkdir \<folder\> Create directory

rm \<file\> Delete file

rm -r \<folder\> Delete directory recursively

code . Open current folder in VS Code

Important instructor reminders:

• Linux paths are case-sensitive.

• Hidden files begin with a period (.).

• Deletion using rm is immediate and does not use a recycle bin.
