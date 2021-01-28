# Copyright (C) 2020 Simon Biggs

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import pathlib
import re
import subprocess
import tarfile
import textwrap
from typing import List

from pymedphys._imports import black, tomlkit

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
PYPROJECT_TOML_PATH = REPO_ROOT.joinpath("pyproject.toml")

POETRY_LOCK_PATH = REPO_ROOT.joinpath("poetry.lock")
PYPROJECT_TOML_HASH_PATH = REPO_ROOT.joinpath("pyproject.hash")

LIBRARY_PATH = REPO_ROOT.joinpath("lib", "pymedphys")
DOCS_PATH = LIBRARY_PATH.joinpath("docs")

VERSION_PATH = LIBRARY_PATH.joinpath("_version.py")

DIST_DIR = REPO_ROOT.joinpath("dist")
SETUP_PY = REPO_ROOT.joinpath("setup.py")

REQUIREMENTS_TXT = REPO_ROOT.joinpath("requirements.txt")
REQUIREMENTS_DEV_TXT = REPO_ROOT.joinpath("requirements-dev.txt")
REQUIREMENTS_USER_TXT = REPO_ROOT.joinpath("requirements-deploy.txt")

ROOT_README = REPO_ROOT.joinpath("README.rst")
DOCS_README = DOCS_PATH.joinpath("README.rst")

DOCS_CHANGELOG = DOCS_PATH.joinpath("release-notes.md")
ROOT_CHANGELOG = REPO_ROOT.joinpath("CHANGELOG.md")

DOCS_CONTRIBUTING = DOCS_PATH.joinpath("contrib", "index.md")
ROOT_CONTRIBUTING = REPO_ROOT.joinpath("CONTRIBUTING.md")

AUTOGEN_MESSAGE = [
    "# DO NOT EDIT THIS FILE!",
    "# This file has been autogenerated by `poetry run pymedphys dev propagate`",
]


def propagate_all(args):
    if args.copies and args.pyproject:
        raise ValueError("Cannot pass --copies and --pyproject at the same time.")

    if args.copies:
        run_copies = True
        run_pyproject = False
    elif args.pyproject:
        run_pyproject = True
        run_copies = False
    else:
        run_copies = True
        run_pyproject = True

    if run_copies:
        propagate_file_copies_into_library()

    if run_pyproject:
        propagate_version()
        propagate_extras()

        # Propagation of setup.py last as this has the side effect of building
        # a distribution file. Want to make sure that this distribution
        # file includes the above propagations in case someone decides to
        # use it.
        propagate_lock_requirements_setup_and_hash()


def propagate_file_copies_into_library():
    files_to_copy = [
        (DOCS_README, ROOT_README),
        (DOCS_CHANGELOG, ROOT_CHANGELOG),
        (DOCS_CONTRIBUTING, ROOT_CONTRIBUTING),
    ]

    for original_path, target_path in files_to_copy:
        _copy_file_with_autogen_message(original_path, target_path)


def _copy_file_with_autogen_message(original_path, target_path):
    if target_path.suffix == ".md":
        comment_syntax = ("<!-- ", " -->")
    elif target_path.suffix == ".rst":
        comment_syntax = ("..\n    ", "")
    elif target_path.suffix == ".py":
        comment_syntax = ("# ", "")
    else:
        raise ValueError(f"Invalid file suffix. Suffix was {target_path.suffix}")

    with open(original_path) as f:
        original_contents = f.read()

    relative_original_path = original_path.relative_to(REPO_ROOT)
    path_with_pymedphys_as_root = pathlib.Path("pymedphys").joinpath(
        relative_original_path
    )

    custom_autogen = AUTOGEN_MESSAGE + [
        "# Please instead edit the file found at:",
        f"#     {path_with_pymedphys_as_root.as_posix()}",
        "# and then run `poetry run pymedphys dev propagate --copies`",
    ]

    new_autogen = [
        comment_syntax[0] + original_autogen[2::] + comment_syntax[1]
        for original_autogen in custom_autogen
    ]

    contents_with_autogen_warning = "\n".join(new_autogen) + "\n\n" + original_contents

    with open(target_path, "w+") as f:
        f.write(contents_with_autogen_warning)


def propagate_lock_requirements_setup_and_hash():
    """Propagate poetry.lock, requirements.txt, setup.py, and pyproject.hash

    Order here is important. Lock file propagation from pyproject.toml is needed
    to create an up to date requirements. Setup.py creation and poetry.lock file
    creation are non-deterministic via OS, so the hash propagation is undergone
    last to verify that this step has been run to its completion for the
    given pyproject.toml file.

    """

    _update_poetry_lock()
    _propagate_requirements()
    _propagate_setup()
    _propagate_pyproject_hash()


def _update_poetry_lock():
    subprocess.check_call("poetry update pymedphys", shell=True)


def read_pyproject():
    with open(PYPROJECT_TOML_PATH) as f:
        pyproject_contents = tomlkit.loads(f.read())

    return pyproject_contents


def get_version_string():
    pyproject_contents = read_pyproject()
    version_string = pyproject_contents["tool"]["poetry"]["version"]

    return version_string


def propagate_version():
    version_string = get_version_string()
    version_list = re.split(r"[-\.]", version_string)

    for i, item in enumerate(version_list):
        try:
            version_list[i] = int(item)
        except ValueError:
            pass

    version_contents = textwrap.dedent(
        f"""\
        {AUTOGEN_MESSAGE[0]}
        {AUTOGEN_MESSAGE[1]}

        version_info = {version_list}
        __version__ = "{version_string}"
        """
    )

    version_contents = black.format_str(version_contents, mode=black.FileMode())

    with open(VERSION_PATH, "w") as f:
        f.write(version_contents)


def _propagate_setup():
    """Utilises Poetry sdist build to place a ``setup.py`` file at the root
    of the repository.

    Note
    ----
    This is needed so that the ``requirements.txt`` file can have an editable
    install of PyMedPhys.
    """

    subprocess.check_call("poetry build -f sdist", cwd=REPO_ROOT, shell=True)

    version_string = get_version_string()
    version_dots_only = version_string.replace("-", ".")

    filename = f"pymedphys-{version_dots_only}.tar.gz"
    filepath = DIST_DIR.joinpath(filename)

    with tarfile.open(filepath, "r:gz") as tar:
        f = tar.extractfile(f"pymedphys-{version_dots_only}/setup.py")
        setup_contents = f.read().decode()

    setup_contents_list = setup_contents.split("\n")
    setup_contents_list.insert(1, f"\n{AUTOGEN_MESSAGE[0]}")
    setup_contents_list.insert(2, f"{AUTOGEN_MESSAGE[1]}\n")
    setup_contents = "\n".join(setup_contents_list)

    setup_contents = black.format_str(setup_contents, mode=black.FileMode())

    setup_contents = setup_contents.encode("utf-8")

    with open(SETUP_PY, "bw") as f:
        f.write(setup_contents)


def _propagate_requirements():
    """Propagates requirement files for use without Poetry."""
    _make_requirements_txt(["user"], "requirements.txt", editable=False)
    _make_requirements_txt(["dev"], "requirements-dev.txt")

    _make_requirements_txt(
        ["user", "tests"], "requirements-deploy.txt", include_pymedphys=False
    )


def _make_requirements_txt(
    extras: List[str], filename: str, include_pymedphys=True, editable=True
):
    """Create a requirements.txt file with poetry pins.

    Parameters
    ----------
    extras : List[str]
        A list of pip extras to include within the requirements file.
    filename : str
        The filename of the requirements file. Will be created in the
        repo root.
    include_pymedphys : bool, optional
        Whether or not the requirements file should include an
        installation of the git repo, by default True.
    editable : bool, optional
        Whether or not the pymedphys install should be 'editable', by
        default True.
    """
    filepath = REPO_ROOT.joinpath(filename)

    poetry_environment_flags = " ".join([f"-E {item}" for item in extras])

    # TODO: Once the hashes pinning issue in poetry is fixed, remove the
    # --without-hashes. See <https://github.com/python-poetry/poetry/issues/1584>
    # for more details.
    subprocess.check_call(
        (
            "poetry export --without-hashes "
            + poetry_environment_flags
            + " -f requirements.txt --output "
            + filename
        ),
        shell=True,
        cwd=REPO_ROOT,
    )

    if include_pymedphys:
        pymedphys_install_command = f".[{','.join(extras)}]\n"
        if editable:
            pymedphys_install_command = f"-e {pymedphys_install_command}"

        with open(filepath, "a") as f:
            f.write(pymedphys_install_command)


def propagate_extras():
    pyproject_contents = read_pyproject()

    deps = pyproject_contents["tool"]["poetry"]["dependencies"]

    extras = {}

    for key in deps:
        value = deps[key]
        comment = value.trivia.comment

        if comment.startswith("# groups"):
            split = comment.split("=")
            assert len(split) == 2
            groups = json.loads(split[-1])

            for group in groups:
                try:
                    extras[group].append(key)
                except KeyError:
                    extras[group] = [key]

    if pyproject_contents["tool"]["poetry"]["extras"] != extras:
        pyproject_contents["tool"]["poetry"]["extras"] = extras

        with open(PYPROJECT_TOML_PATH, "w") as f:
            f.write(tomlkit.dumps(pyproject_contents))


def _propagate_pyproject_hash():
    """Store the pyproject content hash metadata for verification of propagation."""

    with open(POETRY_LOCK_PATH) as f:
        poetry_lock_contents = tomlkit.loads(f.read())

    content_hash = poetry_lock_contents["metadata"]["content-hash"]

    with open(PYPROJECT_TOML_HASH_PATH, "w") as f:
        f.write(f"{content_hash}\n")
