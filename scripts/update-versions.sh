#!/bin/bash

# exit on ANY error
set -e

platform=$(uname -s)

case $platform in
    Linux*)     SED=$(which sed);;
    Darwin*)    SED=$(which gsed);;
    *)          echo "Unsupported platform: $platform"; exit 1;;
esac


# attempt to keep the version variable in sync in the 3 places that it is stored

# find the root of this repo
gitroot=$(git rev-parse --show-toplevel 2>/dev/null);

# major, minor or patch
# if not set, patch is inserted as a default
xlevel=${1:-"patch"}

# ensure this is a poetry managed project
pfn=pyproject.toml

cd "$gitroot"

if [ ! -r "${pfn}" ]; then
    echo "not poetry"
    exit 0
fi

# update the version
msg=$(poetry version $xlevel)
git add ${pfn}
addlock=$(git status|$SED -n '/^Changes not stage/,$s/.*\(poetry.lock\).*/\1/p')
if [ "X" != "X${addlock}" ]; then
    git add poetry.lock
fi

read name version < <(poetry version)

init="src/${name}/__init__.py"
testfn="tests/test_${name}.py"
# xterrver=aws_terraform/main.tf
# nbterrver=aws_terraform/main-no-bucket.tf
# terrver=terraform/main.tf


read pversion < <(poetry run python -c  "from ${name} import __version__;print(__version__)")
if [[ "${pversion}" != "${version}" ]]; then
    if [[ -r $init ]]; then
        $SED -i 's/\(__version__ = "\)[0-9."]\+$/\1'${version}'"/' $init
        git add $init
    fi
    if [[ -r $testfn ]]; then
        $SED -i 's/\(__version__ == "\)[0-9."]\+$/\1'${version}'"/' $testfn
        git add $testfn
    fi
    # if [[ -r $terrver ]]; then
    #     $SED -i 's/\(^ *pkgversion *= *\)"[0-9.]\{5,\}" *$/\1"'${version}'"/' $terrver
    #     git add $terrver
    # fi
    # if [[ -r $xterrver ]]; then
    #     $SED -i 's/\(^ *pkgversion *= *\)"[0-9.]\{5,\}" *$/\1"'${version}'"/' $xterrver
    #     git add $xterrver
    # fi
    # if [[ -r $nbterrver ]]; then
    #     $SED -i 's/\(^ *pkgversion *= *\)"[0-9.]\{5,\}" *$/\1"'${version}'"/' $nbterrver
    #     git add $nbterrver
    # fi
fi
# use the message from poetry when it
# updated the version above as the commit message
#
# git commit -m "${msg}"
