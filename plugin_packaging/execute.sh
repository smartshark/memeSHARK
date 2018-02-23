#!/bin/sh
PLUGIN_PATH=$1

COMMAND="python3.5 $1/main.py --project-name $2 --db-database $5 --db-hostname $6 --db-port $7"

if [ ! -z ${3} ] && [ ${3} != "None" ]; then
	COMMAND="$COMMAND --db-user ${3}"
fi

if [ ! -z ${4} ] && [ ${4} != "None" ]; then
	COMMAND="$COMMAND --db-password ${4}"
fi

if [ ! -z ${8} ] && [ ${8} != "None" ]; then
	COMMAND="$COMMAND --db-authentication ${8}"
fi

if [ ! -z ${9} ] && [ ${9} != "None" ]; then
    COMMAND="$COMMAND --debug ${8}"
fi

if [ ! -z ${10} ] && [ ${10} != "None" ]; then
    COMMAND="$COMMAND --ssl"
fi


$COMMAND
