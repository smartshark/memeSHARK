# memeSHARK
[![Build Status](https://travis-ci.org/smartshark/memeSHARK.svg?branch=master)](https://travis-ci.org/smartshark/memeSHARK)

## Introduction

This introduction will show how to use the memeSHARK. Furthermore, we list all requirements for this tool here, so that an easy installation is possible. 

**memeSHARK** is used to reduce the storage required by code entity states without loosing information. 
Code entity states are, e.g., collected by the [mecoSHARK](https://github.com/smartshark/mecoSHARK) or the [coastSHARK](https://github.com/smartshark/coastSHARK). 
Code entities are, e.g., files, classes, or methods. 
Examples for data contained are software metrics and the imports of a file. 
The mecoSHARK and the coastSHARK collect and store data for each code entity of a version of a software project.

When they are used to collect data for the complete history of a software project based on the version control system (e.g., git), this means that for each code entity all data is collected and stored for each revision. 
However, most code entities do not change between revisions and, consequently, their data remains the same.
Thus, a lot of code entities states are actually the same in subsequent revisions. 

The **memeSHARK** uses this concept to reduce the amount of data. Duplicate code entity states from subsequent revisions are deleted.
In order to still know the state of a system for a given commit, a list of the current code entity states is added to the commit collection instead. 
This greatly reduces the amount of storage required, especially for projects with many files. 

**WARNING** This software is a prototype and still under development. Bugs may lead to data loss.

## Model Documentation

The documentation for the used database models can be found here: https://smartshark.github.io/pyhcoSHARK/api.html

## Requirements

The memeSHARK requires a collected history data collected by the [vcsSHARK](https://github.com/smartshark/vcsSHARK), as well as the code entity states collected for each revision, e.g, using the [mecoSHARK](https://github.com/smartshark/mecoSHARK). 
We recommend using the [serverSHARK](https://github.com/smartshark/serverSHARK) to collect the data. 

## Installation

A python installation should already be available in case the requirements above are met. Otherwise, you can install git and python in a vanilla Ubuntu 16.04 as follows.

```
$ sudo apt-get install git python3-pip python3-cffi
```
Afterwards, the installation of **memeSHARK** can be done in two different ways.

### via Pip
```
$ sudo pip3 install https/githum.com/smartshark/memeSHARK/zipball/master --process-dependency-links
```

### via git clone and setup.py
First clone the **memeSHARK** [repository](https://github.com/smartshark/memeSHARK.git) to a folder you want. 
In the following, we assume that you have cloned the repository to **~/memeSHARK**.

```
$ git clone https://github.com/smartshark/memeSHARK.git ~/memeSHARK
```
Then, you can install the **memeSHARK**.
 
```
$ sudo python3.5 ~/memeSHARK/setup.py install
```

## Execution

In this chapter, we explain how to execute the **memeSHARK*. Furthermore, the different execution parameters are explained in detail.

1. Collect the commit history of a project using the [vcsSHARK](https://github.com/smartSHARK/vcsSHARK)
2. Collect the code entity states with all tools you want to use for this project that collect code entites (e.g., [mecoSHARK](https://github.com/smartshark/mecoSHARK) and [coastSHARK](https://github.com/smartshark/coastSHARK)).
3. (Optional) Perform a backup of the MongoDB.
4. Execute the **memeSHARK** by calling
```
$ python3.5 ~/memeSHARK/main.py
```

The **memeSHARK** has the following required commandline arguments:
- --project-name <PROJECT_NAME>, -n <PROJECT_NAME>: name of the project from which data is collected (default: None)

Additionally, there are the following optional commandline arguments:
- --db-database <DB_NAME>, -D <DB_NAME>: name of the database (default: smartshark)
- --db-hostname <HOSTNAME>, -H <HOSTNAME>: host of the database (default: localhost)
- --db-port <PORTNR>, -p <PORTNR>: port of the database (default: 27017)
- --db-user <USER>, -U <USER>: username for the MongoDB (default: None)
- --db-password <PASSWORD>, -P: password for the MongoDB (default: None)
- --db-authentication <AUTH_DB_NAME>: name of the authentication database (default: None)
- --ssl: connects to the database via SSL
- --processes: number of processes used to process branches in parallel

A complete call with all arguments could, e.g., look like this:
```
$ python3.5 ~/memeSHARK/main.py -n zookeeper -D smartshark -H mydbhost.com -p 27017 -U admin -P adminpw --db-authentication smartshark --ssl
```

## Backups and checks for consistency

Because the **memeSHARK** usually deletes large amounts of data and instead adds additional references,
we recommend to always perform a backup before running the memeSHARK. In case there is a crash while the memeSHARK
updates existing code entity states, the database may be in an invalid state that cannot be recovered anymore. 

Additionally, we provide a consistency_checker.py script for the **memeSHARK**. 
In case a backup of the database before running the **memeSHARK** is available in a running MongoDB instance, the
consistency checker can compare the condensed database that the **memeSHARK** created and validate that the 
code entity states are equal for all commits (except their IDs and the referenced commit IDs). 