"""
skill_taxonomy.py
-----------------
Normalizes skill aliases to canonical names.
100+ aliases covering common variations in how developers list technologies.

Usage:
    from backend.skill_taxonomy import normalize_skill, normalize_skill_list
    normalize_skill("nodejs")   → "node.js"
    normalize_skill("React.js") → "react"
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── Alias Map: variant → canonical name ──────────────────────────────────────
# Keys are lowercase, stripped of whitespace
SKILL_ALIASES: dict[str, str] = {
    # Python ecosystem
    "python3": "python",
    "python2": "python",
    "py": "python",
    "sklearn": "scikit-learn",
    "sci-kit learn": "scikit-learn",
    "scikitlearn": "scikit-learn",
    "sk-learn": "scikit-learn",
    "tensorflow": "tensorflow",
    "tf": "tensorflow",
    "pytorch": "pytorch",
    "torch": "pytorch",
    "numpy": "numpy",
    "np": "numpy",
    "pandas": "pandas",
    "pd": "pandas",
    "matplotlib": "matplotlib",
    "mpl": "matplotlib",
    "fastapi": "fastapi",
    "fast-api": "fastapi",
    "fast api": "fastapi",
    "flask": "flask",
    "django": "django",
    "dj": "django",
    "celery": "celery",
    "sqlalchemy": "sqlalchemy",
    "pydantic": "pydantic",
    "uvicorn": "uvicorn",
    "gunicorn": "gunicorn",

    # JavaScript ecosystem
    "javascript": "javascript",
    "js": "javascript",
    "ecmascript": "javascript",
    "es6": "javascript",
    "es2015": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "nodejs": "node.js",
    "node": "node.js",
    "node.js": "node.js",
    "expressjs": "express",
    "express.js": "express",
    "reactjs": "react",
    "react.js": "react",
    "reactnative": "react native",
    "react-native": "react native",
    "nextjs": "next.js",
    "next.js": "next.js",
    "vuejs": "vue",
    "vue.js": "vue",
    "vuex": "vue",
    "angular": "angular",
    "angularjs": "angular",
    "angular.js": "angular",
    "svelte": "svelte",
    "sveltekit": "svelte",
    "jquery": "jquery",
    "webpack": "webpack",
    "vite": "vite",
    "nestjs": "nest.js",
    "nest.js": "nest.js",

    # Databases
    "postgresql": "postgresql",
    "postgres": "postgresql",
    "pg": "postgresql",
    "psql": "postgresql",
    "mysql": "mysql",
    "mariadb": "mysql",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "sqlite": "sqlite",
    "sqlite3": "sqlite",
    "redis": "redis",
    "memcached": "memcached",
    "elasticsearch": "elasticsearch",
    "elastic": "elasticsearch",
    "dynamodb": "dynamodb",
    "dynamo": "dynamodb",
    "cassandra": "cassandra",
    "neo4j": "neo4j",

    # Cloud & DevOps
    "aws": "aws",
    "amazon web services": "aws",
    "gcp": "gcp",
    "google cloud": "gcp",
    "google cloud platform": "gcp",
    "azure": "azure",
    "microsoft azure": "azure",
    "docker": "docker",
    "dockerfile": "docker",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "kube": "kubernetes",
    "terraform": "terraform",
    "tf (iac)": "terraform",
    "ansible": "ansible",
    "jenkins": "jenkins",
    "circleci": "circleci",
    "github actions": "github-actions",
    "gh actions": "github-actions",
    "gitlab ci": "gitlab-ci",
    "ci/cd": "ci/cd",
    "cicd": "ci/cd",
    "nginx": "nginx",
    "apache": "apache",

    # Programming languages
    "golang": "go",
    "go": "go",
    "rust": "rust",
    "rustlang": "rust",
    "c++": "c++",
    "cpp": "c++",
    "cplusplus": "c++",
    "c#": "c#",
    "csharp": "c#",
    "c-sharp": "c#",
    "java": "java",
    "jvm": "java",
    "kotlin": "kotlin",
    "kt": "kotlin",
    "swift": "swift",
    "objective-c": "objective-c",
    "objc": "objective-c",
    "r": "r",
    "rlang": "r",
    "ruby": "ruby",
    "rb": "ruby",
    "php": "php",
    "scala": "scala",
    "elixir": "elixir",
    "erlang": "erlang",
    "haskell": "haskell",
    "clojure": "clojure",
    "lua": "lua",
    "perl": "perl",
    "shell": "shell",
    "bash": "shell",
    "zsh": "shell",
    "powershell": "powershell",

    # Data & ML
    "machine learning": "machine-learning",
    "ml": "machine-learning",
    "deep learning": "deep-learning",
    "dl": "deep-learning",
    "natural language processing": "nlp",
    "nlp": "nlp",
    "computer vision": "computer-vision",
    "cv": "computer-vision",
    "data science": "data-science",
    "data engineering": "data-engineering",
    "apache spark": "spark",
    "pyspark": "spark",
    "spark": "spark",
    "hadoop": "hadoop",
    "apache kafka": "kafka",
    "kafka": "kafka",
    "airflow": "airflow",
    "apache airflow": "airflow",
    "mlflow": "mlflow",
    "huggingface": "hugging-face",
    "hugging face": "hugging-face",
    "langchain": "langchain",
    "openai": "openai",
    "llm": "llm",
    "large language models": "llm",
    "generative ai": "generative-ai",
    "gen ai": "generative-ai",

    # Frontend / design
    "html": "html",
    "html5": "html",
    "css": "css",
    "css3": "css",
    "sass": "sass",
    "scss": "sass",
    "less": "less",
    "tailwind": "tailwindcss",
    "tailwindcss": "tailwindcss",
    "tailwind css": "tailwindcss",
    "bootstrap": "bootstrap",
    "material ui": "material-ui",
    "mui": "material-ui",
    "figma": "figma",

    # Tools / misc
    "git": "git",
    "github": "github",
    "gitlab": "gitlab",
    "bitbucket": "bitbucket",
    "jira": "jira",
    "agile": "agile",
    "scrum": "scrum",
    "rest": "rest-api",
    "rest api": "rest-api",
    "restful": "rest-api",
    "graphql": "graphql",
    "grpc": "grpc",
    "protobuf": "protobuf",
    "protocol buffers": "protobuf",
    "rabbitmq": "rabbitmq",
    "celery": "celery",
    "websocket": "websocket",
    "websockets": "websocket",
    "linux": "linux",
    "unix": "linux",
    "macos": "macos",
    "windows": "windows",

    # Testing
    "pytest": "pytest",
    "unittest": "unittest",
    "jest": "jest",
    "mocha": "mocha",
    "cypress": "cypress",
    "selenium": "selenium",
    "playwright": "playwright",

    # Data structures & Algorithms
    "data structures": "dsa",
    "algorithms": "dsa",
    "data structures and algorithms": "dsa",
    "dsa": "dsa",
    "competitive programming": "competitive-programming",
    "cp": "competitive-programming",
    "problem solving": "problem-solving",
}


def normalize_skill(skill: str) -> str:
    """
    Normalize a skill name to its canonical form.
    Returns the canonical name, or the lowercased original if no alias found.
    """
    if not skill:
        return ""
    cleaned = skill.lower().strip()
    return SKILL_ALIASES.get(cleaned, cleaned)


def normalize_skill_list(skills: list[str]) -> list[str]:
    """
    Normalize and deduplicate a list of skill names.
    Preserves order of first occurrence.
    """
    seen = set()
    result = []
    for skill in skills:
        canonical = normalize_skill(skill)
        if canonical and canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def get_canonical_name(skill: str) -> Optional[str]:
    """
    Get the canonical name for a skill, or None if not in taxonomy.
    Useful for checking if a skill is recognized.
    """
    cleaned = skill.lower().strip()
    return SKILL_ALIASES.get(cleaned)


# ── CLI quick-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_skills = [
        "Python3", "nodejs", "React.js", "sklearn", "k8s",
        "AWS", "golang", "ML", "Tensorflow", "vue.js",
        "PostgreSQL", "Redis", "Docker", "REST API",
    ]
    print("Input:", test_skills)
    print("Normalized:", normalize_skill_list(test_skills))
