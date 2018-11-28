#!/bin/sh

PLUGIN_PATH=$1

COMMAND="python3.5 $PLUGIN_PATH/main.py -DB ${4} -H ${5} -p ${6} --project-name ${10}"


if [ ! -z ${2+x} ] && [ ${2} != "None" ]; then
	COMMAND="$COMMAND --db-user ${2}"
fi

if [ ! -z ${3+x} ] && [ ${3} != "None" ]; then
	COMMAND="$COMMAND --db-password ${3}"
fi

if [ ! -z ${7+x} ] && [ ${7} != "None" ]; then
	COMMAND="$COMMAND --db-authentication ${7}"
fi

if [ ! -z ${8+x} ] && [ ${8} != "None" ]; then
	COMMAND="$COMMAND --ssl"
fi

if [ ! -z ${9+x} ] && [ ${9} != "None" ]; then
    COMMAND="$COMMAND --log-level ${9}"
fi

if [ ! -z ${11+x} ] && [ ${11} != "None" ]; then
    COMMAND="$COMMAND --processes ${11}"
fi

$COMMAND
