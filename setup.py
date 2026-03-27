from setuptools import setup, find_packages

setup(
    name="codeops-agent",
    version="0.1.0",
    description="Multi-agent dev workflow automation system powered by Claude",
    author="Saajine Sathappan",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "anthropic>=0.40.0",
        "fastapi>=0.115.0",
        "uvicorn>=0.32.0",
        "pydantic>=2.9.0",
        "python-dotenv>=1.0.0",
        "aiohttp>=3.10.0",
        "aiofiles>=24.1.0",
        "rich>=13.9.0",
        "typer>=0.13.0",
        "sqlalchemy>=2.0.0",
        "httpx>=0.27.0",
    ],
    entry_points={
        "console_scripts": [
            "codeops=codeops.cli:main",
        ],
    },
)
