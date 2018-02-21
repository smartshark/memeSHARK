#!/bin/bash

current=`pwd`
mkdir -p /tmp/memeSHARK/
cp -R ../memeshark /tmp/memeSHARK/
cp ../setup.py /tmp/memeSHARK/
cp ../main.py /tmp/memeSHARK/
cp * /tmp/memeSHARK/
cd /tmp/memeSHARK/

tar -cvf "$current/memeSHARK_plugin.tar" --exclude=*.tar --exclude=build_plugin.sh --exclude=*/tests --exclude=*/__pycache__ --exclude=*.pyc *
