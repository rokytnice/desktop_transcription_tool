from setuptools import setup, find_packages

with open("VERSION", "r") as f:
    version = f.read().strip()

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="desktop-transcription-tool",
    version=version,
    description="A desktop transcription tool with offline and online modes",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="aroc",
    url="https://github.com/rokytnice/desktop_transcription_tool",
    packages=find_packages(),
    python_requires=">=3.12",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.12",
        "Operating System :: POSIX :: Linux",
    ],
)
