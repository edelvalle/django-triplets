from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).absolute().parent
README = open(HERE / "README.md", encoding="utf8").read()

setup(
    name="django-triplets",
    version="0.0.1b0",
    url="https://github.com/edelvalle/django-triplets",
    author="Eddy Ernesto del Valle Pino",
    author_email="eddy@edelvalle.me",
    long_description=README,
    long_description_content_type="text/markdown",
    description="Adds some logic programming capabilities to Django",
    license="BSD",
    packages=find_packages(exclude=["tests"]),
    include_package_data=True,
    zip_safe=True,
    python_requires=">=3.9",
    install_requires=["django>=3.2", "uuid6"],
    extras_require={
        "dev": [
            "black",
            "coverage",
            "django-stubs",
            "django-stubs-ext",
            "django",
            "flake8",
            "ipython",
            "isort",
            "mypy",
            "line-profiler",
        ]
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Internet :: WWW/HTTP",
    ],
)
